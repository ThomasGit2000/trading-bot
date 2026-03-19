"""
Multi-Stock Trading Bot with NO STOPS Strategy
Trades multiple symbols simultaneously using MA crossover signals.
Supports categorized stock universe for organized trading.
"""
import os
import sys
import csv
import json
import time
import logging
import threading
import subprocess
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from dotenv import load_dotenv

# Load .env BEFORE importing modules that read environment variables
load_dotenv()

from ib_insync import IB, Stock, LimitOrder, util
from src.strategy import SimpleStrategy, BreakoutStrategy
from src.scalp_ml_strategy import ScalpMLStrategy
from src.dashboard_state import bot_state
from src.regime_detector import RegimeDetector, AdaptiveStrategy
from src.trade_verifier import trade_verifier, TradeStatus
from src.trading_control import trading_control
from src.yfinance_client import YFinanceClient
from src.alpha_engine import alpha_engine, AlphaContext
from src.health_monitor import health_monitor
from src.activity_logger import activity_logger
from src.tick_scalper import tick_scalper
from src.market_state import market_engine
from src.selective_rsi_strategy import SelectiveRSIStrategy, SelectiveRSIConfig

# Import stock universe for category support
try:
    from stock_universe import (
        STOCK_CATEGORIES,
        get_all_symbols,
        get_symbols_by_category,
        get_symbol_category,
        get_position_size,
        generate_position_sizes_json,
        SYMBOL_POSITION_OVERRIDES
    )
    UNIVERSE_AVAILABLE = True
except ImportError:
    UNIVERSE_AVAILABLE = False
    SYMBOL_POSITION_OVERRIDES = {}

# Position value limits in USD
MIN_POSITION_VALUE_USD = float(os.getenv('MIN_POSITION_VALUE_USD', '900'))
MAX_POSITION_VALUE_USD = float(os.getenv('MAX_POSITION_VALUE_USD', '1500'))
MAX_SPREAD_PCT = float(os.getenv('MAX_SPREAD_PCT', '0.15'))  # Max bid-ask spread %

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


# ============================================================================
# MULTIPROCESSING WORKER FUNCTIONS (must be module-level for pickle)
# ============================================================================

def _compute_alpha_worker(args):
    """
    Worker function for parallel alpha computation.
    Runs in separate process to utilize multiple CPU cores.

    Args: tuple of (symbol, alpha_context_dict, strategy_signal, position, regime)
    Returns: tuple of (symbol, alpha_score, action)
    """
    symbol, context_dict, strategy_signal, position, regime = args
    try:
        # Import here to ensure fresh module load in worker process
        from src.alpha_engine import alpha_engine, AlphaContext

        # Reconstruct context
        context = AlphaContext(**context_dict)

        # Compute alpha
        result = alpha_engine.compute_alpha(context)
        alpha_score = result['score']

        # Get action (pass symbol for tick confirmation tracking)
        action = alpha_engine.get_action_for_signal(result, strategy_signal, position, symbol)

        return (symbol, alpha_score, action)
    except Exception as e:
        # Return HOLD on error
        return (symbol, 0.0, 'HOLD')


class StockTrader:
    """Manages trading for a single stock"""

    def __init__(self, symbol: str, position_size: int, short_ma: int, long_ma: int, threshold: float = 0.003, category: str = "UNCATEGORIZED", volume_filter: bool = False, rsi_period: int = 14, strategy_type: str = "MA_CROSSOVER", breakout_lookback: int = 60, breakout_threshold: float = 0.005, stop_loss_pct: float = 0.05, trailing_stop_pct: float = 0.03, atr_filter: bool = False, atr_min_threshold: float = 0.003, atr_period: int = 300):
        self.symbol = symbol
        self.position_size = position_size
        self.category = category
        self.threshold = threshold
        self.strategy_type = strategy_type

        if strategy_type == "SCALP_ML":
            self.strategy = ScalpMLStrategy(
                model_path=os.getenv('SCALP_MODEL_PATH', 'models/scalp_lgbm_v1.txt'),
                entry_threshold=float(os.getenv('SCALP_ENTRY_THRESHOLD', 0.0004)),
                take_profit=float(os.getenv('SCALP_TAKE_PROFIT', 0.0007)),
                stop_loss=float(os.getenv('SCALP_STOP_LOSS', 0.0004)),
                max_hold_seconds=int(os.getenv('SCALP_MAX_HOLD_SEC', 60))
            )
        elif strategy_type == "SCALP_TICK":
            # Tick scalper uses tick_scalper singleton, no separate strategy object
            # Use a simple breakout strategy as placeholder for warmup/data collection
            self.strategy = BreakoutStrategy(
                lookback_periods=20,  # Minimal lookback for warmup
                breakout_threshold=0.01,  # Won't be used
                stop_loss_pct=0.001,
                trailing_stop_pct=0.001
            )
            self.warmup_required = 25  # Quick warmup for scalping
        elif strategy_type == "BREAKOUT":
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
        elif strategy_type == "SELECTIVE_RSI":
            # Use shared SelectiveRSIStrategy - actual strategy handled by MultiStockBot
            # Use breakout strategy as placeholder for price collection
            self.strategy = BreakoutStrategy(
                lookback_periods=50,
                breakout_threshold=0.01,
                stop_loss_pct=stop_loss_pct,
                trailing_stop_pct=trailing_stop_pct
            )
            self.warmup_required = 50  # Need enough data for RSI
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

        # Track real-time ticks separately from preloaded historical data
        # This ensures we have fresh intraday data before trading
        self.realtime_ticks = 0
        self.warmup_required = breakout_lookback if strategy_type == "BREAKOUT" else long_ma
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
        # Beta vs MSCI World (URTH)
        self.beta = None
        # Analyst ratings (Buy/Hold/Sell)
        self.analyst_ratings = None

    def get_state(self, lightweight: bool = False, regime: str = "UNKNOWN") -> dict:
        """Get current state for dashboard. Use lightweight=True for WebSocket updates."""
        short_ma = 0
        long_ma = 0
        signal = "WAIT"
        signal_strength = 0
        rsi = 50  # Default RSI

        if self.strategy_type == "BREAKOUT" or self.strategy_type == "SCALP_TICK":
            # Breakout or Scalp Tick strategy
            if len(self.strategy.prices) >= self.strategy.lookback_periods:
                signal = self.strategy.get_signal()
                signal_strength = self.strategy.get_signal_strength()
                range_high, range_low = self.strategy.get_range()
                short_ma = range_high or 0  # Show range high as "short_ma"
                long_ma = range_low or 0    # Show range low as "long_ma"
            # Get RSI for breakout strategy too
            if hasattr(self.strategy, 'get_current_rsi'):
                rsi = self.strategy.get_current_rsi()
        elif self.strategy_type == "SELECTIVE_RSI":
            # SELECTIVE_RSI: RSI is calculated by the shared SelectiveRSIStrategy in MultiStockBot
            # Signal and RSI will be populated by the bot when it adds selective_rsi indicators
            # For now, get basic RSI from the placeholder strategy if available
            if hasattr(self.strategy, 'get_current_rsi'):
                rsi = self.strategy.get_current_rsi()
        elif self.strategy_type == "MA_CROSSOVER":
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

        if self.strategy_type == "BREAKOUT" or self.strategy_type == "SCALP_TICK":
            # Check ATR filter for breakout/scalp strategy
            raw_atr = self.strategy.get_atr_percent()
            atr_pct = raw_atr  # Store as decimal (0.02 = 2%)
            if hasattr(self.strategy, 'atr_filter') and self.strategy.atr_filter:
                atr_ok = atr_pct >= self.strategy.atr_min_threshold  # Compare decimals
            # Check stop-out status
            if signal == 'STOP_LOSS':
                stop_out = 'LOSS'
            elif signal == 'TRAILING_STOP':
                stop_out = 'TRAIL'
        elif self.strategy_type == "MA_CROSSOVER":
            # Check volume filter for MA strategy
            if hasattr(self.strategy, 'volume_confirm_threshold') and self.strategy.volume_confirm_threshold > 0:
                vol_ok = self.strategy.check_volume_confirmation()
            if signal == 'STOP_LOSS':
                stop_out = 'LOSS'
            elif signal == 'TRAILING_STOP':
                stop_out = 'TRAIL'

        # Compute alpha score and components if enabled
        alpha_score = 0.0
        alpha_components = {}
        if alpha_engine.enabled and self.strategy_type == "BREAKOUT":
            alpha_context = self._build_alpha_context(rsi, atr_pct, regime)
            alpha_result = alpha_engine.compute_alpha(alpha_context)
            alpha_score = alpha_result['score']
            # Extract individual component values for dashboard
            for comp in alpha_result.get('components', []):
                alpha_components[comp.name.lower()] = round(comp.value, 2)

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
            'realtime_ticks': self.realtime_ticks,
            'warmup_required': self.warmup_required,
            'warmup_complete': self.realtime_ticks >= self.warmup_required,
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
            'alpha_components': alpha_components,  # Individual signal values
            'regime': regime,  # Market regime
            'beta': self.beta,  # Beta vs MSCI World (URTH)
            'analyst_ratings': self.analyst_ratings,  # Buy/Hold/Sell counts
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

        # Selective RSI Strategy (shared across all symbols)
        if self.strategy_type == "SELECTIVE_RSI":
            self.selective_rsi = SelectiveRSIStrategy(SelectiveRSIConfig(
                rsi_period=int(os.getenv('SELECTIVE_RSI_PERIOD', '14')),
                rsi_oversold=float(os.getenv('SELECTIVE_RSI_OVERSOLD', '25')),
                rsi_overbought=float(os.getenv('SELECTIVE_RSI_OVERBOUGHT', '70')),
                volume_multiplier=float(os.getenv('SELECTIVE_VOLUME_MULT', '1.0')),
                atr_min_pct=float(os.getenv('SELECTIVE_ATR_MIN', '0.01')),
                stop_loss_pct=float(os.getenv('SELECTIVE_STOP_LOSS', '0.08')),
                profit_target_pct=float(os.getenv('SELECTIVE_PROFIT_TARGET', '0.12')),
                max_positions=int(os.getenv('SELECTIVE_MAX_POSITIONS', '5'))
            ))
            self.selective_positions = {}  # symbol -> {'entry': price, 'shares': int}
            logger.info(f"Selective RSI Strategy: RSI<{self.selective_rsi.config.rsi_oversold}, "
                       f"Vol>{self.selective_rsi.config.volume_multiplier}x, "
                       f"Target {self.selective_rsi.config.profit_target_pct*100:.0f}%, "
                       f"Stop {self.selective_rsi.config.stop_loss_pct*100:.0f}%")
        else:
            self.selective_rsi = None
            self.selective_positions = {}

        # Bot settings
        self.dry_run = os.getenv('DRY_RUN', 'true').lower() == 'true'
        self.price_interval = float(os.getenv('PRICE_INTERVAL_SEC', '5'))
        self.trade_interval = int(os.getenv('TRADE_INTERVAL_SEC', '60'))
        self.tick_mode = os.getenv('TICK_MODE', 'false').lower() == 'true'
        self.trade_cooldown_sec = int(os.getenv('TRADE_COOLDOWN_SEC', '60'))  # Min seconds between trades per stock
        self.symbol_last_trade = {}  # symbol -> timestamp of last trade (for cooldown)
        self.signal_throttle_sec = float(os.getenv('SIGNAL_THROTTLE_SEC', '0.1'))  # Min seconds between signal checks per stock
        self.symbol_last_signal_check = {}  # symbol -> timestamp of last signal check

        # Multi-core processing for parallel alpha computation
        self.parallel_workers = int(os.getenv('PARALLEL_WORKERS', str(multiprocessing.cpu_count())))
        self.use_multiprocessing = os.getenv('USE_MULTIPROCESSING', 'true').lower() == 'true'
        self.process_pool = None  # Initialized in connect() after fork safety
        self.pending_signal_batch = []  # Batch of signals to process in parallel

        # Dashboard
        self.enable_dashboard = os.getenv('ENABLE_DASHBOARD', 'true').lower() == 'true'
        self.dashboard_port = int(os.getenv('DASHBOARD_PORT', '8080'))

        # Tick data collection (for ML training)
        self.collect_tick_data = os.getenv('COLLECT_TICK_DATA', 'false').lower() == 'true'
        self.tick_data_dir = os.path.join(os.path.dirname(__file__), 'data', 'ticks')
        self.tick_writers = {}  # symbol -> csv.writer
        self.tick_files = {}   # symbol -> file handle
        self.tick_counts = {}  # symbol -> count
        self.last_tick_flush = 0

        # IBKR streaming market data
        self.tickers = {}  # symbol -> Ticker object
        self.regime_ticker = None  # Ticker for regime index (SPY)

        # Order tracking for timeout cancellation
        self.pending_orders = {}  # order_id -> {'symbol': str, 'time': float, 'trade': Trade}
        self.order_timeout_seconds = 30  # Cancel unfilled orders after 30 seconds

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

        # Set up market state engine with regime detector
        if self.regime_detector:
            market_engine.set_regime_detector(self.regime_detector)
        market_engine.set_yf_client(self.yfinance_client)

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
        elif self.strategy_type == "SCALP_TICK":
            logger.info(f"Strategy: SCALP_TICK (entry={os.getenv('SCALP_ENTRY_PCT', '0.15')}%, target={os.getenv('SCALP_TARGET_PCT', '0.08')}%, stop={os.getenv('SCALP_STOP_PCT', '0.10')}%)")
        elif self.strategy_type == "SCALP_ML":
            logger.info(f"Strategy: SCALP_ML (model={os.getenv('SCALP_MODEL_PATH', 'models/scalp_lgbm_v1.txt')})")
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

                    # Also load into SelectiveRSI strategy (uses add_historical_bar for direct loading)
                    if self.selective_rsi:
                        for bar in prices_to_load:
                            self.selective_rsi.add_historical_bar(
                                symbol, bar.close, bar.high, bar.low, bar.volume
                            )

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

    def adjust_position_sizes_for_value_limits(self):
        """Adjust position sizes to meet min/max USD value requirements"""
        logger.info(f"Adjusting position sizes for ${MIN_POSITION_VALUE_USD:.0f}-${MAX_POSITION_VALUE_USD:.0f} range...")
        adjusted = 0

        for symbol, trader in self.traders.items():
            if trader.position_size == 0:
                continue  # Skip monitor-only stocks

            price = trader.last_price
            if price <= 0:
                continue

            # Check if symbol has explicit override - respect it
            if UNIVERSE_AVAILABLE and symbol in SYMBOL_POSITION_OVERRIDES:
                override_size = SYMBOL_POSITION_OVERRIDES[symbol]
                if trader.position_size != override_size:
                    old_size = trader.position_size
                    trader.position_size = override_size
                    adjusted += 1
                    logger.info(f"{symbol}: Override {old_size} -> {override_size} shares (explicit limit)")
                continue

            current_value = trader.position_size * price

            # Check if exceeds max (1/5 rule)
            if current_value > MAX_POSITION_VALUE_USD:
                max_shares = int(MAX_POSITION_VALUE_USD / price)
                if max_shares < 1:
                    max_shares = 1  # At least 1 share
                old_size = trader.position_size
                trader.position_size = max_shares
                adjusted += 1
                logger.info(f"{symbol}: Reduced {old_size} -> {max_shares} shares (${price:.2f} x {max_shares} = ${max_shares * price:.0f}) - MAX limit")
            # Check if below min
            elif current_value < MIN_POSITION_VALUE_USD:
                min_shares = int(MIN_POSITION_VALUE_USD / price) + 1
                # But cap at max
                if min_shares * price > MAX_POSITION_VALUE_USD:
                    min_shares = int(MAX_POSITION_VALUE_USD / price)
                old_size = trader.position_size
                trader.position_size = min_shares
                adjusted += 1
                logger.info(f"{symbol}: Increased {old_size} -> {min_shares} shares (${price:.2f} x {min_shares} = ${min_shares * price:.0f}) - MIN limit")

        if adjusted > 0:
            logger.info(f"Adjusted {adjusted} position sizes to meet ${MIN_POSITION_VALUE_USD:.0f}-${MAX_POSITION_VALUE_USD:.0f} range")
        else:
            logger.info(f"All position sizes already within ${MIN_POSITION_VALUE_USD:.0f}-${MAX_POSITION_VALUE_USD:.0f} range")

    def init_tick_collection(self):
        """Initialize tick data CSV files for ML training"""
        if not self.collect_tick_data:
            return

        os.makedirs(self.tick_data_dir, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")

        for symbol in self.symbols:
            filepath = os.path.join(self.tick_data_dir, f'{symbol}_{date_str}.csv')
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

            self.tick_files[symbol] = f
            self.tick_writers[symbol] = writer
            self.tick_counts[symbol] = 0

        logger.info(f"Tick data collection ENABLED for {len(self.symbols)} symbols -> {self.tick_data_dir}")

    def close_tick_files(self):
        """Close all tick data CSV files"""
        for symbol, f in self.tick_files.items():
            try:
                f.close()
                logger.info(f"Saved tick data: {symbol} ({self.tick_counts.get(symbol, 0):,} ticks)")
            except Exception:
                pass
        self.tick_files = {}
        self.tick_writers = {}

    def cancel_stale_orders(self):
        """Cancel any open orders from previous sessions to start fresh"""
        try:
            open_orders = self.ib.openOrders()
            if not open_orders:
                logger.info("No stale orders to cancel")
                return

            cancelled_count = 0
            for order in open_orders:
                try:
                    # Get the trade object for this order
                    trades = [t for t in self.ib.openTrades() if t.order.orderId == order.orderId]
                    if trades:
                        trade = trades[0]
                        symbol = trade.contract.symbol
                        self.ib.cancelOrder(order)
                        logger.warning(f"[STARTUP] Cancelled stale order: {order.action} {order.totalQuantity} {symbol} @ ${order.lmtPrice:.2f}")
                        activity_logger.log_order_cancelled(symbol, order.action, int(order.totalQuantity), "Stale order from previous session", order.orderId)
                        cancelled_count += 1
                except Exception as e:
                    logger.error(f"Failed to cancel order {order.orderId}: {e}")

            if cancelled_count > 0:
                logger.info(f"[STARTUP] Cancelled {cancelled_count} stale orders")
                self.ib.sleep(1)  # Allow cancellations to process

        except Exception as e:
            logger.error(f"Error checking for stale orders: {e}")

    def cancel_timed_out_orders(self):
        """Cancel any orders that haven't filled within the timeout period"""
        if not self.pending_orders:
            return

        current_time = time.time()
        orders_to_remove = []

        for order_id, order_info in self.pending_orders.items():
            age = current_time - order_info['time']
            if age > self.order_timeout_seconds:
                try:
                    trade = order_info['trade']
                    # Check if order is still active
                    if trade.orderStatus.status in ['PreSubmitted', 'Submitted', 'PendingSubmit']:
                        self.ib.cancelOrder(trade.order)
                        logger.warning(f"[TIMEOUT] Cancelled unfilled order after {age:.0f}s: {trade.order.action} {trade.order.totalQuantity} {order_info['symbol']} @ ${trade.order.lmtPrice:.2f}")
                        activity_logger.log_order_cancelled(
                            order_info['symbol'],
                            trade.order.action,
                            int(trade.order.totalQuantity),
                            f"Timeout after {self.order_timeout_seconds}s",
                            order_id
                        )
                        # Restore reserved cash for cancelled BUY orders
                        if trade.order.action == 'BUY':
                            qty = float(trade.order.totalQuantity)
                            price = float(trade.order.lmtPrice)
                            restored = price * qty + max(qty * 1.50, 2.00)
                            self.available_cash_usd += restored
                            logger.debug(f"Restored ${restored:.2f} from cancelled {order_info['symbol']} order")
                    orders_to_remove.append(order_id)
                except Exception as e:
                    logger.error(f"Failed to cancel timed out order {order_id}: {e}")
                    orders_to_remove.append(order_id)

        # Also check for filled/cancelled orders to clean up
        for order_id, order_info in self.pending_orders.items():
            if order_id not in orders_to_remove:
                trade = order_info['trade']
                if trade.orderStatus.status in ['Filled', 'Cancelled', 'Inactive']:
                    # Restore cash for BUY orders that were cancelled/rejected (not filled)
                    if trade.order.action == 'BUY' and trade.orderStatus.status in ['Cancelled', 'Inactive']:
                        qty = float(trade.order.totalQuantity)
                        price = float(trade.order.lmtPrice)
                        restored = price * qty + max(qty * 1.50, 2.00)
                        self.available_cash_usd += restored
                        logger.debug(f"Restored ${restored:.2f} from {trade.orderStatus.status} {order_info['symbol']} order")
                    orders_to_remove.append(order_id)

        # Remove processed orders
        for order_id in orders_to_remove:
            del self.pending_orders[order_id]

    def connect(self):
        """Connect to Interactive Brokers and subscribe to market data"""
        try:
            # Initialize ProcessPoolExecutor for multi-core signal processing
            if self.use_multiprocessing and self.tick_mode:
                self.process_pool = ProcessPoolExecutor(max_workers=self.parallel_workers)
                logger.info(f"MULTI-CORE ENABLED: ProcessPoolExecutor with {self.parallel_workers} workers")

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

            # Subscribe to tick events for per-tick processing
            if self.tick_mode:
                self.ib.pendingTickersEvent += self.on_pending_tickers
                logger.info("TICK MODE ENABLED: Processing every tick in real-time")

            # Allow time for initial data to arrive
            self.ib.sleep(2)
            logger.info("IBKR streaming market data initialized")

            # Cancel any stale orders from previous sessions
            self.cancel_stale_orders()

            # Initialize tick data collection if enabled
            self.init_tick_collection()

            return True
        except Exception as e:
            logger.error(f"Failed to connect to IB: {e}")
            return False

    def disconnect(self):
        """Disconnect from IB and cancel market data subscriptions"""
        # Shutdown process pool if running
        if self.process_pool:
            self.process_pool.shutdown(wait=False)
            logger.info("ProcessPoolExecutor shutdown")

        # Close tick data files if collecting
        self.close_tick_files()

        # Stop tick data collector if running
        if hasattr(self, 'collector_process') and self.collector_process:
            try:
                self.collector_process.terminate()
                self.collector_process.wait(timeout=3)
                logger.info("Tick data collector stopped")
                # Remove PID file
                pid_file = os.path.join(os.path.dirname(__file__), 'data', 'collector_pid.txt')
                if os.path.exists(pid_file):
                    os.remove(pid_file)
            except Exception:
                pass

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

    def on_pending_tickers(self, tickers):
        """Process incoming ticks in real-time (called per-tick when TICK_MODE enabled)

        Multi-core optimization: Batches alpha computations and processes them
        in parallel across multiple CPU cores using ProcessPoolExecutor.
        """
        stocks_to_evaluate = []  # Collect stocks that need signal evaluation
        current_time = time.time()

        # Phase 1: Update all trader states (sequential, fast)
        for ticker in tickers:
            symbol = ticker.contract.symbol
            if symbol not in self.traders:
                # Could be regime ticker (SPY)
                if self.regime_detector and symbol == self.regime_index:
                    price = self._extract_price_from_ticker(ticker)
                    if price:
                        self.regime_detector.update_price(price)
                continue

            trader = self.traders[symbol]
            price = self._extract_price_from_ticker(ticker)
            if not price:
                continue

            # Update trader state
            trader.last_price = price
            trader.last_bid = ticker.bid if ticker.bid and not util.isNan(ticker.bid) and ticker.bid > 0 else price
            trader.last_ask = ticker.ask if ticker.ask and not util.isNan(ticker.ask) and ticker.ask > 0 else price
            trader.data_source = 'IBKR'

            # Track price update for health monitoring (prevents false stale data warnings)
            self.last_price_update = current_time
            self.consecutive_stale_count = 0
            self.stale_data_warned = False

            # Get volume/bid/ask size for strategy
            volume = 0
            bid_size = 100
            ask_size = 100
            if ticker.lastSize and not util.isNan(ticker.lastSize):
                volume = ticker.lastSize
            if ticker.bidSize and not util.isNan(ticker.bidSize):
                bid_size = ticker.bidSize
            if ticker.askSize and not util.isNan(ticker.askSize):
                ask_size = ticker.askSize

            # Add price to strategy
            if trader.strategy_type == "SCALP_ML":
                trader.strategy.add_tick(
                    price=price, volume=volume,
                    bid=trader.last_bid, ask=trader.last_ask,
                    bid_size=bid_size, ask_size=ask_size
                )
            elif trader.strategy_type == "SELECTIVE_RSI":
                # Add bar to shared selective RSI strategy
                if self.selective_rsi:
                    high = ticker.high if ticker.high and not util.isNan(ticker.high) else price
                    low = ticker.low if ticker.low and not util.isNan(ticker.low) else price
                    self.selective_rsi.add_bar(symbol, price, high, low, volume)
                    # Update today's cumulative volume from IBKR (for rel_vol calculation)
                    if ticker.volume and not util.isNan(ticker.volume) and ticker.volume > 0:
                        self.selective_rsi.update_today_volume(symbol, ticker.volume)
                trader.strategy.add_price(price)
            elif trader.strategy_type == "SCALP_TICK":
                # Tick scalper processes every tick directly
                if tick_scalper.enabled:
                    result = tick_scalper.on_tick(symbol, price, volume)

                    # Execute scalp trades immediately (no batching)
                    if result['action'] == 'BUY' and trader.position == 0:
                        trader.position = self.get_position(trader)
                        if trader.position == 0 and self._should_evaluate_signal(trader, current_time):
                            logger.info(f"[SCALP] {symbol}: BUY @ ${price:.2f} | {result['reason']}")
                            if self.place_order(trader, 'BUY', trader.position_size):
                                tick_scalper.enter_position(symbol, price, trader.position_size)
                                self.symbol_last_trade[symbol] = current_time

                    elif result['action'] == 'SELL':
                        # Position was already cleared by on_tick(), use result or check IBKR position
                        trader.position = self.get_position(trader)
                        if trader.position > 0:
                            sell_qty = int(trader.position)  # Sell entire position on stop
                            logger.info(f"[SCALP] {symbol}: SELL @ ${price:.2f} | {result['reason']} | P&L: {result.get('pnl_pct', 0)*100:+.2f}%")
                            if self.place_order(trader, 'SELL', sell_qty):
                                self.symbol_last_trade[symbol] = current_time

                    trader.realtime_ticks += 1
                    continue  # Skip normal signal evaluation for scalp
            else:
                trader.strategy.add_price(price)

            trader.realtime_ticks += 1

            # Check if this stock needs signal evaluation (skip for SCALP_TICK)
            if trader.strategy_type != "SCALP_TICK" and trader.realtime_ticks >= trader.warmup_required:
                # Apply filters before adding to batch
                if self._should_evaluate_signal(trader, current_time):
                    stocks_to_evaluate.append(trader)

        # Phase 2: Process signals (parallel or sequential)
        if stocks_to_evaluate:
            if self.process_pool and self.use_multiprocessing and len(stocks_to_evaluate) > 1:
                self._evaluate_signals_parallel(stocks_to_evaluate, current_time)
            else:
                # Sequential fallback
                for trader in stocks_to_evaluate:
                    self._check_signal_for_stock(trader)

    def _should_evaluate_signal(self, trader, current_time: float) -> bool:
        """Check if a stock should be evaluated for signals (pre-filters)"""
        symbol = trader.symbol

        # Skip if market is closed
        if not self.is_market_open():
            return False

        # Skip if we have a pending order
        if self._has_pending_order(symbol):
            return False

        # Signal throttle check
        last_check = self.symbol_last_signal_check.get(symbol, 0)
        if current_time - last_check < self.signal_throttle_sec:
            return False

        # Trade cooldown check
        last_trade = self.symbol_last_trade.get(symbol, 0)
        if current_time - last_trade < self.trade_cooldown_sec:
            return False

        # Not connected check
        if not self.ib.isConnected():
            return False

        # Minimum data requirement
        if trader.strategy_type in ("BREAKOUT", "SCALP_TICK", "SELECTIVE_RSI"):
            min_data = trader.strategy.lookback_periods
        else:
            min_data = trader.strategy.long_window
        if len(trader.strategy.prices) < min_data:
            return False

        return True

    def _evaluate_signals_parallel(self, traders: list, current_time: float):
        """
        Evaluate signals for multiple stocks in parallel using ProcessPoolExecutor.
        Utilizes multiple CPU cores for alpha computation.
        """
        # Get regime once (shared across all stocks)
        regime = 'UNKNOWN'
        if self.regime_detector:
            regime = self.regime_detector.get_regime()

        # Prepare batch of signal computation tasks
        tasks = []
        trader_map = {}  # symbol -> trader (for result processing)

        for trader in traders:
            symbol = trader.symbol

            # Mark signal check time
            self.symbol_last_signal_check[symbol] = current_time

            # Get current position (fast cache lookup)
            trader.position = self.get_position(trader)

            # Get strategy signal
            stock_signal = trader.strategy.get_signal()

            # Apply regime-aware logic if enabled
            if self.adaptive_strategy and regime != 'UNKNOWN':
                regime_action = self.adaptive_strategy.get_action(symbol, stock_signal, int(trader.position))
            else:
                regime_action = stock_signal

            # SELECTIVE_RSI is handled separately via _check_selective_rsi_signal
            if trader.strategy_type == "SELECTIVE_RSI":
                if self.selective_rsi:
                    self._check_selective_rsi_signal(trader, current_time)
                continue

            # Skip if not using alpha engine (execute directly for BREAKOUT only)
            if not alpha_engine.enabled or trader.strategy_type != "BREAKOUT":
                self._execute_signal(trader, regime_action, 0.0, regime, current_time)
                continue

            # Prepare alpha context for parallel computation
            rsi = 50.0
            if hasattr(trader.strategy, 'get_current_rsi'):
                rsi = trader.strategy.get_current_rsi()
            atr_pct = trader.strategy.get_atr_percent()
            alpha_context = trader._build_alpha_context(rsi, atr_pct, regime)

            # Convert context to dict for pickle serialization
            context_dict = {
                'prices': list(alpha_context.prices),  # Convert deque to list for pickle
                'current_price': alpha_context.current_price,
                'range_high': alpha_context.range_high,
                'range_low': alpha_context.range_low,
                'rsi': alpha_context.rsi,
                'atr_pct': alpha_context.atr_pct,
                'relative_volume': alpha_context.relative_volume,
                'regime': alpha_context.regime,
                'news_sentiment': alpha_context.news_sentiment,
                'in_position': alpha_context.in_position
            }

            tasks.append((symbol, context_dict, regime_action, int(trader.position), regime))
            trader_map[symbol] = (trader, regime_action, regime)

        # Submit all tasks to process pool and collect results
        if tasks:
            try:
                # Use map for efficient parallel execution
                results = list(self.process_pool.map(_compute_alpha_worker, tasks, timeout=1.0))

                # Process results and execute trades
                for symbol, alpha_score, action in results:
                    if symbol in trader_map:
                        trader, _, regime = trader_map[symbol]
                        self._execute_signal(trader, action, alpha_score, regime, current_time)

            except Exception as e:
                logger.warning(f"Parallel alpha computation error: {e}, falling back to sequential")
                # Fallback to sequential processing
                for symbol, (trader, regime_action, regime) in trader_map.items():
                    self._check_signal_for_stock(trader)

    def _execute_signal(self, trader, action: str, alpha_score: float, regime: str, current_time: float):
        """Execute a trade signal (BUY/SELL) - runs on main thread"""
        symbol = trader.symbol

        # Sync strategy state with actual position
        if trader.position > 0 and not trader.strategy.in_position:
            trader.strategy.enter_position(trader.last_price)
        elif trader.position == 0 and trader.strategy.in_position:
            trader.strategy.exit_position("Closed externally")

        # Execute trade
        if action == 'BUY' and trader.position == 0:
            logger.info(f"[TICK] {symbol}: BUY @ ${trader.last_price:.2f} | Alpha: {alpha_score:+.2f} | {regime}")
            if self.place_order(trader, 'BUY', trader.position_size):
                trader.strategy.enter_position(trader.last_price)
                self.symbol_last_trade[symbol] = current_time
        elif action == 'SELL' and trader.position > 0:
            sell_qty = min(int(trader.position), trader.position_size)
            logger.info(f"[TICK] {symbol}: SELL @ ${trader.last_price:.2f} | Alpha: {alpha_score:+.2f} | {regime}")
            if self.place_order(trader, 'SELL', sell_qty):
                trader.strategy.exit_position(f"Breakout breakdown ({regime} market)")
                self.symbol_last_trade[symbol] = current_time

    def _extract_price_from_ticker(self, ticker) -> float:
        """Extract best price from ticker object"""
        price = None
        if ticker.last and not util.isNan(ticker.last) and ticker.last > 0:
            price = ticker.last
        elif ticker.bid and ticker.ask and not util.isNan(ticker.bid) and not util.isNan(ticker.ask) and ticker.bid > 0:
            price = (ticker.bid + ticker.ask) / 2
        elif ticker.close and not util.isNan(ticker.close) and ticker.close > 0:
            price = ticker.close
        return price

    def _has_pending_order(self, symbol: str) -> bool:
        """Check if there's a pending order for this symbol"""
        for order_id, order_info in self.pending_orders.items():
            if order_info['symbol'] == symbol:
                return True
        return False

    def _check_signal_for_stock(self, trader):
        """
        Evaluate signal for a single stock (sequential fallback).
        Used when multiprocessing is disabled or for single-stock evaluation.
        """
        symbol = trader.symbol
        current_time = time.time()

        # Mark signal check time
        self.symbol_last_signal_check[symbol] = current_time

        # Get current position
        trader.position = self.get_position(trader)

        # Get signal from strategy
        stock_signal = trader.strategy.get_signal()

        # Get regime
        regime = 'UNKNOWN'
        if self.regime_detector:
            regime = self.regime_detector.get_regime()

        # Apply regime-aware logic if enabled
        if self.adaptive_strategy and regime != 'UNKNOWN':
            regime_action = self.adaptive_strategy.get_action(symbol, stock_signal, int(trader.position))
        else:
            regime_action = stock_signal

        # Apply alpha engine for BREAKOUT strategy
        action = regime_action
        alpha_score = 0.0

        if trader.strategy_type == "SELECTIVE_RSI" and self.selective_rsi:
            # Use Selective RSI strategy logic
            self._check_selective_rsi_signal(trader, current_time)
            return  # Handled by selective RSI method

        if alpha_engine.enabled and trader.strategy_type == "BREAKOUT":
            rsi = 50.0
            if hasattr(trader.strategy, 'get_current_rsi'):
                rsi = trader.strategy.get_current_rsi()
            atr_pct = trader.strategy.get_atr_percent()

            alpha_context = trader._build_alpha_context(rsi, atr_pct, regime)
            alpha_result = alpha_engine.compute_alpha(alpha_context)
            alpha_score = alpha_result['score']

            action = alpha_engine.get_action_for_signal(alpha_result, regime_action, int(trader.position), trader.symbol)

        # Execute the signal using shared method
        self._execute_signal(trader, action, alpha_score, regime, current_time)

    def _check_selective_rsi_signal(self, trader, current_time: float):
        """Check Selective RSI signals for a single stock."""
        symbol = trader.symbol

        # Check for exits first (if we have a position)
        if symbol in self.selective_positions:
            pos = self.selective_positions[symbol]
            should_exit, reason = self.selective_rsi.check_exit_signal(symbol, pos['entry'])

            if should_exit:
                trader.position = self.get_position(trader)
                if trader.position > 0:
                    price = trader.last_price
                    pnl_pct = (price - pos['entry']) / pos['entry'] * 100
                    logger.info(f"[SELECTIVE RSI] {symbol}: SELL @ ${price:.2f} | {reason} | P&L: {pnl_pct:+.1f}%")
                    if self.place_order(trader, 'SELL', int(trader.position)):
                        del self.selective_positions[symbol]
                        self.symbol_last_trade[symbol] = current_time
                return

        # Check for entries (only if not at max positions)
        if len(self.selective_positions) >= self.selective_rsi.config.max_positions:
            return

        # Check entry signal
        should_buy, context = self.selective_rsi.check_entry_signal(symbol)

        # Log when RSI is low but filters block (useful for debugging)
        rsi = context.get('rsi')
        if rsi is not None and rsi < self.selective_rsi.config.rsi_oversold and not should_buy:
            logger.info(f"[SELECTIVE RSI] {symbol}: RSI={rsi:.1f} but BLOCKED: {context.get('reason', 'unknown')}")

        if should_buy:
            trader.position = self.get_position(trader)
            if trader.position == 0:
                price = trader.last_price
                logger.info(f"[SELECTIVE RSI] {symbol}: BUY @ ${price:.2f} | {context['reason']}")
                if self.place_order(trader, 'BUY', trader.position_size):
                    self.selective_positions[symbol] = {
                        'entry': price,
                        'shares': trader.position_size
                    }
                    self.symbol_last_trade[symbol] = current_time
            else:
                logger.info(f"[SELECTIVE RSI] {symbol}: Signal but already has position ({trader.position} shares)")

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

        # Market hours check - only trade during regular market hours
        if not self.is_market_open():
            trade_verifier.record_skipped(
                trader.symbol, action, quantity, price, "Market closed"
            )
            # Don't log every skipped order during pre/post market to avoid spam
            return False

        # Spread filter - block BUY orders on wide-spread stocks (SELL always allowed)
        if action == 'BUY' and trader.last_bid > 0 and trader.last_ask > 0:
            spread_pct = (trader.last_ask - trader.last_bid) / price * 100
            if spread_pct > MAX_SPREAD_PCT:
                trade_verifier.record_skipped(
                    trader.symbol, action, quantity, price, f"Wide spread {spread_pct:.2f}%"
                )
                logger.warning(f"[SPREAD FILTER] {trader.symbol}: Spread {spread_pct:.2f}% > {MAX_SPREAD_PCT:.2f}% - BUY blocked")
                return False

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
        pending_trades = self.ib.openTrades()
        for pending in pending_trades:
            if (pending.contract.symbol == trader.symbol and
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
            # Calculate signal strength based on strategy type
            if trader.strategy_type == "BREAKOUT":
                # Use breakout strategy's signal strength
                signal_strength = trader.strategy.get_signal_strength() / 100.0  # Convert 0-100 to 0-1
            elif hasattr(trader.strategy, 'long_window') and len(trader.strategy.prices) >= trader.strategy.long_window:
                # MA strategy: calculate from MA distance
                short_ma = sum(trader.strategy.prices[-trader.strategy.short_window:]) / trader.strategy.short_window
                long_ma = sum(trader.strategy.prices[-trader.strategy.long_window:]) / trader.strategy.long_window
                signal_strength = abs(short_ma - long_ma) / long_ma
            else:
                signal_strength = 0.01  # Default for weak signal

            # Pay premium to ensure fill - increased for fast movers like AMD
            # 0.15% premium catches most momentum moves while limiting slippage
            if action == 'BUY':
                limit_price = round(price * 1.0015, 2)  # Pay 0.15% premium - ensure fill
            else:  # SELL
                limit_price = round(price * 0.9985, 2)  # Accept 0.15% discount - ensure fill

            order = LimitOrder(action, quantity, limit_price)
            ib_trade = self.ib.placeOrder(trader.contract, order)

            # Update trade record with order ID
            trade_verifier.update_order_id(trade_id, ib_trade.order.orderId)
            logger.info(f"Order placed: {action} {quantity} {trader.symbol} @ ${limit_price:.2f} (Trade ID: {trade_id})")

            # Log to activity logger
            activity_logger.log_order_placed(trader.symbol, action, quantity, limit_price, ib_trade.order.orderId)

            # Track order for timeout cancellation
            self.pending_orders[ib_trade.order.orderId] = {
                'symbol': trader.symbol,
                'time': time.time(),
                'trade': ib_trade
            }

            # Reserve cash immediately to prevent over-ordering
            if action == 'BUY':
                order_cost = limit_price * quantity
                commission_buffer = max(quantity * 1.50, 2.00)
                self.available_cash_usd -= (order_cost + commission_buffer)
                logger.debug(f"Reserved ${order_cost + commission_buffer:.2f} for {trader.symbol} - Remaining: ${self.available_cash_usd:.2f}")

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
                # Get tick data from ticker
                volume = 0
                bid = trader.last_bid
                ask = trader.last_ask
                bid_size = 100
                ask_size = 100

                if trader.ticker:
                    if trader.ticker.lastSize and not util.isNan(trader.ticker.lastSize):
                        volume = trader.ticker.lastSize
                    if trader.ticker.bidSize and not util.isNan(trader.ticker.bidSize):
                        bid_size = trader.ticker.bidSize
                    if trader.ticker.askSize and not util.isNan(trader.ticker.askSize):
                        ask_size = trader.ticker.askSize

                # Write tick data to CSV if collecting
                if self.collect_tick_data and symbol in self.tick_writers:
                    self.tick_writers[symbol].writerow([
                        datetime.now().isoformat(timespec='milliseconds'),
                        price,
                        volume,
                        bid,
                        ask,
                        bid_size,
                        ask_size,
                        0, 0, 0, 0,  # Level 2 bid2/ask2 (requires subscription)
                        0, 0, 0, 0   # Level 2 bid3/ask3 (requires subscription)
                    ])
                    self.tick_counts[symbol] = self.tick_counts.get(symbol, 0) + 1

                # SCALP_ML needs additional tick data (bid/ask/volume)
                if trader.strategy_type == "SCALP_ML":
                    trader.strategy.add_tick(
                        price=price,
                        volume=volume,
                        bid=bid,
                        ask=ask,
                        bid_size=bid_size,
                        ask_size=ask_size
                    )
                else:
                    trader.strategy.add_price(price)
                # Track real-time ticks for warmup (separate from preloaded historical data)
                trader.realtime_ticks += 1
                collected += 1

        # Flush tick files periodically (every 60 seconds)
        if self.collect_tick_data and time.time() - self.last_tick_flush > 60:
            for f in self.tick_files.values():
                f.flush()
            self.last_tick_flush = time.time()

        if collected > 0:
            logger.info(f"Collected prices for {collected}/{len(self.traders)} stocks (IBKR)")
            health_monitor.record_price_update(collected)

        # Record tick writes for health monitoring
        if self.collect_tick_data:
            total_ticks = sum(self.tick_counts.values())
            if total_ticks > 0:
                health_monitor.record_tick_write(total_ticks)

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

                    # Fetch analyst ratings (Buy/Hold/Sell)
                    analyst = self.yfinance_client.get_analyst_ratings(symbol)
                    if analyst:
                        trader.analyst_ratings = analyst

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

        # Phase 1: Compute signals and alpha scores for all stocks
        trade_candidates = []  # (symbol, trader, action, alpha_score, alpha_signal, stock_signal)

        for symbol, trader in self.traders.items():
            if not self.ib.isConnected():
                logger.warning("Not connected to IB")
                continue

            # SELECTIVE_RSI is handled by _check_selective_rsi_signal via tick events
            # Skip it here to prevent duplicate/conflicting trades
            if trader.strategy_type == "SELECTIVE_RSI":
                continue

            # Check minimum data requirement (depends on strategy type)
            if trader.strategy_type in ("BREAKOUT", "SCALP_TICK", "SELECTIVE_RSI"):
                min_data = trader.strategy.lookback_periods
            else:
                min_data = trader.strategy.long_window

            if len(trader.strategy.prices) < min_data:
                logger.info(f"{symbol}: Collecting data ({len(trader.strategy.prices)}/{min_data})")
                continue

            # CRITICAL: Require real-time warmup before trading
            # Historical daily bars are NOT sufficient for intraday breakout detection
            if trader.realtime_ticks < trader.warmup_required:
                logger.info(f"{symbol}: Warmup ({trader.realtime_ticks}/{trader.warmup_required} ticks)")
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

                # Get final action from alpha engine (pass symbol for tick confirmation)
                action = alpha_engine.get_action_for_signal(alpha_result, regime_action, int(trader.position), symbol)

                logger.info(f"{symbol}: ${trader.last_price:.2f} | Pos: {trader.position} | Signal: {stock_signal} | Alpha: {alpha_score:+.2f} ({alpha_signal}) | Regime: {regime} | Action: {action}")
            else:
                logger.info(f"{symbol}: ${trader.last_price:.2f} | Pos: {trader.position} | Signal: {stock_signal} | Regime: {regime} | Action: {action}")

            # Sync strategy state with actual position
            if trader.position > 0 and not trader.strategy.in_position:
                trader.strategy.enter_position(trader.last_price)
            elif trader.position == 0 and trader.strategy.in_position:
                trader.strategy.exit_position("Closed externally")

            # Collect trade candidates
            trade_candidates.append((symbol, trader, action, alpha_score, alpha_signal, stock_signal))

        # Phase 2: Sort by alpha score (highest first) and execute trades
        # Process SELLs first (free up capital), then BUYs by alpha score
        sells = [(s, t, a, alpha, asig, ssig) for s, t, a, alpha, asig, ssig in trade_candidates if a == 'SELL' and t.position > 0]
        buys = [(s, t, a, alpha, asig, ssig) for s, t, a, alpha, asig, ssig in trade_candidates if a == 'BUY' and t.position == 0]

        # Sort BUYs by alpha score descending (highest alpha first)
        buys.sort(key=lambda x: x[3], reverse=True)

        if buys:
            logger.info(f"BUY candidates sorted by alpha: {[(s, f'{alpha:+.2f}') for s, t, a, alpha, asig, ssig in buys[:10]]}")

        # Execute SELLs first (free up capital)
        for symbol, trader, action, alpha_score, alpha_signal, stock_signal in sells:
            sell_qty = min(int(trader.position), trader.position_size)
            if alpha_engine.enabled:
                logger.info(f"{symbol}: SELL SIGNAL [Alpha: {alpha_score:+.2f}, {regime}] - Closing position")
            else:
                logger.info(f"{symbol}: SELL SIGNAL [{regime}] - Closing position")
            if self.place_order(trader, 'SELL', sell_qty):
                exit_reason = "Breakout breakdown" if trader.strategy_type == "BREAKOUT" else "MA crossover"
                trader.strategy.exit_position(f"{exit_reason} ({regime} market)")

        # Execute BUYs sorted by alpha (highest first)
        for symbol, trader, action, alpha_score, alpha_signal, stock_signal in buys:
            if alpha_engine.enabled:
                logger.info(f"{symbol}: BUY SIGNAL [Alpha: {alpha_score:+.2f}, {regime}] - Opening position")
            else:
                logger.info(f"{symbol}: BUY SIGNAL [{regime}] - Opening position")
            if self.place_order(trader, 'BUY', trader.position_size):
                trader.strategy.enter_position(trader.last_price)

    def calculate_betas(self):
        """Calculate beta for all stocks vs URTH using 1 year of daily returns (stable)"""
        import yfinance as yf

        # Only calculate once (betas are cached)
        if hasattr(self, '_betas_calculated') and self._betas_calculated:
            return

        logger.info("Calculating 1-year betas vs URTH (MSCI World Index)...")

        try:
            # Fetch 1 year of daily data for URTH
            urth = yf.Ticker("URTH")
            urth_hist = urth.history(period="1y")

            if len(urth_hist) < 100:
                logger.warning("Not enough URTH history for beta calculation")
                return

            # Calculate URTH daily returns
            urth_returns = urth_hist['Close'].pct_change().dropna()
            urth_mean = urth_returns.mean()
            urth_variance = urth_returns.var()

            if urth_variance == 0:
                logger.warning("URTH variance is zero, cannot calculate betas")
                return

            # Calculate beta for each stock
            symbols = list(self.traders.keys())
            for symbol in symbols:
                trader = self.traders[symbol]

                if symbol == 'URTH':
                    trader.beta = 1.0
                    continue

                try:
                    # Fetch stock history
                    stock = yf.Ticker(symbol)
                    stock_hist = stock.history(period="1y")

                    if len(stock_hist) < 100:
                        continue

                    # Align dates with URTH
                    stock_returns = stock_hist['Close'].pct_change().dropna()

                    # Find common dates
                    common_dates = urth_returns.index.intersection(stock_returns.index)
                    if len(common_dates) < 100:
                        continue

                    urth_ret = urth_returns.loc[common_dates]
                    stock_ret = stock_returns.loc[common_dates]

                    # Calculate covariance and beta
                    covariance = ((stock_ret - stock_ret.mean()) * (urth_ret - urth_ret.mean())).mean()
                    beta = covariance / urth_variance

                    trader.beta = round(beta, 2)

                except Exception as e:
                    logger.debug(f"Could not calculate beta for {symbol}: {e}")
                    continue

            self._betas_calculated = True

            # Log some examples
            betas = [(s, t.beta) for s, t in self.traders.items() if t.beta is not None]
            betas.sort(key=lambda x: x[1], reverse=True)
            logger.info(f"Betas calculated for {len(betas)} stocks (1-year daily returns)")
            if betas:
                top3 = betas[:3]
                bot3 = betas[-3:]
                logger.info(f"  Highest beta: {', '.join(f'{s}={b}' for s,b in top3)}")
                logger.info(f"  Lowest beta: {', '.join(f'{s}={b}' for s,b in bot3)}")

        except Exception as e:
            logger.error(f"Beta calculation failed: {e}")

    def update_dashboard(self):
        """Update dashboard with all stock states (lightweight for performance)"""
        # Get current regime for alpha calculations
        current_regime = "UNKNOWN"
        regime_state = None
        if self.regime_detector:
            regime_state = self.regime_detector.get_state()
            current_regime = self.regime_detector.get_regime()

        # Sync positions from IBKR for accurate dashboard display
        try:
            positions = self.ib.positions()
            position_map = {pos.contract.symbol: pos.position for pos in positions}
            for symbol, trader in self.traders.items():
                trader.position = position_map.get(symbol, 0)
        except Exception:
            pass  # Use cached positions if sync fails

        # Calculate beta vs MSCI World (URTH)
        self.calculate_betas()

        states = []
        for symbol, trader in self.traders.items():
            state = trader.get_state(lightweight=True, regime=current_regime)

            # Add SELECTIVE_RSI indicators if strategy is active
            if self.strategy_type == "SELECTIVE_RSI" and self.selective_rsi:
                indicators = self.selective_rsi.get_indicators(symbol)
                rsi = indicators.get('rsi')
                rel_vol = indicators.get('rel_vol')
                atr_pct = indicators.get('atr_pct')

                state['selective_rsi'] = {
                    'rsi': round(rsi or 0, 1),
                    'rel_vol': round(rel_vol, 2) if rel_vol is not None else None,
                    'atr_pct': round((atr_pct or 0) * 100, 2),  # Convert to %
                }

                # Update main signal based on RSI levels
                state['rsi'] = round(rsi, 1) if rsi else 0

                # Set signal and strength based on RSI
                # Signal bar position matches RSI: low RSI = left (green/BUY), high RSI = right (red/SELL)
                if rsi is not None:
                    oversold = self.selective_rsi.config.rsi_oversold  # 25
                    overbought = self.selective_rsi.config.rsi_overbought  # 70

                    if rsi < oversold:
                        # Oversold - BUY signal (left side, green)
                        state['signal'] = 'BUY'
                        # Lower RSI = more negative = further left
                        state['signal_strength'] = (rsi - 50) * 2  # RSI 0 = -100, RSI 25 = -50
                        state['selective_rsi']['oversold'] = True
                    elif rsi > overbought:
                        # Overbought - SELL signal (right side, red)
                        state['signal'] = 'SELL'
                        # Higher RSI = more positive = further right
                        state['signal_strength'] = (rsi - 50) * 2  # RSI 70 = +40, RSI 100 = +100
                    else:
                        # Neutral zone - HOLD
                        state['signal'] = 'HOLD'
                        # RSI 25-70 maps to strength -50 to +40 (centered)
                        state['signal_strength'] = (rsi - 50) * 2

                # Check if in position
                if symbol in self.selective_positions:
                    pos = self.selective_positions[symbol]
                    state['selective_rsi']['in_position'] = True
                    state['selective_rsi']['entry_price'] = pos['entry']
                    pnl_pct = (trader.last_price - pos['entry']) / pos['entry'] * 100 if pos['entry'] > 0 else 0
                    state['selective_rsi']['pnl_pct'] = round(pnl_pct, 2)

            states.append(state)

        # Check if tick collector is running
        collector_running = False
        if hasattr(self, 'collector_process') and self.collector_process:
            collector_running = self.collector_process.poll() is None  # None means still running

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
            'alpha_threshold': alpha_engine.threshold if alpha_engine.enabled else 0.30,
            'collector_running': collector_running
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

        # Log timezone and market hours info
        from datetime import datetime
        import pytz
        local_tz = datetime.now().astimezone().tzinfo
        eastern = pytz.timezone('US/Eastern')
        now_local = datetime.now()
        now_eastern = datetime.now(eastern)
        market_open = now_eastern.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now_eastern.replace(hour=16, minute=0, second=0, microsecond=0)
        is_weekday = now_eastern.weekday() < 5
        is_market_hours = market_open <= now_eastern <= market_close
        market_open_now = is_weekday and is_market_hours

        logger.info(f"=" * 50)
        logger.info(f"LOCAL TIME:  {now_local.strftime('%Y-%m-%d %H:%M:%S %Z')} ({local_tz})")
        logger.info(f"MARKET TIME: {now_eastern.strftime('%Y-%m-%d %H:%M:%S %Z')} (US/Eastern)")
        logger.info(f"Market hours: 09:30 - 16:00 ET (Mon-Fri)")
        if market_open_now:
            logger.info(f"MARKET STATUS: ** OPEN ** - Live trading active")
        else:
            reason = "Weekend" if not is_weekday else "Outside hours"
            logger.info(f"MARKET STATUS: CLOSED ({reason}) - Orders will queue")
        logger.info(f"=" * 50)

        logger.info(f"Trading: {', '.join(self.symbols)}")

        # Restore trading state from last session (persisted in trading_control.json)
        saved_state = trading_control.get_state()
        if saved_state['enabled']:
            logger.info("Trading control: ENABLED (restored from last session)")
        else:
            logger.info("Trading control: DISABLED (enable from dashboard)")

        # Log bot startup
        activity_logger.log_bot_start()

        if not self.dry_run:
            logger.warning("LIVE TRADING MODE - Real money will be used!")
            logger.warning("Press Ctrl+C within 5 seconds to abort...")
            time.sleep(5)

        if not self.connect():
            logger.error("Failed to connect. Exiting.")
            return

        # Sync existing IBKR positions with scalp strategy for stop-loss tracking
        if self.strategy_type == 'SCALP_TICK':
            try:
                positions = self.ib.positions()
                pos_list = [(p.contract.symbol, p.position, p.avgCost) for p in positions if p.position > 0]
                if pos_list:
                    tick_scalper.sync_positions(pos_list)
            except Exception as e:
                logger.warning(f"Could not sync positions: {e}")

        # Pre-load historical data so MAs are ready immediately
        self.preload_historical_data()

        # Adjust position sizes to meet minimum value requirement
        self.adjust_position_sizes_for_value_limits()

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

        # Start tick data collector for ML training (runs alongside bot)
        self.collector_process = None
        try:
            collector_script = os.path.join(os.path.dirname(__file__), 'collect_tick_data.py')
            if os.path.exists(collector_script):
                self.collector_process = subprocess.Popen(
                    [sys.executable, collector_script],
                    cwd=os.path.dirname(__file__),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                logger.info(f"Tick data collector started (PID: {self.collector_process.pid})")
                # Write collector PID to file for dashboard to read
                pid_file = os.path.join(os.path.dirname(__file__), 'data', 'collector_pid.txt')
                os.makedirs(os.path.dirname(pid_file), exist_ok=True)
                with open(pid_file, 'w') as f:
                    f.write(str(self.collector_process.pid))
        except Exception as e:
            logger.warning(f"Failed to start tick data collector: {e}")

        logger.info(f"Collecting prices every {self.price_interval}s, checking trades every {self.trade_interval}s")

        # Health monitoring variables
        self.last_price_update = time.time()
        self.last_health_check = 0
        self.stale_data_warned = False
        self.consecutive_stale_count = 0

        try:
            while True:
                current_time = time.time()

                # Collect prices (skip in tick mode - handled by callback)
                if not self.tick_mode:
                    if current_time - self.last_price_time >= self.price_interval:
                        self.collect_prices()
                        self.last_price_time = current_time
                        self.last_price_update = current_time  # Track successful price update
                        self.consecutive_stale_count = 0
                        self.stale_data_warned = False

                # Cancel timed-out orders (30 second timeout)
                self.cancel_timed_out_orders()

                # Health check every 30 seconds
                if current_time - self.last_health_check >= 30:
                    self._check_health(current_time)
                    self.last_health_check = current_time

                # Update events and news (every 5 minutes)
                if current_time - self.last_info_time >= 300:
                    self.update_stock_info()
                    self.last_info_time = current_time

                # Update cash balance (every 60 seconds)
                self.update_cash_balance()

                # Update dashboard
                self.update_dashboard()

                # Check signals (skip in tick mode - handled per-tick)
                if not self.tick_mode:
                    if current_time - self.last_trade_time >= self.trade_interval:
                        self.check_signals()
                        self.last_trade_time = current_time

                # Faster loop in tick mode for responsiveness
                self.ib.sleep(0.01 if self.tick_mode else 0.1)

        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            self.disconnect()

    def _check_health(self, current_time):
        """Monitor system health: IBKR connection, data freshness, subprocess status"""

        # Update health monitor with current state
        health_monitor.check_ibkr_connection(self.ib)
        health_monitor.check_dashboard()
        health_monitor.check_price_feed()
        health_monitor.check_tick_collection(self.collect_tick_data)

        # Check IBKR connection
        if not self.ib.isConnected():
            health_monitor.record_error('ibkr_connection', 'Disconnected')
            activity_logger.log_connection('disconnected')
            logger.error("[HEALTH] IBKR DISCONNECTED - Attempting reconnect...")
            try:
                self.ib.disconnect()
                time.sleep(2)
                self.connect()
                logger.info("[HEALTH] IBKR reconnected successfully")
                activity_logger.log_reconnect(True, "Connection restored")
            except Exception as e:
                logger.error(f"[HEALTH] IBKR reconnect failed: {e}")
                activity_logger.log_reconnect(False, str(e))

        # Check for stale data (no price updates for 60+ seconds)
        time_since_update = current_time - self.last_price_update
        if time_since_update > 60:
            self.consecutive_stale_count += 1
            if not self.stale_data_warned or self.consecutive_stale_count % 5 == 0:
                logger.warning(f"[HEALTH] STALE DATA - No price updates for {time_since_update:.0f}s (count: {self.consecutive_stale_count})")
                self.stale_data_warned = True

            # After 5 consecutive stale checks (2.5 min), try to reconnect
            if self.consecutive_stale_count >= 5:
                logger.error("[HEALTH] Persistent stale data - forcing IBKR reconnect")
                try:
                    self.ib.disconnect()
                    time.sleep(2)
                    self.connect()
                    self.consecutive_stale_count = 0
                except Exception as e:
                    logger.error(f"[HEALTH] Reconnect failed: {e}")

        # Check dashboard subprocess
        if self.enable_dashboard and hasattr(self, 'dashboard_process') and self.dashboard_process:
            if self.dashboard_process.poll() is not None:
                logger.warning("[HEALTH] Dashboard crashed - restarting...")
                health_monitor.record_error('dashboard', 'Process crashed')
                activity_logger.log_dashboard_restart("crashed")
                try:
                    self.dashboard_process = subprocess.Popen(
                        [sys.executable, '-m', 'src.multi_dashboard'],
                        cwd=os.path.dirname(__file__)
                    )
                    logger.info(f"[HEALTH] Dashboard restarted (PID: {self.dashboard_process.pid})")
                except Exception as e:
                    logger.error(f"[HEALTH] Dashboard restart failed: {e}")
                    activity_logger.log_error("Dashboard", f"Restart failed: {e}")

        # Check tick collector subprocess
        if hasattr(self, 'collector_process') and self.collector_process:
            if self.collector_process.poll() is not None:
                logger.warning("[HEALTH] Tick collector crashed - restarting...")
                try:
                    collector_script = os.path.join(os.path.dirname(__file__), 'collect_tick_data.py')
                    self.collector_process = subprocess.Popen(
                        [sys.executable, collector_script],
                        cwd=os.path.dirname(__file__),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    logger.info(f"[HEALTH] Tick collector restarted (PID: {self.collector_process.pid})")
                except Exception as e:
                    logger.error(f"[HEALTH] Tick collector restart failed: {e}")


if __name__ == '__main__':
    bot = MultiStockBot()
    bot.start()
