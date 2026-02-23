"""Find a strategy that beats buy and hold"""
from src.backtest import run_backtest, Backtester
import logging
logging.basicConfig(level=logging.WARNING)

# Get buy & hold benchmark
bt = Backtester(initial_capital=10000)
data = bt.fetch_data('TSLA', '2y')
prices = [d['close'] for d in data]
start_price = prices[0]
end_price = prices[-1]
buy_hold_pct = ((end_price - start_price) / start_price) * 100
shares_bh = int(10000 / start_price)
buy_hold_final = shares_bh * end_price

print('='*70)
print('  CHALLENGE: BEAT BUY AND HOLD')
print('='*70)
print(f'Buy and Hold: {shares_bh} shares, $10,000 -> ${buy_hold_final:,.0f} ({buy_hold_pct:+.1f}%)')
print()

results = []

# Strategy 1: Full capital, aggressive momentum
print('[1] FULL CAPITAL MOMENTUM')
r1 = run_backtest(
    symbol='TSLA', period='2y', capital=10000,
    position_size=50,
    short_ma=5, long_ma=20,
    stop_loss_pct=0.15, trailing_stop_pct=0.12, trail_after_profit_pct=0.08,
    min_hold_days=5, rsi_filter=False, volume_filter=False
)
results.append(('1. Full Capital Momentum', r1))

# Strategy 2: Buy the dip
print('[2] BUY THE DIP')
r2 = run_backtest(
    symbol='TSLA', period='2y', capital=10000,
    position_size=50,
    short_ma=3, long_ma=10,
    stop_loss_pct=0.20, trailing_stop_pct=0.15, trail_after_profit_pct=0.10,
    min_hold_days=3, rsi_filter=True, volume_filter=False
)
results.append(('2. Buy The Dip', r2))

# Strategy 3: Scalper
print('[3] SCALPER MA(2/5)')
r3 = run_backtest(
    symbol='TSLA', period='2y', capital=10000,
    position_size=50,
    short_ma=2, long_ma=5,
    stop_loss_pct=0.05, trailing_stop_pct=0.04, trail_after_profit_pct=0.02,
    min_hold_days=1, rsi_filter=False, volume_filter=False
)
results.append(('3. Scalper MA(2/5)', r3))

# Strategy 4: Wide trailing stop
print('[4] TREND RIDER (wide stops)')
r4 = run_backtest(
    symbol='TSLA', period='2y', capital=10000,
    position_size=50,
    short_ma=10, long_ma=50,
    stop_loss_pct=0.25, trailing_stop_pct=0.25, trail_after_profit_pct=0.20,
    min_hold_days=20, rsi_filter=False, volume_filter=False
)
results.append(('4. Trend Rider', r4))

# Strategy 5: No stops at all
print('[5] NO STOPS - ride everything')
r5 = run_backtest(
    symbol='TSLA', period='2y', capital=10000,
    position_size=50,
    short_ma=10, long_ma=30,
    stop_loss_pct=None, trailing_stop_pct=None,
    min_hold_days=0, rsi_filter=False, volume_filter=False
)
results.append(('5. No Stops', r5))

# Strategy 6: Very long MA - catch big trends only
print('[6] BIG TREND ONLY MA(20/100)')
r6 = run_backtest(
    symbol='TSLA', period='2y', capital=10000,
    position_size=50,
    short_ma=20, long_ma=100,
    stop_loss_pct=0.30, trailing_stop_pct=0.20, trail_after_profit_pct=0.15,
    min_hold_days=10, rsi_filter=False, volume_filter=False
)
results.append(('6. Big Trend MA(20/100)', r6))

# Strategy 7: Pyramid - add to winners
print('[7] SIMPLE ENTRY - minimal filters')
r7 = run_backtest(
    symbol='TSLA', period='2y', capital=10000,
    position_size=50,
    short_ma=5, long_ma=15,
    stop_loss_pct=0.10, trailing_stop_pct=None,
    min_hold_days=0, rsi_filter=False, volume_filter=False
)
results.append(('7. Simple Entry', r7))

print()
print('='*70)
print('  RESULTS vs BUY AND HOLD')
print('='*70)
print(f'{"Strategy":<40} {"Return":>12} {"vs BnH":>12} {"Win%":>8}')
print('-'*70)
print(f'{"BUY AND HOLD (benchmark)":<40} {buy_hold_pct:>+11.1f}% {"---":>12} {"N/A":>8}')
for name, r in results:
    diff = r.total_return_pct - buy_hold_pct
    beat = "BEATS!" if diff > 0 else ""
    print(f'{name:<40} {r.total_return_pct:>+11.1f}% {diff:>+11.1f}% {r.win_rate:>7.1f}% {beat}')
print('='*70)

# Find best
best = max(results, key=lambda x: x[1].total_return_pct)
print(f'\nBest Strategy: {best[0]} with {best[1].total_return_pct:+.1f}%')
if best[1].total_return_pct > buy_hold_pct:
    print('>>> BEATS BUY AND HOLD! <<<')
else:
    print(f'Still {buy_hold_pct - best[1].total_return_pct:.1f}% behind buy and hold')
