"""Test MA strategy on different stocks to find where it beats buy & hold"""
from src.backtest import run_backtest, Backtester, MomentumStrategy
import logging
logging.basicConfig(level=logging.WARNING)

print('='*70)
print('  MA STRATEGY VS BUY & HOLD - MULTIPLE STOCKS (2 YEARS)')
print('='*70)

# Test various stock types
stocks = [
    # Sideways/Volatile
    ('NIO', 200, 'China EV - Volatile'),
    ('RIVN', 100, 'EV Startup - Volatile'),
    ('LCID', 200, 'EV Startup - Declining'),
    ('AMC', 200, 'Meme Stock'),
    ('GME', 50, 'Meme Stock'),

    # Tech that struggled
    ('INTC', 100, 'Chip - Struggling'),
    ('SNAP', 150, 'Social Media - Volatile'),
    ('PYPL', 50, 'Fintech - Declining'),
    ('ZM', 30, 'Pandemic Stock'),
    ('ROKU', 30, 'Streaming - Volatile'),

    # Commodity/Cyclical
    ('XOM', 50, 'Oil Major'),
    ('FCX', 100, 'Copper Mining'),
    ('CLF', 150, 'Steel'),

    # Biotech - very volatile
    ('MRNA', 30, 'Biotech - Post-COVID'),

    # Strong performers (for comparison)
    ('NVDA', 75, 'AI Chip Leader'),
    ('META', 25, 'Big Tech Recovery'),
    ('AAPL', 60, 'Stable Growth'),
]

results = []

print(f"\n{'Stock':<8} {'Type':<25} {'Strategy':>10} {'Buy&Hold':>10} {'Diff':>10} {'Trades':>8} {'Win%':>8}")
print('-'*90)

for symbol, pos_size, description in stocks:
    try:
        # Get buy and hold
        bt = Backtester(initial_capital=10000)
        data = bt.fetch_data(symbol, '2y')
        if not data or len(data) < 50:
            continue

        prices = [d['close'] for d in data]
        start_price = prices[0]
        end_price = prices[-1]
        buy_hold_pct = ((end_price - start_price) / start_price) * 100

        # Run strategy
        strategy = MomentumStrategy(
            short_window=10,
            long_window=30,
            threshold=0.01,
            stop_loss_pct=None,
            trailing_stop_pct=None
        )
        backtester = Backtester(initial_capital=10000, position_size=pos_size)
        result = backtester.run(symbol, strategy, '2y')

        diff = result.total_return_pct - buy_hold_pct
        beat = "BEATS!" if diff > 0 else ""

        results.append({
            'symbol': symbol,
            'description': description,
            'strategy': result.total_return_pct,
            'buyhold': buy_hold_pct,
            'diff': diff,
            'trades': result.num_trades,
            'win_rate': result.win_rate
        })

        print(f"{symbol:<8} {description:<25} {result.total_return_pct:>+9.1f}% {buy_hold_pct:>+9.1f}% {diff:>+9.1f}% {result.num_trades:>8} {result.win_rate:>7.1f}% {beat}")

    except Exception as e:
        print(f"{symbol:<8} ERROR: {e}")

# Sort by outperformance
results.sort(key=lambda x: x['diff'], reverse=True)

print('\n' + '='*70)
print('  STOCKS WHERE STRATEGY BEATS BUY & HOLD')
print('='*70)

winners = [r for r in results if r['diff'] > 0]
if winners:
    for r in winners:
        print(f"\n{r['symbol']} ({r['description']})")
        print(f"  Strategy: {r['strategy']:+.1f}% | Buy&Hold: {r['buyhold']:+.1f}% | Outperformance: {r['diff']:+.1f}%")
        print(f"  Trades: {r['trades']} | Win Rate: {r['win_rate']:.1f}%")
else:
    print("\nNo stocks found where strategy beats buy & hold in this period.")

print('\n' + '='*70)
print('  STOCKS WHERE STRATEGY LOSES LEAST')
print('='*70)
for r in results[:5]:
    print(f"{r['symbol']:<8} Strategy: {r['strategy']:+.1f}% | B&H: {r['buyhold']:+.1f}% | Diff: {r['diff']:+.1f}%")

print('\n' + '='*70)
print('  KEY INSIGHT')
print('='*70)
print("""
The MA crossover strategy tends to BEAT buy & hold when:
- Stock is in a DOWNTREND (strategy avoids losses)
- Stock is SIDEWAYS with big swings (strategy captures swings)
- Stock has CRASHES that don't recover

The strategy LOSES to buy & hold when:
- Stock is in a strong UPTREND
- Stock recovers from every dip
""")
