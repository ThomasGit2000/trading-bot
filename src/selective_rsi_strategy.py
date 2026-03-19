"""
Selective RSI Strategy - Buy oversold with volume confirmation

Strategy Logic:
- BUY when: RSI < 25 AND relative volume > 1.0x AND ATR > 1%
- SELL when: RSI > 70 OR profit target (+12%) OR stop loss (-8%)
- Max 5 concurrent positions
- Prioritize most oversold stocks

Backtest Results (14 days, 71 stocks):
- 23 trades, 65.2% win rate, +$192.66 profit
- ~$14/day on $7,246 capital = 48% annualized
"""

import numpy as np
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple


@dataclass
class SelectiveRSIConfig:
    """Configuration for Selective RSI Strategy."""
    rsi_period: int = 14
    rsi_oversold: float = 25.0      # Buy when RSI < this (BULL/NEUTRAL)
    rsi_oversold_bear: float = 15.0 # Buy when RSI < this (BEAR market - stricter)
    rsi_overbought: float = 70.0    # Sell when RSI > this
    volume_multiplier: float = 1.0  # Min relative volume
    atr_min_pct: float = 0.01       # Min ATR as % of price (1%)
    atr_period: int = 14
    stop_loss_pct: float = 0.08     # 8% stop loss
    profit_target_pct: float = 0.12 # 12% profit target
    max_positions: int = 5          # Max concurrent positions
    lookback: int = 50              # Price history to keep
    bar_interval_sec: int = 60      # Aggregate ticks into 1-minute bars


class SelectiveRSIStrategy:
    """
    Selective RSI Mean Reversion Strategy.

    Buys oversold stocks with volume confirmation and sufficient volatility.
    Exits on overbought, profit target, or stop loss.
    """

    def __init__(self, config: Optional[SelectiveRSIConfig] = None):
        self.config = config or SelectiveRSIConfig()

        # Per-symbol completed bars (for RSI calculation)
        self.prices: Dict[str, deque] = {}
        self.highs: Dict[str, deque] = {}
        self.lows: Dict[str, deque] = {}
        self.volumes: Dict[str, deque] = {}

        # Current bar being built (tick aggregation)
        self._current_bar: Dict[str, Dict] = {}  # symbol -> {open, high, low, close, volume, start_time}

        # Computed indicators (cached)
        self._rsi_cache: Dict[str, float] = {}
        self._atr_cache: Dict[str, float] = {}
        self._rel_vol_cache: Dict[str, float] = {}

        # Today's cumulative volume (from IBKR ticker.volume)
        self._today_volume: Dict[str, float] = {}

    def _init_symbol(self, symbol: str):
        """Initialize data structures for a new symbol."""
        if symbol not in self.prices:
            self.prices[symbol] = deque(maxlen=self.config.lookback)
            self.highs[symbol] = deque(maxlen=self.config.lookback)
            self.lows[symbol] = deque(maxlen=self.config.lookback)
            self.volumes[symbol] = deque(maxlen=self.config.lookback)

    def add_bar(self, symbol: str, close: float, high: float, low: float, volume: float):
        """
        Add tick data - aggregates into bars based on bar_interval_sec.
        Only adds completed bars to price history for RSI calculation.
        """
        self._init_symbol(symbol)
        current_time = time.time()

        # Initialize current bar if needed
        if symbol not in self._current_bar:
            self._current_bar[symbol] = {
                'open': close,
                'high': high,
                'low': low,
                'close': close,
                'volume': volume,
                'start_time': current_time
            }
            return

        bar = self._current_bar[symbol]

        # Update current bar with tick data
        bar['high'] = max(bar['high'], high)
        bar['low'] = min(bar['low'], low)
        bar['close'] = close
        bar['volume'] += volume

        # Check if bar interval has elapsed
        if current_time - bar['start_time'] >= self.config.bar_interval_sec:
            # Complete the bar - add to history for RSI/ATR calculation
            self.prices[symbol].append(bar['close'])
            self.highs[symbol].append(bar['high'])
            self.lows[symbol].append(bar['low'])
            # NOTE: Don't append minute volumes to daily volumes deque!
            # The volumes deque contains daily volumes from historical data.
            # Mixing minute volumes (thousands) with daily volumes (millions)
            # corrupts the relative volume calculation.
            # self.volumes[symbol].append(bar['volume'])  # DISABLED

            # Clear cache for RSI and ATR (prices changed)
            # But keep rel_vol cache (volumes unchanged - still daily data)
            self._rsi_cache.pop(symbol, None)
            self._atr_cache.pop(symbol, None)
            # self._rel_vol_cache.pop(symbol, None)  # Keep rel_vol cache

            # Start new bar
            self._current_bar[symbol] = {
                'open': close,
                'high': high,
                'low': low,
                'close': close,
                'volume': volume,
                'start_time': current_time
            }

    def add_historical_bar(self, symbol: str, close: float, high: float, low: float, volume: float):
        """Add a completed historical bar directly (no aggregation)."""
        self._init_symbol(symbol)

        self.prices[symbol].append(close)
        self.highs[symbol].append(high)
        self.lows[symbol].append(low)
        self.volumes[symbol].append(volume)

        # Clear cache for this symbol
        self._rsi_cache.pop(symbol, None)
        self._atr_cache.pop(symbol, None)
        self._rel_vol_cache.pop(symbol, None)

    def update_today_volume(self, symbol: str, cumulative_volume: float):
        """Update today's cumulative volume from IBKR ticker.volume."""
        if cumulative_volume and cumulative_volume > 0:
            self._today_volume[symbol] = cumulative_volume
            # Clear rel_vol cache when today's volume updates
            self._rel_vol_cache.pop(symbol, None)

    def add_price(self, symbol: str, price: float, volume: float = 0):
        """Add price tick (uses price for high/low)."""
        self.add_bar(symbol, price, price, price, volume)

    def compute_rsi(self, symbol: str, include_current_bar: bool = False) -> Optional[float]:
        """Compute RSI for a symbol using completed bars only."""
        if not include_current_bar and symbol in self._rsi_cache:
            return self._rsi_cache[symbol]

        if symbol not in self.prices:
            return None

        prices = list(self.prices[symbol])

        # Optionally include current bar's close for real-time display
        if include_current_bar and symbol in self._current_bar:
            prices = prices + [self._current_bar[symbol]['close']]

        period = self.config.rsi_period

        if len(prices) < period + 1:
            return None

        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        if not include_current_bar:
            self._rsi_cache[symbol] = rsi
        return rsi

    def get_bars_count(self, symbol: str) -> int:
        """Get number of completed bars for a symbol."""
        if symbol not in self.prices:
            return 0
        return len(self.prices[symbol])

    def compute_atr(self, symbol: str) -> Optional[float]:
        """Compute ATR for a symbol."""
        if symbol in self._atr_cache:
            return self._atr_cache[symbol]

        if symbol not in self.prices:
            return None

        closes = list(self.prices[symbol])
        highs = list(self.highs[symbol])
        lows = list(self.lows[symbol])
        period = self.config.atr_period

        if len(closes) < period + 1:
            return None

        trs = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            trs.append(tr)

        atr = np.mean(trs[-period:])
        self._atr_cache[symbol] = atr
        return atr

    def compute_atr_pct(self, symbol: str) -> Optional[float]:
        """Compute ATR as percentage of current price."""
        atr = self.compute_atr(symbol)
        if atr is None or symbol not in self.prices or not self.prices[symbol]:
            return None

        current_price = self.prices[symbol][-1]
        if current_price <= 0:
            return None

        return atr / current_price

    def compute_relative_volume(self, symbol: str, include_current_bar: bool = False) -> Optional[float]:
        """Compute relative volume vs expected volume for this time of day.

        Uses today's cumulative volume from IBKR (ticker.volume) compared
        against the expected volume at this point in the trading day.
        rel_vol = 1.0 means normal volume for this time of day.
        """
        if not include_current_bar and symbol in self._rel_vol_cache:
            return self._rel_vol_cache[symbol]

        if symbol not in self.volumes:
            return None

        volumes = list(self.volumes[symbol])

        if len(volumes) < 1:
            return None

        # Use today's cumulative volume from IBKR if available
        if symbol in self._today_volume and self._today_volume[symbol] > 0:
            current_vol = self._today_volume[symbol]
        else:
            # Fallback to last historical volume (yesterday)
            current_vol = volumes[-1] if volumes else 0

        # Average of historical daily volumes
        avg_vol = np.mean(volumes) if volumes else 0

        if avg_vol <= 0:
            rel_vol = 1.0
        else:
            # Adjust for time of day (trading hours 9:30-16:00 ET = 390 minutes)
            from datetime import datetime
            import pytz
            et = pytz.timezone('America/New_York')
            now = datetime.now(et)
            market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

            # Calculate elapsed fraction of trading day
            if now < market_open:
                time_fraction = 0.01  # Pre-market, use small fraction
            elif now > market_close:
                time_fraction = 1.0  # After hours, use full day
            else:
                elapsed_minutes = (now - market_open).total_seconds() / 60
                total_minutes = 390  # 6.5 hours
                time_fraction = max(0.01, elapsed_minutes / total_minutes)

            # Expected volume at this time = avg_vol * time_fraction
            expected_vol = avg_vol * time_fraction
            rel_vol = current_vol / expected_vol

        if not include_current_bar:
            self._rel_vol_cache[symbol] = rel_vol
        return rel_vol

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol (uses current bar's close)."""
        # Prefer current bar's close (most recent tick)
        if symbol in self._current_bar:
            return self._current_bar[symbol]['close']
        # Fallback to last completed bar
        if symbol not in self.prices or not self.prices[symbol]:
            return None
        return self.prices[symbol][-1]

    def check_entry_signal(self, symbol: str, regime: str = "NEUTRAL") -> Tuple[bool, Dict]:
        """
        Check if symbol has valid entry signal.

        Args:
            symbol: Stock symbol
            regime: Market regime ("BULL", "BEAR", or "NEUTRAL")

        Returns:
            (should_buy, context_dict)
        """
        # Use include_current_bar=True to match dashboard display
        rsi = self.compute_rsi(symbol, include_current_bar=True)
        rel_vol = self.compute_relative_volume(symbol)
        atr_pct = self.compute_atr_pct(symbol)

        # Regime-adjusted RSI threshold: stricter in bear markets
        if regime == "BEAR":
            rsi_threshold = self.config.rsi_oversold_bear  # 15 in bear
        else:
            rsi_threshold = self.config.rsi_oversold  # 25 in bull/neutral

        context = {
            'rsi': rsi,
            'rel_vol': rel_vol,
            'atr_pct': atr_pct,
            'regime': regime,
            'rsi_threshold': rsi_threshold,
            'filters_passed': False,
            'reason': ''
        }

        # Check all filters
        if rsi is None:
            context['reason'] = 'Insufficient data for RSI'
            return False, context

        if rsi >= rsi_threshold:
            context['reason'] = f'RSI {rsi:.1f} >= {rsi_threshold} ({regime})'
            return False, context

        if rel_vol is None:
            context['reason'] = 'Insufficient data for Volume'
            return False, context
        if rel_vol < self.config.volume_multiplier:
            context['reason'] = f'Volume {rel_vol:.2f}x < {self.config.volume_multiplier}x'
            return False, context

        if atr_pct is None:
            context['reason'] = 'Insufficient data for ATR'
            return False, context
        if atr_pct < self.config.atr_min_pct:
            context['reason'] = f'ATR {atr_pct*100:.2f}% < {self.config.atr_min_pct*100:.1f}%'
            return False, context

        # All filters passed
        context['filters_passed'] = True
        context['reason'] = f'RSI={rsi:.1f}, Vol={rel_vol:.1f}x, ATR={atr_pct*100:.2f}%'
        return True, context

    def check_exit_signal(self, symbol: str, entry_price: float) -> Tuple[bool, str]:
        """
        Check if position should be exited.

        Returns:
            (should_exit, reason)
        """
        current_price = self.get_current_price(symbol)
        if current_price is None:
            return False, ''

        pnl_pct = (current_price - entry_price) / entry_price

        # Check stop loss
        if pnl_pct <= -self.config.stop_loss_pct:
            return True, 'STOP_LOSS'

        # Check profit target
        if pnl_pct >= self.config.profit_target_pct:
            return True, 'TARGET'

        # Check overbought
        rsi = self.compute_rsi(symbol)
        if rsi is not None and rsi >= self.config.rsi_overbought:
            return True, 'OVERBOUGHT'

        return False, ''

    def get_buy_candidates(self, symbols: List[str]) -> List[Tuple[str, float, Dict]]:
        """
        Get list of symbols that pass all entry filters.
        Sorted by RSI (most oversold first).

        Returns:
            List of (symbol, rsi, context) tuples
        """
        candidates = []

        for symbol in symbols:
            should_buy, context = self.check_entry_signal(symbol)
            if should_buy:
                rsi = context['rsi']
                candidates.append((symbol, rsi, context))

        # Sort by RSI (lowest first = most oversold)
        candidates.sort(key=lambda x: x[1])

        return candidates

    def get_indicators(self, symbol: str) -> Dict:
        """Get all indicators for a symbol (for dashboard display)."""
        return {
            'rsi': self.compute_rsi(symbol, include_current_bar=True),  # Real-time RSI for display
            'atr_pct': self.compute_atr_pct(symbol),
            'rel_vol': self.compute_relative_volume(symbol),  # Use cached from completed bars (not current bar - mixes daily/minute volumes)
            'price': self.get_current_price(symbol),
            'bars': self.get_bars_count(symbol)
        }
