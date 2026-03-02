import os
import time
import logging
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv
from ib_insync import IB, Stock, LimitOrder
from src.strategy import SimpleStrategy, calculate_rsi
from src.dashboard_state import bot_state
from src.dashboard import run_dashboard
from src.order_utils import OrderConfirmation
from src.alpha_vantage import AlphaVantageClient
from src.yfinance_client import YFinanceClient
from src.fundamental_data import FundamentalDataClient, EarningsAnalyzer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()


class TradingBot:
    def __init__(self):
        self.ib = IB()
        self.host = os.getenv('IB_HOST', '127.0.0.1')
        self.port = int(os.getenv('IB_PORT', '4001'))
        self.client_id = int(os.getenv('IB_CLIENT_ID', '1'))

        self.symbol = os.getenv('SYMBOL', 'NIO')
        self.exchange = os.getenv('EXCHANGE', 'SMART')
        self.currency = os.getenv('CURRENCY', 'USD')
        self.position_size = int(os.getenv('POSITION_SIZE', '15'))
        self.dry_run = os.getenv('DRY_RUN', 'true').lower() == 'true'

        # Timing settings
        self.price_interval = float(os.getenv('PRICE_INTERVAL_SEC', '5'))  # Collect price every X seconds
        self.trade_interval = int(os.getenv('TRADE_INTERVAL_SEC', '60'))   # Check for trades every X seconds

        # Dashboard settings
        self.enable_dashboard = os.getenv('ENABLE_DASHBOARD', 'true').lower() == 'true'
        self.dashboard_port = int(os.getenv('DASHBOARD_PORT', '8080'))

        # Alpha Vantage backup data source
        self.enable_alpha_vantage = os.getenv('ENABLE_ALPHA_VANTAGE', 'true').lower() == 'true'
        self.alpha_vantage = None
        self.data_source = 'IB'  # Track current data source: 'IB' or 'ALPHA_VANTAGE'
        self.ib_failures = 0  # Track consecutive IB failures
        self.av_last_fetch = 0  # Rate limit Alpha Vantage calls
        self.av_min_interval = 15  # Minimum seconds between AV calls (free tier: 5/min)

        if self.enable_alpha_vantage:
            try:
                self.alpha_vantage = AlphaVantageClient()
                logger.info("Alpha Vantage backup data source enabled")
            except ValueError as e:
                logger.warning(f"Alpha Vantage disabled: {e}")
                self.enable_alpha_vantage = False

        # Yahoo Finance backup data source (free, unlimited historical data)
        self.enable_yfinance = os.getenv('ENABLE_YFINANCE', 'true').lower() == 'true'
        self.yfinance = None
        self.yf_last_fetch = 0
        self.yf_min_interval = 5  # Minimum seconds between yfinance calls

        if self.enable_yfinance:
            try:
                self.yfinance = YFinanceClient()
                logger.info("Yahoo Finance backup data source enabled")
            except Exception as e:
                logger.warning(f"Yahoo Finance disabled: {e}")
                self.enable_yfinance = False

        self.contract = Stock(self.symbol, self.exchange, self.currency)

        # Strategy settings (optimized from backtesting)
        # Fundamental data settings
        self.use_fundamental_filter = os.getenv('USE_FUNDAMENTAL_FILTER', 'false').lower() == 'true'
        self.earnings_blackout_days = int(os.getenv('EARNINGS_BLACKOUT_DAYS', '3'))
        self.fundamental_client = None
        self.fundamental_fetch_interval = 3600  # Fetch fundamental data every hour
        self.last_fundamental_fetch = 0

        if self.use_fundamental_filter:
            try:
                self.fundamental_client = FundamentalDataClient(blackout_days=self.earnings_blackout_days)
                logger.info("Fundamental data filter enabled")
            except Exception as e:
                logger.warning(f"Fundamental data disabled: {e}")
                self.use_fundamental_filter = False

        # Earnings analyzer for post-earnings signals (PEAD strategy)
        self.earnings_analyzer = EarningsAnalyzer()
        self.last_earnings_check = 0
        self.earnings_check_interval = 3600  # Check earnings every hour

        self.strategy = SimpleStrategy(
            short_window=int(os.getenv('SHORT_MA', '10')),
            long_window=int(os.getenv('LONG_MA', '30')),
            threshold=float(os.getenv('MA_THRESHOLD', '0.01')),
            stop_loss_pct=float(os.getenv('STOP_LOSS_PCT', '0.15')),
            trailing_stop_pct=float(os.getenv('TRAILING_STOP_PCT', '0.10')),
            trail_after_profit_pct=float(os.getenv('TRAIL_AFTER_PROFIT_PCT', '0.08')),
            min_hold_periods=int(os.getenv('MIN_HOLD_PERIODS', '5')),
            rsi_overbought=int(os.getenv('RSI_OVERBOUGHT', '70')),
            volume_ma_period=int(os.getenv('VOLUME_MA_PERIOD', '20')),
            volume_confirm_threshold=float(os.getenv('VOLUME_CONFIRM_THRESHOLD', '1.5')),
            volume_min_threshold=float(os.getenv('VOLUME_MIN_THRESHOLD', '0.5')),
            use_fundamental_filter=self.use_fundamental_filter,
            earnings_blackout_days=self.earnings_blackout_days,
            require_bullish_fundamental=os.getenv('REQUIRE_BULLISH_FUNDAMENTAL', 'false').lower() == 'true',
            block_bearish_fundamental=os.getenv('BLOCK_BEARISH_FUNDAMENTAL', 'true').lower() == 'true'
        )

        # Index tracking for market filter
        self.index_symbol = os.getenv('INDEX_SYMBOL', 'KWEB')
        self.index_drop_threshold = float(os.getenv('INDEX_DROP_THRESHOLD', '0.02'))
        self.index_lookback = int(os.getenv('INDEX_LOOKBACK_DAYS', '5'))
        self.index_prices = []
        self.last_index_fetch = 0
        self.index_fetch_interval = 3600  # Fetch index once per hour

        self.position = 0
        self.last_bid = 0
        self.last_ask = 0
        self.last_price = 0
        self.last_volume = 0
        self.limit_offset = 0.01
        self.ticker = None

        self.last_price_time = 0
        self.last_trade_time = 0

        mode = "DRY RUN" if self.dry_run else "LIVE TRADING"
        logger.info(f"Bot initialized - Symbol: {self.symbol}, Port: {self.port}, Mode: {mode}")
        logger.info(f"Price collection: every {self.price_interval}s, Trade check: every {self.trade_interval}s")
        logger.info(f"Volume filter: confirm>{self.strategy.volume_confirm_threshold}x, min>{self.strategy.volume_min_threshold}x (MA{self.strategy.volume_ma_period})")
        logger.info(f"Fundamental filter: {'ENABLED' if self.use_fundamental_filter else 'DISABLED'}")
        logger.info(f"Alpha Vantage backup: {'ENABLED' if self.enable_alpha_vantage else 'DISABLED'}")
        logger.info(f"Yahoo Finance backup: {'ENABLED' if self.enable_yfinance else 'DISABLED'}")
        if not self.dry_run:
            logger.warning("WARNING:  LIVE TRADING ENABLED - Real money will be used!")

    def connect(self):
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            logger.info(f"Connected to IB Gateway at {self.host}:{self.port}")

            self.ib.qualifyContracts(self.contract)
            logger.info(f"Contract qualified: {self.contract}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to IB: {e}")
            return False

    def disconnect(self):
        if self.ticker:
            self.ib.cancelMktData(self.contract)
        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Disconnected from IB")

    def start_streaming(self):
        """Start streaming market data (delayed if no subscription)"""
        # Request delayed data if live not available (type 3 = delayed)
        self.ib.reqMarketDataType(3)
        self.ticker = self.ib.reqMktData(self.contract, '', False, False)
        logger.info(f"Started streaming market data for {self.symbol} (delayed if no subscription)")

    def load_historical_data(self):
        """Fetch historical data for dashboard chart, fallback to Alpha Vantage"""
        bars = None
        data_source = 'IB'

        # Try IB first
        try:
            bars = self.ib.reqHistoricalData(
                self.contract,
                endDateTime='',
                durationStr='1 D',
                barSizeSetting='5 mins',
                whatToShow='TRADES',
                useRTH=True,
                formatDate=1
            )
        except Exception as e:
            logger.warning(f"IB historical data failed: {e}")

        # Fallback to Alpha Vantage if IB fails
        if not bars and self.alpha_vantage:
            logger.info("Falling back to Alpha Vantage for historical data...")
            intraday = self.alpha_vantage.get_intraday(self.symbol, '5min')
            if intraday:
                data_source = 'ALPHA_VANTAGE'
                hist_prices = [bar['close'] for bar in intraday]
                hist_times = [bar['datetime'].strftime('%H:%M') for bar in intraday]
                rsi = calculate_rsi(hist_prices)

                self.last_price = hist_prices[-1]
                self.last_bid = hist_prices[-1]
                self.last_ask = hist_prices[-1]

                short_ma = sum(hist_prices[-self.strategy.short_window:]) / self.strategy.short_window if len(hist_prices) >= self.strategy.short_window else hist_prices[-1]
                long_ma = sum(hist_prices[-self.strategy.long_window:]) / self.strategy.long_window if len(hist_prices) >= self.strategy.long_window else hist_prices[-1]

                bot_state.update(
                    historical_prices=hist_prices,
                    historical_times=hist_times,
                    rsi_values=rsi,
                    last_price=self.last_price,
                    short_ma=short_ma,
                    long_ma=long_ma,
                    short_window=self.strategy.short_window,
                    long_window=self.strategy.long_window,
                    last_price_update=datetime.now(),
                    is_live_streaming=False
                )
                logger.info(f"Loaded {len(intraday)} bars from Alpha Vantage (last price: ${self.last_price:.2f})")
                return

        # Fallback to Yahoo Finance if Alpha Vantage also fails
        if not bars and self.yfinance:
            logger.info("Falling back to Yahoo Finance for historical data...")
            history = self.yfinance.get_history(self.symbol, '5d')  # Last 5 days of daily data
            if history:
                hist_prices = [bar['close'] for bar in history]
                hist_volumes = [bar['volume'] for bar in history]
                hist_times = [bar['date'].strftime('%m/%d') for bar in history]
                rsi = calculate_rsi(hist_prices) if len(hist_prices) >= 14 else []

                self.last_price = hist_prices[-1]
                self.last_bid = hist_prices[-1]
                self.last_ask = hist_prices[-1]
                self.last_volume = hist_volumes[-1] if hist_volumes else 0

                # Pre-load volume history into strategy
                for vol in hist_volumes:
                    self.strategy.add_volume(vol)

                short_ma = sum(hist_prices[-self.strategy.short_window:]) / min(len(hist_prices), self.strategy.short_window)
                long_ma = sum(hist_prices[-self.strategy.long_window:]) / min(len(hist_prices), self.strategy.long_window)

                bot_state.update(
                    historical_prices=hist_prices,
                    historical_times=hist_times,
                    rsi_values=rsi,
                    last_price=self.last_price,
                    short_ma=short_ma,
                    long_ma=long_ma,
                    short_window=self.strategy.short_window,
                    long_window=self.strategy.long_window,
                    last_price_update=datetime.now(),
                    is_live_streaming=False
                )
                logger.info(f"Loaded {len(history)} bars from Yahoo Finance (last price: ${self.last_price:.2f})")
                return

        if bars:
            hist_prices = [bar.close for bar in bars]
            hist_volumes = [bar.volume for bar in bars]
            hist_times = [bar.date.strftime('%H:%M') for bar in bars]
            rsi = calculate_rsi(hist_prices)

            # Use last historical price as current price if no live data
            self.last_price = hist_prices[-1]
            self.last_bid = hist_prices[-1]
            self.last_ask = hist_prices[-1]
            self.last_volume = hist_volumes[-1] if hist_volumes else 0

            # Pre-load volume history into strategy
            for vol in hist_volumes:
                self.strategy.add_volume(vol)

            # Calculate MAs from historical data
            short_ma = sum(hist_prices[-self.strategy.short_window:]) / self.strategy.short_window
            long_ma = sum(hist_prices[-self.strategy.long_window:]) / self.strategy.long_window

            # Get the time of the last bar for staleness tracking (use naive datetime)
            last_bar_time = datetime.now()

            bot_state.update(
                historical_prices=hist_prices,
                historical_times=hist_times,
                rsi_values=rsi,
                last_price=self.last_price,
                short_ma=short_ma,
                long_ma=long_ma,
                short_window=self.strategy.short_window,
                long_window=self.strategy.long_window,
                last_price_update=last_bar_time,
                is_live_streaming=False
            )
            logger.info(f"Loaded {len(bars)} historical bars from IB (last price: ${self.last_price:.2f})")
            logger.info(f"Historical MAs - Short: ${short_ma:.4f}, Long: ${long_ma:.4f}")
        else:
            logger.warning("No historical data received from IB or Alpha Vantage")

    def get_current_price(self):
        """Get current price from streaming ticker, fallback to Alpha Vantage"""
        import math
        price = None

        # Try IB first
        if self.ticker:
            price = self.ticker.marketPrice()
            bid = self.ticker.bid
            ask = self.ticker.ask
            volume = self.ticker.volume if hasattr(self.ticker, 'volume') else 0

            # Check for valid price (not None, not 0, not NaN)
            if price and price > 0 and not math.isnan(price):
                self.last_price = price
                self.last_bid = bid if bid and bid > 0 else price
                self.last_ask = ask if ask and ask > 0 else price
                self.last_volume = volume if volume and volume > 0 else self.last_volume
                self.data_source = 'IB'
                self.ib_failures = 0
                return price

        # IB failed - try backup sources immediately
        current_time = time.time()

        # Try Alpha Vantage first (rate limited to every 15s)
        if self.alpha_vantage and current_time - self.av_last_fetch >= self.av_min_interval:
            self.av_last_fetch = current_time
            quote = self.alpha_vantage.get_quote(self.symbol)
            if quote and quote['price'] > 0:
                self.last_price = quote['price']
                self.last_bid = quote['price']
                self.last_ask = quote['price']
                self.last_volume = quote.get('volume', 0) or self.last_volume
                self.data_source = 'ALPHA_VANTAGE'
                logger.info(f"Using Alpha Vantage price: ${quote['price']:.2f}, volume: {self.last_volume:,}")
                return quote['price']

        # Try Yahoo Finance as last resort
        if self.yfinance and current_time - self.yf_last_fetch >= self.yf_min_interval:
            self.yf_last_fetch = current_time
            quote = self.yfinance.get_quote(self.symbol)
            if quote and quote['price'] > 0:
                self.last_price = quote['price']
                self.last_bid = quote['price']
                self.last_ask = quote['price']
                self.last_volume = quote.get('volume', 0) or self.last_volume
                self.data_source = 'YFINANCE'
                logger.info(f"Using Yahoo Finance price: ${quote['price']:.2f}, volume: {self.last_volume:,}")
                return quote['price']

        return None

    def get_position(self):
        positions = self.ib.positions()
        for pos in positions:
            if pos.contract.symbol == self.symbol:
                return pos.position
        return 0

    def place_order(self, action, quantity):
        mid_price = (self.last_bid + self.last_ask) / 2
        if action == 'BUY':
            limit_price = round(mid_price + self.limit_offset, 2)
        else:
            limit_price = round(mid_price - self.limit_offset, 2)

        if self.dry_run:
            logger.info(f"[DRY RUN] Would place {action} LIMIT order for {quantity} shares of {self.symbol} at ${limit_price:.2f}")
            logger.info(f"[DRY RUN] Bid: ${self.last_bid:.2f}, Ask: ${self.last_ask:.2f}, Mid: ${mid_price:.2f}")
            return None

        try:
            # Use OrderConfirmation for verified trading
            confirmer = OrderConfirmation(self.ib)
            logger.info(f"Placing verified order: {action} {quantity} {self.symbol} at ${limit_price:.2f}")
            logger.info(f"Bid: ${self.last_bid:.2f}, Ask: ${self.last_ask:.2f}, Mid: ${mid_price:.2f}")

            success, message, details = confirmer.place_and_confirm(
                symbol=self.symbol,
                action=action,
                quantity=quantity,
                price=limit_price,
                timeout=60
            )

            if success:
                logger.info(f"VERIFIED: {message}")
                logger.info(f"Position: {details['position_before']} -> {details['position_after']}")
            else:
                logger.error(f"VERIFICATION FAILED: {message}")
                if details:
                    logger.error(f"Details: position_before={details.get('position_before')}, position_after={details.get('position_after')}, status={details.get('status')}")

            return details
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None

    def collect_price(self):
        """Collect price and volume for strategy analysis"""
        price = self.get_current_price()
        if price:
            self.strategy.add_price(price)
            self.strategy.add_volume(self.last_volume)
            logger.debug(f"Price collected: ${price:.2f}, Volume: {self.last_volume:,} (total: {len(self.strategy.prices)})")
            return True
        return False

    def update_dashboard_state(self):
        """Update the shared state for dashboard"""
        # Use session MAs if available, otherwise keep historical MAs
        short_ma = bot_state.short_ma  # Keep existing value
        long_ma = bot_state.long_ma    # Keep existing value

        if len(self.strategy.prices) >= self.strategy.short_window:
            short_ma = sum(self.strategy.prices[-self.strategy.short_window:]) / self.strategy.short_window
        if len(self.strategy.prices) >= self.strategy.long_window:
            long_ma = sum(self.strategy.prices[-self.strategy.long_window:]) / self.strategy.long_window

        signal = "HOLD"
        if len(self.strategy.prices) >= self.strategy.long_window:
            signal = self.strategy.get_signal()

        # Detect market data type (1=Live, 3=Delayed, 4=Delayed Frozen)
        data_mode = "UNKNOWN"
        if self.data_source == 'ALPHA_VANTAGE':
            data_mode = "ALPHA_VANTAGE"
        elif self.data_source == 'YFINANCE':
            data_mode = "YFINANCE"
        elif self.ticker and hasattr(self.ticker, 'marketDataType'):
            mdt = self.ticker.marketDataType
            if mdt == 1:
                data_mode = "LIVE"
            elif mdt in (3, 4):
                data_mode = "DELAYED"

        bot_state.update(
            last_price=self.last_price,
            last_bid=self.last_bid,
            last_ask=self.last_ask,
            position=self.position,
            position_size=self.position_size,
            symbol=self.symbol,
            prices=list(self.strategy.prices),
            short_window=self.strategy.short_window,
            long_window=self.strategy.long_window,
            short_ma=short_ma,
            long_ma=long_ma,
            current_signal=signal,
            is_connected=self.ib.isConnected(),
            dry_run=self.dry_run,
            data_mode=data_mode,
            last_price_update=datetime.now()
        )

    def fetch_index_price(self):
        """Fetch current index price for market filter"""
        current_time = time.time()
        if current_time - self.last_index_fetch < self.index_fetch_interval:
            return  # Already fetched recently

        try:
            if self.yfinance:
                history = self.yfinance.get_history(self.index_symbol, '1mo')
                if history:
                    self.index_prices = [bar['close'] for bar in history]
                    self.last_index_fetch = current_time
                    logger.info(f"Fetched {len(self.index_prices)} {self.index_symbol} prices")
        except Exception as e:
            logger.warning(f"Failed to fetch index prices: {e}")

    def fetch_fundamental_data(self):
        """Fetch fundamental data (earnings, news, analyst ratings)"""
        if not self.fundamental_client:
            return

        current_time = time.time()
        if current_time - self.last_fundamental_fetch < self.fundamental_fetch_interval:
            return  # Already fetched recently

        try:
            logger.info(f"Fetching fundamental data for {self.symbol}...")
            data = self.fundamental_client.get_all_fundamental_data(self.symbol)
            self.strategy.update_fundamental_data(data)
            self.last_fundamental_fetch = current_time

            # Log summary
            earnings = data.get('earnings')
            news_sentiment, news_score, news_count = data.get('news_sentiment', ('neutral', 0, 0))
            analyst = data.get('analyst_rating')

            if earnings and earnings.next_earnings_date:
                logger.info(f"Earnings: {earnings.days_until_earnings} days until {earnings.next_earnings_date.strftime('%Y-%m-%d')}, blackout: {earnings.in_blackout_period}")

            logger.info(f"News: {news_sentiment} ({news_score:.2f}), Analyst: {analyst.recommendation if analyst else 'N/A'} ({analyst.score:.1f}/5)" if analyst else f"News: {news_sentiment}")

        except Exception as e:
            logger.error(f"Failed to fetch fundamental data: {e}")

    def fetch_earnings_signal(self):
        """Fetch earnings signal for post-earnings trading (PEAD strategy)"""
        current_time = time.time()
        if current_time - self.last_earnings_check < self.earnings_check_interval:
            return  # Already checked recently

        try:
            logger.info(f"Checking earnings signal for {self.symbol}...")

            # Get earnings signal
            signal, strength, reason = self.earnings_analyzer.get_earnings_signal(self.symbol)

            # Check if earnings were recently released (last 7 days)
            just_released = self.earnings_analyzer.check_earnings_just_released(self.symbol, hours=168)

            if just_released and signal in ('strong_buy', 'buy', 'strong_sell', 'sell'):
                logger.info(f"EARNINGS SIGNAL: {signal} (strength: {strength:.2f})")
                logger.info(f"Reason: {reason}")
                self.strategy.update_earnings_signal(signal, strength, reason)
            else:
                # Clear earnings signal if no recent earnings or neutral
                self.strategy.update_earnings_signal(None, 0, None)
                if just_released:
                    logger.info(f"Earnings just released but signal is neutral: {reason}")
                else:
                    logger.debug("No recent earnings release")

            self.last_earnings_check = current_time

        except Exception as e:
            logger.error(f"Failed to fetch earnings signal: {e}")

    def is_index_dropping(self) -> bool:
        """Check if the index is in a selloff"""
        if len(self.index_prices) < self.index_lookback:
            return False

        current_idx = self.index_prices[-1]
        past_idx = self.index_prices[-self.index_lookback]

        if past_idx <= 0:
            return False

        change = (current_idx - past_idx) / past_idx
        is_dropping = change <= -self.index_drop_threshold

        if is_dropping:
            logger.info(f"{self.index_symbol} down {change*100:.1f}% over {self.index_lookback} days - market selloff")

        return is_dropping

    def check_trade_signal(self):
        """Check for trade signals and execute if needed"""
        if not self.ib.isConnected():
            logger.warning("Not connected to IB, attempting reconnect...")
            if not self.connect():
                return

        price = self.last_price
        if price <= 0:
            return

        logger.info(f"{self.symbol} price: ${price:.2f} | Bid: ${self.last_bid:.2f} Ask: ${self.last_ask:.2f}")

        self.position = self.get_position()
        logger.info(f"Current position: {self.position} shares | Prices collected: {len(self.strategy.prices)}")

        # Sync strategy position state with actual position
        if self.position > 0 and not self.strategy.in_position:
            self.strategy.enter_position(price)
        elif self.position == 0 and self.strategy.in_position:
            self.strategy.exit_position("Position closed externally")

        # Fetch index data for market filter
        self.fetch_index_price()
        index_dropping = self.is_index_dropping()

        # Fetch fundamental data (earnings, news, analyst ratings)
        self.fetch_fundamental_data()

        # Fetch earnings signal for PEAD strategy
        self.fetch_earnings_signal()

        # Get signal from strategy
        signal = self.strategy.get_signal(index_dropping=index_dropping)

        # Log strategy status
        status = self.strategy.get_status()
        if self.strategy.in_position:
            logger.info(f"Position: entry=${status['entry_price']:.2f}, peak=${status['peak_price']:.2f}, "
                       f"held={status['periods_held']} periods, PnL=${status['unrealized_pnl']:.2f}")

        # Execute trades based on signal
        if signal == 'BUY' and self.position == 0:
            logger.info(f"Signal: BUY - Opening position")
            result = self.place_order('BUY', self.position_size)
            if result or self.dry_run:
                self.strategy.enter_position(price)

        elif signal == 'SELL' and self.position > 0:
            sell_qty = min(abs(self.position), self.position_size)
            logger.info(f"Signal: SELL (MA crossover) - Closing position ({sell_qty} shares)")
            result = self.place_order('SELL', sell_qty)
            if result or self.dry_run:
                self.strategy.exit_position("MA crossover sell")

        elif signal == 'STOP_LOSS' and self.position > 0:
            sell_qty = min(abs(self.position), self.position_size)
            logger.warning(f"Signal: STOP-LOSS - Protecting capital ({sell_qty} shares)")
            result = self.place_order('SELL', sell_qty)
            if result or self.dry_run:
                self.strategy.exit_position("Stop-loss triggered")

        elif signal == 'TRAILING_STOP' and self.position > 0:
            sell_qty = min(abs(self.position), self.position_size)
            logger.info(f"Signal: TRAILING STOP - Locking in profits ({sell_qty} shares)")
            result = self.place_order('SELL', sell_qty)
            if result or self.dry_run:
                self.strategy.exit_position("Trailing stop triggered")
        elif signal == 'SELL' and self.position <= 0:
            logger.info(f"Signal: SELL - No position to sell (avoiding short)")
        else:
            logger.info(f"Signal: {signal} - No action")

    def start(self):
        logger.info("Starting trading bot...")

        if not self.dry_run:
            logger.warning(f"WARNING:  LIVE TRADING MODE - Position size: {self.position_size} shares of {self.symbol}")
            logger.warning("Press Ctrl+C within 5 seconds to abort...")
            time.sleep(5)

        if not self.connect():
            logger.error("Failed to connect. Exiting.")
            return

        self.start_streaming()

        # Fetch historical data for chart
        self.load_historical_data()

        # Start dashboard server in background thread
        if self.enable_dashboard:
            dashboard_thread = threading.Thread(
                target=run_dashboard,
                kwargs={'host': '0.0.0.0', 'port': self.dashboard_port},
                daemon=True
            )
            dashboard_thread.start()
            logger.info(f"Dashboard started at http://localhost:{self.dashboard_port}")

        logger.info(f"Collecting prices every {self.price_interval}s, checking trades every {self.trade_interval}s")
        logger.info("Waiting for price data...")

        try:
            while True:
                current_time = time.time()

                # Collect price at regular intervals
                if current_time - self.last_price_time >= self.price_interval:
                    self.collect_price()
                    self.last_price_time = current_time

                # Update dashboard state
                self.update_dashboard_state()

                # Check for trade signals at regular intervals
                if current_time - self.last_trade_time >= self.trade_interval:
                    self.check_trade_signal()
                    self.last_trade_time = current_time

                # Small sleep to prevent CPU spinning
                self.ib.sleep(0.1)

        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            self.disconnect()


if __name__ == '__main__':
    bot = TradingBot()
    bot.start()
