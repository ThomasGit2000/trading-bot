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
from ib_insync import IB, Stock, LimitOrder, util
from src.strategy import SimpleStrategy, BreakoutStrategy
from src.dashboard_state import bot_state
from src.regime_detector import RegimeDetector, AdaptiveStrategy
from src.trade_verifier import trade_verifier, TradeStatus
from src.trading_control import trading_control
from src.yfinance_client import YFinanceClient
from src.alpha_engine import alpha_engine, AlphaContext

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

    def __init__(self, symbol: str, position_size: int, short_ma: int, long_ma: int, threshold: float = 0.003, category: str = "UNCATEGORIZED", volume_filter: bool = False, rsi_period: int = 14, strategy_type: str = "MA_CROSSOVER", breakout_lookback: int = 60, breakout_threshold: float = 0.005, stop_loss_pct: float = 0.05, trailing_stop_pct: float = 0.03, atr_filter: bool = False, atr_min_threshold: float = 0.003, atr_period: int = 300):
        self.symbol = symbol
        self.position_size = position_size
        self.category = category
        self.threshold = threshold
        self.strategy_type = strategy_type

        if strategy_type == "BREAKOUT":
            self.strategy = BreakoutStrategy(
                lookback_periods=breakout_lookback,
                breakout_threshold=breakout_threshold,
                stop_loss_pct=stop_loss_pct,
                trailing_stop_pct=trailing_stop_pct,
                trail_after_profit_pct=0.01,
                min_hold_periods=10,
                atr_filter=atr_filter,
                atr_min_threshold=atr_min_threshold,
                atr_period=atr_period
            )
        else:  # MA_CROSSOVER (default)
            self.strategy = SimpleStrategy(
                short_window=short_ma,
                long_window=long_ma,
                threshold=threshold,
                stop_loss_pct=stop_loss_pct,
                trailing_stop_pct=trailing_stop_pct,
                min_hold_periods=5,
                volume_confirm_threshold=1.5 if volume_filter else 0,
                volume_min_threshold=0.5 if volume_filter else 0,
                rsi_period=rsi_period
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
        # 24H intraday prices for sparkline
        self.intraday_prices = []
        self.last_intraday_update = 0

    def get_state(self, lightweight: bool = False) -> dict:
        """Get current state for dashboard. Use lightweight=True for WebSocket updates."""
        short_ma = 0
        long_ma = 0
        signal = "WAIT"
        signal_strength = 0
        rsi = 50  # Default RSI

        if self.strategy_type == "BREAKOUT":
            # Breakout strategy
            if len(self.strategy.prices) >= self.strategy.lookback_periods:
                signal = self.strategy.get_signal()
                signal_strength = self.strategy.get_signal_strength()
                range_high, range_low = self.strategy.get_range()
                short_ma = range_high or 0  # Show range high as "short_ma"
                long_ma = range_low or 0    # Show range low as "long_ma"
        else:
            # MA Crossover strategy
            if len(self.strategy.prices) >= self.strategy.short_window:
                short_ma = sum(list(self.strategy.prices)[-self.strategy.short_window:]) / self.strategy.short_window
            if len(self.strategy.prices) >= self.strategy.long_window:
                long_ma = sum(list(self.strategy.prices)[-self.strategy.long_window:]) / self.strategy.long_window
                signal = self.strategy.get_signal()
                signal_strength, _ = self._calculate_probability(short_ma, long_ma)
            rsi = self.strategy.get_current_rsi()

        # Determine filter status and stop-out state
        vol_ok = True  # Default OK
        atr_ok = True
        atr_pct = 0
        stop_out = None  # None, 'TRAIL', or 'LOSS'

        if self.strategy_type == "BREAKOUT":
            # Check ATR filter for breakout strategy
            raw_atr = self.strategy.get_atr_percent()
            atr_pct = raw_atr  # Store as decimal (0.02 = 2%)
            if hasattr(self.strategy, 'atr_filter') and self.strategy.atr_filter:
                atr_ok = atr_pct >= self.strategy.atr_min_threshold  # Compare decimals
            # Check stop-out status
            if signal == 'STOP_LOSS':
                stop_out = 'LOSS'
            elif signal == 'TRAILING_STOP':
                stop_out = 'TRAIL'
        else:
            # Check volume filter for MA strategy
            if hasattr(self.strategy, 'volume_confirm_threshold') and self.strategy.volume_confirm_threshold > 0:
                vol_ok = self.strategy.check_volume_confirmation()
            if signal == 'STOP_LOSS':
                stop_out = 'LOSS'
            elif signal == 'TRAILING_STOP':
                stop_out = 'TRAIL'

        # Compute alpha score if enabled
        alpha_score = 0.0
        if alpha_engine.enabled and self.strategy_type == "BREAKOUT":
            alpha_context = self._build_alpha_context(rsi, atr_pct, "UNKNOWN")
            alpha_result = alpha_engine.compute_alpha(alpha_context)
            alpha_score = alpha_result['score']

        state = {
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
            'rsi': rsi,
            'signal': signal,
            'prices_collected': len(self.strategy.prices),
            'data_source': self.data_source,
            'in_position': self.strategy.in_position,
            'signal_strength': signal_strength,
            'upcoming_events': self.upcoming_events,
            'vol_ok': vol_ok,
            'atr_ok': atr_ok,
            'atr_pct': atr_pct,
            'stop_out': stop_out,
            'news_sentiment': self._get_news_sentiment(),  # Lightweight sentiment score
            'alpha_score': alpha_score,  # Alpha engine composite score
        }

        # Only include heavy data for full state requests (not WebSocket)
        if not lightweight:
            state['news'] = self.news
            state['price_history'] = self.intraday_prices[-50:] if self.intraday_prices else []
            state['tick_prices'] = list(self.strategy.prices)[-60:] if self.strategy.prices else []

        return state

    def _calculate_probability(self, short_ma: float, long_ma: float) -> tuple:
        """
        Calculate signal strength based on MA crossover thresholds.
        Shows how close we are to actual BUY or SELL signals.

        Scale: -100 (SELL signal) to +100 (BUY signal)
        """
        if long_ma == 0:
            return (0, 0)

        threshold = self.threshold  # Use configured threshold (0.3%)

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

    def _get_news_sentiment(self) -> float:
        """Calculate average sentiment score from news (-100 to +100)"""
        if not self.news:
            return 0
        scores = [n.get('sentiment_score', 0) for n in self.news if isinstance(n, dict)]
        if not scores:
            return 0
        avg = sum(scores) / len(scores)
        return round(avg * 100, 1)  # Scale -1..+1 to -100..+100

    def _build_alpha_context(self, rsi: float = 50.0, atr_pct: float = 0.0, regime: str = "UNKNOWN") -> AlphaContext:
        """Build context for alpha engine computation"""
        # Get strategy context
        strategy_ctx = {}
        if hasattr(self.strategy, 'get_alpha_context'):
            strategy_ctx = self.strategy.get_alpha_context()

        # Get relative volume (default 1.0 if not available)
        relative_volume = 1.0
        if hasattr(self.strategy, 'get_relative_volume'):
            relative_volume = self.strategy.get_relative_volume()

        # Get news sentiment (-1 to +1 scale)
        news_sentiment = self._get_news_sentiment() / 100.0  # Convert back to -1..+1

        return AlphaContext(
            prices=strategy_ctx.get('prices', list(self.strategy.prices)),
            current_price=self.last_price,
            range_high=strategy_ctx.get('range_high'),
            range_low=strategy_ctx.get('range_low'),
            rsi=rsi,
            atr_pct=atr_pct,
            relative_volume=relative_volume,
            regime=regime,
            news_sentiment=news_sentiment,
            in_position=self.strategy.in_position,
        )


class MultiStockBot:
    """Trading bot for multiple stocks"""

    def __init__(self):
        self.ib = IB()
        self.host = os.getenv('IB_HOST', '127.0.0.1')
        self.port = int(os.getenv('IB_PORT', '7496'))
        self.client_id = int(os.getenv('IB_CLIENT_ID', '1'))

        # Cash balance caching (updated every 60s)
        self.available_cash_usd = 0
        self.net_liquidation_usd = 0
        self.last_balance_check = 0
        self.usd_dkk_rate = 6.9  # Approximate USD to DKK rate

        # Circuit breakers (safety limits)
        self.daily_trades = 0
        self.daily_loss_usd = 0
        self.max_trades_per_day = 100  # Max 100 trades/day
        self.max_daily_loss_usd = 1000  # Max $1000 loss/day (~14% of account)
        self.last_reset_date = datetime.now().date()

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
        self.strategy_type = os.getenv('STRATEGY_TYPE', 'MA_CROSSOVER').upper()
        self.short_ma = int(os.getenv('SHORT_MA', '10'))
        self.long_ma = int(os.getenv('LONG_MA', '30'))
        self.ma_threshold = float(os.getenv('MA_THRESHOLD', '0.003'))
        self.breakout_lookback = int(os.getenv('BREAKOUT_LOOKBACK', '60'))
        self.breakout_threshold = float(os.getenv('BREAKOUT_THRESHOLD', '0.005'))
        self.atr_filter = os.getenv('ATR_FILTER', 'false').lower() == 'true'
        self.atr_min_threshold = float(os.getenv('ATR_MIN_THRESHOLD', '0.003'))
        self.atr_period = int(os.getenv('ATR_PERIOD', '300'))  # 5 min smoothing
        self.rsi_period = int(os.getenv('RSI_PERIOD', '14'))
        self.volume_filter = os.getenv('VOLUME_FILTER', 'false').lower() == 'true'
        self.stop_loss_pct = float(os.getenv('STOP_LOSS_PCT', '0.05'))
        self.trailing_stop_pct = float(os.getenv('TRAILING_STOP_PCT', '0.03'))

        # Bot settings
        self.dry_run = os.getenv('DRY_RUN', 'true').lower() == 'true'
        self.price_interval = float(os.getenv('PRICE_INTERVAL_SEC', '5'))
        self.trade_interval = int(os.getenv('TRADE_INTERVAL_SEC', '60'))

        # Dashboard
        self.enable_dashboard = os.getenv('ENABLE_DASHBOARD', 'true').lower() == 'true'
        self.dashboard_port = int(os.getenv('DASHBOARD_PORT', '8080'))

        # IBKR streaming market data
        self.tickers = {}  # symbol -> Ticker object
        self.regime_ticker = None  # Ticker for regime index (SPY)

        # Regime detection (BULL/BEAR market awareness)
        self.regime_enabled = os.getenv('REGIME_AWARE', 'true').lower() == 'true'
        self.regime_index = os.getenv('REGIME_INDEX', 'SPY')
        self.regime_short_ma = int(os.getenv('REGIME_SHORT_MA', '20'))
        self.regime_long_ma = int(os.getenv('REGIME_LONG_MA', '50'))

        if self.regime_enabled:
            self.regime_detector = RegimeDetector(
                index_symbol=self.regime_index,
                short_window=self.regime_short_ma,
                long_window=self.regime_long_ma
            )
            self.adaptive_strategy = AdaptiveStrategy(self.regime_detector)
            logger.info(f"Regime detection ENABLED: {self.regime_index} MA({self.regime_short_ma}/{self.regime_long_ma})")
            logger.info("  BULL market: Buy signals active, SELL signals IGNORED (hold)")
            logger.info("  BEAR market: Full MA crossover strategy active")
        else:
            self.regime_detector = None
            self.adaptive_strategy = None
            logger.info("Regime detection DISABLED: Using standard MA crossover")

        # YFinance client for events and supplementary data
        self.yfinance_client = YFinanceClient()

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
                threshold=self.ma_threshold,
                category=category,
                volume_filter=self.volume_filter,
                rsi_period=self.rsi_period,
                strategy_type=self.strategy_type,
                breakout_lookback=self.breakout_lookback,
                breakout_threshold=self.breakout_threshold,
                stop_loss_pct=self.stop_loss_pct,
                trailing_stop_pct=self.trailing_stop_pct,
                atr_filter=self.atr_filter,
                atr_min_threshold=self.atr_min_threshold,
                atr_period=self.atr_period
            )
            logger.info(f"Created trader for {symbol} [{category}] (size: {pos_size})")

        self.last_price_time = 0
        self.last_trade_time = 0
        self.last_info_time = 0
        self._market_open_cache = None
        self._market_open_cache_time = 0

        mode = "DRY RUN" if self.dry_run else "LIVE TRADING"
        logger.info(f"Multi-Stock Bot initialized - Symbols: {self.symbols}, Mode: {mode}")
        if self.strategy_type == "BREAKOUT":
            atr_status = f", ATR>{self.atr_min_threshold*100:.1f}%" if self.atr_filter else ""
            logger.info(f"Strategy: BREAKOUT (lookback={self.breakout_lookback}, threshold={self.breakout_threshold*100:.2f}%{atr_status})")
        else:
            logger.info(f"Strategy: MA({self.short_ma}/{self.long_ma}) threshold={self.ma_threshold*100:.1f}%, RSI({self.rsi_period})")

    def preload_historical_data(self):
        """Pre-load historical prices from IBKR so MAs have meaningful values at startup"""
        logger.info("Pre-loading historical data from IBKR...")

        for symbol, trader in self.traders.items():
            try:
                # Fetch daily bars from IBKR (3 months of data)
                bars = self.ib.reqHistoricalData(
                    trader.contract,
                    endDateTime='',
                    durationStr='3 M',
                    barSizeSetting='1 day',
                    whatToShow='TRADES',
                    useRTH=True,
                    formatDate=1
                )

                if bars and len(bars) >= self.long_ma:
                    # Add closing prices to strategy (take last long_ma * 2 for buffer)
                    prices_to_load = bars[-(self.long_ma * 2):]
                    for bar in prices_to_load:
                        trader.strategy.add_price(bar.close)

                    # Set last price from most recent bar
                    trader.last_price = bars[-1].close
                    trader.previous_close = bars[-2].close if len(bars) > 1 else bars[-1].close

                    logger.info(f"{symbol}: Loaded {len(prices_to_load)} historical prices from IBKR (latest: ${trader.last_price:.2f})")
                else:
                    logger.warning(f"{symbol}: Insufficient historical data ({len(bars) if bars else 0} bars)")

            except Exception as e:
                logger.error(f"{symbol}: Failed to load historical data: {e}")

        # Also preload regime detector data from IBKR
        if self.regime_detector:
            try:
                regime_contract = Stock(self.regime_index, 'SMART', 'USD')
                self.ib.qualifyContracts(regime_contract)
                bars = self.ib.reqHistoricalData(
                    regime_contract,
                    endDateTime='',
                    durationStr='3 M',
                    barSizeSetting='1 day',
                    whatToShow='TRADES',
                    useRTH=True,
                    formatDate=1
                )
                if bars and len(bars) >= self.regime_long_ma:
                    prices_to_load = bars[-(self.regime_long_ma * 2):]
                    for bar in prices_to_load:
                        self.regime_detector.update_price(bar.close)
                    regime = self.regime_detector.get_regime()
                    logger.info(f"Regime ({self.regime_index}): Loaded {len(prices_to_load)} historical prices from IBKR - Current: {regime}")
            except Exception as e:
                logger.error(f"Failed to load regime historical data: {e}")

    def connect(self):
        """Connect to Interactive Brokers and subscribe to market data"""
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            logger.info(f"Connected to IB Gateway at {self.host}:{self.port}")

            # Initialize trade verifier with IB connection
            trade_verifier.set_ib(self.ib)

            # Qualify contracts and subscribe to streaming market data
            for symbol, trader in self.traders.items():
                self.ib.qualifyContracts(trader.contract)
                logger.info(f"Contract qualified: {trader.contract}")

                # Subscribe to streaming market data
                ticker = self.ib.reqMktData(trader.contract, '', False, False)
                self.tickers[symbol] = ticker
                trader.ticker = ticker
                logger.info(f"Subscribed to market data: {symbol}")

            # Subscribe to regime index if enabled
            if self.regime_detector:
                regime_contract = Stock(self.regime_index, 'SMART', 'USD')
                self.ib.qualifyContracts(regime_contract)
                self.regime_ticker = self.ib.reqMktData(regime_contract, '', False, False)
                logger.info(f"Subscribed to regime index: {self.regime_index}")

            # Allow time for initial data to arrive
            self.ib.sleep(2)
            logger.info("IBKR streaming market data initialized")

            return True
        except Exception as e:
            logger.error(f"Failed to connect to IB: {e}")
            return False

    def disconnect(self):
        """Disconnect from IB and cancel market data subscriptions"""
        # Stop dashboard subprocess if running
        if hasattr(self, 'dashboard_process') and self.dashboard_process:
            try:
                self.dashboard_process.terminate()
                self.dashboard_process.wait(timeout=3)
                logger.info("Dashboard process stopped")
            except Exception:
                pass

        if self.ib.isConnected():
            # Cancel all market data subscriptions
            for symbol, ticker in self.tickers.items():
                try:
                    self.ib.cancelMktData(ticker.contract)
                except Exception:
                    pass
            if self.regime_ticker:
                try:
                    self.ib.cancelMktData(self.regime_ticker.contract)
                except Exception:
                    pass

            self.ib.disconnect()
            logger.info("Disconnected from IB")

    def is_market_open(self) -> bool:
        """Check if US stock market is currently open (cached for 30 seconds)"""
        import time as _time
        current_time = _time.time()

        # Return cached value if less than 30 seconds old
        if self._market_open_cache is not None and (current_time - self._market_open_cache_time) < 30:
            return self._market_open_cache

        from datetime import datetime
        import pytz

        eastern = pytz.timezone('US/Eastern')
        now = datetime.now(eastern)

        # Market closed on weekends
        if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
            self._market_open_cache = False
            self._market_open_cache_time = current_time
            return False

        # Market hours: 9:30 AM - 4:00 PM Eastern
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

        result = market_open <= now <= market_close
        self._market_open_cache = result
        self._market_open_cache_time = current_time
        return result

    def get_price(self, trader: StockTrader) -> float:
        """Get current price from IBKR streaming market data"""
        ticker = trader.ticker
        if not ticker:
            logger.warning(f"No ticker for {trader.symbol}")
            return trader.last_price if trader.last_price > 0 else None

        # Get the best available price from streaming data
        price = None

        # Prefer last traded price
        if ticker.last and not util.isNan(ticker.last) and ticker.last > 0:
            price = ticker.last
        # Fall back to mid price
        elif ticker.bid and ticker.ask and not util.isNan(ticker.bid) and not util.isNan(ticker.ask) and ticker.bid > 0:
            price = (ticker.bid + ticker.ask) / 2
        # Fall back to close price from ticker
        elif ticker.close and not util.isNan(ticker.close) and ticker.close > 0:
            price = ticker.close
        # Fall back to last known price (from historical preload)
        elif trader.last_price > 0:
            price = trader.last_price
            trader.data_source = 'IBKR_CACHED'
            return price

        if price and price > 0:
            trader.last_price = price
            trader.last_bid = ticker.bid if ticker.bid and not util.isNan(ticker.bid) and ticker.bid > 0 else price
            trader.last_ask = ticker.ask if ticker.ask and not util.isNan(ticker.ask) and ticker.ask > 0 else price
            trader.previous_close = ticker.close if ticker.close and not util.isNan(ticker.close) and ticker.close > 0 else trader.previous_close
            trader.data_source = 'IBKR'
            return price

        # Ultimate fallback to cached price
        if trader.last_price > 0:
            trader.data_source = 'IBKR_CACHED'
            return trader.last_price

        return None

    def get_position(self, trader: StockTrader) -> float:
        """Get current position for a stock"""
        positions = self.ib.positions()
        for pos in positions:
            if pos.contract.symbol == trader.symbol:
                return pos.position
        return 0

    def update_cash_balance(self):
        """Update available cash and net liquidation (cached, updated every 60s)"""
        current_time = time.time()
        if current_time - self.last_balance_check < 60:
            return  # Use cached values

        try:
            account_summary = self.ib.accountSummary()
            for item in account_summary:
                if item.tag == 'AvailableFunds':
                    self.available_cash_usd = float(item.value)
                elif item.tag == 'NetLiquidation':
                    self.net_liquidation_usd = float(item.value)

            self.last_balance_check = current_time
            logger.info(f"Cash updated: Available ${self.available_cash_usd:,.2f} | Net Liq ${self.net_liquidation_usd:,.2f}")
        except Exception as e:
            logger.error(f"Failed to update cash balance: {e}")

    def place_order(self, trader: StockTrader, action: str, quantity: int):
        """Place an order with verification"""
        price = trader.last_price

        # Check master trading control
        if not trading_control.is_enabled():
            trade_verifier.record_skipped(
                trader.symbol, action, quantity, price, "Trading disabled"
            )
            logger.info(f"[TRADING DISABLED] {action} {quantity} {trader.symbol} @ ${price:.2f} - Order skipped")
            return False

        # Market hours check removed - ATR filter handles low-volatility periods
        # Trading allowed 24/7, ATR >= 0.20% requirement filters out dead markets

        # Reset daily counters at start of new day
        today = datetime.now().date()
        if today != self.last_reset_date:
            self.daily_trades = 0
            self.daily_loss_usd = 0
            self.last_reset_date = today
            logger.info(f"[NEW DAY] Circuit breakers reset - Max trades: {self.max_trades_per_day}, Max loss: ${self.max_daily_loss_usd}")

        # Circuit breaker: Max trades per day
        if self.daily_trades >= self.max_trades_per_day:
            trade_verifier.record_skipped(
                trader.symbol, action, quantity, price, "Max daily trades reached"
            )
            logger.warning(f"[CIRCUIT BREAKER] Max daily trades ({self.max_trades_per_day}) reached - Trading halted")
            return False

        # Circuit breaker: Max daily loss
        if self.daily_loss_usd >= self.max_daily_loss_usd:
            trade_verifier.record_skipped(
                trader.symbol, action, quantity, price, "Max daily loss reached"
            )
            logger.warning(f"[CIRCUIT BREAKER] Max daily loss (${self.max_daily_loss_usd}) reached - Trading halted")
            return False

        # Check available cash for BUY orders (using cached balance)
        if action == 'BUY':
            order_cost = price * quantity
            # Reserve $1.50 per share for commission (IBKR charges ~$1 minimum)
            commission_buffer = max(quantity * 1.50, 2.00)
            total_cost = order_cost + commission_buffer

            if total_cost > self.available_cash_usd:
                trade_verifier.record_skipped(
                    trader.symbol, action, quantity, price, "Insufficient cash (incl. commission)"
                )
                logger.info(f"[INSUFFICIENT CASH] BUY {quantity} {trader.symbol} @ ${price:.2f} = ${order_cost:.2f} + commission ${commission_buffer:.2f} - Available: ${self.available_cash_usd:.2f}")
                return False

        # Data validation - check for bad prices
        if price <= 0 or price > 100000:
            trade_verifier.record_skipped(
                trader.symbol, action, quantity, price, "Invalid price"
            )
            logger.warning(f"[INVALID PRICE] {action} {quantity} {trader.symbol} @ ${price:.2f} - Order blocked")
            return False

        if quantity <= 0 or quantity > 10000:
            trade_verifier.record_skipped(
                trader.symbol, action, quantity, price, "Invalid quantity"
            )
            logger.warning(f"[INVALID QUANTITY] {action} {quantity} {trader.symbol} qty={quantity} - Order blocked")
            return False

        # Check for duplicate/pending orders for this symbol
        pending_orders = self.ib.openOrders()
        for pending in pending_orders:
            if (hasattr(pending.contract, 'symbol') and
                pending.contract.symbol == trader.symbol and
                pending.order.action == action):
                trade_verifier.record_skipped(
                    trader.symbol, action, quantity, price, "Duplicate order pending"
                )
                logger.info(f"[DUPLICATE ORDER] {action} {quantity} {trader.symbol} - Order already pending (ID: {pending.order.orderId})")
                return False

        if self.dry_run:
            trade_verifier.record_skipped(
                trader.symbol, action, quantity, price, "Dry run mode"
            )
            logger.info(f"[DRY RUN] {action} {quantity} {trader.symbol} @ ${price:.2f}")
            return True

        # Record trade attempt
        trade_id = trade_verifier.record_attempt(trader.symbol, action, quantity, price)

        try:
            # Dynamic order pricing based on signal strength and volatility
            # Calculate signal strength from MA distance
            if len(trader.strategy.prices) >= trader.strategy.long_window:
                short_ma = sum(trader.strategy.prices[-trader.strategy.short_window:]) / trader.strategy.short_window
                long_ma = sum(trader.strategy.prices[-trader.strategy.long_window:]) / trader.strategy.long_window
                signal_strength = abs(short_ma - long_ma) / long_ma
            else:
                signal_strength = 0.01  # Default for weak signal

            # Always pay premium to ensure fill
            if action == 'BUY':
                limit_price = round(price * 1.0002, 2)  # Pay 0.02% premium - ensure fill
            else:  # SELL
                limit_price = round(price * 0.9998, 2)  # Accept 0.02% discount - ensure fill

            order = LimitOrder(action, quantity, limit_price)
            ib_trade = self.ib.placeOrder(trader.contract, order)

            # Update trade record with order ID
            trade_verifier.update_order_id(trade_id, ib_trade.order.orderId)
            logger.info(f"Order placed: {action} {quantity} {trader.symbol} @ ${limit_price:.2f} (Trade ID: {trade_id})")

            # Increment daily trade counter
            self.daily_trades += 1

            # Track daily loss for SELL orders (approximate)
            if action == 'SELL' and trader.strategy.entry_price > 0:
                realized_pnl = (price - trader.strategy.entry_price) * quantity
                if realized_pnl < 0:
                    self.daily_loss_usd += abs(realized_pnl)
                    logger.info(f"[P&L TRACKING] Daily loss: ${self.daily_loss_usd:.2f} / ${self.max_daily_loss_usd} max")

            # Schedule verification after a short delay
            self._schedule_verification(trade_id, delay=2.0)

            return True
        except Exception as e:
            trade_verifier.update_status(trade_id, TradeStatus.FAILED, error_message=str(e))
            logger.error(f"Order failed for {trader.symbol}: {e}")
            return False

    def _schedule_verification(self, trade_id: str, delay: float = 2.0):
        """Schedule trade verification after delay"""
        def _verify():
            time.sleep(delay)
            success = trade_verifier.verify_trade(trade_id)
            if not success:
                logger.warning(f"Trade {trade_id} verification: Position not confirmed")

        thread = threading.Thread(target=_verify, daemon=True)
        thread.start()

    def collect_prices(self):
        """Collect prices from IBKR streaming data"""
        # Allow IB to process incoming data
        self.ib.sleep(0.1)

        collected = 0
        for symbol, trader in self.traders.items():
            price = self.get_price(trader)
            if price:
                trader.strategy.add_price(price)
                collected += 1
        if collected > 0:
            logger.info(f"Collected prices for {collected}/{len(self.traders)} stocks (IBKR)")

        # Update regime detector from IBKR streaming data
        if self.regime_detector and hasattr(self, 'regime_ticker') and self.regime_ticker:
            ticker = self.regime_ticker
            price = None
            if ticker.last and not util.isNan(ticker.last) and ticker.last > 0:
                price = ticker.last
            elif ticker.bid and ticker.ask and not util.isNan(ticker.bid) and not util.isNan(ticker.ask) and ticker.bid > 0:
                price = (ticker.bid + ticker.ask) / 2
            elif ticker.close and not util.isNan(ticker.close) and ticker.close > 0:
                price = ticker.close

            if price and price > 0:
                self.regime_detector.update_price(price)
                regime = self.regime_detector.get_regime()
                logger.info(f"Market Regime: {regime} ({self.regime_index}: ${price:.2f})")

    def update_stock_info(self):
        """Update intraday price history from IBKR for sparkline charts, events and news from YFinance"""
        current_time = time.time()
        intraday_updated = 0
        events_updated = 0
        news_updated = 0

        for symbol, trader in self.traders.items():
            # Update intraday prices every 10 minutes
            if current_time - trader.last_intraday_update >= 600:
                try:
                    # Fetch 1-day of 5-minute bars from IBKR
                    bars = self.ib.reqHistoricalData(
                        trader.contract,
                        endDateTime='',
                        durationStr='1 D',
                        barSizeSetting='5 mins',
                        whatToShow='TRADES',
                        useRTH=True,
                        formatDate=1
                    )
                    if bars:
                        trader.intraday_prices = [bar.close for bar in bars]
                        trader.last_intraday_update = current_time
                        intraday_updated += 1
                except Exception as e:
                    pass  # Silently skip failed updates

            # Update events (earnings, dividends) and news every 1 hour
            if current_time - trader.last_info_update >= 3600:  # 1 hour
                try:
                    # Fetch upcoming events
                    events = self.yfinance_client.get_upcoming_events(symbol)
                    trader.upcoming_events = events

                    # Fetch latest news with VADER sentiment
                    news = self.yfinance_client.get_news(symbol, limit=3)
                    trader.news = news

                    trader.last_info_update = current_time
                    if events:  # Only count if we got data
                        events_updated += 1
                    if news:
                        news_updated += 1
                except Exception as e:
                    pass  # Silently skip failed updates

        if intraday_updated > 0:
            logger.info(f"Updated intraday charts for {intraday_updated} stocks (IBKR)")
        if events_updated > 0:
            logger.info(f"Updated events for {events_updated} stocks (YFinance)")
        if news_updated > 0:
            logger.info(f"Updated news with VADER sentiment for {news_updated} stocks (YFinance)")

    def check_signals(self):
        """Check trading signals for all stocks with regime awareness and alpha engine"""
        # Get current market regime
        regime = 'UNKNOWN'
        if self.regime_detector:
            regime = self.regime_detector.get_regime()

        for symbol, trader in self.traders.items():
            if not self.ib.isConnected():
                logger.warning("Not connected to IB")
                continue

            # Check minimum data requirement (depends on strategy type)
            if trader.strategy_type == "BREAKOUT":
                min_data = trader.strategy.lookback_periods
            else:
                min_data = trader.strategy.long_window

            if len(trader.strategy.prices) < min_data:
                logger.info(f"{symbol}: Collecting data ({len(trader.strategy.prices)}/{min_data})")
                continue

            trader.position = self.get_position(trader)
            stock_signal = trader.strategy.get_signal()

            # Apply regime-aware logic if enabled
            if self.adaptive_strategy and regime != 'UNKNOWN':
                regime_action = self.adaptive_strategy.get_action(symbol, stock_signal, int(trader.position))
            else:
                regime_action = stock_signal

            # Apply alpha engine for BREAKOUT strategy
            action = regime_action
            alpha_score = 0.0
            alpha_signal = 'N/A'

            if alpha_engine.enabled and trader.strategy_type == "BREAKOUT":
                # Get RSI and ATR for alpha context
                rsi = 50.0
                if hasattr(trader.strategy, 'get_current_rsi'):
                    rsi = trader.strategy.get_current_rsi()
                atr_pct = trader.strategy.get_atr_percent()

                # Build alpha context and compute score
                alpha_context = trader._build_alpha_context(rsi, atr_pct, regime)
                alpha_result = alpha_engine.compute_alpha(alpha_context)
                alpha_score = alpha_result['score']
                alpha_signal = alpha_result['signal']

                # Get final action from alpha engine
                action = alpha_engine.get_action_for_signal(alpha_result, regime_action, int(trader.position))

                logger.info(f"{symbol}: ${trader.last_price:.2f} | Pos: {trader.position} | Signal: {stock_signal} | Alpha: {alpha_score:+.2f} ({alpha_signal}) | Regime: {regime} | Action: {action}")
            else:
                logger.info(f"{symbol}: ${trader.last_price:.2f} | Pos: {trader.position} | Signal: {stock_signal} | Regime: {regime} | Action: {action}")

            # Sync strategy state with actual position
            if trader.position > 0 and not trader.strategy.in_position:
                trader.strategy.enter_position(trader.last_price)
            elif trader.position == 0 and trader.strategy.in_position:
                trader.strategy.exit_position("Closed externally")

            # Execute trades based on alpha-aware action
            if action == 'BUY' and trader.position == 0:
                if alpha_engine.enabled:
                    logger.info(f"{symbol}: BUY SIGNAL [Alpha: {alpha_score:+.2f}, {regime}] - Opening position")
                else:
                    logger.info(f"{symbol}: BUY SIGNAL [{regime}] - Opening position")
                if self.place_order(trader, 'BUY', trader.position_size):
                    trader.strategy.enter_position(trader.last_price)

            elif action == 'SELL' and trader.position > 0:
                sell_qty = min(int(trader.position), trader.position_size)
                if alpha_engine.enabled:
                    logger.info(f"{symbol}: SELL SIGNAL [Alpha: {alpha_score:+.2f}, {regime}] - Closing position")
                else:
                    logger.info(f"{symbol}: SELL SIGNAL [{regime}] - Closing position")
                if self.place_order(trader, 'SELL', sell_qty):
                    exit_reason = "Breakout breakdown" if trader.strategy_type == "BREAKOUT" else "MA crossover"
                    trader.strategy.exit_position(f"{exit_reason} ({regime} market)")

            elif regime_action == 'BUY' and action == 'HOLD' and trader.position == 0:
                logger.info(f"{symbol}: BUY blocked - Alpha {alpha_score:+.2f} < {alpha_engine.threshold}")

            elif stock_signal == 'SELL' and action == 'HOLD' and trader.position > 0:
                logger.info(f"{symbol}: SELL signal IGNORED - BULL market, holding position")

    def update_dashboard(self):
        """Update dashboard with all stock states (lightweight for performance)"""
        states = []
        for symbol, trader in self.traders.items():
            states.append(trader.get_state(lightweight=True))  # Skip chart data for WebSocket

        # Include regime state
        regime_state = None
        if self.regime_detector:
            regime_state = self.regime_detector.get_state()

        state_data = {
            'multi_stock': True,
            'stocks': states,
            'is_connected': self.ib.isConnected(),
            'dry_run': self.dry_run,
            'last_update': datetime.now().isoformat(),
            'regime_aware': self.regime_enabled,
            'regime': regime_state,
            'market_open': self.is_market_open(),
            'trading': trade_verifier.get_state(),
            'trading_control': trading_control.get_state(),
            'net_liquidation_dkk': round(self.net_liquidation_usd, 2),  # IB values are already in DKK
            'excess_liquidity_dkk': round(self.available_cash_usd, 2),  # IB values are already in DKK
            'available_cash_usd': round(self.available_cash_usd, 2),
            'strategy_type': self.strategy_type,
            'data_requirement': self.breakout_lookback if self.strategy_type == "BREAKOUT" else self.long_ma,
            'alpha_engine_enabled': alpha_engine.enabled,
            'alpha_threshold': alpha_engine.threshold if alpha_engine.enabled else 0.30
        }

        # Update in-memory state (for backward compat)
        bot_state.update(**state_data)

        # Also write to file for separate dashboard process
        try:
            import json
            state_file = os.path.join(os.path.dirname(__file__), 'data', 'bot_state.json')
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            # Direct write (simpler, avoids Windows file locking issues with rename)
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f)
        except Exception as e:
            logger.error(f"Failed to write state file: {e}")

    def start(self):
        """Start the trading bot"""
        logger.info("Starting Multi-Stock Trading Bot...")
        logger.info(f"Trading: {', '.join(self.symbols)}")

        # Force trading to start disabled for safety - must be enabled from dashboard
        trading_control.disable(by="bot_startup")
        logger.info("Trading control: DISABLED (must enable from dashboard)")

        if not self.dry_run:
            logger.warning("LIVE TRADING MODE - Real money will be used!")
            logger.warning("Press Ctrl+C within 5 seconds to abort...")
            time.sleep(5)

        if not self.connect():
            logger.error("Failed to connect. Exiting.")
            return

        # Pre-load historical data so MAs are ready immediately
        self.preload_historical_data()

        # Initial cash balance check
        self.update_cash_balance()

        # Start dashboard as subprocess (separate process for better responsiveness)
        if self.enable_dashboard:
            import sys
            # Use -m to run as module so imports work correctly
            self.dashboard_process = subprocess.Popen(
                [sys.executable, '-m', 'src.multi_dashboard'],
                cwd=os.path.dirname(__file__)
            )
            time.sleep(1)  # Give dashboard time to start
            logger.info(f"Dashboard started at http://localhost:{self.dashboard_port} (PID: {self.dashboard_process.pid})")

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

                # Update cash balance (every 60 seconds)
                self.update_cash_balance()

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
