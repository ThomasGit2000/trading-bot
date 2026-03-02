"""Alternative strategies to beat NVDA buy & hold"""
from src.backtest import Backtester, MomentumStrategy
from src.yfinance_client import YFinanceClient
import logging
logging.basicConfig(level=logging.WARNING)

symbol = 'NVDA'
period = '2y'
capital = 10000

# Get data
bt = Backtester(initial_capital=capital)
data = bt.fetch_data(symbol, period)
prices = [d['close'] for d in data]
dates = [d.get('date') or d.get('timestamp') for d in data]
start_price = prices[0]
end_price = prices[-1]
buy_hold_pct = ((end_price - start_price) / start_price) * 100

print('='*70)
print(f'  NVDA ALTERNATIVE STRATEGIES')
print(f'  Buy & Hold: ${start_price:.2f} -> ${end_price:.2f} (+{buy_hold_pct:.1f}%)')
print('='*70)

# Strategy 1: Buy and Hold with DCA on dips
print("\n--- STRATEGY 1: Buy the Dip (DCA) ---")
# Buy more when price drops 10%+ from recent high
dca_capital = capital
shares = 0
peak = 0
buys = []

for i, price in enumerate(prices):
    if price > peak:
        peak = price

    drop = (peak - price) / peak if peak > 0 else 0

    # Initial buy
    if shares == 0 and dca_capital >= price:
        qty = int(dca_capital * 0.5 / price)  # Start with 50%
        if qty > 0:
            shares += qty
            dca_capital -= qty * price
            buys.append((dates[i], price, qty, "Initial"))

    # Buy the dip - when down 15%+ from peak
    elif drop >= 0.15 and dca_capital >= price:
        qty = int(dca_capital * 0.3 / price)  # Add 30% of remaining
        if qty > 0:
            shares += qty
            dca_capital -= qty * price
            buys.append((dates[i], price, qty, f"Dip {drop*100:.0f}%"))
            peak = price  # Reset peak after buying dip

final_value = dca_capital + shares * end_price
dca_return = ((final_value - capital) / capital) * 100

print(f"Buys: {len(buys)}")
for date, price, qty, reason in buys:
    print(f"  {str(date)[:10]}: {qty} shares @ ${price:.2f} ({reason})")
print(f"Final shares: {shares}, Cash: ${dca_capital:.2f}")
print(f"Final value: ${final_value:.2f} ({dca_return:+.1f}%)")
print(f"vs Buy & Hold: {dca_return - buy_hold_pct:+.1f}%")

# Strategy 2: Leveraged position on strong trend
print("\n--- STRATEGY 2: Stay in Market (100% invested) ---")
# Just buy and hold with all capital immediately
shares = int(capital / start_price)
remaining = capital - shares * start_price
final_value = remaining + shares * end_price
stay_return = ((final_value - capital) / capital) * 100
print(f"Buy {shares} shares @ ${start_price:.2f}")
print(f"Final value: ${final_value:.2f} ({stay_return:+.1f}%)")
print(f"vs Buy & Hold benchmark: {stay_return - buy_hold_pct:+.1f}%")

# Strategy 3: Buy breakouts only
print("\n--- STRATEGY 3: Breakout Only (no exits) ---")
bo_capital = capital
shares = 0
peak_20d = 0
buys = []

for i in range(20, len(prices)):
    price = prices[i]
    peak_20d = max(prices[i-20:i])

    # Buy on breakout to new 20-day high
    if price > peak_20d and shares == 0:
        qty = int(bo_capital / price)
        if qty > 0:
            shares = qty
            bo_capital -= qty * price
            buys.append((dates[i], price, qty))

# Never sell - hold to end
final_value = bo_capital + shares * end_price
if buys:
    entry = buys[0][1]
    bo_return = ((final_value - capital) / capital) * 100
    print(f"Entry: {str(buys[0][0])[:10]} @ ${entry:.2f}")
    print(f"Final value: ${final_value:.2f} ({bo_return:+.1f}%)")
    print(f"vs Buy & Hold: {bo_return - buy_hold_pct:+.1f}%")

# Strategy 4: Higher threshold MA (only exit on major crashes)
print("\n--- STRATEGY 4: MA(10/30) with 5% threshold (less sensitive) ---")
# Only signal when MA difference is 5%+ instead of 1%
class HighThresholdStrategy(MomentumStrategy):
    def __init__(self):
        super().__init__(short_window=10, long_window=30, threshold=0.05)

strategy = HighThresholdStrategy()
backtester = Backtester(initial_capital=capital, position_size=100)
result = backtester.run(symbol, strategy, period)
diff = result.total_return_pct - buy_hold_pct
print(f"Return: {result.total_return_pct:+.1f}% | Trades: {result.num_trades} | Win: {result.win_rate:.1f}%")
print(f"vs Buy & Hold: {diff:+.1f}%")

# Strategy 5: Very slow MA that rarely triggers
print("\n--- STRATEGY 5: Ultra-Slow MA(100/200) ---")
strategy = MomentumStrategy(short_window=100, long_window=200, threshold=0.01)
backtester = Backtester(initial_capital=capital, position_size=100)
result = backtester.run(symbol, strategy, period)
diff = result.total_return_pct - buy_hold_pct
print(f"Return: {result.total_return_pct:+.1f}% | Trades: {result.num_trades} | Win: {result.win_rate:.1f}%")
print(f"vs Buy & Hold: {diff:+.1f}%")

# Strategy 6: Enter on MA signal, never exit (ride the trend)
print("\n--- STRATEGY 6: MA Entry, No Exit (Hold Forever) ---")
# Use MA crossover for entry only, hold indefinitely
ma_cap = capital
shares = 0
entry_price = 0

for i in range(30, len(prices)):
    if shares > 0:
        continue  # Already in position, hold

    price = prices[i]
    short_ma = sum(prices[i-10:i]) / 10
    long_ma = sum(prices[i-30:i]) / 30

    if short_ma > long_ma * 1.01:  # Buy signal
        shares = int(ma_cap / price)
        ma_cap -= shares * price
        entry_price = price
        print(f"Entry: {str(dates[i])[:10]} @ ${price:.2f}")
        break

final_value = ma_cap + shares * end_price
ma_hold_return = ((final_value - capital) / capital) * 100
print(f"Final value: ${final_value:.2f} ({ma_hold_return:+.1f}%)")
print(f"vs Buy & Hold: {ma_hold_return - buy_hold_pct:+.1f}%")

print("\n" + "="*70)
print("  CONCLUSION")
print("="*70)
print(f"""
For NVDA's strong 2-year bull run (+{buy_hold_pct:.0f}%), active trading strategies
underperform simple buy-and-hold because:

1. Every exit means missing potential gains
2. Re-entries occur at higher prices
3. The stock recovered from every dip

The BEST strategy for a trending stock is: BUY AND HOLD

MA crossover strategies work better for:
- Sideways/choppy markets
- Stocks that don't recover from dips
- Capital preservation during bear markets

For NVDA specifically, the optimal approach would be:
- Buy on first MA crossover signal
- NEVER sell (ignore sell signals)
- This captures ~{ma_hold_return:.0f}% vs pure buy & hold ~{buy_hold_pct:.0f}%
""")
