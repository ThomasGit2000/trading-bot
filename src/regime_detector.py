"""
Market Regime Detector
Determines if we're in a bull or bear market based on SPY/QQQ trends.
"""
import logging
from collections import deque
from datetime import datetime, timedelta
from src.yfinance_client import YFinanceClient

logger = logging.getLogger(__name__)


class RegimeDetector:
    """
    Detects market regime (BULL/BEAR) based on index trends.

    BULL market: Index short MA > long MA (stay invested, ignore sell signals)
    BEAR market: Index short MA < long MA (use MA crossover strategy)
    """

    def __init__(self, index_symbol: str = 'SPY', short_window: int = 20,
                 long_window: int = 50, threshold: float = 0.01):
        """
        Args:
            index_symbol: Market index to track (SPY, QQQ, etc.)
            short_window: Short MA period for regime detection
            long_window: Long MA period for regime detection
            threshold: Threshold for regime change (1% default)
        """
        self.index_symbol = index_symbol
        self.short_window = short_window
        self.long_window = long_window
        self.threshold = threshold

        self.prices = deque(maxlen=long_window + 10)
        self.current_regime = 'UNKNOWN'
        self.regime_start = None
        self.last_update = None

        self.yfinance = YFinanceClient()

        logger.info(f"RegimeDetector initialized: {index_symbol} MA({short_window}/{long_window})")

    def update_price(self, price: float) -> str:
        """
        Update with new price and return current regime.

        Returns:
            'BULL', 'BEAR', or 'UNKNOWN'
        """
        self.prices.append(price)
        self.last_update = datetime.now()

        if len(self.prices) < self.long_window:
            return 'UNKNOWN'

        prices_list = list(self.prices)
        short_ma = sum(prices_list[-self.short_window:]) / self.short_window
        long_ma = sum(prices_list[-self.long_window:]) / self.long_window

        old_regime = self.current_regime

        # Determine regime with threshold to avoid whipsaws
        if short_ma > long_ma * (1 + self.threshold):
            self.current_regime = 'BULL'
        elif short_ma < long_ma * (1 - self.threshold):
            self.current_regime = 'BEAR'
        elif self.current_regime == 'UNKNOWN':
            # First time with enough data - default based on MA comparison
            if short_ma >= long_ma:
                self.current_regime = 'BULL'
            else:
                self.current_regime = 'BEAR'
        # else: keep current regime (hysteresis)

        if self.current_regime != old_regime:
            self.regime_start = datetime.now()
            logger.info(f"REGIME CHANGE: {old_regime} -> {self.current_regime}")
            logger.info(f"  {self.index_symbol}: Short MA={short_ma:.2f}, Long MA={long_ma:.2f}")

        return self.current_regime

    def fetch_and_update(self) -> str:
        """
        Fetch current index price and update regime.

        Returns:
            Current regime ('BULL', 'BEAR', or 'UNKNOWN')
        """
        try:
            quote = self.yfinance.get_quote(self.index_symbol)
            if quote and quote['price'] > 0:
                return self.update_price(quote['price'])
        except Exception as e:
            logger.warning(f"Failed to fetch {self.index_symbol}: {e}")

        return self.current_regime

    def get_regime(self) -> str:
        """Get current market regime."""
        return self.current_regime

    def get_state(self) -> dict:
        """Get current state for dashboard."""
        prices_list = list(self.prices) if self.prices else []

        short_ma = 0
        long_ma = 0
        if len(prices_list) >= self.short_window:
            short_ma = sum(prices_list[-self.short_window:]) / self.short_window
        if len(prices_list) >= self.long_window:
            long_ma = sum(prices_list[-self.long_window:]) / self.long_window

        return {
            'index': self.index_symbol,
            'regime': self.current_regime,
            'regime_start': self.regime_start.isoformat() if self.regime_start else None,
            'price': prices_list[-1] if prices_list else 0,
            'short_ma': short_ma,
            'long_ma': long_ma,
            'data_points': len(self.prices),
            'required_points': self.long_window,
            'last_update': self.last_update.isoformat() if self.last_update else None
        }

    def should_use_ma_signals(self) -> bool:
        """
        Returns True if we should use MA crossover signals (BEAR market).
        Returns False if we should buy-and-hold (BULL market).
        """
        return self.current_regime == 'BEAR'

    def should_exit_position(self, stock_signal: str) -> bool:
        """
        Determine if we should exit a position based on regime and stock signal.

        In BULL market: Never exit (ignore sell signals) - ride the trend
        In BEAR market: Follow MA signals - exit on sell signals

        Args:
            stock_signal: The signal from stock's MA strategy ('BUY', 'SELL', 'HOLD')

        Returns:
            True if should exit, False otherwise
        """
        if self.current_regime == 'BULL':
            # Bull market - ignore sell signals, stay invested
            return False
        elif self.current_regime == 'BEAR':
            # Bear market - follow the MA signals
            return stock_signal == 'SELL'
        else:
            # Unknown regime - be cautious, follow signals
            return stock_signal == 'SELL'

    def should_enter_position(self, stock_signal: str) -> bool:
        """
        Determine if we should enter a position based on regime and stock signal.

        In BULL market: Enter on any buy signal (aggressive)
        In BEAR market: Only enter on strong buy signals (conservative)

        Args:
            stock_signal: The signal from stock's MA strategy

        Returns:
            True if should enter, False otherwise
        """
        if stock_signal != 'BUY':
            return False

        # In any regime, enter on buy signal
        # Could add more conservative logic for bear markets later
        return True


class AdaptiveStrategy:
    """
    Wrapper that adapts trading behavior based on market regime.

    BULL MARKET:
        - Enter on MA crossover buy signals
        - NEVER exit (ignore sell signals)
        - Goal: Capture full upside of bull runs

    BEAR MARKET:
        - Enter on MA crossover buy signals
        - Exit on MA crossover sell signals
        - Goal: Preserve capital during downturns
    """

    def __init__(self, regime_detector: RegimeDetector):
        self.regime_detector = regime_detector
        logger.info("AdaptiveStrategy initialized - regime-aware trading enabled")

    def get_action(self, stock_symbol: str, stock_signal: str,
                   current_position: int) -> str:
        """
        Get trading action based on regime and stock signal.

        Args:
            stock_symbol: The stock being traded
            stock_signal: Signal from stock's MA strategy ('BUY', 'SELL', 'HOLD')
            current_position: Current position in the stock

        Returns:
            'BUY', 'SELL', or 'HOLD'
        """
        regime = self.regime_detector.get_regime()

        # Not in position - check for entry
        if current_position == 0:
            if self.regime_detector.should_enter_position(stock_signal):
                logger.info(f"{stock_symbol}: BUY signal in {regime} market")
                return 'BUY'
            return 'HOLD'

        # In position - check for exit
        if self.regime_detector.should_exit_position(stock_signal):
            logger.info(f"{stock_symbol}: SELL signal in {regime} market")
            return 'SELL'

        # In position but regime says hold
        if stock_signal == 'SELL' and regime == 'BULL':
            logger.debug(f"{stock_symbol}: Ignoring SELL signal in BULL market")

        return 'HOLD'
