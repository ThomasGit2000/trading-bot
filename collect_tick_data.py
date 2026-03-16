"""
Collect tick and Level 2 orderbook data from IBKR for ML training.
Run during market hours (9:30 AM - 4:00 PM ET) for 5-10 trading days.

Usage:
    python collect_tick_data.py

Output:
    data/ticks/{SYMBOL}_{DATE}.csv
"""

import csv
import os
import time
from datetime import datetime
from collections import deque
from ib_insync import IB, Stock, util


class TickDataCollector:
    """Collects tick and Level 2 data from IBKR."""

    def __init__(self, symbols, output_dir='data/ticks'):
        self.ib = IB()
        self.symbols = symbols
        self.output_dir = output_dir
        self.writers = {}
        self.files = {}
        self.contracts = {}
        self.tick_counts = {s: 0 for s in symbols}
        self.start_time = None

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

    def connect(self):
        """Connect to IBKR and subscribe to market data."""
        print("Connecting to IBKR...")
        self.ib.connect('127.0.0.1', 7496, clientId=99)
        print("Connected!")

        for symbol in self.symbols:
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            self.contracts[symbol] = contract

            # Subscribe to regular market data (Level 1 - included in basic subscription)
            # This provides: last price, bid, ask, volume
            self.ib.reqMktData(contract, '', False, False)

            # Try Level 2 market depth (requires add-on subscription)
            try:
                self.ib.reqMktDepth(contract, numRows=5)
            except Exception as e:
                print(f"  {symbol}: Level 2 not available (using Level 1 only)")

            # Initialize CSV file
            self._init_csv(symbol)
            print(f"Subscribed to {symbol}")

        # Set up event handlers
        self.ib.pendingTickersEvent += self.on_pending_tickers

        self.start_time = time.time()
        print(f"\nCollecting data for: {', '.join(self.symbols)}")
        print("Using Level 1 data (bid/ask/last)")
        print("Press Ctrl+C to stop\n")

    def _init_csv(self, symbol):
        """Initialize CSV file for a symbol."""
        date_str = datetime.now().strftime("%Y%m%d")
        filepath = os.path.join(self.output_dir, f'{symbol}_{date_str}.csv')

        # Append if file exists, otherwise create new
        file_exists = os.path.exists(filepath)
        f = open(filepath, 'a', newline='')
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow([
                'timestamp', 'price', 'volume',
                'bid', 'ask', 'bid_size', 'ask_size',
                'bid2', 'ask2', 'bid2_size', 'ask2_size',
                'bid3', 'ask3', 'bid3_size', 'ask3_size'
            ])

        self.files[symbol] = f
        self.writers[symbol] = writer

    def on_pending_tickers(self, tickers):
        """Handle incoming tick data."""
        for ticker in tickers:
            if not ticker.contract:
                continue

            symbol = ticker.contract.symbol
            if symbol not in self.writers:
                continue

            # Get price (last trade or close)
            price = ticker.last if ticker.last and not util.isNan(ticker.last) and ticker.last > 0 else None
            if not price:
                price = ticker.close if ticker.close and not util.isNan(ticker.close) and ticker.close > 0 else None
            if not price or price <= 0:
                continue

            volume = ticker.lastSize if ticker.lastSize and not util.isNan(ticker.lastSize) else 0

            # Level 1 bid/ask (always available with basic subscription)
            bid = ticker.bid if ticker.bid and not util.isNan(ticker.bid) and ticker.bid > 0 else 0
            ask = ticker.ask if ticker.ask and not util.isNan(ticker.ask) and ticker.ask > 0 else 0
            bid_size = ticker.bidSize if ticker.bidSize and not util.isNan(ticker.bidSize) else 0
            ask_size = ticker.askSize if ticker.askSize and not util.isNan(ticker.askSize) else 0

            # Level 2 data (from market depth - may not be available)
            bid2, ask2, bid2_size, ask2_size = 0, 0, 0, 0
            bid3, ask3, bid3_size, ask3_size = 0, 0, 0, 0

            if hasattr(ticker, 'domBids') and ticker.domBids and len(ticker.domBids) > 0:
                bid = ticker.domBids[0].price
                bid_size = ticker.domBids[0].size
                if len(ticker.domBids) > 1:
                    bid2 = ticker.domBids[1].price
                    bid2_size = ticker.domBids[1].size
                if len(ticker.domBids) > 2:
                    bid3 = ticker.domBids[2].price
                    bid3_size = ticker.domBids[2].size

            if hasattr(ticker, 'domAsks') and ticker.domAsks and len(ticker.domAsks) > 0:
                ask = ticker.domAsks[0].price
                ask_size = ticker.domAsks[0].size
                if len(ticker.domAsks) > 1:
                    ask2 = ticker.domAsks[1].price
                    ask2_size = ticker.domAsks[1].size
                if len(ticker.domAsks) > 2:
                    ask3 = ticker.domAsks[2].price
                    ask3_size = ticker.domAsks[2].size

            # Write row
            row = [
                datetime.now().isoformat(timespec='milliseconds'),
                price,
                volume,
                bid, ask, bid_size, ask_size,
                bid2, ask2, bid2_size, ask2_size,
                bid3, ask3, bid3_size, ask3_size
            ]

            self.writers[symbol].writerow(row)
            self.tick_counts[symbol] += 1

    def print_stats(self):
        """Print collection statistics."""
        elapsed = time.time() - self.start_time
        hours = elapsed / 3600

        print(f"\n--- Stats (running {hours:.1f}h) ---")
        for symbol, count in self.tick_counts.items():
            rate = count / elapsed if elapsed > 0 else 0
            print(f"  {symbol}: {count:,} ticks ({rate:.1f}/sec)")
        print()

    def run(self):
        """Run the data collection loop."""
        last_stats = time.time()

        while True:
            self.ib.sleep(0.01)  # 10ms sleep, process events

            # Print stats every 60 seconds
            if time.time() - last_stats > 60:
                self.print_stats()
                # Flush files
                for f in self.files.values():
                    f.flush()
                last_stats = time.time()

    def stop(self):
        """Stop collection and cleanup."""
        print("\nStopping data collection...")
        self.print_stats()

        # Close all files
        for symbol, f in self.files.items():
            f.close()
            print(f"Saved {symbol} data")

        # Disconnect
        self.ib.disconnect()
        print("Disconnected from IBKR")


def main():
    # Top liquid stocks for ML training
    symbols = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META']

    print("=" * 50)
    print("TICK DATA COLLECTOR FOR ML TRAINING")
    print("=" * 50)
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Output: data/ticks/")
    print("=" * 50)

    collector = TickDataCollector(symbols)

    try:
        collector.connect()
        collector.run()
    except KeyboardInterrupt:
        pass
    finally:
        collector.stop()


if __name__ == '__main__':
    main()
