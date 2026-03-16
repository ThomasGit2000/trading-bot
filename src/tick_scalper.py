"""
Tick Scalper Strategy - Fast momentum scalping on tick data.

Designed for per-tick execution with:
- Quick entries on momentum bursts
- Tight stops (0.05-0.1%)
- Fast exits (target or timeout)
- No overnight holds
"""
import os
import time
import logging
from collections import deque
from dataclasses import dataclass
from typing import Optional, Dict

logger = logging.getLogger(__name__)


@dataclass
class ScalpPosition:
    """Track a scalp position."""
    entry_price: float
    entry_time: float
    shares: int
    direction: str  # 'LONG' or 'SHORT'
    peak_price: float
    ticks_held: int = 0


class TickScalper:
    """
    Fast momentum scalping strategy for tick data.

    Entry: Price moves X% in Y ticks (momentum burst)
    Exit: Target hit, stop hit, or max hold time reached
    """

    def __init__(self):
        # Load config from environment
        self.enabled = os.getenv('SCALP_ENABLED', 'true').lower() == 'true'

        # Strategy type: 'MOMENTUM' or 'MEAN_REVERSION'
        self.strategy = os.getenv('SCALP_STRATEGY', 'MEAN_REVERSION')

        # Entry parameters (MEAN_REVERSION: buy dips, MOMENTUM: buy breakouts)
        self.lookback_ticks = int(os.getenv('SCALP_LOOKBACK_TICKS', '20'))  # Ticks to measure move
        self.entry_threshold = float(os.getenv('SCALP_ENTRY_PCT', '0.15')) / 100  # 0.15% move triggers entry
        self.min_volume_ratio = float(os.getenv('SCALP_MIN_VOLUME', '1.0'))  # Min relative volume

        # Exit parameters
        self.target_pct = float(os.getenv('SCALP_TARGET_PCT', '0.08')) / 100  # 0.08% target
        self.stop_pct = float(os.getenv('SCALP_STOP_PCT', '0.10')) / 100  # 0.10% stop
        self.max_hold_ticks = int(os.getenv('SCALP_MAX_HOLD_TICKS', '50'))  # ~5 seconds
        self.trail_after_pct = float(os.getenv('SCALP_TRAIL_AFTER', '0.04')) / 100  # Trail after 0.04%
        self.trail_pct = float(os.getenv('SCALP_TRAIL_PCT', '0.02')) / 100  # 0.02% trailing stop

        # Cooldown
        self.cooldown_ticks = int(os.getenv('SCALP_COOLDOWN_TICKS', '30'))  # Ticks between trades

        # State per symbol
        self._prices: Dict[str, deque] = {}  # symbol -> recent prices
        self._volumes: Dict[str, deque] = {}  # symbol -> recent volumes
        self._positions: Dict[str, Optional[ScalpPosition]] = {}  # symbol -> position
        self._cooldowns: Dict[str, int] = {}  # symbol -> ticks until can trade
        self._stats: Dict[str, dict] = {}  # symbol -> {wins, losses, pnl}

        if self.enabled:
            logger.info(f"TickScalper ENABLED - Strategy: {self.strategy}")
            if self.strategy == 'MEAN_REVERSION':
                logger.info(f"  Entry: Buy when price DROPS {self.entry_threshold*100:.2f}% in {self.lookback_ticks} ticks")
            else:
                logger.info(f"  Entry: Buy when price RISES {self.entry_threshold*100:.2f}% in {self.lookback_ticks} ticks")
            logger.info(f"  Exit: Target {self.target_pct*100:.2f}%, Stop {self.stop_pct*100:.2f}%, Max {self.max_hold_ticks} ticks")
            logger.info(f"  Trail: After {self.trail_after_pct*100:.2f}%, trail {self.trail_pct*100:.2f}%")

    def _get_or_create_state(self, symbol: str):
        """Initialize state for a symbol."""
        if symbol not in self._prices:
            self._prices[symbol] = deque(maxlen=self.lookback_ticks + 50)
            self._volumes[symbol] = deque(maxlen=100)
            self._positions[symbol] = None
            self._cooldowns[symbol] = 0
            self._stats[symbol] = {'wins': 0, 'losses': 0, 'pnl': 0.0}

    def on_tick(self, symbol: str, price: float, volume: float = 0) -> dict:
        """
        Process a tick and return trading action.

        Returns:
            {
                'action': 'BUY' | 'SELL' | 'HOLD',
                'reason': str,
                'position': ScalpPosition or None
            }
        """
        self._get_or_create_state(symbol)

        # Update price history
        self._prices[symbol].append(price)
        if volume > 0:
            self._volumes[symbol].append(volume)

        # Decrease cooldown
        if self._cooldowns[symbol] > 0:
            self._cooldowns[symbol] -= 1

        # Check if we have a position
        pos = self._positions[symbol]

        if pos is not None:
            # Manage existing position
            return self._manage_position(symbol, price, pos)
        else:
            # Look for entry
            return self._check_entry(symbol, price)

    def _check_entry(self, symbol: str, price: float) -> dict:
        """Check for scalp entry signal."""
        prices = self._prices[symbol]

        # Need enough history
        if len(prices) < self.lookback_ticks:
            return {'action': 'HOLD', 'reason': 'collecting_data', 'position': None}

        # Check cooldown
        if self._cooldowns[symbol] > 0:
            return {'action': 'HOLD', 'reason': f'cooldown_{self._cooldowns[symbol]}', 'position': None}

        # Calculate price change
        old_price = prices[-self.lookback_ticks]
        price_change = (price - old_price) / old_price

        # Check for entry signal based on strategy
        entry_signal = False

        if self.strategy == 'MEAN_REVERSION':
            # Buy when price DROPS (negative change)
            if price_change <= -self.entry_threshold:
                entry_signal = True
                signal_reason = f'dip_{price_change*100:.2f}%'
        else:
            # MOMENTUM: Buy when price RISES (positive change)
            if price_change >= self.entry_threshold:
                entry_signal = True
                signal_reason = f'momentum_{price_change*100:.2f}%'

        if entry_signal:
            # Check volume if available
            volumes = self._volumes[symbol]
            if len(volumes) >= 20:
                recent_vol = sum(list(volumes)[-10:]) / 10
                avg_vol = sum(volumes) / len(volumes)
                vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

                if vol_ratio < self.min_volume_ratio:
                    return {'action': 'HOLD', 'reason': f'low_volume_{vol_ratio:.2f}', 'position': None}

            # Entry signal!
            return {
                'action': 'BUY',
                'reason': signal_reason,
                'position': None,
                'price_change': price_change
            }

        return {'action': 'HOLD', 'reason': 'no_signal', 'position': None}

    def _manage_position(self, symbol: str, price: float, pos: ScalpPosition) -> dict:
        """Manage existing scalp position."""
        pos.ticks_held += 1

        # Update peak
        if price > pos.peak_price:
            pos.peak_price = price

        pnl_pct = (price - pos.entry_price) / pos.entry_price

        # Check stop loss
        if pnl_pct <= -self.stop_pct:
            return self._exit_position(symbol, price, 'stop_loss', pnl_pct)

        # Check target
        if pnl_pct >= self.target_pct:
            return self._exit_position(symbol, price, 'target', pnl_pct)

        # Check trailing stop (after minimum profit)
        if pnl_pct >= self.trail_after_pct:
            peak_pnl = (pos.peak_price - pos.entry_price) / pos.entry_price
            drawdown = (pos.peak_price - price) / pos.peak_price

            if drawdown >= self.trail_pct:
                return self._exit_position(symbol, price, 'trailing', pnl_pct)

        # Check max hold time
        if pos.ticks_held >= self.max_hold_ticks:
            return self._exit_position(symbol, price, 'timeout', pnl_pct)

        return {'action': 'HOLD', 'reason': f'holding_{pos.ticks_held}', 'position': pos}

    def _exit_position(self, symbol: str, price: float, reason: str, pnl_pct: float) -> dict:
        """Exit a position and record stats."""
        pos = self._positions[symbol]

        # Update stats
        if pnl_pct > 0:
            self._stats[symbol]['wins'] += 1
        else:
            self._stats[symbol]['losses'] += 1
        self._stats[symbol]['pnl'] += pnl_pct * 100

        # Clear position
        self._positions[symbol] = None

        # Set cooldown
        self._cooldowns[symbol] = self.cooldown_ticks

        logger.info(f"[SCALP] {symbol}: EXIT {reason} @ ${price:.2f} | P&L: {pnl_pct*100:+.2f}% | Held: {pos.ticks_held} ticks")

        return {
            'action': 'SELL',
            'reason': reason,
            'position': pos,
            'pnl_pct': pnl_pct
        }

    def enter_position(self, symbol: str, price: float, shares: int):
        """Record entry of a position."""
        self._get_or_create_state(symbol)

        self._positions[symbol] = ScalpPosition(
            entry_price=price,
            entry_time=time.time(),
            shares=shares,
            direction='LONG',
            peak_price=price,
            ticks_held=0
        )

        logger.info(f"[SCALP] {symbol}: ENTRY @ ${price:.2f} | {shares} shares")

    def get_position(self, symbol: str) -> Optional[ScalpPosition]:
        """Get current position for symbol."""
        return self._positions.get(symbol)

    def get_stats(self, symbol: str = None) -> dict:
        """Get trading stats."""
        if symbol:
            stats = self._stats.get(symbol, {'wins': 0, 'losses': 0, 'pnl': 0.0})
            total = stats['wins'] + stats['losses']
            stats['win_rate'] = stats['wins'] / total * 100 if total > 0 else 0
            return stats
        else:
            # Aggregate all symbols
            total_wins = sum(s['wins'] for s in self._stats.values())
            total_losses = sum(s['losses'] for s in self._stats.values())
            total_pnl = sum(s['pnl'] for s in self._stats.values())
            total = total_wins + total_losses
            return {
                'wins': total_wins,
                'losses': total_losses,
                'pnl': total_pnl,
                'win_rate': total_wins / total * 100 if total > 0 else 0
            }

    def sync_positions(self, ibkr_positions: list):
        """Sync existing IBKR positions so stop-loss works on bot restart.

        Args:
            ibkr_positions: List of (symbol, shares, avg_cost) tuples
        """
        synced = 0
        for symbol, shares, avg_cost in ibkr_positions:
            if shares > 0 and avg_cost > 0:
                self._get_or_create_state(symbol)

                # Only sync if we don't already have a position tracked
                if self._positions.get(symbol) is None:
                    self._positions[symbol] = ScalpPosition(
                        entry_price=avg_cost,
                        entry_time=time.time(),
                        shares=int(shares),
                        direction='LONG',
                        peak_price=avg_cost,  # Conservative - use avg cost as peak
                        ticks_held=0
                    )
                    synced += 1
                    logger.info(f"[SCALP] {symbol}: SYNCED existing position - {int(shares)} shares @ ${avg_cost:.2f}")

        if synced > 0:
            logger.info(f"[SCALP] Synced {synced} existing positions for stop-loss tracking")


# Singleton
tick_scalper = TickScalper()
