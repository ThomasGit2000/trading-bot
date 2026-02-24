"""
Multi-Stock Trading Bot with NO STOPS Strategy
Trades multiple symbols simultaneously using MA crossover signals.
Supports categorized stock universe for organized trading.
"""
import os
import sys
import json
import time
import logging
import threading
import subprocess
from datetime import datetime
from dotenv import load_dotenv
from ib_insync import IB, Stock, LimitOrder
from src.strategy import SimpleStrategy
from src.dashboard_state import bot_state
from src.yfinance_client import YFinanceClient

# Import stock universe for category support
try:
    from stock_universe import (
        STOCK_CATEGORIES,
        get_all_symbols,
        get_symbols_by_category,
        get_symbol_category,
        get_position_size,
        generate_position_sizes_json
    )
    UNIVERSE_AVAILABLE = True
except ImportError:
    UNIVERSE_AVAILABLE = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/multi_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()


class StockTrader:
    """Manages trading for a single stock"""

    def __init__(self, symbol: str, position_size: int, short_ma: int, long_ma: int, category: str = "UNCATEGORIZED"):
        self.symbol = symbol
        self.position_size = position_size
        self.category = category
        self.strategy = SimpleStrategy(
            short_window=short_ma,
            long_window=long_ma,
            threshold=0.01,
            stop_loss_pct=None,  # NO STOPS
            trailing_stop_pct=None,  # NO STOPS
            min_hold_periods=0
        )
        self.contract = Stock(symbol, 'SMART', 'USD')
        self.position = 0
        self.last_price = 0
        self.last_bid = 0
        self.last_ask = 0
        self.previous_close = 0
        self.ticker = None
        self.data_source = 'UNKNOWN'
        # Events and news
        self.upcoming_events = {}
        self.news = []
        self.last_info_update = 0

    def get_state(self) -> dict:
        """Get current state for dashboard"""
        short_ma = 0
        long_ma = 0
        signal = "WAIT"
        signal_strength = 0

        if len(self.strategy.prices) >= self.strategy.short_window:
            short_ma = sum(list(self.strategy.prices)[-self.strategy.short_window:]) / self.strategy.short_window
        if len(self.strategy.prices) >= self.strategy.long_window:
            long_ma = sum(list(self.strategy.prices)[-self.strategy.long_window:]) / self.strategy.long_window
            signal = self.strategy.get_signal()

            # Calculate signal strength (-100 to +100)
            signal_strength, _ = self._calculate_probability(short_ma, long_ma)

        return {
            'symbol': self.symbol,
            'category': self.category,
            'price': self.last_price,
            'bid': self.last_bid,
            'ask': self.last_ask,
            'previous_close': self.previous_close,
            'position': self.position,
            'position_size': self.position_size,
            'short_ma': short_ma,
            'long_ma': long_ma,
            'signal': signal,
            'prices_collected': len(self.strategy.prices),
            'data_source': self.data_source,
            'in_position': self.strategy.in_position,
            'signal_strength': signal_strength,
            'upcoming_events': self.upcoming_events,
            'news': self.news
        }

    def _calculate_probability(self, short_ma: float, long_ma: float) -> tuple:
        """
        Calculate signal strength based on MA crossover thresholds.
        Shows how close we are to actual BUY or SELL signals.

        Scale: -100 (SELL signal) to +100 (BUY signal)
        - BUY triggers at: short_ma > long_ma * 1.01 (1% above)
        - SELL triggers at: short_ma < long_ma * 0.99 (1% below)
        """
        if long_ma == 0:
            return (0, 0)

        threshold = 0.01  # 1% threshold matching strategy

        # Calculate the thresholds
        buy_threshold = long_ma * (1 + threshold)
        sell_threshold = long_ma * (1 - threshold)

        # Range between thresholds
        threshold_range = buy_threshold - sell_threshold

        if threshold_range == 0:
            return (0, 0)

        # Where is short_ma relative to the thresholds?
        if short_ma >= buy_threshold:
            # Above buy threshold = BUY signal active
            signal = 100
        elif short_ma <= sell_threshold:
            # Below sell threshold = SELL signal active
            signal = -100
        else:
            # Between thresholds: scale linearly
            # sell_threshold = -100, long_ma = 0, buy_threshold = +100
            position = (short_ma - sell_threshold) / threshold_range
            signal = (position * 200) - 100  # Scale 0-1 to -100 to +100

        return (round(signal, 1), 0)


class MultiStockBot:
    """Trading bot for multiple stocks"""

    def __init__(self):
        self.ib = IB()
        self.host = os.getenv('IB_HOST', '127.0.0.1')
        self.port = int(os.getenv('IB_PORT', '7496'))
        self.client_id = int(os.getenv('IB_CLIENT_ID', '1'))

        # Parse symbols - support both direct symbols and categories
        symbols_str = os.getenv('SYMBOLS', 'TSLA,NIO')
        categories_str = os.getenv('CATEGORIES', '')

        self.symbols = []
        self.symbol_categories = {}  # Track which category each symbol belongs to

        # Load from categories if specified and universe is available
        if categories_str and UNIVERSE_AVAILABLE:
            categories = [c.strip() for c in categories_str.split(',') if c.strip()]
            if 'ALL' in categories:
                self.symbols = get_all_symbols()
            else:
                for cat in categories:
                    cat_symbols = get_symbols_by_category(cat)
                    for sym in cat_symbols:
                        if sym not in self.symbols:
                            self.symbols.append(sym)
                            self.symbol_categories[sym] = cat
            logger.info(f"Loaded {len(self.symbols)} symbols from categories: {categories}")
        else:
            # Fall back to direct symbol list
            self.symbols = [s.strip() for s in symbols_str.split(',') if s.strip()]

        # Parse position sizes - auto-generate from categories if not specified
        pos_sizes_str = os.getenv('POSITION_SIZES', '')
        if pos_sizes_str:
            try:
                self.position_sizes = json.loads(pos_sizes_str)
            except:
                self.position_sizes = {}
        elif UNIVERSE_AVAILABLE:
            # Auto-generate position sizes based on categories
            self.position_sizes = generate_position_sizes_json(self.symbols)
            logger.info("Auto-generated position sizes from stock universe")
        else:
            self.position_sizes = {}

        # Strategy settings
        self.short_ma = int(os.getenv('SHORT_MA', '10'))
        self.long_ma = int(os.getenv('LONG_MA', '30'))

        # Bot settings
        self.dry_run = os.getenv('DRY_RUN', 'true').lower() == 'true'
        self.price_interval = float(os.getenv('PRICE_INTERVAL_SEC', '5'))
        self.trade_interval = int(os.getenv('TRADE_INTERVAL_SEC', '60'))

        # Dashboard
        self.enable_dashboard = os.getenv('ENABLE_DASHBOARD', 'true').lower() == 'true'
        self.dashboard_port = int(os.getenv('DASHBOARD_PORT', '8080'))

        # Data sources
        self.yfinance = YFinanceClient()

        # Create traders for each symbol
        self.traders = {}
        for symbol in self.symbols:
            pos_size = self.position_sizes.get(symbol, 10)
            # Get category from tracking dict or lookup from universe
            if symbol in self.symbol_categories:
                category = self.symbol_categories[symbol]
            elif UNIVERSE_AVAILABLE:
                category = get_symbol_category(symbol)
            else:
                category = "UNCATEGORIZED"

            self.traders[symbol] = StockTrader(
                symbol=symbol,
                position_size=pos_size,
                short_ma=self.short_ma,
                long_ma=self.long_ma,
                category=category
            )
            logger.info(f"Created trader for {symbol} [{category}] (size: {pos_size})")

        self.last_price_time = 0
        self.last_trade_time = 0
        self.last_info_time = 0

        mode = "DRY RUN" if self.dry_run else "LIVE TRADING"
        logger.info(f"Multi-Stock Bot initialized - Symbols: {self.symbols}, Mode: {mode}")
        logger.info(f"Strategy: NO STOPS MA({self.short_ma}/{self.long_ma})")

    def connect(self):
        """Connect to Interactive Brokers"""
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            logger.info(f"Connected to IB Gateway at {self.host}:{self.port}")

            # Qualify contracts
            for symbol, trader in self.traders.items():
                self.ib.qualifyContracts(trader.contract)
                logger.info(f"Contract qualified: {trader.contract}")

            return True
        except Exception as e:
            logger.error(f"Failed to connect to IB: {e}")
            return False

    def disconnect(self):
        """Disconnect from IB"""
        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Disconnected from IB")

    def get_price(self, trader: StockTrader) -> float:
        """Get current price for a stock using Yahoo Finance"""
        try:
            quote = self.yfinance.get_quote(trader.symbol)
            if quote and quote['price'] > 0:
                trader.last_price = quote['price']
                trader.last_bid = quote['price']
                trader.last_ask = quote['price']
                trader.previous_close = quote.get('previous_close', 0)
                trader.data_source = 'YFINANCE'
                return quote['price']
        except Exception as e:
            logger.warning(f"Failed to get price for {trader.symbol}: {e}")
        return None

    def get_position(self, trader: StockTrader) -> float:
        """Get current position for a stock"""
        positions = self.ib.positions()
        for pos in positions:
            if pos.contract.symbol == trader.symbol:
                return pos.position
        return 0

    def place_order(self, trader: StockTrader, action: str, quantity: int):
        """Place an order"""
        price = trader.last_price

        if self.dry_run:
            logger.info(f"[DRY RUN] {action} {quantity} {trader.symbol} @ ${price:.2f}")
            return True

        try:
            if action == 'BUY':
                limit_price = round(price * 1.001, 2)  # Slightly above market
            else:
                limit_price = round(price * 0.999, 2)  # Slightly below market

            order = LimitOrder(action, quantity, limit_price)
            trade = self.ib.placeOrder(trader.contract, order)
            logger.info(f"Order placed: {action} {quantity} {trader.symbol} @ ${limit_price:.2f}")
            return True
        except Exception as e:
            logger.error(f"Order failed for {trader.symbol}: {e}")
            return False

    def collect_prices(self):
        """Collect prices for all stocks in background thread"""
        def _collect():
            collected = 0
            for symbol, trader in self.traders.items():
                price = self.get_price(trader)
                if price:
                    trader.strategy.add_price(price)
                    collected += 1
            if collected > 0:
                logger.info(f"Collected prices for {collected}/{len(self.traders)} stocks")

        thread = threading.Thread(target=_collect, daemon=True)
        thread.start()

    def update_stock_info(self):
        """Update events and news for all stocks in background thread"""
        def _update_info():
            current_time = time.time()
            updated = 0
            for symbol, trader in self.traders.items():
                # Update every 5 minutes
                if current_time - trader.last_info_update >= 300:
                    try:
                        trader.upcoming_events = self.yfinance.get_upcoming_events(symbol)
                        trader.news = self.yfinance.get_news(symbol, limit=3)
                        trader.last_info_update = current_time
                        updated += 1
                    except Exception as e:
                        pass  # Silently skip failed updates
            if updated > 0:
                logger.info(f"Updated news/events for {updated} stocks")

        # Run in background thread to avoid blocking main loop
        thread = threading.Thread(target=_update_info, daemon=True)
        thread.start()

    def check_signals(self):
        """Check trading signals for all stocks"""
        for symbol, trader in self.traders.items():
            if not self.ib.isConnected():
                logger.warning("Not connected to IB")
                continue

            if len(trader.strategy.prices) < trader.strategy.long_window:
                logger.info(f"{symbol}: Collecting data ({len(trader.strategy.prices)}/{trader.strategy.long_window})")
                continue

            trader.position = self.get_position(trader)
            signal = trader.strategy.get_signal()

            logger.info(f"{symbol}: ${trader.last_price:.2f} | Position: {trader.position} | Signal: {signal}")

            # Sync strategy state with actual position
            if trader.position > 0 and not trader.strategy.in_position:
                trader.strategy.enter_position(trader.last_price)
            elif trader.position == 0 and trader.strategy.in_position:
                trader.strategy.exit_position("Closed externally")

            # Execute trades
            if signal == 'BUY' and trader.position == 0:
                logger.info(f"{symbol}: BUY SIGNAL - Opening position")
                if self.place_order(trader, 'BUY', trader.position_size):
                    trader.strategy.enter_position(trader.last_price)

            elif signal == 'SELL' and trader.position > 0:
                sell_qty = min(int(trader.position), trader.position_size)
                logger.info(f"{symbol}: SELL SIGNAL - Closing position")
                if self.place_order(trader, 'SELL', sell_qty):
                    trader.strategy.exit_position("MA crossover")

    def update_dashboard(self):
        """Update dashboard with all stock states"""
        states = []
        for symbol, trader in self.traders.items():
            states.append(trader.get_state())

        state_data = {
            'multi_stock': True,
            'stocks': states,
            'is_connected': self.ib.isConnected(),
            'dry_run': self.dry_run,
            'last_update': datetime.now().isoformat()
        }

        # Update in-memory state (for backward compat)
        bot_state.update(**state_data)

        # Also write to file for separate dashboard process
        try:
            import json
            state_file = os.path.join(os.path.dirname(__file__), 'data', 'bot_state.json')
            with open(state_file, 'w') as f:
                json.dump(state_data, f)
        except Exception:
            pass  # Silently ignore file write errors

    def start(self):
        """Start the trading bot"""
        logger.info("Starting Multi-Stock Trading Bot...")
        logger.info(f"Trading: {', '.join(self.symbols)}")

        if not self.dry_run:
            logger.warning("LIVE TRADING MODE - Real money will be used!")
            logger.warning("Press Ctrl+C within 5 seconds to abort...")
            time.sleep(5)

        if not self.connect():
            logger.error("Failed to connect. Exiting.")
            return

        # Start dashboard in thread
        if self.enable_dashboard:
            from src.multi_dashboard import run_multi_dashboard
            dashboard_thread = threading.Thread(
                target=run_multi_dashboard,
                kwargs={'host': '0.0.0.0', 'port': self.dashboard_port},
                daemon=True
            )
            dashboard_thread.start()
            logger.info(f"Dashboard started at http://localhost:{self.dashboard_port}")

        logger.info(f"Collecting prices every {self.price_interval}s, checking trades every {self.trade_interval}s")

        try:
            while True:
                current_time = time.time()

                # Collect prices
                if current_time - self.last_price_time >= self.price_interval:
                    self.collect_prices()
                    self.last_price_time = current_time

                # Update events and news (every 5 minutes)
                if current_time - self.last_info_time >= 300:
                    self.update_stock_info()
                    self.last_info_time = current_time

                # Update dashboard
                self.update_dashboard()

                # Check signals
                if current_time - self.last_trade_time >= self.trade_interval:
                    self.check_signals()
                    self.last_trade_time = current_time

                self.ib.sleep(0.1)

        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            self.disconnect()


if __name__ == '__main__':
    bot = MultiStockBot()
    bot.start()
