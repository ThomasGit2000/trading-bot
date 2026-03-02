"""SQLite database for storing price and trade data"""
import sqlite3
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / 'data' / 'trading.db'


def get_connection():
    """Get database connection"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables"""
    conn = get_connection()
    cursor = conn.cursor()

    # Price data table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL NOT NULL,
            volume INTEGER,
            source TEXT,
            UNIQUE(symbol, timestamp)
        )
    ''')

    # Trades table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            action TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            status TEXT,
            pnl REAL,
            notes TEXT
        )
    ''')

    # Backtest results table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS backtests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            start_date DATE,
            end_date DATE,
            strategy TEXT,
            initial_capital REAL,
            final_capital REAL,
            total_return REAL,
            num_trades INTEGER,
            win_rate REAL,
            max_drawdown REAL,
            sharpe_ratio REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_prices_symbol_ts ON prices(symbol, timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)')

    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {DB_PATH}")


def save_prices(symbol: str, prices: list, source: str = 'yfinance'):
    """Save price data to database

    Args:
        symbol: Stock symbol
        prices: List of dicts with date, open, high, low, close, volume
        source: Data source name
    """
    conn = get_connection()
    cursor = conn.cursor()

    count = 0
    for p in prices:
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO prices (symbol, timestamp, open, high, low, close, volume, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                symbol,
                p.get('date') or p.get('timestamp') or p.get('datetime'),
                p.get('open'),
                p.get('high'),
                p.get('low'),
                p['close'],
                p.get('volume'),
                source
            ))
            count += 1
        except Exception as e:
            logger.warning(f"Failed to insert price: {e}")

    conn.commit()
    conn.close()
    logger.info(f"Saved {count} prices for {symbol}")
    return count


def get_prices(symbol: str, start_date: str = None, end_date: str = None) -> list:
    """Get prices from database

    Args:
        symbol: Stock symbol
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        List of price dicts
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = 'SELECT * FROM prices WHERE symbol = ?'
    params = [symbol]

    if start_date:
        query += ' AND timestamp >= ?'
        params.append(start_date)
    if end_date:
        query += ' AND timestamp <= ?'
        params.append(end_date)

    query += ' ORDER BY timestamp ASC'

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_price_count(symbol: str) -> int:
    """Get count of prices for a symbol"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM prices WHERE symbol = ?', (symbol,))
    count = cursor.fetchone()[0]
    conn.close()
    return count


def save_backtest(result: dict):
    """Save backtest result"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO backtests (symbol, start_date, end_date, strategy, initial_capital,
                               final_capital, total_return, num_trades, win_rate, max_drawdown, sharpe_ratio)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        result['symbol'],
        result['start_date'],
        result['end_date'],
        result['strategy'],
        result['initial_capital'],
        result['final_capital'],
        result['total_return'],
        result['num_trades'],
        result['win_rate'],
        result['max_drawdown'],
        result.get('sharpe_ratio')
    ))

    conn.commit()
    conn.close()


# Initialize on import
init_db()
