"""
Multi-strategy backtesting comparison for NIO
Tests various strategies to find the best performer
"""
import logging
from dataclasses import dataclass
from typing import List, Tuple
from src.yfinance_client import YFinanceClient

logging.basicConfig(level=logging.WARNING)


@dataclass
class TradeResult:
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    pnl: float
    pnl_pct: float
    exit_reason: str


@dataclass
class StrategyResult:
    name: str
    total_return: float
    total_return_pct: float
    num_trades: int
    win_rate: float
    max_drawdown_pct: float
    sharpe: float
    trades: List[TradeResult]


def calculate_rsi(prices: list, period: int = 14) -> list:
    """Calculate RSI"""
    if len(prices) < period + 1:
        return [50] * len(prices)

    rsi = [50] * period
    for i in range(period, len(prices)):
        gains, losses = [], []
        for j in range(i - period + 1, i + 1):
            change = prices[j] - prices[j-1]
            gains.append(max(0, change))
            losses.append(max(0, -change))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            rsi.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100 - (100 / (1 + rs)))

    return rsi


def calculate_macd(prices: list) -> Tuple[list, list, list]:
    """Calculate MACD, Signal, and Histogram"""
    def ema(data, period):
        result = [data[0]]
        mult = 2 / (period + 1)
        for i in range(1, len(data)):
            result.append((data[i] * mult) + (result[-1] * (1 - mult)))
        return result

    ema12 = ema(prices, 12)
    ema26 = ema(prices, 26)
    macd = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
    signal = ema(macd, 9)
    histogram = [m - s for m, s in zip(macd, signal)]

    return macd, signal, histogram


def calculate_bollinger(prices: list, period: int = 20, std_mult: float = 2) -> Tuple[list, list, list]:
    """Calculate Bollinger Bands"""
    upper, middle, lower = [], [], []

    for i in range(len(prices)):
        if i < period - 1:
            upper.append(prices[i])
            middle.append(prices[i])
            lower.append(prices[i])
        else:
            window = prices[i - period + 1:i + 1]
            ma = sum(window) / period
            std = (sum((p - ma) ** 2 for p in window) / period) ** 0.5
            middle.append(ma)
            upper.append(ma + std_mult * std)
            lower.append(ma - std_mult * std)

    return upper, middle, lower


def backtest_strategy(prices: list, dates: list, signals: list,
                      stop_loss: float = 0.10, take_profit: float = 0.15,
                      max_hold: int = 30) -> StrategyResult:
    """Generic backtester for any signal list"""
    capital = 10000
    position = 0
    entry_price = 0
    entry_date = None
    entry_idx = 0
    trades = []
    equity = [capital]
    peak = capital
    max_dd = 0

    for i in range(len(prices)):
        price = prices[i]
        signal = signals[i]

        if position > 0:
            # Check exits
            current_value = capital + position * price
            pnl_pct = (price - entry_price) / entry_price
            days_held = i - entry_idx

            exit_reason = None

            if pnl_pct <= -stop_loss:
                exit_reason = "STOP_LOSS"
            elif pnl_pct >= take_profit:
                exit_reason = "TAKE_PROFIT"
            elif days_held >= max_hold:
                exit_reason = "MAX_HOLD"
            elif signal == -1:
                exit_reason = "SIGNAL"

            if exit_reason:
                pnl = position * (price - entry_price)
                capital += position * price
                trades.append(TradeResult(
                    entry_date=entry_date,
                    entry_price=entry_price,
                    exit_date=str(dates[i])[:10],
                    exit_price=price,
                    pnl=pnl,
                    pnl_pct=pnl_pct * 100,
                    exit_reason=exit_reason
                ))
                position = 0

        elif signal == 1 and position == 0:
            # Enter position
            shares = int(capital / price)
            if shares > 0:
                position = min(shares, 100)  # Max 100 shares
                entry_price = price
                entry_date = str(dates[i])[:10]
                entry_idx = i
                capital -= position * price

        # Track equity
        current_equity = capital + position * price
        equity.append(current_equity)
        if current_equity > peak:
            peak = current_equity
        dd = (peak - current_equity) / peak
        if dd > max_dd:
            max_dd = dd

    # Close any open position
    if position > 0:
        price = prices[-1]
        pnl = position * (price - entry_price)
        capital += position * price
        trades.append(TradeResult(
            entry_date=entry_date,
            entry_price=entry_price,
            exit_date=str(dates[-1])[:10],
            exit_price=price,
            pnl=pnl,
            pnl_pct=((price - entry_price) / entry_price) * 100,
            exit_reason="CLOSE"
        ))

    # Calculate metrics
    final_capital = capital
    total_return = final_capital - 10000
    total_return_pct = total_return / 10000 * 100

    winning = [t for t in trades if t.pnl > 0]
    win_rate = len(winning) / len(trades) * 100 if trades else 0

    # Simple Sharpe approximation
    if len(equity) > 1:
        returns = [(equity[i] - equity[i-1]) / equity[i-1] for i in range(1, len(equity))]
        avg_ret = sum(returns) / len(returns) if returns else 0
        std_ret = (sum((r - avg_ret) ** 2 for r in returns) / len(returns)) ** 0.5 if returns else 1
        sharpe = (avg_ret / std_ret) * (252 ** 0.5) if std_ret > 0 else 0
    else:
        sharpe = 0

    return StrategyResult(
        name="",
        total_return=total_return,
        total_return_pct=total_return_pct,
        num_trades=len(trades),
        win_rate=win_rate,
        max_drawdown_pct=max_dd * 100,
        sharpe=sharpe,
        trades=trades
    )


def strategy_ma_crossover(prices: list, short: int = 10, long: int = 30) -> list:
    """MA Crossover: Buy when short > long, sell when short < long"""
    signals = [0] * len(prices)

    for i in range(long, len(prices)):
        short_ma = sum(prices[i-short+1:i+1]) / short
        long_ma = sum(prices[i-long+1:i+1]) / long

        if short_ma > long_ma * 1.01:
            signals[i] = 1  # Buy
        elif short_ma < long_ma * 0.99:
            signals[i] = -1  # Sell

    return signals


def strategy_rsi_mean_reversion(prices: list, oversold: int = 30, overbought: int = 70) -> list:
    """Mean Reversion: Buy oversold, sell overbought"""
    rsi = calculate_rsi(prices, 14)
    signals = [0] * len(prices)

    for i in range(20, len(prices)):
        ma20 = sum(prices[i-19:i+1]) / 20

        if rsi[i] < oversold and prices[i] > ma20 * 0.95:
            signals[i] = 1  # Buy oversold
        elif rsi[i] > overbought:
            signals[i] = -1  # Sell overbought

    return signals


def strategy_macd(prices: list) -> list:
    """MACD Crossover: Buy when MACD crosses above signal"""
    macd, signal, hist = calculate_macd(prices)
    signals = [0] * len(prices)

    for i in range(27, len(prices)):
        if hist[i] > 0 and hist[i-1] <= 0:
            signals[i] = 1  # Bullish crossover
        elif hist[i] < 0 and hist[i-1] >= 0:
            signals[i] = -1  # Bearish crossover

    return signals


def strategy_bollinger(prices: list) -> list:
    """Bollinger Bands: Buy at lower band, sell at upper band"""
    upper, middle, lower = calculate_bollinger(prices, 20, 2)
    signals = [0] * len(prices)

    for i in range(20, len(prices)):
        if prices[i] <= lower[i]:
            signals[i] = 1  # Buy at lower band
        elif prices[i] >= upper[i]:
            signals[i] = -1  # Sell at upper band

    return signals


def strategy_breakout(prices: list, lookback: int = 20) -> list:
    """Breakout: Buy on new high, sell on new low"""
    signals = [0] * len(prices)

    for i in range(lookback, len(prices)):
        window = prices[i-lookback:i]
        high = max(window)
        low = min(window)

        if prices[i] > high:
            signals[i] = 1  # Breakout high
        elif prices[i] < low:
            signals[i] = -1  # Breakdown

    return signals


def strategy_rsi_divergence(prices: list) -> list:
    """RSI with trend confirmation"""
    rsi = calculate_rsi(prices, 14)
    signals = [0] * len(prices)

    for i in range(50, len(prices)):
        ma50 = sum(prices[i-49:i+1]) / 50
        ma20 = sum(prices[i-19:i+1]) / 20

        # Buy: RSI oversold + price above MA50 + MA20 turning up
        if rsi[i] < 35 and prices[i] > ma50 and ma20 > sum(prices[i-24:i-4]) / 20:
            signals[i] = 1
        # Sell: RSI overbought or price below MA50
        elif rsi[i] > 70 or prices[i] < ma50 * 0.95:
            signals[i] = -1

    return signals


def strategy_triple_ma(prices: list) -> list:
    """Triple MA: Fast(5) > Medium(20) > Slow(50) for trend"""
    signals = [0] * len(prices)

    for i in range(50, len(prices)):
        ma5 = sum(prices[i-4:i+1]) / 5
        ma20 = sum(prices[i-19:i+1]) / 20
        ma50 = sum(prices[i-49:i+1]) / 50

        if ma5 > ma20 > ma50:
            signals[i] = 1  # Uptrend aligned
        elif ma5 < ma20 < ma50:
            signals[i] = -1  # Downtrend aligned

    return signals


def run_comparison():
    """Run all strategies and compare"""
    print("Fetching NIO 1-year data...")
    client = YFinanceClient()
    history = client.get_history('NIO', '1y')

    if not history:
        print("Failed to fetch data")
        return

    prices = [bar['close'] for bar in history]
    dates = [bar['date'] for bar in history]

    print(f"Loaded {len(prices)} days of data")
    print(f"Period: {str(dates[0])[:10]} to {str(dates[-1])[:10]}")
    print(f"Price range: ${min(prices):.2f} - ${max(prices):.2f}")

    # Buy and hold benchmark
    bh_return = (prices[-1] - prices[0]) / prices[0] * 100
    print(f"\nBuy & Hold return: {bh_return:+.2f}%")

    strategies = [
        ("1. MA Crossover (10/30)", strategy_ma_crossover(prices, 10, 30), 0.15, 0.15),
        ("2. RSI Mean Reversion", strategy_rsi_mean_reversion(prices, 30, 70), 0.10, 0.15),
        ("3. MACD Crossover", strategy_macd(prices), 0.12, 0.15),
        ("4. Bollinger Bands", strategy_bollinger(prices), 0.10, 0.12),
        ("5. Breakout (20-day)", strategy_breakout(prices, 20), 0.15, 0.20),
        ("6. RSI + Trend Filter", strategy_rsi_divergence(prices), 0.10, 0.15),
        ("7. Triple MA (5/20/50)", strategy_triple_ma(prices), 0.12, 0.18),
    ]

    results = []

    print("\n" + "="*70)
    print("  STRATEGY COMPARISON RESULTS")
    print("="*70)

    for name, signals, sl, tp in strategies:
        result = backtest_strategy(prices, dates, signals, stop_loss=sl, take_profit=tp)
        result.name = name
        results.append(result)

    # Sort by return
    results.sort(key=lambda x: x.total_return_pct, reverse=True)

    print(f"\n{'Strategy':<30} {'Return':>10} {'Trades':>8} {'Win%':>8} {'MaxDD':>8} {'Sharpe':>8}")
    print("-"*70)

    for r in results:
        print(f"{r.name:<30} {r.total_return_pct:>+9.2f}% {r.num_trades:>8} {r.win_rate:>7.1f}% {r.max_drawdown_pct:>7.2f}% {r.sharpe:>8.2f}")

    print("-"*70)
    print(f"{'Buy & Hold':<30} {bh_return:>+9.2f}%")
    print()

    # Show best strategy details
    best = results[0]
    print("="*70)
    print(f"  BEST STRATEGY: {best.name}")
    print("="*70)
    print(f"  Return: ${best.total_return:.2f} ({best.total_return_pct:+.2f}%)")
    print(f"  Trades: {best.num_trades}")
    print(f"  Win Rate: {best.win_rate:.1f}%")
    print(f"  Max Drawdown: {best.max_drawdown_pct:.2f}%")
    print(f"  Sharpe Ratio: {best.sharpe:.2f}")
    print()
    print("  Trade Log:")
    print("  " + "-"*60)
    for t in best.trades:
        status = "WIN" if t.pnl > 0 else "LOSS"
        print(f"  {t.entry_date} ${t.entry_price:.2f} -> {t.exit_date} ${t.exit_price:.2f} | {t.exit_reason:<12} | ${t.pnl:+.2f} ({t.pnl_pct:+.1f}%) {status}")

    return results


if __name__ == '__main__':
    run_comparison()
