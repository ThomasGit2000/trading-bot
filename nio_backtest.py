"""NIO Backtest - NO STOPS MA(10/30) - 2 Years"""
from src.backtest import run_backtest, Backtester
import logging
logging.basicConfig(level=logging.WARNING)

# Get buy & hold benchmark for NIO
bt = Backtester(initial_capital=10000)
data = bt.fetch_data('NIO', '2y')
prices = [d['close'] for d in data]
start_price = prices[0]
end_price = prices[-1]
buy_hold_pct = ((end_price - start_price) / start_price) * 100
shares_bh = int(10000 / start_price)
buy_hold_final = shares_bh * end_price

print('='*70)
print('  NIO BACKTEST - NO STOPS MA(10/30) - 2 YEARS')
print('='*70)
# Check data structure
if data:
    first_date = data[0].get('date') or data[0].get('timestamp') or 'N/A'
    last_date = data[-1].get('date') or data[-1].get('timestamp') or 'N/A'
    if hasattr(first_date, 'strftime'):
        print(f'Period: {first_date.strftime("%Y-%m-%d")} to {last_date.strftime("%Y-%m-%d")}')
    else:
        print(f'Period: 2 years')
print(f'Start Price: ${start_price:.2f}  |  End Price: ${end_price:.2f}')
print()
print(f'BUY AND HOLD: {shares_bh} shares, $10,000 -> ${buy_hold_final:,.0f} ({buy_hold_pct:+.1f}%)')
print()

# Run NO STOPS strategy (current strategy)
print('Running NO STOPS MA(10/30) strategy...')
result = run_backtest(
    symbol='NIO', period='2y', capital=10000,
    position_size=200,
    short_ma=10, long_ma=30,
    stop_loss_pct=None, trailing_stop_pct=None,
    min_hold_days=0, rsi_filter=False, volume_filter=False
)

print()
print('='*70)
print('  RESULTS')
print('='*70)
print(f'Strategy Return:    {result.total_return_pct:+.1f}%')
print(f'Buy & Hold Return:  {buy_hold_pct:+.1f}%')
diff = result.total_return_pct - buy_hold_pct
beat_msg = "BEATS BUY & HOLD!" if diff > 0 else ""
print(f'Difference:         {diff:+.1f}% {beat_msg}')
print()
print(f'Final Capital:      ${result.final_capital:,.2f}')
print(f'Total Trades:       {result.num_trades}')
print(f'Winning Trades:     {result.winning_trades}')
print(f'Losing Trades:      {result.losing_trades}')
print(f'Win Rate:           {result.win_rate:.1f}%')
print(f'Max Drawdown:       {result.max_drawdown_pct:.1f}%')
print(f'Sharpe Ratio:       {result.sharpe_ratio:.2f}')
print('='*70)

# Show trades
print()
print('TRADES:')
print('-'*70)
for t in result.trades:
    pnl_str = f'P/L: ${t.pnl:+.2f}' if t.action == 'SELL' else ''
    print(f'{t.date.strftime("%Y-%m-%d")} {t.action:4} {t.quantity} shares @ ${t.price:.2f}  {pnl_str}')
print('-'*70)
