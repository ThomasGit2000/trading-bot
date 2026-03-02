"""
Tick Data Collector - Stores real-time price data for backtesting

Collects tick/bar data from IB and stores in SQLite for historical analysis.
Run this alongside the main bot to build your own tick database.
"""
import os
import time
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from ib_insync import IB, Stock

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / 'data' / 'ticks.db'


class TickCollector:
    """Collects and stores tick data from IB"""

    def __init__(self, symbol: str = 'NIO'):
        self.symbol = symbol
        self.ib = IB()
        self.host = os.getenv('IB_HOST', '127.0.0.1')
        self.port = int(os.getenv('IB_PORT', '7496'))
        self.client_id = int(os.getenv('IB_CLIENT_ID', '99'))  # Different client ID

        self.contract = Stock(symbol, 'SMART', 'USD')
        self.ticker = None

        self._init_db()

    def _init_db(self):
        """Initialize SQLite database"""
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # Tick data table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                price REAL NOT NULL,
                bid REAL,
                ask REAL,
                volume INTEGER,
                UNIQUE(symbol, timestamp)
            )
        ''')

        # 1-minute bars table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bars_1m (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER,
                UNIQUE(symbol, timestamp)
            )
        ''')

        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ticks_ts ON ticks(symbol, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_bars_ts ON bars_1m(symbol, timestamp)')

        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {DB_PATH}")

    def connect(self):
        """Connect to IB"""
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            self.ib.reqMarketDataType(3)  # Delayed data OK
            self.ib.qualifyContracts(self.contract)
            logger.info(f"Connected to IB for {self.symbol}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False

    def disconnect(self):
        """Disconnect from IB"""
        if self.ticker:
            self.ib.cancelMktData(self.contract)
        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Disconnected")

    def save_tick(self, timestamp, price, bid, ask, volume):
        """Save a tick to database"""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO ticks (symbol, timestamp, price, bid, ask, volume)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (self.symbol, timestamp, price, bid, ask, volume))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to save tick: {e}")
        finally:
            conn.close()

    def save_bar(self, timestamp, open_p, high, low, close, volume):
        """Save a 1-minute bar to database"""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO bars_1m (symbol, timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (self.symbol, timestamp, open_p, high, low, close, volume))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to save bar: {e}")
        finally:
            conn.close()

    def collect_realtime(self, duration_hours: float = 6.5):
        """Collect real-time ticks during market hours"""
        if not self.connect():
            return

        self.ticker = self.ib.reqMktData(self.contract, '', False, False)
        logger.info(f"Started collecting ticks for {self.symbol}")

        start_time = time.time()
        end_time = start_time + (duration_hours * 3600)

        # Track for 1-min bars
        bar_start = None
        bar_prices = []
        bar_volume = 0
        tick_count = 0

        try:
            while time.time() < end_time:
                self.ib.sleep(0.5)  # Poll every 500ms

                price = self.ticker.marketPrice()
                bid = self.ticker.bid
                ask = self.ticker.ask

                if price and price > 0:
                    now = datetime.now()
                    timestamp = now.strftime('%Y-%m-%d %H:%M:%S.%f')

                    # Save tick
                    self.save_tick(timestamp, price, bid, ask, 0)
                    tick_count += 1

                    # Build 1-min bar
                    current_minute = now.replace(second=0, microsecond=0)
                    if bar_start is None:
                        bar_start = current_minute
                        bar_prices = [price]
                    elif current_minute > bar_start:
                        # Save completed bar
                        if bar_prices:
                            self.save_bar(
                                bar_start.strftime('%Y-%m-%d %H:%M:%S'),
                                bar_prices[0],
                                max(bar_prices),
                                min(bar_prices),
                                bar_prices[-1],
                                len(bar_prices)
                            )
                        bar_start = current_minute
                        bar_prices = [price]
                    else:
                        bar_prices.append(price)

                    if tick_count % 100 == 0:
                        logger.info(f"Collected {tick_count} ticks, last: ${price:.2f}")

        except KeyboardInterrupt:
            logger.info("Stopping collection...")
        finally:
            # Save final bar
            if bar_prices and bar_start:
                self.save_bar(
                    bar_start.strftime('%Y-%m-%d %H:%M:%S'),
                    bar_prices[0],
                    max(bar_prices),
                    min(bar_prices),
                    bar_prices[-1],
                    len(bar_prices)
                )

            self.disconnect()
            logger.info(f"Collection complete. Total ticks: {tick_count}")

    def get_tick_count(self) -> int:
        """Get total tick count in database"""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM ticks WHERE symbol = ?', (self.symbol,))
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_bar_count(self) -> int:
        """Get total 1-min bar count in database"""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM bars_1m WHERE symbol = ?', (self.symbol,))
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_bars(self, limit: int = 1000) -> list:
        """Get recent 1-minute bars for backtesting"""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('''
            SELECT timestamp, open, high, low, close, volume
            FROM bars_1m WHERE symbol = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (self.symbol, limit))
        rows = cursor.fetchall()
        conn.close()
        return [{'timestamp': r[0], 'open': r[1], 'high': r[2],
                 'low': r[3], 'close': r[4], 'volume': r[5]} for r in reversed(rows)]


def show_stats():
    """Show collection statistics"""
    collector = TickCollector()
    print(f"\n{'='*50}")
    print(f"  TICK DATABASE STATS: {collector.symbol}")
    print(f"{'='*50}")
    print(f"  Database: {DB_PATH}")
    print(f"  Ticks collected: {collector.get_tick_count():,}")
    print(f"  1-min bars: {collector.get_bar_count():,}")
    print()


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'stats':
        show_stats()
    else:
        print("Starting tick collection (6.5 hours)...")
        print("Press Ctrl+C to stop early")
        collector = TickCollector('NIO')
        collector.collect_realtime(6.5)  # Full trading day
