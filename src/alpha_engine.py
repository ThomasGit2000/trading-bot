"""
Micro-Alpha Engine for Trading Signals

Combines 6 alpha signals with configurable weights to improve win rate.
The alpha engine adds confluence filters to the base breakout strategy.

Alpha Signals:
- Breakout: Distance from range midpoint (-1 to +1)
- Volume: Relative volume confirmation
- ATR Momentum: Higher volatility = stronger signal
- RSI Momentum: Oversold (30-40) = bullish, Overbought (>70) = bearish
- Market Regime: BULL = +0.5, BEAR = -0.5
- Sentiment: VADER news score (-1 to +1)

Scoring:
    alpha_score = sum(signal_value * weight)  # Range: -1.0 to +1.0
    >= 0.50  -> Strong BUY
    >= 0.30  -> BUY
    -0.30 to 0.30 -> HOLD
    <= -0.30 -> SELL
"""
import os
import logging
from dataclasses import dataclass
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class AlphaResult:
    """Result from a single alpha signal computation."""
    name: str
    value: float  # -1.0 to +1.0
    weight: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0 (how reliable is this signal)

    @property
    def weighted_value(self) -> float:
        """Get weighted contribution to total alpha score."""
        return self.value * self.weight * self.confidence


@dataclass
class AlphaContext:
    """Context data needed for alpha computation."""
    # Price data
    prices: List[float]
    current_price: float
    range_high: Optional[float] = None
    range_low: Optional[float] = None

    # Indicators
    rsi: float = 50.0
    atr_pct: float = 0.0
    relative_volume: float = 1.0

    # Market context
    regime: str = "UNKNOWN"  # BULL, BEAR, UNKNOWN
    news_sentiment: float = 0.0  # -1.0 to +1.0

    # Position state
    in_position: bool = False


class MicroAlphaEngine:
    """
    Micro-alpha engine that combines multiple signals for better trading decisions.

    Each alpha signal returns a value from -1.0 (strongly bearish) to +1.0 (strongly bullish).
    The composite score is the weighted sum of all signals.
    """

    # Default weights (sum to 1.0)
    DEFAULT_WEIGHTS = {
        'breakout': 0.35,
        'volume': 0.20,
        'atr': 0.12,
        'rsi': 0.12,
        'regime': 0.11,
        'sentiment': 0.10,
    }

    # Thresholds for trading decisions
    STRONG_BUY_THRESHOLD = 0.50
    BUY_THRESHOLD = 0.30
    SELL_THRESHOLD = -0.30

    def __init__(self):
        """Initialize the alpha engine with weights from environment."""
        self.enabled = os.getenv('ALPHA_ENGINE_ENABLED', 'false').lower() == 'true'
        self.threshold = float(os.getenv('ALPHA_THRESHOLD', '0.30'))

        # Hard filters (block trades regardless of alpha score)
        self.rsi_max = float(os.getenv('ALPHA_RSI_MAX', '70'))  # Block if RSI >= this
        self.volume_min = float(os.getenv('ALPHA_VOLUME_MIN', '0'))  # Block if rel_vol < this

        # Load weights from environment or use defaults
        self.weights = {
            'breakout': float(os.getenv('ALPHA_WEIGHT_BREAKOUT', str(self.DEFAULT_WEIGHTS['breakout']))),
            'volume': float(os.getenv('ALPHA_WEIGHT_VOLUME', str(self.DEFAULT_WEIGHTS['volume']))),
            'atr': float(os.getenv('ALPHA_WEIGHT_ATR', str(self.DEFAULT_WEIGHTS['atr']))),
            'rsi': float(os.getenv('ALPHA_WEIGHT_RSI', str(self.DEFAULT_WEIGHTS['rsi']))),
            'regime': float(os.getenv('ALPHA_WEIGHT_REGIME', str(self.DEFAULT_WEIGHTS['regime']))),
            'sentiment': float(os.getenv('ALPHA_WEIGHT_SENTIMENT', str(self.DEFAULT_WEIGHTS['sentiment']))),
        }

        # Normalize weights to sum to 1.0
        total_weight = sum(self.weights.values())
        if total_weight > 0:
            self.weights = {k: v / total_weight for k, v in self.weights.items()}

        if self.enabled:
            logger.info(f"Alpha Engine ENABLED - Threshold: {self.threshold}")
            logger.info(f"  Hard Filters: RSI < {self.rsi_max}, Volume > {self.volume_min}x")
            logger.info(f"  Weights: {self.weights}")
        else:
            logger.info("Alpha Engine DISABLED - Using raw breakout signals")

    def check_hard_filters(self, context: AlphaContext) -> tuple:
        """
        Check hard filters that block trades regardless of alpha score.

        Returns:
            (passed: bool, reason: str or None)
        """
        # RSI filter - block overbought
        if self.rsi_max > 0 and context.rsi >= self.rsi_max:
            return False, f"RSI {context.rsi:.1f} >= {self.rsi_max}"

        # Volume filter - block low volume
        if self.volume_min > 0 and context.relative_volume < self.volume_min:
            return False, f"Volume {context.relative_volume:.2f}x < {self.volume_min}x"

        return True, None

    def compute_alpha(self, context: AlphaContext) -> Dict:
        """
        Compute composite alpha score from all signals.

        Args:
            context: AlphaContext with all necessary data

        Returns:
            Dict with:
                - score: float (-1.0 to +1.0)
                - signal: str (STRONG_BUY, BUY, HOLD, SELL)
                - components: List[AlphaResult]
                - reasoning: str (explanation of decision)
        """
        if not self.enabled:
            return {
                'score': 0.0,
                'signal': 'HOLD',
                'components': [],
                'reasoning': 'Alpha engine disabled',
                'hard_filter_passed': True,
                'hard_filter_reason': None
            }

        # Check hard filters first
        hard_filter_passed, hard_filter_reason = self.check_hard_filters(context)

        # Compute individual alpha signals
        components = [
            self.compute_breakout_alpha(context),
            self.compute_volume_alpha(context),
            self.compute_atr_alpha(context),
            self.compute_rsi_alpha(context),
            self.compute_regime_alpha(context),
            self.compute_sentiment_alpha(context),
        ]

        # Calculate composite score
        score = sum(c.weighted_value for c in components)

        # Clamp to [-1.0, 1.0]
        score = max(-1.0, min(1.0, score))

        # Determine signal
        if score >= self.STRONG_BUY_THRESHOLD:
            signal = 'STRONG_BUY'
        elif score >= self.threshold:
            signal = 'BUY'
        elif score <= self.SELL_THRESHOLD:
            signal = 'SELL'
        else:
            signal = 'HOLD'

        # Build reasoning string
        reasoning = self._build_reasoning(components, score, signal)

        # Add hard filter info to reasoning if blocked
        if not hard_filter_passed:
            reasoning = f"BLOCKED ({hard_filter_reason}) - {reasoning}"

        return {
            'score': round(score, 3),
            'signal': signal,
            'components': components,
            'reasoning': reasoning,
            'hard_filter_passed': hard_filter_passed,
            'hard_filter_reason': hard_filter_reason
        }

    def compute_breakout_alpha(self, context: AlphaContext) -> AlphaResult:
        """
        Compute breakout alpha based on price position within range.

        Returns +1.0 when price is at range high (bullish breakout potential)
        Returns -1.0 when price is at range low (bearish breakdown potential)
        Returns 0.0 when price is at midpoint
        """
        if context.range_high is None or context.range_low is None:
            return AlphaResult(
                name='breakout',
                value=0.0,
                weight=self.weights['breakout'],
                confidence=0.0  # No data = no confidence
            )

        range_size = context.range_high - context.range_low
        if range_size <= 0:
            return AlphaResult(
                name='breakout',
                value=0.0,
                weight=self.weights['breakout'],
                confidence=0.5
            )

        # Midpoint of the range
        midpoint = (context.range_high + context.range_low) / 2

        # Distance from midpoint as ratio of half-range
        half_range = range_size / 2
        distance = context.current_price - midpoint

        # Normalize to -1.0 to +1.0
        value = distance / half_range
        value = max(-1.0, min(1.0, value))

        return AlphaResult(
            name='breakout',
            value=value,
            weight=self.weights['breakout'],
            confidence=1.0
        )

    def compute_volume_alpha(self, context: AlphaContext) -> AlphaResult:
        """
        Compute volume alpha based on relative volume.

        High volume (>1.5x) confirms direction = +0.5 (bullish if price up)
        Normal volume (0.8-1.5x) = 0.0 (neutral)
        Low volume (<0.8x) = -0.3 (weak signal, less confidence)
        """
        rel_vol = context.relative_volume

        if rel_vol >= 2.0:
            # Very high volume - strong confirmation
            price_up = len(context.prices) >= 2 and context.current_price > context.prices[-2]
            value = 0.8 if price_up else -0.3
            confidence = 1.0
        elif rel_vol >= 1.5:
            # High volume - confirmation
            price_up = len(context.prices) >= 2 and context.current_price > context.prices[-2]
            value = 0.5 if price_up else -0.2
            confidence = 0.9
        elif rel_vol >= 0.8:
            # Normal volume - neutral
            value = 0.0
            confidence = 0.7
        else:
            # Low volume - weak/unreliable signal
            value = -0.3
            confidence = 0.5

        return AlphaResult(
            name='volume',
            value=value,
            weight=self.weights['volume'],
            confidence=confidence
        )

    def compute_atr_alpha(self, context: AlphaContext) -> AlphaResult:
        """
        Compute ATR momentum alpha.

        Higher ATR = more volatility = stronger breakout potential
        ATR >= 0.5% -> +0.5 (strong momentum)
        ATR >= 0.25% -> +0.2 (moderate momentum)
        ATR < 0.25% -> -0.3 (low volatility, avoid)
        """
        atr_pct = context.atr_pct

        if atr_pct >= 0.005:  # 0.5%
            value = 0.5
            confidence = 1.0
        elif atr_pct >= 0.0025:  # 0.25%
            value = 0.2
            confidence = 0.8
        elif atr_pct >= 0.001:  # 0.1%
            value = 0.0
            confidence = 0.6
        else:
            value = -0.3  # Low volatility = avoid trading
            confidence = 0.5

        return AlphaResult(
            name='atr',
            value=value,
            weight=self.weights['atr'],
            confidence=confidence
        )

    def compute_rsi_alpha(self, context: AlphaContext) -> AlphaResult:
        """
        Compute RSI momentum alpha.

        RSI 30-40 = oversold = bullish (+0.5)
        RSI 40-60 = neutral (0.0)
        RSI 60-70 = slightly overbought (-0.2)
        RSI >70 = overbought = bearish (-0.5)
        RSI <30 = extremely oversold = very bullish (+0.8)
        """
        rsi = context.rsi

        if rsi < 30:
            value = 0.8  # Extremely oversold - strong buy
            confidence = 0.9
        elif rsi < 40:
            value = 0.5  # Oversold - bullish
            confidence = 0.85
        elif rsi <= 60:
            value = 0.0  # Neutral
            confidence = 0.7
        elif rsi <= 70:
            value = -0.2  # Slightly overbought
            confidence = 0.75
        else:
            value = -0.5  # Overbought - bearish
            confidence = 0.85

        return AlphaResult(
            name='rsi',
            value=value,
            weight=self.weights['rsi'],
            confidence=confidence
        )

    def compute_regime_alpha(self, context: AlphaContext) -> AlphaResult:
        """
        Compute market regime alpha.

        BULL market = +0.5 (favor buying)
        BEAR market = -0.5 (favor selling/avoiding)
        UNKNOWN = 0.0 (neutral)
        """
        regime = context.regime.upper()

        if regime == 'BULL':
            value = 0.5
            confidence = 0.9
        elif regime == 'BEAR':
            value = -0.5
            confidence = 0.9
        else:
            value = 0.0
            confidence = 0.5

        return AlphaResult(
            name='regime',
            value=value,
            weight=self.weights['regime'],
            confidence=confidence
        )

    def compute_sentiment_alpha(self, context: AlphaContext) -> AlphaResult:
        """
        Compute news sentiment alpha.

        Uses VADER sentiment score directly (-1.0 to +1.0).
        Positive news = bullish, Negative news = bearish.
        """
        sentiment = context.news_sentiment

        # Clamp to [-1.0, 1.0]
        value = max(-1.0, min(1.0, sentiment))

        # Confidence based on absolute sentiment value
        # Strong sentiment = more confident
        confidence = 0.5 + abs(value) * 0.5

        return AlphaResult(
            name='sentiment',
            value=value,
            weight=self.weights['sentiment'],
            confidence=confidence
        )

    def _build_reasoning(self, components: List[AlphaResult], score: float, signal: str) -> str:
        """Build human-readable reasoning for the alpha decision."""
        # Sort by absolute weighted contribution
        sorted_components = sorted(
            components,
            key=lambda c: abs(c.weighted_value),
            reverse=True
        )

        # Get top 2 contributors
        top_factors = []
        for c in sorted_components[:2]:
            direction = "bullish" if c.value > 0 else "bearish" if c.value < 0 else "neutral"
            top_factors.append(f"{c.name}({direction}: {c.value:+.2f})")

        return f"Alpha {score:+.2f} -> {signal}: {', '.join(top_factors)}"

    def get_action_for_signal(self, alpha_result: Dict, raw_signal: str, position: int) -> str:
        """
        Determine trading action based on alpha score and raw signal.

        Args:
            alpha_result: Result from compute_alpha()
            raw_signal: Raw signal from strategy (BUY, SELL, HOLD, STOP_LOSS, etc.)
            position: Current position (0 = no position, >0 = long)

        Returns:
            Action to take (BUY, SELL, HOLD)
        """
        if not self.enabled:
            # If alpha engine disabled, use raw signal
            if raw_signal in ('BUY', 'SELL', 'STOP_LOSS', 'TRAILING_STOP'):
                return raw_signal if raw_signal != 'STOP_LOSS' and raw_signal != 'TRAILING_STOP' else 'SELL'
            return 'HOLD'

        score = alpha_result['score']
        alpha_signal = alpha_result['signal']
        hard_filter_passed = alpha_result.get('hard_filter_passed', True)
        hard_filter_reason = alpha_result.get('hard_filter_reason')

        # Stop-loss and trailing stop always execute (risk management)
        if raw_signal in ('STOP_LOSS', 'TRAILING_STOP'):
            return 'SELL'

        # BUY logic: Need raw BUY signal AND alpha confirmation AND hard filters pass
        if raw_signal == 'BUY' and position == 0:
            # Check hard filters first
            if not hard_filter_passed:
                logger.info(f"BUY blocked by hard filter: {hard_filter_reason}")
                return 'HOLD'

            # Check alpha threshold
            if score >= self.threshold:
                logger.info(f"BUY confirmed: Alpha {score:.2f} >= {self.threshold}")
                return 'BUY'
            else:
                logger.info(f"BUY blocked: Alpha {score:.2f} < {self.threshold}")
                return 'HOLD'

        # SELL logic: Either alpha says SELL or raw signal says SELL
        if raw_signal == 'SELL' and position > 0:
            if score <= self.SELL_THRESHOLD:
                logger.info(f"SELL confirmed: Alpha {score:.2f} <= {self.SELL_THRESHOLD}")
                return 'SELL'
            # Even if alpha doesn't confirm, respect raw SELL signal
            logger.info(f"SELL on raw signal (alpha {score:.2f})")
            return 'SELL'

        # Alpha-initiated SELL (even without raw SELL signal)
        if position > 0 and score <= self.SELL_THRESHOLD:
            logger.info(f"SELL initiated by alpha: {score:.2f}")
            return 'SELL'

        return 'HOLD'


# Singleton instance
alpha_engine = MicroAlphaEngine()
