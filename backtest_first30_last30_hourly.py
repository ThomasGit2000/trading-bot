"""
Backtest: First Hour / Last Hour Intraday Momentum Strategy
Using hourly data (Yahoo keeps ~2 years)
QQQ for 2025
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

print(f"=" * 60)
print(f"BACKTEST: First Hour / Last Hour Strategy")
print(f"=" * 60)
print(f"Symbol: {SYMBOL}")
print(f"Period: {START_DATE} to {END_DATE}")
print(f"Starting Capital: ${STARTING_CAPITAL:,.2f}")
print(f"Entry Threshold: {THRESHOLD*100:.1f}%")
print(f"=" * 60)

# Download hourly data
print(f"\nDownloading {SYMBOL} hourly data...")
ticker = yf.Ticker(SYMBOL)

# Get data in chunks
all_data = []
current_start = datetime.strptime(START_DATE, "%Y-%m-%d")
end_dt = datetime.strptime(END_DATE, "%Y-%m-%d")

while current_start < end_dt:
    chunk_end = min(current_start + timedelta(days=700), end_dt)
    try:
        data = ticker.history(
            start=current_start.strftime("%Y-%m-%d"),
            end=chunk_end.strftime("%Y-%m-%d"),
            interval="1h"
        )
        if len(data) > 0:
            all_data.append(data)
            print(f"  Downloaded {current_start.strftime('%Y-%m-%d')} to {chunk_end.strftime('%Y-%m-%d')}: {len(data)} bars")
    except Exception as e:
        print(f"  Error: {e}")
    current_start = chunk_end + timedelta(days=1)

if not all_data:
    print("ERROR: No data downloaded!")
    exit(1)

df = pd.concat(all_data)
df = df[~df.index.duplicated(keep='first')]
print(f"\nTotal bars: {len(df)}")

# Get unique trading days
df['date'] = df.index.date
df['hour'] = df.index.hour
trading_days = df['date'].unique()
print(f"Trading days: {len(trading_days)}")

# Backtest
trades = []
capital = STARTING_CAPITAL

for day in trading_days:
    day_data = df[df['date'] == day].copy()

    if len(day_data) < 5:  # Need enough bars
        continue

    # First hour bar (9:30-10:30 = hour 9 or 10 depending on timezone)
    first_hour = day_data[day_data['hour'].isin([9, 10])].head(1)

    # Last hour bar (15:00-16:00 = hour 15)
    last_hour = day_data[day_data['hour'] == 15].tail(1)

    if len(first_hour) == 0 or len(last_hour) == 0:
        continue

    # Calculate first hour return
    open_price = first_hour.iloc[0]['Open']
    first_hour_close = first_hour.iloc[0]['Close']
    first_hour_return = (first_hour_close - open_price) / open_price

    # Entry after first hour
    entry_bars = day_data[day_data['hour'] >= 10]
    if len(entry_bars) < 2:
        continue
    entry_price = entry_bars.iloc[1]['Open']  # Enter at start of second hour

    # Exit at close
    exit_price = last_hour.iloc[0]['Close']

    # Trading logic
    signal = "NONE"
    pnl = 0

    if first_hour_return > THRESHOLD:
        signal = "LONG"
        shares = int(capital / entry_price)
        if shares > 0:
            pnl = shares * (exit_price - entry_price)
            capital += pnl

    elif first_hour_return < -THRESHOLD:
        signal = "SHORT"
        shares = int(capital / entry_price)
        if shares > 0:
            pnl = shares * (entry_price - exit_price)
            capital += pnl

    if signal != "NONE":
        trade = {
            'date': day,
            'signal': signal,
            'first_hr_ret': first_hour_return * 100,
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
    total_trades = len(trades_df)
    winning_trades = len(trades_df[trades_df['pnl'] > 0])
    losing_trades = len(trades_df[trades_df['pnl'] < 0])
    win_rate = winning_trades / total_trades * 100

    total_pnl = capital - STARTING_CAPITAL
    total_return = (capital / STARTING_CAPITAL - 1) * 100

    avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
    avg_loss = trades_df[trades_df['pnl'] < 0]['pnl'].mean() if losing_trades > 0 else 0

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
        print(f"Long P&L:            ${long_trades['pnl'].sum():.2f}")
    if len(short_trades) > 0:
        print(f"Short P&L:           ${short_trades['pnl'].sum():.2f}")

    print(f"\n--- Best & Worst ---")
    best = trades_df.loc[trades_df['pnl'].idxmax()]
    worst = trades_df.loc[trades_df['pnl'].idxmin()]
    print(f"Best Trade:          ${best['pnl']:.2f} on {best['date']} ({best['signal']})")
    print(f"Worst Trade:         ${worst['pnl']:.2f} on {worst['date']} ({worst['signal']})")

    trades_df['peak'] = trades_df['capital'].cummax()
    trades_df['drawdown'] = (trades_df['capital'] - trades_df['peak']) / trades_df['peak'] * 100
    max_dd = trades_df['drawdown'].min()
    print(f"Max Drawdown:        {max_dd:.2f}%")

    # Monthly breakdown
    trades_df['month'] = pd.to_datetime(trades_df['date']).dt.to_period('M')
    monthly = trades_df.groupby('month')['pnl'].agg(['sum', 'count'])
    print(f"\n--- Monthly P&L ---")
    for month, row in monthly.iterrows():
        print(f"{month}: ${row['sum']:>8.2f} ({int(row['count'])} trades)")

    print(f"\n--- Last 10 Trades ---")
    print(trades_df[['date', 'signal', 'first_hr_ret', 'entry', 'exit', 'pnl', 'capital']].tail(10).to_string(index=False))

print(f"\n" + "=" * 60)
