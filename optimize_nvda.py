"""Optimize strategy parameters for NVDA to beat buy & hold"""
from src.backtest import run_backtest, Backtester, MomentumStrategy, print_results
import logging
logging.basicConfig(level=logging.WARNING)

symbol = 'NVDA'
period = '2y'
capital = 10000

# Get buy and hold benchmark
bt = Backtester(initial_capital=capital)
data = bt.fetch_data(symbol, period)
prices = [d['close'] for d in data]
start_price = prices[0]
end_price = prices[-1]
buy_hold_pct = ((end_price - start_price) / start_price) * 100

print('='*70)
print(f'  NVDA STRATEGY OPTIMIZATION')
print(f'  Goal: Beat Buy & Hold ({buy_hold_pct:+.1f}%)')
print('='*70)

results = []

# Test different strategy combinations
strategies = [
    # (name, short_ma, long_ma, stop_loss, trailing_stop, rsi_filter, min_hold, trail_after)
    ("Baseline MA(10/30)", 10, 30, None, None, False, 0, None),
    ("Faster MA(5/15)", 5, 15, None, None, False, 0, None),
    ("Slower MA(20/50)", 20, 50, None, None, False, 0, None),
    ("Very Slow MA(30/90)", 30, 90, None, None, False, 0, None),
    ("Trend MA(50/200)", 50, 200, None, None, False, 0, None),

    # With RSI filter
    ("MA(10/30) + RSI<70", 10, 30, None, None, True, 0, None),
    ("MA(20/50) + RSI<70", 20, 50, None, None, True, 0, None),

    # With trailing stops
    ("MA(10/30) + Trail 10%", 10, 30, None, 0.10, False, 0, None),
    ("MA(10/30) + Trail 15%", 10, 30, None, 0.15, False, 0, None),
    ("MA(10/30) + Trail 20%", 10, 30, None, 0.20, False, 0, None),
    ("MA(20/50) + Trail 15%", 20, 50, None, 0.15, False, 0, None),

    # With stop loss
    ("MA(10/30) + SL 8%", 10, 30, 0.08, None, False, 0, None),
    ("MA(10/30) + SL 10%", 10, 30, 0.10, None, False, 0, None),
    ("MA(10/30) + SL 15%", 10, 30, 0.15, None, False, 0, None),

    # Combo: trailing + stop loss
    ("MA(10/30) + SL10% + Trail15%", 10, 30, 0.10, 0.15, False, 0, None),
    ("MA(20/50) + SL10% + Trail15%", 20, 50, 0.10, 0.15, False, 0, None),

    # Min hold days (reduce whipsaws)
    ("MA(10/30) + Hold 5d", 10, 30, None, None, False, 5, None),
    ("MA(10/30) + Hold 10d", 10, 30, None, None, False, 10, None),
    ("MA(20/50) + Hold 10d", 20, 50, None, None, False, 10, None),

    # Trail after profit
    ("MA(10/30) + Trail15% after 10%", 10, 30, None, 0.15, False, 0, 0.10),
    ("MA(20/50) + Trail15% after 10%", 20, 50, None, 0.15, False, 0, 0.10),

    # Best combos
    ("MA(20/50) + RSI + Hold5d", 20, 50, None, None, True, 5, None),
    ("MA(20/50) + Trail20% + Hold5d", 20, 50, None, 0.20, False, 5, None),
    ("MA(30/90) + RSI + Hold10d", 30, 90, None, None, True, 10, None),
    ("MA(50/200) + Trail20%", 50, 200, None, 0.20, False, 0, None),
]

print(f"\nTesting {len(strategies)} strategies...\n")
print(f"{'Strategy':<35} {'Return':>10} {'vs B&H':>10} {'Trades':>8} {'Win%':>8} {'Sharpe':>8}")
print('-'*80)

for name, short_ma, long_ma, sl, ts, rsi, hold, trail_after in strategies:
    try:
        strategy = MomentumStrategy(
            short_window=short_ma,
            long_window=long_ma,
            threshold=0.01,
            stop_loss_pct=sl,
            trailing_stop_pct=ts,
            rsi_filter=rsi,
            min_hold_days=hold,
            trail_after_profit_pct=trail_after
        )

        backtester = Backtester(initial_capital=capital, position_size=75)
        result = backtester.run(symbol, strategy, period)

        diff = result.total_return_pct - buy_hold_pct
        beat = "BEATS!" if diff > 0 else ""

        results.append({
            'name': name,
            'return': result.total_return_pct,
            'diff': diff,
            'trades': result.num_trades,
            'win_rate': result.win_rate,
            'sharpe': result.sharpe_ratio,
            'max_dd': result.max_drawdown_pct
        })

        print(f"{name:<35} {result.total_return_pct:>+9.1f}% {diff:>+9.1f}% {result.num_trades:>8} {result.win_rate:>7.1f}% {result.sharpe_ratio:>8.2f} {beat}")

    except Exception as e:
        print(f"{name:<35} ERROR: {e}")

# Sort by outperformance
results.sort(key=lambda x: x['diff'], reverse=True)

print('\n' + '='*70)
print('  TOP 5 STRATEGIES (by outperformance vs Buy & Hold)')
print('='*70)

for i, r in enumerate(results[:5], 1):
    beat = "BEATS B&H!" if r['diff'] > 0 else ""
    print(f"\n{i}. {r['name']}")
    print(f"   Return: {r['return']:+.1f}% | vs B&H: {r['diff']:+.1f}% | Trades: {r['trades']} | Win: {r['win_rate']:.1f}% | Sharpe: {r['sharpe']:.2f} {beat}")

# Check if any beat buy and hold
winners = [r for r in results if r['diff'] > 0]
print(f"\n{'='*70}")
if winners:
    print(f"  {len(winners)} strategies beat Buy & Hold!")
else:
    print(f"  No strategies beat Buy & Hold for this period.")
    print(f"  NVDA was in a strong bull market - holding was optimal.")
print(f"{'='*70}")
