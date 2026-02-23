"""Backtest No Stops strategy on TSLA and NIO"""
from src.backtest import run_backtest, Backtester
import logging
logging.basicConfig(level=logging.WARNING)

print('='*70)
print('  NO STOPS STRATEGY: TSLA vs NIO')
print('='*70)

results = {}

for symbol in ['TSLA', 'NIO']:
    print(f'\n{"="*70}')
    print(f'  {symbol} BACKTEST')
    print(f'{"="*70}')

    # Get buy and hold benchmark
    bt = Backtester(initial_capital=10000)
    data = bt.fetch_data(symbol, '2y')
    prices = [d['close'] for d in data]
    start_price = prices[0]
    end_price = prices[-1]
    buy_hold_pct = ((end_price - start_price) / start_price) * 100

    # Position size based on stock price
    if symbol == 'TSLA':
        pos_size = 50  # ~$20k position
    else:
        pos_size = 2000  # ~$10k position for NIO at $5

    print(f'\nBuy and Hold: ${start_price:.2f} -> ${end_price:.2f} ({buy_hold_pct:+.1f}%)')
    print(f'\nNo Stops Strategy (MA 10/30, position size {pos_size}):')

    r = run_backtest(
        symbol=symbol,
        period='2y',
        capital=10000,
        position_size=pos_size,
        short_ma=10,
        long_ma=30,
        stop_loss_pct=None,  # NO STOP LOSS
        trailing_stop_pct=None,  # NO TRAILING STOP
        min_hold_days=0,
        rsi_filter=False,
        volume_filter=False
    )

    results[symbol] = {
        'strategy_return': r.total_return_pct,
        'buy_hold_return': buy_hold_pct,
        'win_rate': r.win_rate,
        'sharpe': r.sharpe_ratio,
        'trades': r.num_trades,
        'max_dd': r.max_drawdown_pct
    }

print('\n' + '='*70)
print('  FINAL COMPARISON')
print('='*70)
print(f'\n{"Stock":<8} {"Strategy":>12} {"Buy&Hold":>12} {"Diff":>10} {"Win%":>8} {"Sharpe":>8}')
print('-'*70)
for symbol, data in results.items():
    diff = data['strategy_return'] - data['buy_hold_return']
    beat = "BEATS!" if diff > 0 else ""
    print(f'{symbol:<8} {data["strategy_return"]:>+11.1f}% {data["buy_hold_return"]:>+11.1f}% {diff:>+9.1f}% {data["win_rate"]:>7.1f}% {data["sharpe"]:>8.2f} {beat}')
print('='*70)
