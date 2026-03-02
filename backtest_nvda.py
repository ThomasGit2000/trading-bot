"""Backtest No Stops strategy on NVDA - 2 years"""
from src.backtest import run_backtest, Backtester
import logging
logging.basicConfig(level=logging.WARNING)

symbol = 'NVDA'
print('='*70)
print(f'  NVDA BACKTEST - NO STOPS MA(10/30) - 2 YEARS')
print('='*70)

# Get buy and hold benchmark
bt = Backtester(initial_capital=10000)
data = bt.fetch_data(symbol, '2y')
prices = [d['close'] for d in data]
start_price = prices[0]
end_price = prices[-1]
buy_hold_pct = ((end_price - start_price) / start_price) * 100

print(f'Data points: {len(data)}')
print(f"Date range: {data[0]['date']} to {data[-1]['date']}")
print(f'Buy and Hold: ${start_price:.2f} -> ${end_price:.2f} ({buy_hold_pct:+.1f}%)')

# Position size for NVDA
pos_size = 75

print(f'\nRunning No Stops Strategy (MA 10/30, position size {pos_size})...')

r = run_backtest(
    symbol=symbol,
    period='2y',
    capital=10000,
    position_size=pos_size,
    short_ma=10,
    long_ma=30,
    stop_loss_pct=None,
    trailing_stop_pct=None,
    min_hold_days=0,
    rsi_filter=False,
    volume_filter=False
)

print(f'\n--- RESULTS ---')
print(f'Total Trades: {r.num_trades}')
print(f'Win Rate: {r.win_rate:.1f}%')
print(f'Strategy Return: {r.total_return_pct:+.1f}%')
print(f'Buy & Hold Return: {buy_hold_pct:+.1f}%')
print(f'Outperformance: {r.total_return_pct - buy_hold_pct:+.1f}%')
print(f'Max Drawdown: {r.max_drawdown_pct:.1f}%')
print(f'Sharpe Ratio: {r.sharpe_ratio:.2f}')
print(f'Final Capital: ${r.final_capital:,.2f}')

# Show individual trades
print(f'\n--- TRADE HISTORY ({r.num_trades} trades) ---')
for i, trade in enumerate(r.trades, 1):
    print(f"{i:2}. {trade['entry_date']} BUY @ ${trade['entry_price']:.2f} -> {trade['exit_date']} SELL @ ${trade['exit_price']:.2f} | P/L: {trade['pnl_pct']:+.1f}%")
