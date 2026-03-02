"""
Simple backtest comparing MA strategies
"""
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta

# Test symbols
SYMBOLS = ['AAPL', 'MSFT', 'NVDA', 'AMD', 'TSLA', 'META', 'GOOGL', 'AMZN', 'PLTR', 'MARA']

# Strategies to test
STRATEGIES = {
    'MA(10/30)': (10, 30, 0.010),
    'MA(10/20)': (10, 20, 0.008),
    'MA(8/21)': (8, 21, 0.008),
    'MA(5/15)': (5, 15, 0.005),
}

def simple_ma_backtest(prices, short, long, threshold, stop_loss=0.05):
    """Simple MA crossover backtest"""
    cash = 10000
    shares = 0
    entry_price = 0
    trades = []

    for i in range(long, len(prices)):
        price = prices[i]

        # Calculate MAs
        short_ma = np.mean(prices[i-short:i])
        long_ma = np.mean(prices[i-long:i])

        # Check stop-loss
        if shares > 0 and entry_price > 0:
            loss = (entry_price - price) / entry_price
            if loss >= stop_loss:
                cash = shares * price
                pnl = cash - 10000
                trades.append(('SELL_STOP', price, pnl))
                shares = 0
                entry_price = 0
                continue

        # Buy signal
        if shares == 0 and short_ma > long_ma * (1 + threshold):
            shares = cash / price
            entry_price = price
            cash = 0
            trades.append(('BUY', price, 0))

        # Sell signal
        elif shares > 0 and short_ma < long_ma * (1 - threshold):
            cash = shares * price
            pnl = cash - 10000
            trades.append(('SELL', price, pnl))
            shares = 0
            entry_price = 0

    # Close final position
    if shares > 0:
        cash = shares * prices[-1]
        pnl = cash - 10000
        trades.append(('SELL_FINAL', prices[-1], pnl))

    total_return = ((cash - 10000) / 10000) * 100
    wins = [t for t in trades if t[0].startswith('SELL') and t[2] > 0]
    losses = [t for t in trades if t[0].startswith('SELL') and t[2] < 0]

    return {
        'return': total_return,
        'trades': len([t for t in trades if t[0].startswith('SELL')]),
        'win_rate': (len(wins) / max(len(wins) + len(losses), 1)) * 100,
        'final_value': cash
    }

print("=" * 80)
print("MA STRATEGY BACKTEST - 1 YEAR")
print("=" * 80)
print()

# Download data
end_date = datetime.now()
start_date = end_date - timedelta(days=365)

results = {name: {'returns': [], 'trades': [], 'win_rates': []}
           for name in list(STRATEGIES.keys()) + ['Buy & Hold']}

print(f"Testing {len(SYMBOLS)} stocks from {start_date.date()} to {end_date.date()}")
print()

for symbol in SYMBOLS:
    try:
        df = yf.download(symbol, start=start_date, end=end_date, progress=False)
        if len(df) < 100:
            continue

        prices = df['Close'].values

        # Buy & Hold
        bh_return = float((prices[-1] - prices[0]) / prices[0] * 100)
        results['Buy & Hold']['returns'].append(bh_return)

        print(f"{symbol:6} | B&H: {bh_return:>7.2f}% ", end='')

        # Test each MA strategy
        for name, (short, long, threshold) in STRATEGIES.items():
            res = simple_ma_backtest(prices, short, long, threshold)
            results[name]['returns'].append(float(res['return']))
            results[name]['trades'].append(int(res['trades']))
            results[name]['win_rates'].append(float(res['win_rate']))

            print(f"| {name}: {float(res['return']):>7.2f}% ({int(res['trades']):2}T) ", end='')

        print()

    except Exception as e:
        print(f"{symbol:6} | Error: {e}")

print()
print("=" * 80)
print("SUMMARY RESULTS")
print("=" * 80)
print()

# Calculate averages
summary = []
for name in ['Buy & Hold'] + list(STRATEGIES.keys()):
    avg_return = np.mean(results[name]['returns']) if results[name]['returns'] else 0
    avg_trades = np.mean(results[name]['trades']) if results[name]['trades'] else 0
    avg_win_rate = np.mean(results[name]['win_rates']) if results[name]['win_rates'] else 0

    summary.append({
        'name': name,
        'return': avg_return,
        'trades': avg_trades,
        'win_rate': avg_win_rate
    })

# Sort by return
summary.sort(key=lambda x: x['return'], reverse=True)

print(f"{'Strategy':<25} {'Avg Return':>12} {'Avg Trades':>12} {'Win Rate':>10}")
print("-" * 80)

for i, s in enumerate(summary):
    rank = f"#{i+1}"
    if s['name'] == 'Buy & Hold':
        print(f"{rank} {s['name']:<23} {s['return']:>11.2f}%  {'N/A':>12}  {'N/A':>10}")
    else:
        print(f"{rank} {s['name']:<23} {s['return']:>11.2f}%  {s['trades']:>11.1f}  {s['win_rate']:>9.1f}%")

print()
print("=" * 80)
print("RECOMMENDATION")
print("=" * 80)
print()

winner = summary[0]
print(f"BEST PERFORMER: {winner['name']}")
print(f"  Average Return: {winner['return']:.2f}%")
if winner['name'] != 'Buy & Hold':
    print(f"  Avg Trades: {winner['trades']:.0f}")
    print(f"  Win Rate: {winner['win_rate']:.1f}%")

    # Get parameters
    if winner['name'] in STRATEGIES:
        short, long, threshold = STRATEGIES[winner['name']]
        print()
        print(f"CONFIGURATION:")
        print(f"  SHORT_MA={short}")
        print(f"  LONG_MA={long}")
        print(f"  MA_THRESHOLD={threshold}")

print()
