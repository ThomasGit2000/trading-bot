"""
IMPROVED First Hour / Last Hour Strategy
Testing multiple enhancements
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Parameters
SYMBOL = "QQQ"
START_DATE = "2025-01-01"
END_DATE = "2025-12-31"
STARTING_CAPITAL = 5000

print(f"=" * 70)
print(f"TESTING IMPROVEMENTS TO FIRST HOUR / LAST HOUR STRATEGY")
print(f"=" * 70)
print(f"Symbol: {SYMBOL}")
print(f"Period: {START_DATE} to {END_DATE}")
print(f"Starting Capital: ${STARTING_CAPITAL:,.2f}")
print(f"=" * 70)

# Download data
print(f"\nDownloading data...")
ticker = yf.Ticker(SYMBOL)

# Hourly data for strategy
hourly = ticker.history(start=START_DATE, end=END_DATE, interval="1h")
print(f"Hourly bars: {len(hourly)}")

# Daily data for trend filter
daily = ticker.history(start="2024-10-01", end=END_DATE, interval="1d")
daily['SMA20'] = daily['Close'].rolling(20).mean()
daily['SMA50'] = daily['Close'].rolling(50).mean()
daily['Trend'] = np.where(daily['Close'] > daily['SMA20'], 'BULL', 'BEAR')
print(f"Daily bars: {len(daily)}")

# Prepare hourly data
hourly['date'] = hourly.index.date
hourly['hour'] = hourly.index.hour
trading_days = hourly['date'].unique()
print(f"Trading days: {len(trading_days)}")


def run_backtest(name, threshold=0.003, trend_filter=False, strong_signal_only=False,
                 avoid_monday=False, stop_loss=None, long_only_bull=False):
    """Run backtest with specified parameters"""
    capital = STARTING_CAPITAL
    trades = []

    for day in trading_days:
        day_data = hourly[hourly['date'] == day].copy()
        if len(day_data) < 5:
            continue

        # Get daily trend
        day_str = pd.Timestamp(day)
        daily_row = daily[daily.index.date == day]
        if len(daily_row) == 0:
            trend = 'UNKNOWN'
        else:
            trend = daily_row.iloc[0]['Trend']

        # First hour
        first_hour = day_data[day_data['hour'].isin([9, 10])].head(1)
        last_hour = day_data[day_data['hour'] == 15].tail(1)
        if len(first_hour) == 0 or len(last_hour) == 0:
            continue

        open_price = first_hour.iloc[0]['Open']
        first_hour_close = first_hour.iloc[0]['Close']
        first_hour_return = (first_hour_close - open_price) / open_price

        # Entry
        entry_bars = day_data[day_data['hour'] >= 10]
        if len(entry_bars) < 2:
            continue
        entry_price = entry_bars.iloc[1]['Open']
        exit_price = last_hour.iloc[0]['Close']

        # Determine signal
        signal = "NONE"

        # Strong signal filter (use 0.5% instead of 0.3%)
        actual_threshold = 0.005 if strong_signal_only else threshold

        if first_hour_return > actual_threshold:
            signal = "LONG"
        elif first_hour_return < -actual_threshold:
            signal = "SHORT"

        if signal == "NONE":
            continue

        # FILTER: Trend alignment
        if trend_filter:
            if signal == "LONG" and trend == "BEAR":
                continue
            if signal == "SHORT" and trend == "BULL":
                continue

        # FILTER: Long only in bull market
        if long_only_bull and trend == "BULL" and signal == "SHORT":
            continue

        # FILTER: Avoid Monday
        if avoid_monday and pd.Timestamp(day).dayofweek == 0:
            continue

        # Calculate P&L
        shares = int(capital / entry_price)
        if shares == 0:
            continue

        if signal == "LONG":
            pnl = shares * (exit_price - entry_price)
            # Stop loss check (simplified - using close, not intraday low)
            if stop_loss:
                intraday_low = day_data['Low'].min()
                stop_price = entry_price * (1 - stop_loss)
                if intraday_low < stop_price:
                    pnl = shares * (stop_price - entry_price)
        else:  # SHORT
            pnl = shares * (entry_price - exit_price)
            if stop_loss:
                intraday_high = day_data['High'].max()
                stop_price = entry_price * (1 + stop_loss)
                if intraday_high > stop_price:
                    pnl = shares * (entry_price - stop_price)

        capital += pnl
        trades.append({
            'date': day,
            'signal': signal,
            'trend': trend,
            'pnl': pnl,
            'capital': capital
        })

    # Calculate stats
    if len(trades) == 0:
        return None

    trades_df = pd.DataFrame(trades)
    total_trades = len(trades_df)
    winning = len(trades_df[trades_df['pnl'] > 0])
    win_rate = winning / total_trades * 100
    total_return = (capital / STARTING_CAPITAL - 1) * 100

    trades_df['peak'] = trades_df['capital'].cummax()
    trades_df['dd'] = (trades_df['capital'] - trades_df['peak']) / trades_df['peak'] * 100
    max_dd = trades_df['dd'].min()

    return {
        'name': name,
        'trades': total_trades,
        'win_rate': win_rate,
        'return': total_return,
        'final_capital': capital,
        'max_dd': max_dd,
        'pnl': capital - STARTING_CAPITAL
    }


# Run all variations
print(f"\n" + "=" * 70)
print("TESTING DIFFERENT IMPROVEMENTS")
print("=" * 70)

results = []

# 1. Baseline
r = run_backtest("1. BASELINE (0.3% threshold)")
if r: results.append(r)

# 2. Higher threshold
r = run_backtest("2. Higher threshold (0.5%)", strong_signal_only=True)
if r: results.append(r)

# 3. Trend filter
r = run_backtest("3. Trend filter (trade with trend)", trend_filter=True)
if r: results.append(r)

# 4. Long only in bull
r = run_backtest("4. No shorts in bull market", long_only_bull=True)
if r: results.append(r)

# 5. Avoid Monday
r = run_backtest("5. Avoid Mondays", avoid_monday=True)
if r: results.append(r)

# 6. Stop loss 1%
r = run_backtest("6. With 1% stop loss", stop_loss=0.01)
if r: results.append(r)

# 7. Stop loss 0.5%
r = run_backtest("7. With 0.5% stop loss", stop_loss=0.005)
if r: results.append(r)

# 8. Combo: Trend + Higher threshold
r = run_backtest("8. COMBO: Trend + 0.5% threshold", trend_filter=True, strong_signal_only=True)
if r: results.append(r)

# 9. Combo: Trend + No Monday
r = run_backtest("9. COMBO: Trend + No Monday", trend_filter=True, avoid_monday=True)
if r: results.append(r)

# 10. Best combo attempt
r = run_backtest("10. BEST: Trend + 0.5% + No Monday", trend_filter=True, strong_signal_only=True, avoid_monday=True)
if r: results.append(r)

# Print results table
print(f"\n{'Strategy':<40} {'Trades':>7} {'Win%':>7} {'Return':>9} {'MaxDD':>8} {'Final $':>10}")
print("-" * 85)

for r in sorted(results, key=lambda x: x['return'], reverse=True):
    print(f"{r['name']:<40} {r['trades']:>7} {r['win_rate']:>6.1f}% {r['return']:>8.2f}% {r['max_dd']:>7.2f}% ${r['final_capital']:>9,.2f}")

print(f"\n" + "=" * 70)
print("ANALYSIS")
print("=" * 70)

baseline = next(r for r in results if 'BASELINE' in r['name'])
best = max(results, key=lambda x: x['return'])
best_sharpe = max(results, key=lambda x: x['return'] / abs(r['max_dd']) if r['max_dd'] != 0 else 0)

print(f"\nBaseline Return:     {baseline['return']:.2f}%")
print(f"Best Return:         {best['return']:.2f}% ({best['name']})")
print(f"Improvement:         +{best['return'] - baseline['return']:.2f}%")

print(f"\n" + "=" * 70)
