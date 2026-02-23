"""
Trading strategy module with MA Crossover, RSI, Volume, Fundamentals, and risk management.

Optimized parameters from backtesting:
- MA(10/30) crossover with 1% threshold
- 15% stop-loss from entry
- 10% trailing stop from peak (only after 8% profit)
- RSI filter (don't buy when RSI > 70)
- Volume filter (require 1.2x avg volume for trades, block below 0.3x)
- Fundamental filter (earnings blackout, news sentiment, analyst ratings)
- Index filter (hold during market selloffs)
- 5-day minimum hold period
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def calculate_rsi(prices: list, period: int = 14) -> list:
    """Calculate RSI for a list of prices"""
    if len(prices) < period + 1:
        return []

    rsi_values = []
    for i in range(period, len(prices)):
        gains = []
        losses = []
        for j in range(i - period + 1, i + 1):
            change = prices[j] - prices[j-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            rsi_values.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100 - (100 / (1 + rs)))

    # Pad beginning with None to align with prices
    return [None] * period + rsi_values


class SimpleStrategy:
    """
    Enhanced MA crossover strategy with risk management.

    Features:
    - MA crossover signals (10/30 default)
    - RSI overbought filter
    - Stop-loss protection
    - Trailing stop to lock in profits
    - Minimum hold period to avoid whipsaw
    """

    def __init__(self, short_window=10, long_window=30, threshold=0.01,
                 stop_loss_pct=0.15, trailing_stop_pct=0.10,
                 trail_after_profit_pct=0.08, min_hold_periods=5,
                 rsi_overbought=70, rsi_period=14,
                 volume_ma_period=20, volume_confirm_threshold=1.5,
                 volume_min_threshold=0.5,
                 use_fundamental_filter=False, earnings_blackout_days=3,
                 require_bullish_fundamental=False, block_bearish_fundamental=True):
        # MA parameters
        self.short_window = short_window
        self.long_window = long_window
        self.threshold = threshold  # 1% threshold to avoid whipsawing

        # Risk management
        self.stop_loss_pct = stop_loss_pct  # 15% stop-loss from entry
        self.trailing_stop_pct = trailing_stop_pct  # 10% trailing stop from peak
        self.trail_after_profit_pct = trail_after_profit_pct  # Only trail after 8% profit
        self.min_hold_periods = min_hold_periods  # Minimum periods before exit

        # RSI filter
        self.rsi_overbought = rsi_overbought
        self.rsi_period = rsi_period

        # Volume filter
        self.volume_ma_period = volume_ma_period  # Period for volume average
        self.volume_confirm_threshold = volume_confirm_threshold  # Require 1.5x avg for confirmation
        self.volume_min_threshold = volume_min_threshold  # Block trades below 0.5x avg

        # Fundamental filter
        self.use_fundamental_filter = use_fundamental_filter
        self.earnings_blackout_days = earnings_blackout_days
        self.require_bullish_fundamental = require_bullish_fundamental  # Require bullish signal to buy
        self.block_bearish_fundamental = block_bearish_fundamental  # Block buys on bearish signal

        # Fundamental data cache
        self.fundamental_data = None
        self.fundamental_last_update = None

        # Earnings signal (Post-Earnings Announcement Drift)
        self.earnings_signal = None  # 'strong_buy', 'buy', 'hold', 'sell', 'strong_sell'
        self.earnings_signal_reason = None
        self.earnings_signal_strength = 0

        # State tracking
        self.prices = []
        self.volumes = []  # Volume history
        self.entry_price = 0
        self.peak_price = 0
        self.periods_held = 0
        self.in_position = False

    def add_price(self, price):
        """Add a new price to the history"""
        self.prices.append(price)

        # Track peak price since entry
        if self.in_position and price > self.peak_price:
            self.peak_price = price

        # Increment hold counter
        if self.in_position:
            self.periods_held += 1

        # Keep only what we need (with some buffer)
        max_prices = max(self.long_window, self.rsi_period, self.volume_ma_period) * 3
        if len(self.prices) > max_prices:
            self.prices = self.prices[-max_prices:]
        if len(self.volumes) > max_prices:
            self.volumes = self.volumes[-max_prices:]

    def add_volume(self, volume: int):
        """Add a new volume to the history"""
        self.volumes.append(volume)

    def get_volume_ma(self) -> float:
        """Calculate average volume over the volume_ma_period"""
        if len(self.volumes) < self.volume_ma_period:
            if len(self.volumes) == 0:
                return 0
            return sum(self.volumes) / len(self.volumes)
        return sum(self.volumes[-self.volume_ma_period:]) / self.volume_ma_period

    def get_relative_volume(self) -> float:
        """Calculate current volume relative to average (1.0 = average)"""
        if len(self.volumes) == 0:
            return 1.0  # Default to neutral if no volume data
        current_volume = self.volumes[-1]
        avg_volume = self.get_volume_ma()
        if avg_volume <= 0:
            return 1.0
        return current_volume / avg_volume

    def check_volume_confirmation(self) -> bool:
        """Check if volume is high enough to confirm a signal"""
        return self.get_relative_volume() >= self.volume_confirm_threshold

    def check_volume_too_low(self) -> bool:
        """Check if volume is too low to trade"""
        return self.get_relative_volume() < self.volume_min_threshold

    def update_fundamental_data(self, fundamental_data: dict):
        """Update fundamental data from external source

        Args:
            fundamental_data: Dict with 'earnings', 'news_sentiment', 'analyst_rating' keys
        """
        self.fundamental_data = fundamental_data
        self.fundamental_last_update = datetime.now()

    def check_earnings_blackout(self) -> bool:
        """Check if we're in earnings blackout period"""
        if not self.use_fundamental_filter or not self.fundamental_data:
            return False

        earnings = self.fundamental_data.get('earnings')
        if earnings and hasattr(earnings, 'in_blackout_period'):
            return earnings.in_blackout_period
        return False

    def update_earnings_signal(self, signal: str, strength: float, reason: str):
        """Update earnings signal from EarningsAnalyzer

        Args:
            signal: 'strong_buy', 'buy', 'hold', 'sell', 'strong_sell'
            strength: Signal strength (0.0 to 1.0)
            reason: Explanation of signal
        """
        self.earnings_signal = signal
        self.earnings_signal_strength = strength
        self.earnings_signal_reason = reason
        logger.info(f"Earnings signal updated: {signal} (strength: {strength:.2f}) - {reason}")

    def check_earnings_buy_signal(self) -> tuple:
        """Check if earnings signal triggers a buy

        Returns:
            (should_buy, reason) tuple
        """
        if not self.earnings_signal:
            return False, None

        if self.earnings_signal == 'strong_buy' and self.earnings_signal_strength >= 0.5:
            return True, f"EARNINGS BEAT: {self.earnings_signal_reason}"
        elif self.earnings_signal == 'buy' and self.earnings_signal_strength >= 0.3:
            return True, f"EARNINGS POSITIVE: {self.earnings_signal_reason}"

        return False, None

    def check_earnings_sell_signal(self) -> tuple:
        """Check if earnings signal triggers a sell

        Returns:
            (should_sell, reason) tuple
        """
        if not self.earnings_signal:
            return False, None

        if self.earnings_signal == 'strong_sell' and self.earnings_signal_strength >= 0.5:
            return True, f"EARNINGS MISS: {self.earnings_signal_reason}"
        elif self.earnings_signal == 'sell' and self.earnings_signal_strength >= 0.3:
            return True, f"EARNINGS NEGATIVE: {self.earnings_signal_reason}"

        return False, None

    def check_fundamental_signal(self) -> tuple:
        """Check fundamental signal for trading

        Returns:
            (signal, reason) - signal is 'bullish', 'bearish', or 'neutral'
        """
        if not self.use_fundamental_filter or not self.fundamental_data:
            return 'neutral', None

        # Check news sentiment
        news_data = self.fundamental_data.get('news_sentiment')
        if news_data:
            sentiment, score, count = news_data
        else:
            sentiment, score, count = 'neutral', 0, 0

        # Check analyst rating
        analyst = self.fundamental_data.get('analyst_rating')
        if analyst and hasattr(analyst, 'score'):
            analyst_score = analyst.score
            analyst_rec = analyst.recommendation
        else:
            analyst_score = 3.0
            analyst_rec = 'hold'

        # Combine signals
        bullish_signals = []
        bearish_signals = []

        if sentiment == 'positive':
            bullish_signals.append(f"News: positive ({score:.2f})")
        elif sentiment == 'negative':
            bearish_signals.append(f"News: negative ({score:.2f})")

        if analyst_score >= 3.5:
            bullish_signals.append(f"Analysts: {analyst_rec} ({analyst_score:.1f})")
        elif analyst_score <= 2.5:
            bearish_signals.append(f"Analysts: {analyst_rec} ({analyst_score:.1f})")

        if len(bullish_signals) > len(bearish_signals):
            return 'bullish', '; '.join(bullish_signals)
        elif len(bearish_signals) > len(bullish_signals):
            return 'bearish', '; '.join(bearish_signals)
        else:
            return 'neutral', None

    def get_current_rsi(self) -> float:
        """Calculate current RSI"""
        if len(self.prices) < self.rsi_period + 1:
            return 50  # Neutral default

        rsi_values = calculate_rsi(self.prices, self.rsi_period)
        return rsi_values[-1] if rsi_values and rsi_values[-1] is not None else 50

    def check_stop_loss(self, current_price: float) -> bool:
        """Check if stop-loss is triggered"""
        if not self.stop_loss_pct or self.stop_loss_pct <= 0:
            return False  # No stop loss configured
        if not self.in_position or self.entry_price <= 0:
            return False
        loss_pct = (self.entry_price - current_price) / self.entry_price
        return loss_pct >= self.stop_loss_pct

    def check_trailing_stop(self, current_price: float) -> bool:
        """Check if trailing stop is triggered (only after profit threshold)"""
        if not self.trailing_stop_pct or self.trailing_stop_pct <= 0:
            return False  # No trailing stop configured
        if not self.in_position or self.peak_price <= 0:
            return False

        # Only activate trailing stop after reaching profit threshold
        if self.trail_after_profit_pct and self.trail_after_profit_pct > 0:
            profit_pct = (self.peak_price - self.entry_price) / self.entry_price
            if profit_pct < self.trail_after_profit_pct:
                return False  # Not enough profit yet

        # Check if dropped from peak
        drop_pct = (self.peak_price - current_price) / self.peak_price
        return drop_pct >= self.trailing_stop_pct

    def enter_position(self, price: float):
        """Record entry into position"""
        self.in_position = True
        self.entry_price = price
        self.peak_price = price
        self.periods_held = 0
        logger.info(f"Strategy: Entered position at ${price:.2f}")

    def exit_position(self, reason: str = ""):
        """Record exit from position"""
        self.in_position = False
        self.entry_price = 0
        self.peak_price = 0
        self.periods_held = 0
        logger.info(f"Strategy: Exited position ({reason})")

    def get_signal(self, index_dropping: bool = False) -> str:
        """Get current trading signal based on collected prices

        Args:
            index_dropping: True if the market index is in a selloff

        Returns:
            'BUY', 'SELL', 'STOP_LOSS', 'TRAILING_STOP', or 'HOLD'
        """
        # Not enough data yet
        if len(self.prices) < self.long_window:
            logger.info(f"Collecting data: {len(self.prices)}/{self.long_window}")
            return 'HOLD'

        current_price = self.prices[-1]

        # === EXIT SIGNALS (if in position) ===
        if self.in_position:
            # Stop-loss always active (protect capital)
            if self.check_stop_loss(current_price):
                logger.info(f"STOP-LOSS triggered: ${current_price:.2f} (entry: ${self.entry_price:.2f})")
                return 'STOP_LOSS'

            # Trailing stop (only after min hold and profit threshold)
            if self.periods_held >= self.min_hold_periods:
                if self.check_trailing_stop(current_price):
                    logger.info(f"TRAILING STOP triggered: ${current_price:.2f} (peak: ${self.peak_price:.2f})")
                    return 'TRAILING_STOP'

        # Calculate moving averages
        short_ma = sum(self.prices[-self.short_window:]) / self.short_window
        long_ma = sum(self.prices[-self.long_window:]) / self.long_window
        rsi = self.get_current_rsi()
        rel_volume = self.get_relative_volume()

        logger.info(f"MA({self.short_window}): ${short_ma:.4f}, MA({self.long_window}): ${long_ma:.4f}, RSI: {rsi:.1f}, RelVol: {rel_volume:.2f}x")

        # === EARNINGS SIGNAL OVERRIDE ===
        # If earnings just came out with strong signal, it can override other filters
        earnings_buy, earnings_buy_reason = self.check_earnings_buy_signal()
        earnings_sell, earnings_sell_reason = self.check_earnings_sell_signal()

        if earnings_buy and not self.in_position:
            # Strong earnings beat - buy even if other indicators are neutral
            # Still respect RSI overbought (don't chase)
            if rsi <= self.rsi_overbought:
                logger.info(f"EARNINGS BUY SIGNAL: {earnings_buy_reason}")
                return 'BUY'
            else:
                logger.info(f"Earnings buy blocked: RSI {rsi:.1f} > {self.rsi_overbought} (overbought)")

        if earnings_sell and self.in_position:
            # Strong earnings miss - sell immediately
            logger.info(f"EARNINGS SELL SIGNAL: {earnings_sell_reason}")
            return 'SELL'

        # Volume filter - block all trades on very low volume
        if self.check_volume_too_low():
            logger.info(f"Trade blocked: Volume too low ({rel_volume:.2f}x < {self.volume_min_threshold}x avg)")
            return 'HOLD'

        # Fundamental filter - check earnings blackout (skip if we have earnings signal)
        if not self.earnings_signal and self.check_earnings_blackout():
            logger.info("Trade blocked: Earnings blackout period")
            return 'HOLD'

        # Get fundamental signal
        fundamental_signal, fundamental_reason = self.check_fundamental_signal()

        # === BUY SIGNAL ===
        if short_ma > long_ma * (1 + self.threshold):
            # RSI filter - don't buy overbought
            if rsi > self.rsi_overbought:
                logger.info(f"BUY blocked: RSI {rsi:.1f} > {self.rsi_overbought} (overbought)")
                return 'HOLD'
            # Index filter - don't buy during market selloff
            if index_dropping:
                logger.info("BUY blocked: Market index selling off")
                return 'HOLD'
            # Volume confirmation - require above-average volume
            if not self.check_volume_confirmation():
                logger.info(f"BUY blocked: Volume too low ({rel_volume:.2f}x < {self.volume_confirm_threshold}x avg)")
                return 'HOLD'
            # Fundamental filter - block on bearish signal
            if self.use_fundamental_filter and self.block_bearish_fundamental and fundamental_signal == 'bearish':
                logger.info(f"BUY blocked: Bearish fundamentals ({fundamental_reason})")
                return 'HOLD'
            # Fundamental filter - require bullish signal
            if self.use_fundamental_filter and self.require_bullish_fundamental and fundamental_signal != 'bullish':
                logger.info(f"BUY blocked: Requires bullish fundamentals (current: {fundamental_signal})")
                return 'HOLD'
            if fundamental_signal == 'bullish':
                logger.info(f"BUY confirmed: Bullish fundamentals ({fundamental_reason})")
            return 'BUY'

        # === SELL SIGNAL ===
        elif short_ma < long_ma * (1 - self.threshold):
            # Check minimum hold period
            if self.in_position and self.periods_held < self.min_hold_periods:
                logger.info(f"SELL blocked: Only held {self.periods_held}/{self.min_hold_periods} periods")
                return 'HOLD'
            # Index filter - hold during market selloff (not stock-specific weakness)
            if index_dropping:
                logger.info("SELL blocked: Market selloff, holding position")
                return 'HOLD'
            # Volume confirmation - require above-average volume for MA crossover sells
            if not self.check_volume_confirmation():
                logger.info(f"SELL blocked: Volume too low ({rel_volume:.2f}x < {self.volume_confirm_threshold}x avg)")
                return 'HOLD'
            return 'SELL'

        return 'HOLD'

    def analyze(self, current_price):
        """Legacy method for compatibility"""
        self.add_price(current_price)
        return self.get_signal()

    def get_status(self) -> dict:
        """Get current strategy status for dashboard"""
        current_price = self.prices[-1] if self.prices else 0
        current_volume = self.volumes[-1] if self.volumes else 0

        # Get fundamental status
        fundamental_signal, fundamental_reason = self.check_fundamental_signal()
        earnings_blackout = self.check_earnings_blackout()

        return {
            'in_position': self.in_position,
            'entry_price': self.entry_price,
            'peak_price': self.peak_price,
            'periods_held': self.periods_held,
            'current_price': current_price,
            'unrealized_pnl': (current_price - self.entry_price) if self.in_position else 0,
            'unrealized_pnl_pct': ((current_price - self.entry_price) / self.entry_price * 100) if self.in_position and self.entry_price > 0 else 0,
            'rsi': self.get_current_rsi(),
            'stop_loss_price': self.entry_price * (1 - self.stop_loss_pct) if self.in_position else 0,
            'trailing_stop_price': self.peak_price * (1 - self.trailing_stop_pct) if self.in_position else 0,
            'volume': current_volume,
            'volume_ma': self.get_volume_ma(),
            'relative_volume': self.get_relative_volume(),
            'fundamental_signal': fundamental_signal,
            'fundamental_reason': fundamental_reason,
            'earnings_blackout': earnings_blackout,
            'earnings_signal': self.earnings_signal,
            'earnings_signal_strength': self.earnings_signal_strength,
            'earnings_signal_reason': self.earnings_signal_reason,
        }
