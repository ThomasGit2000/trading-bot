"""
Multi-Stock Trading Bot with NO STOPS Strategy
Trades multiple symbols simultaneously using MA crossover signals.
"""
import os
import json
import time
import logging
import threading
from datetime import datetime
from dotenv import load_dotenv
from ib_insync import IB, Stock, LimitOrder
from src.strategy import SimpleStrategy
from src.dashboard_state import bot_state
from src.yfinance_client import YFinanceClient

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

    def __init__(self, symbol: str, position_size: int, short_ma: int, long_ma: int):
        self.symbol = symbol
        self.position_size = position_size
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
        buy_probability = 0
        sell_probability = 0

        if len(self.strategy.prices) >= self.strategy.short_window:
            short_ma = sum(list(self.strategy.prices)[-self.strategy.short_window:]) / self.strategy.short_window
        if len(self.strategy.prices) >= self.strategy.long_window:
            long_ma = sum(list(self.strategy.prices)[-self.strategy.long_window:]) / self.strategy.long_window
            signal = self.strategy.get_signal()

            # Calculate crossover probability
            buy_probability, sell_probability = self._calculate_probability(short_ma, long_ma)

        return {
            'symbol': self.symbol,
            'price': self.last_price,
            'bid': self.last_bid,
            'ask': self.last_ask,
            'position': self.position,
            'position_size': self.position_size,
            'short_ma': short_ma,
            'long_ma': long_ma,
            'signal': signal,
            'prices_collected': len(self.strategy.prices),
            'data_source': self.data_source,
            'in_position': self.strategy.in_position,
            'buy_probability': buy_probability,
            'sell_probability': sell_probability,
            'upcoming_events': self.upcoming_events,
            'news': self.news
        }

    def _calculate_probability(self, short_ma: float, long_ma: float) -> tuple:
        """
        Calculate probability of buy/sell signal based on MA convergence.
        Returns (buy_prob, sell_prob) as percentages 0-100.
        """
        if long_ma == 0 or self.last_price == 0:
            return (0, 0)

        # Gap between MAs as percentage of price
        gap_pct = abs(short_ma - long_ma) / self.last_price * 100

        # Calculate momentum (rate of change) using recent prices
        prices = list(self.strategy.prices)
        momentum = 0
        if len(prices) >= 5:
            recent_avg = sum(prices[-5:]) / 5
            older_avg = sum(prices[-10:-5]) / 5 if len(prices) >= 10 else recent_avg
            momentum = (recent_avg - older_avg) / self.last_price * 100

        # Base probability: inversely proportional to gap
        # At 0% gap = 95% probability, at 1% gap = ~50%, at 2%+ gap = low
        base_prob = max(0, min(95, 95 - (gap_pct * 45)))

        # Adjust based on momentum and direction
        if short_ma < long_ma:
            # Below long MA - potential BUY
            # Positive momentum increases buy probability
            buy_prob = min(95, base_prob + (momentum * 20))
            sell_prob = max(0, 100 - buy_prob - 10)  # Lower sell prob
        else:
            # Above long MA - potential SELL
            # Negative momentum increases sell probability
            sell_prob = min(95, base_prob - (momentum * 20))
            buy_prob = max(0, 100 - sell_prob - 10)  # Lower buy prob

        return (round(max(0, buy_prob), 1), round(max(0, sell_prob), 1))


class MultiStockBot:
    """Trading bot for multiple stocks"""

    def __init__(self):
        self.ib = IB()
        self.host = os.getenv('IB_HOST', '127.0.0.1')
        self.port = int(os.getenv('IB_PORT', '7496'))
        self.client_id = int(os.getenv('IB_CLIENT_ID', '1'))

        # Parse symbols
        symbols_str = os.getenv('SYMBOLS', 'TSLA,NIO')
        self.symbols = [s.strip() for s in symbols_str.split(',')]

        # Parse position sizes
        pos_sizes_str = os.getenv('POSITION_SIZES', '{}')
        try:
            self.position_sizes = json.loads(pos_sizes_str)
        except:
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
            self.traders[symbol] = StockTrader(
                symbol=symbol,
                position_size=pos_size,
                short_ma=self.short_ma,
                long_ma=self.long_ma
            )
            logger.info(f"Created trader for {symbol} (size: {pos_size})")

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
        """Collect prices for all stocks"""
        for symbol, trader in self.traders.items():
            price = self.get_price(trader)
            if price:
                trader.strategy.add_price(price)
                logger.debug(f"{symbol}: ${price:.2f} (collected: {len(trader.strategy.prices)})")

    def update_stock_info(self):
        """Update events and news for all stocks (called less frequently)"""
        current_time = time.time()
        for symbol, trader in self.traders.items():
            # Update every 5 minutes
            if current_time - trader.last_info_update >= 300:
                try:
                    trader.upcoming_events = self.yfinance.get_upcoming_events(symbol)
                    trader.news = self.yfinance.get_news(symbol, limit=3)
                    trader.last_info_update = current_time
                    logger.info(f"{symbol}: Updated events and news")
                except Exception as e:
                    logger.warning(f"Failed to update info for {symbol}: {e}")

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

        # Update shared state (will be read by dashboard)
        bot_state.update(
            multi_stock=True,
            stocks=states,
            is_connected=self.ib.isConnected(),
            dry_run=self.dry_run,
            last_update=datetime.now().isoformat()
        )

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

        # Start dashboard
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
