"""
Hybrid Strategy: Combines trend-following with mean-reversion scalping

This strategy aims to capture both:
1. Big trends (buy & hold core position)
2. Short-term swings (active scalping)

Best of both worlds approach.
"""
import logging
from datetime import datetime, timedelta
from typing import Tuple

logger = logging.getLogger(__name__)


class HybridStrategy:
    """
    Hybrid Strategy combining:
    - Core Position: Trend-following (50-70% of capital)
    - Scalp Position: Mean-reversion RSI (30-50% of capital)

    Parameters optimized from backtesting:
    - RSI(7) for quick signals
    - 20/80 thresholds (more extreme = higher win rate)
    - 1.5% stop-loss, 2.5% take-profit for scalps
    - 10% trailing stop for core position
    """

    def __init__(self,
                 # Core position settings
                 core_allocation: float = 0.6,  # 60% for trend-following
                 core_entry_rsi: int = 40,      # Buy core when RSI < 40
                 core_trailing_stop: float = 0.10,
                 # Scalp settings
                 scalp_rsi_period: int = 7,
                 scalp_oversold: int = 20,
                 scalp_overbought: int = 80,
                 scalp_stop_loss: float = 0.015,
                 scalp_take_profit: float = 0.025,
                 # General
                 rsi_period: int = 14):

        # Core position
        self.core_allocation = core_allocation
        self.core_entry_rsi = core_entry_rsi
        self.core_trailing_stop = core_trailing_stop
        self.core_position = 0
        self.core_entry_price = 0
        self.core_peak_price = 0

        # Scalp position
        self.scalp_rsi_period = scalp_rsi_period
        self.scalp_oversold = scalp_oversold
        self.scalp_overbought = scalp_overbought
        self.scalp_stop_loss = scalp_stop_loss
        self.scalp_take_profit = scalp_take_profit
        self.scalp_position = 0
        self.scalp_entry_price = 0
        self.scalp_entry_time = None

        # Price history
        self.prices = []
        self.rsi_period = rsi_period

        self.name = f"Hybrid(Core:{int(core_allocation*100)}% + Scalp RSI({scalp_rsi_period}) {scalp_oversold}/{scalp_overbought})"

    def add_price(self, price: float):
        """Add new price to history"""
        self.prices.append(price)

        # Update core peak
        if self.core_position > 0 and price > self.core_peak_price:
            self.core_peak_price = price

        # Keep limited history
        max_prices = max(self.rsi_period, self.scalp_rsi_period) * 5
        if len(self.prices) > max_prices:
            self.prices = self.prices[-max_prices:]

    def calculate_rsi(self, period: int) -> float:
        """Calculate RSI for given period"""
        if len(self.prices) < period + 1:
            return 50

        gains, losses = [], []
        for i in range(-period, 0):
            change = self.prices[i] - self.prices[i-1]
            gains.append(max(0, change))
            losses.append(max(0, -change))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def get_ma(self, period: int) -> float:
        """Get simple moving average"""
        if len(self.prices) < period:
            return self.prices[-1] if self.prices else 0
        return sum(self.prices[-period:]) / period

    def get_core_signal(self) -> str:
        """Get signal for core (trend-following) position"""
        if len(self.prices) < 50:
            return 'HOLD'

        price = self.prices[-1]
        rsi = self.calculate_rsi(self.rsi_period)
        ma50 = self.get_ma(50)
        ma20 = self.get_ma(20)

        # If in position, check for exit
        if self.core_position > 0:
            # Trailing stop
            if self.core_peak_price > 0:
                drop = (self.core_peak_price - price) / self.core_peak_price
                if drop >= self.core_trailing_stop:
                    return 'CORE_EXIT_TRAIL'

            # Exit if trend reverses (price below MA50 and RSI weak)
            if price < ma50 * 0.95 and rsi > 50:
                return 'CORE_EXIT_TREND'

        # Entry: RSI oversold + price above MA50 (uptrend intact)
        elif rsi < self.core_entry_rsi and price > ma50 and ma20 > ma50:
            return 'CORE_BUY'

        return 'HOLD'

    def get_scalp_signal(self) -> str:
        """Get signal for scalp (mean-reversion) position"""
        if len(self.prices) < self.scalp_rsi_period + 5:
            return 'HOLD'

        price = self.prices[-1]
        rsi = self.calculate_rsi(self.scalp_rsi_period)
        ma20 = self.get_ma(20)

        # If in scalp position, check exits
        if self.scalp_position > 0 and self.scalp_entry_price > 0:
            pnl_pct = (price - self.scalp_entry_price) / self.scalp_entry_price

            # Stop-loss
            if pnl_pct <= -self.scalp_stop_loss:
                return 'SCALP_EXIT_SL'

            # Take-profit
            if pnl_pct >= self.scalp_take_profit:
                return 'SCALP_EXIT_TP'

            # RSI exit (overbought)
            if rsi > self.scalp_overbought:
                return 'SCALP_EXIT_RSI'

        # Entry: RSI oversold + some trend confirmation
        elif rsi < self.scalp_oversold and price > self.prices[-3]:  # Bouncing
            return 'SCALP_BUY'

        return 'HOLD'

    def get_signal(self) -> Tuple[str, str]:
        """Get both core and scalp signals

        Returns:
            Tuple of (core_signal, scalp_signal)
        """
        core_signal = self.get_core_signal()
        scalp_signal = self.get_scalp_signal()
        return core_signal, scalp_signal

    def enter_core(self, price: float, quantity: int):
        """Record core position entry"""
        self.core_position = quantity
        self.core_entry_price = price
        self.core_peak_price = price
        logger.info(f"CORE: Entered {quantity} shares at ${price:.2f}")

    def exit_core(self, reason: str = ""):
        """Record core position exit"""
        logger.info(f"CORE: Exited ({reason})")
        self.core_position = 0
        self.core_entry_price = 0
        self.core_peak_price = 0

    def enter_scalp(self, price: float, quantity: int):
        """Record scalp position entry"""
        self.scalp_position = quantity
        self.scalp_entry_price = price
        self.scalp_entry_time = datetime.now()
        logger.info(f"SCALP: Entered {quantity} shares at ${price:.2f}")

    def exit_scalp(self, reason: str = ""):
        """Record scalp position exit"""
        logger.info(f"SCALP: Exited ({reason})")
        self.scalp_position = 0
        self.scalp_entry_price = 0
        self.scalp_entry_time = None

    def get_status(self) -> dict:
        """Get current strategy status"""
        price = self.prices[-1] if self.prices else 0

        core_pnl = 0
        if self.core_position > 0 and self.core_entry_price > 0:
            core_pnl = (price - self.core_entry_price) / self.core_entry_price * 100

        scalp_pnl = 0
        if self.scalp_position > 0 and self.scalp_entry_price > 0:
            scalp_pnl = (price - self.scalp_entry_price) / self.scalp_entry_price * 100

        return {
            'core_position': self.core_position,
            'core_entry': self.core_entry_price,
            'core_peak': self.core_peak_price,
            'core_pnl_pct': core_pnl,
            'scalp_position': self.scalp_position,
            'scalp_entry': self.scalp_entry_price,
            'scalp_pnl_pct': scalp_pnl,
            'rsi_14': self.calculate_rsi(14),
            'rsi_7': self.calculate_rsi(7),
            'price': price,
        }


# Quick test
if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.yfinance_client import YFinanceClient

    logging.basicConfig(level=logging.INFO)

    print("="*60)
    print("  HYBRID STRATEGY BACKTEST")
    print("="*60)

    client = YFinanceClient()
    history = client.get_history('NIO', '1y')

    if not history:
        print("Failed to get data")
        exit()

    prices = [bar['close'] for bar in history]
    dates = [bar['date'] for bar in history]

    strategy = HybridStrategy()

    capital = 10000
    core_capital = capital * 0.6
    scalp_capital = capital * 0.4

    core_shares = 0
    scalp_shares = 0
    trades = []

    for i, price in enumerate(prices):
        strategy.add_price(price)

        if i < 50:
            continue

        core_sig, scalp_sig = strategy.get_signal()

        # Core trades
        if core_sig == 'CORE_BUY' and core_shares == 0:
            core_shares = int(core_capital / price)
            strategy.enter_core(price, core_shares)
            trades.append(('CORE_BUY', dates[i], price))

        elif core_sig.startswith('CORE_EXIT') and core_shares > 0:
            pnl = core_shares * (price - strategy.core_entry_price)
            strategy.exit_core(core_sig)
            core_capital += core_shares * price
            trades.append(('CORE_SELL', dates[i], price, pnl))
            core_shares = 0

        # Scalp trades
        if scalp_sig == 'SCALP_BUY' and scalp_shares == 0:
            scalp_shares = min(100, int(scalp_capital / price))
            strategy.enter_scalp(price, scalp_shares)
            trades.append(('SCALP_BUY', dates[i], price))

        elif scalp_sig.startswith('SCALP_EXIT') and scalp_shares > 0:
            pnl = scalp_shares * (price - strategy.scalp_entry_price)
            strategy.exit_scalp(scalp_sig)
            scalp_capital += scalp_shares * price
            trades.append(('SCALP_SELL', dates[i], price, pnl))
            scalp_shares = 0

    # Close positions
    if core_shares > 0:
        core_capital += core_shares * prices[-1]
    if scalp_shares > 0:
        scalp_capital += scalp_shares * prices[-1]

    final = core_capital + scalp_capital
    ret = (final - 10000) / 10000 * 100
    bh = (prices[-1] - prices[0]) / prices[0] * 100

    print(f"\nResults:")
    print(f"  Initial: $10,000")
    print(f"  Final: ${final:.2f}")
    print(f"  Return: {ret:+.2f}%")
    print(f"  Buy & Hold: {bh:+.2f}%")
    print(f"  Trades: {len([t for t in trades if 'SELL' in t[0]])}")
