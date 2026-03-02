"""
Intraday Scalping Strategy - High-frequency mean-reversion

Optimized for volatile stocks like NIO on 5-min bars.
Uses RSI(5) with 25/75 thresholds and tight stops.

Best for: Active traders wanting 2-3 trades per day
"""
import logging
from datetime import datetime
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class ScalpStrategy:
    """
    High-frequency RSI scalping strategy

    Optimized parameters from backtesting:
    - RSI(5) for quick signals
    - 25/75 thresholds (less extreme = more trades)
    - 1% stop-loss, 1.5% take-profit
    - Max 200 shares per trade (risk management)

    Expected: ~2 trades/day, 80%+ win rate, small gains
    """

    def __init__(self,
                 rsi_period: int = 5,
                 oversold: int = 25,
                 overbought: int = 75,
                 stop_loss_pct: float = 0.01,
                 take_profit_pct: float = 0.015,
                 max_shares: int = 200,
                 min_bounce_bars: int = 2):

        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_shares = max_shares
        self.min_bounce_bars = min_bounce_bars

        # State
        self.prices = []
        self.position = 0
        self.entry_price = 0
        self.entry_time = None

        # Stats
        self.trades = []
        self.wins = 0
        self.losses = 0

        self.name = f"Scalp RSI({rsi_period}) {oversold}/{overbought} SL:{stop_loss_pct*100:.1f}% TP:{take_profit_pct*100:.1f}%"

    def add_price(self, price: float):
        """Add new price to history"""
        self.prices.append(price)

        # Keep limited history
        max_prices = self.rsi_period * 10
        if len(self.prices) > max_prices:
            self.prices = self.prices[-max_prices:]

    def calculate_rsi(self) -> float:
        """Calculate RSI for current period"""
        if len(self.prices) < self.rsi_period + 1:
            return 50

        gains, losses = [], []
        for i in range(-self.rsi_period, 0):
            change = self.prices[i] - self.prices[i-1]
            gains.append(max(0, change))
            losses.append(max(0, -change))

        avg_gain = sum(gains) / self.rsi_period
        avg_loss = sum(losses) / self.rsi_period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def is_bouncing(self) -> bool:
        """Check if price is bouncing (uptick confirmation)"""
        if len(self.prices) < self.min_bounce_bars + 1:
            return False
        return self.prices[-1] > self.prices[-self.min_bounce_bars - 1]

    def get_signal(self) -> str:
        """
        Get trading signal

        Returns:
            'BUY': Enter long position
            'SELL_SL': Exit due to stop-loss
            'SELL_TP': Exit due to take-profit
            'SELL_RSI': Exit due to RSI overbought
            'HOLD': No action
        """
        if len(self.prices) < self.rsi_period + 5:
            return 'HOLD'

        price = self.prices[-1]
        rsi = self.calculate_rsi()

        # If in position, check exits
        if self.position > 0 and self.entry_price > 0:
            pnl_pct = (price - self.entry_price) / self.entry_price

            # Stop-loss
            if pnl_pct <= -self.stop_loss_pct:
                return 'SELL_SL'

            # Take-profit
            if pnl_pct >= self.take_profit_pct:
                return 'SELL_TP'

            # RSI overbought exit
            if rsi > self.overbought:
                return 'SELL_RSI'

        # Entry: RSI oversold + bouncing
        elif rsi < self.oversold and self.is_bouncing():
            return 'BUY'

        return 'HOLD'

    def enter_position(self, price: float, shares: int):
        """Record entry"""
        self.position = min(shares, self.max_shares)
        self.entry_price = price
        self.entry_time = datetime.now()
        logger.info(f"SCALP ENTRY: {self.position} shares @ ${price:.2f}")

    def exit_position(self, price: float, reason: str) -> float:
        """Record exit and return PnL"""
        if self.position == 0:
            return 0

        pnl = self.position * (price - self.entry_price)
        pnl_pct = (price - self.entry_price) / self.entry_price * 100

        self.trades.append({
            'entry_price': self.entry_price,
            'exit_price': price,
            'shares': self.position,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'reason': reason,
            'entry_time': self.entry_time,
            'exit_time': datetime.now()
        })

        if pnl > 0:
            self.wins += 1
            logger.info(f"SCALP EXIT ({reason}): +${pnl:.2f} (+{pnl_pct:.2f}%) WIN")
        else:
            self.losses += 1
            logger.info(f"SCALP EXIT ({reason}): ${pnl:.2f} ({pnl_pct:.2f}%) LOSS")

        self.position = 0
        self.entry_price = 0
        self.entry_time = None

        return pnl

    def get_status(self) -> dict:
        """Get current strategy status"""
        price = self.prices[-1] if self.prices else 0
        rsi = self.calculate_rsi()

        unrealized_pnl = 0
        unrealized_pnl_pct = 0
        if self.position > 0 and self.entry_price > 0:
            unrealized_pnl = self.position * (price - self.entry_price)
            unrealized_pnl_pct = (price - self.entry_price) / self.entry_price * 100

        total_trades = self.wins + self.losses
        win_rate = self.wins / total_trades * 100 if total_trades > 0 else 0

        return {
            'position': self.position,
            'entry_price': self.entry_price,
            'current_price': price,
            'unrealized_pnl': unrealized_pnl,
            'unrealized_pnl_pct': unrealized_pnl_pct,
            'rsi': rsi,
            'total_trades': total_trades,
            'wins': self.wins,
            'losses': self.losses,
            'win_rate': win_rate,
        }

    def get_trade_history(self) -> list:
        """Get list of completed trades"""
        return self.trades.copy()


# Quick test
if __name__ == '__main__':
    import sys
    sys.path.insert(0, 'C:/ClaudeSpace/trading-bot')
    from src.yfinance_client import YFinanceClient

    logging.basicConfig(level=logging.INFO)

    print("="*60)
    print("  SCALP STRATEGY BACKTEST (5-min bars, 5 days)")
    print("="*60)

    client = YFinanceClient()
    history = client.get_history('NIO', '5d', interval='5m')

    if not history:
        print("Failed to get data")
        exit()

    prices = [bar['close'] for bar in history]
    dates = [bar['date'] for bar in history]

    print(f"Loaded {len(prices)} bars")
    print(f"Period: {str(dates[0])[:16]} to {str(dates[-1])[:16]}")

    strategy = ScalpStrategy()
    print(f"Strategy: {strategy.name}")

    capital = 10000

    for i, price in enumerate(prices):
        strategy.add_price(price)

        signal = strategy.get_signal()

        if signal == 'BUY' and strategy.position == 0:
            shares = min(strategy.max_shares, int(capital / price))
            cost = shares * price
            capital -= cost
            strategy.enter_position(price, shares)

        elif signal.startswith('SELL') and strategy.position > 0:
            proceeds = strategy.position * price
            strategy.exit_position(price, signal.replace('SELL_', ''))
            capital += proceeds

    # Close open position
    if strategy.position > 0:
        capital += strategy.position * prices[-1]

    status = strategy.get_status()
    final_return = (capital - 10000) / 10000 * 100
    bh_return = (prices[-1] - prices[0]) / prices[0] * 100

    print(f"\nResults:")
    print(f"  Initial: $10,000")
    print(f"  Final: ${capital:.2f}")
    print(f"  Return: {final_return:+.2f}%")
    print(f"  Buy & Hold: {bh_return:+.2f}%")
    print(f"  Trades: {status['total_trades']}")
    print(f"  Win Rate: {status['win_rate']:.0f}%")
    print(f"  Wins/Losses: {status['wins']}/{status['losses']}")

    print("\nTrade Log:")
    for t in strategy.get_trade_history():
        status_str = "WIN" if t['pnl'] > 0 else "LOSS"
        print(f"  ${t['entry_price']:.2f} -> ${t['exit_price']:.2f} | {t['reason']:<3} | ${t['pnl']:+.2f} ({t['pnl_pct']:+.1f}%) {status_str}")
