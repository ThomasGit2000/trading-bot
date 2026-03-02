"""
Backtest: First 30 / Last 30 Intraday Momentum Strategy
QQQ from Jan 1, 2026
Starting capital: $5,000
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# Parameters
SYMBOL = "QQQ"
START_DATE = "2025-01-01"
END_DATE = "2025-12-31"
STARTING_CAPITAL = 5000
THRESHOLD = 0.003  # 0.3% threshold for entry
COMMISSION = 0.00  # IB commission negligible for this size

print(f"=" * 60)
print(f"BACKTEST: First 30 / Last 30 Strategy")
print(f"=" * 60)
print(f"Symbol: {SYMBOL}")
print(f"Period: {START_DATE} to {END_DATE}")
print(f"Starting Capital: ${STARTING_CAPITAL:,.2f}")
print(f"Entry Threshold: {THRESHOLD*100:.1f}%")
print(f"=" * 60)

# Download intraday data (5-minute intervals)
print(f"\nDownloading {SYMBOL} intraday data...")
ticker = yf.Ticker(SYMBOL)

# Get data in chunks (yfinance limits intraday to 60 days per request)
all_data = []
current_start = datetime.strptime(START_DATE, "%Y-%m-%d")
end_dt = datetime.now()

while current_start < end_dt:
    chunk_end = min(current_start + timedelta(days=59), end_dt)
    try:
        data = ticker.history(
            start=current_start.strftime("%Y-%m-%d"),
            end=chunk_end.strftime("%Y-%m-%d"),
            interval="5m"
        )
        if len(data) > 0:
            all_data.append(data)
            print(f"  Downloaded {current_start.strftime('%Y-%m-%d')} to {chunk_end.strftime('%Y-%m-%d')}: {len(data)} bars")
    except Exception as e:
        print(f"  Error: {e}")
    current_start = chunk_end

if not all_data:
    print("ERROR: No data downloaded!")
    exit(1)

df = pd.concat(all_data)
df = df[~df.index.duplicated(keep='first')]
print(f"\nTotal bars: {len(df)}")

# Get unique trading days
df['date'] = df.index.date
df['time'] = df.index.time
trading_days = df['date'].unique()
print(f"Trading days: {len(trading_days)}")

# Backtest
trades = []
capital = STARTING_CAPITAL
position = 0
shares = 0

for day in trading_days:
    day_data = df[df['date'] == day].copy()

    if len(day_data) < 20:  # Need enough bars
        continue

    # Get first 30 minutes (9:30-10:00) - approximately first 6 bars of 5-min data
    # Market opens at 9:30, so we look for bars between 9:30 and 10:00
    first_30 = day_data[(day_data['time'] >= pd.Timestamp('09:30').time()) &
                         (day_data['time'] < pd.Timestamp('10:00').time())]

    # Get last 30 minutes (15:30-16:00)
    last_30 = day_data[(day_data['time'] >= pd.Timestamp('15:30').time()) &
                        (day_data['time'] < pd.Timestamp('16:00').time())]

    if len(first_30) < 2 or len(last_30) < 2:
        continue

    # Calculate first 30 min return
    open_price = first_30.iloc[0]['Open']
    first_30_close = first_30.iloc[-1]['Close']
    first_30_return = (first_30_close - open_price) / open_price

    # Entry price at 10:00
    entry_bars = day_data[day_data['time'] >= pd.Timestamp('10:00').time()]
    if len(entry_bars) == 0:
        continue
    entry_price = entry_bars.iloc[0]['Open']

    # Exit price at 15:55 (near close)
    exit_bars = day_data[day_data['time'] >= pd.Timestamp('15:50').time()]
    if len(exit_bars) == 0:
        continue
    exit_price = exit_bars.iloc[-1]['Close']

    # Trading logic
    signal = "NONE"
    pnl = 0

    if first_30_return > THRESHOLD:
        # BUY signal
        signal = "LONG"
        shares = int(capital / entry_price)
        if shares > 0:
            pnl = shares * (exit_price - entry_price) - COMMISSION * 2
            capital += pnl

    elif first_30_return < -THRESHOLD:
        # SHORT signal
        signal = "SHORT"
        shares = int(capital / entry_price)
        if shares > 0:
            pnl = shares * (entry_price - exit_price) - COMMISSION * 2
            capital += pnl

    if signal != "NONE":
        trade = {
            'date': day,
            'signal': signal,
            'first_30_ret': first_30_return * 100,
            'entry': entry_price,
            'exit': exit_price,
            'shares': shares,
            'pnl': pnl,
            'capital': capital
        }
        trades.append(trade)

# Results
print(f"\n" + "=" * 60)
print("RESULTS")
print("=" * 60)

trades_df = pd.DataFrame(trades)

if len(trades_df) == 0:
    print("No trades executed!")
else:
    # Statistics
    total_trades = len(trades_df)
    winning_trades = len(trades_df[trades_df['pnl'] > 0])
    losing_trades = len(trades_df[trades_df['pnl'] < 0])
    win_rate = winning_trades / total_trades * 100

    total_pnl = capital - STARTING_CAPITAL
    total_return = (capital / STARTING_CAPITAL - 1) * 100

    avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
    avg_loss = trades_df[trades_df['pnl'] < 0]['pnl'].mean() if losing_trades > 0 else 0

    # Long vs Short breakdown
    long_trades = trades_df[trades_df['signal'] == 'LONG']
    short_trades = trades_df[trades_df['signal'] == 'SHORT']

    print(f"\nStarting Capital:    ${STARTING_CAPITAL:,.2f}")
    print(f"Ending Capital:      ${capital:,.2f}")
    print(f"Total P&L:           ${total_pnl:,.2f}")
    print(f"Total Return:        {total_return:.2f}%")

    print(f"\n--- Trade Statistics ---")
    print(f"Total Trades:        {total_trades}")
    print(f"Winning Trades:      {winning_trades} ({win_rate:.1f}%)")
    print(f"Losing Trades:       {losing_trades}")
    print(f"Avg Win:             ${avg_win:.2f}")
    print(f"Avg Loss:            ${avg_loss:.2f}")

    print(f"\n--- Long vs Short ---")
    print(f"Long Trades:         {len(long_trades)}")
    print(f"Short Trades:        {len(short_trades)}")
    if len(long_trades) > 0:
        long_pnl = long_trades['pnl'].sum()
        print(f"Long P&L:            ${long_pnl:.2f}")
    if len(short_trades) > 0:
        short_pnl = short_trades['pnl'].sum()
        print(f"Short P&L:           ${short_pnl:.2f}")

    # Best/Worst days
    print(f"\n--- Best & Worst ---")
    best = trades_df.loc[trades_df['pnl'].idxmax()]
    worst = trades_df.loc[trades_df['pnl'].idxmin()]
    print(f"Best Trade:          ${best['pnl']:.2f} on {best['date']} ({best['signal']})")
    print(f"Worst Trade:         ${worst['pnl']:.2f} on {worst['date']} ({worst['signal']})")

    # Max drawdown
    trades_df['peak'] = trades_df['capital'].cummax()
    trades_df['drawdown'] = (trades_df['capital'] - trades_df['peak']) / trades_df['peak'] * 100
    max_dd = trades_df['drawdown'].min()
    print(f"Max Drawdown:        {max_dd:.2f}%")

    # Print last 10 trades
    print(f"\n--- Last 10 Trades ---")
    print(trades_df[['date', 'signal', 'first_30_ret', 'entry', 'exit', 'pnl', 'capital']].tail(10).to_string(index=False))

print(f"\n" + "=" * 60)
