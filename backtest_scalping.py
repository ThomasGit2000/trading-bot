"""
SCALPING STRATEGY BACKTEST
Target: 0.25% daily from ~100 trades
Testing multiple scalping approaches
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Parameters
SYMBOLS = ["TQQQ", "SOXL", "QQQ", "SPY"]  # High volume, high volatility
START_DATE = "2025-01-01"
END_DATE = "2025-12-31"
STARTING_CAPITAL = 10000  # Need more capital for scalping

# Cost assumptions (realistic for IB)
COMMISSION_PER_SHARE = 0.005  # $0.005 per share
SPREAD_COST_PCT = 0.01  # 0.01% spread (1 cent per $100)

print("=" * 70)
print("SCALPING STRATEGY ANALYSIS")
print("=" * 70)
print(f"Target: 0.25% daily (~$25 on $10k)")
print(f"Capital: ${STARTING_CAPITAL:,}")
print(f"Period: {START_DATE} to {END_DATE}")
print("=" * 70)

# Download 5-minute data (last 60 days only available)
print("\nDownloading recent 5-min data for scalping analysis...")

all_data = {}
for symbol in SYMBOLS:
    ticker = yf.Ticker(symbol)
    data = ticker.history(period="60d", interval="5m")
    if len(data) > 0:
        data['symbol'] = symbol
        data['date'] = data.index.date
        data['time'] = data.index.time
        data['returns'] = data['Close'].pct_change()
        all_data[symbol] = data
        print(f"  {symbol}: {len(data)} bars, {len(data['date'].unique())} days")


def calculate_strategy_stats(trades_df, name, capital):
    """Calculate strategy statistics"""
    if len(trades_df) == 0:
        return None

    total_trades = len(trades_df)
    winners = len(trades_df[trades_df['net_pnl'] > 0])
    win_rate = winners / total_trades * 100

    gross_pnl = trades_df['gross_pnl'].sum()
    total_costs = trades_df['costs'].sum()
    net_pnl = trades_df['net_pnl'].sum()

    avg_win = trades_df[trades_df['net_pnl'] > 0]['net_pnl'].mean() if winners > 0 else 0
    avg_loss = trades_df[trades_df['net_pnl'] < 0]['net_pnl'].mean() if winners < total_trades else 0

    return {
        'name': name,
        'trades': total_trades,
        'trades_per_day': total_trades / len(trades_df['date'].unique()),
        'win_rate': win_rate,
        'gross_pnl': gross_pnl,
        'costs': total_costs,
        'net_pnl': net_pnl,
        'return_pct': (net_pnl / capital) * 100,
        'avg_win': avg_win,
        'avg_loss': avg_loss
    }


def run_momentum_scalping(df, capital, threshold=0.001):
    """
    Strategy 1: Momentum Scalping
    Buy when price moves up X% in 5 min, sell after next bar
    """
    trades = []
    position = 0
    entry_price = 0

    for i in range(1, len(df) - 1):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        next_row = df.iloc[i+1]

        ret = (row['Close'] - prev_row['Close']) / prev_row['Close']

        # Entry signal: strong 5-min move
        if position == 0 and abs(ret) > threshold:
            position = 1 if ret > 0 else -1
            entry_price = row['Close']
            shares = int(capital / entry_price)

            # Exit next bar
            exit_price = next_row['Close']

            if position == 1:
                gross_pnl = shares * (exit_price - entry_price)
            else:
                gross_pnl = shares * (entry_price - exit_price)

            # Costs: commission + spread
            costs = (shares * COMMISSION_PER_SHARE * 2) + (shares * entry_price * SPREAD_COST_PCT / 100 * 2)

            trades.append({
                'date': row.name.date(),
                'entry': entry_price,
                'exit': exit_price,
                'shares': shares,
                'gross_pnl': gross_pnl,
                'costs': costs,
                'net_pnl': gross_pnl - costs
            })

            position = 0

    return pd.DataFrame(trades)


def run_mean_reversion_scalping(df, capital, lookback=6, threshold=0.003):
    """
    Strategy 2: Mean Reversion Scalping
    Buy when price drops X% below 30-min average, sell at mean
    """
    trades = []
    df = df.copy()
    df['sma'] = df['Close'].rolling(lookback).mean()
    df['deviation'] = (df['Close'] - df['sma']) / df['sma']

    position = 0
    entry_price = 0
    entry_idx = 0

    for i in range(lookback, len(df) - 1):
        row = df.iloc[i]

        if pd.isna(row['deviation']):
            continue

        # Entry: price deviated from mean
        if position == 0 and abs(row['deviation']) > threshold:
            position = 1 if row['deviation'] < -threshold else -1  # Buy dip, sell rip
            entry_price = row['Close']
            entry_idx = i
            shares = int(capital / entry_price)

        # Exit: price returns to mean OR max hold 6 bars (30 min)
        elif position != 0:
            bars_held = i - entry_idx
            returned_to_mean = abs(row['deviation']) < threshold / 2
            max_hold = bars_held >= 6

            if returned_to_mean or max_hold:
                exit_price = row['Close']

                if position == 1:
                    gross_pnl = shares * (exit_price - entry_price)
                else:
                    gross_pnl = shares * (entry_price - exit_price)

                costs = (shares * COMMISSION_PER_SHARE * 2) + (shares * entry_price * SPREAD_COST_PCT / 100 * 2)

                trades.append({
                    'date': row.name.date(),
                    'entry': entry_price,
                    'exit': exit_price,
                    'shares': shares,
                    'gross_pnl': gross_pnl,
                    'costs': costs,
                    'net_pnl': gross_pnl - costs
                })

                position = 0

    return pd.DataFrame(trades)


def run_breakout_scalping(df, capital, lookback=12):
    """
    Strategy 3: Breakout Scalping
    Buy breakout above 1-hour high, sell after X bars
    """
    trades = []
    df = df.copy()
    df['high_lookback'] = df['High'].rolling(lookback).max()
    df['low_lookback'] = df['Low'].rolling(lookback).min()

    position = 0
    entry_price = 0
    entry_idx = 0

    for i in range(lookback, len(df) - 1):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]

        # Entry: breakout
        if position == 0:
            if row['Close'] > prev_row['high_lookback']:
                position = 1
                entry_price = row['Close']
                entry_idx = i
                shares = int(capital / entry_price)
            elif row['Close'] < prev_row['low_lookback']:
                position = -1
                entry_price = row['Close']
                entry_idx = i
                shares = int(capital / entry_price)

        # Exit: hold for 3 bars (15 min)
        elif position != 0 and (i - entry_idx) >= 3:
            exit_price = row['Close']

            if position == 1:
                gross_pnl = shares * (exit_price - entry_price)
            else:
                gross_pnl = shares * (entry_price - exit_price)

            costs = (shares * COMMISSION_PER_SHARE * 2) + (shares * entry_price * SPREAD_COST_PCT / 100 * 2)

            trades.append({
                'date': row.name.date(),
                'entry': entry_price,
                'exit': exit_price,
                'shares': shares,
                'gross_pnl': gross_pnl,
                'costs': costs,
                'net_pnl': gross_pnl - costs
            })

            position = 0

    return pd.DataFrame(trades)


# Run backtests
print("\n" + "=" * 70)
print("STRATEGY COMPARISON")
print("=" * 70)

all_results = []

for symbol in SYMBOLS:
    if symbol not in all_data:
        continue

    df = all_data[symbol]
    print(f"\n--- {symbol} ---")

    # Strategy 1: Momentum
    trades = run_momentum_scalping(df, STARTING_CAPITAL, threshold=0.002)
    result = calculate_strategy_stats(trades, f"{symbol} Momentum", STARTING_CAPITAL)
    if result:
        all_results.append(result)
        print(f"Momentum: {result['trades']} trades, {result['trades_per_day']:.1f}/day, Net: ${result['net_pnl']:.2f} ({result['return_pct']:.2f}%)")

    # Strategy 2: Mean Reversion
    trades = run_mean_reversion_scalping(df, STARTING_CAPITAL, threshold=0.003)
    result = calculate_strategy_stats(trades, f"{symbol} Mean Rev", STARTING_CAPITAL)
    if result:
        all_results.append(result)
        print(f"Mean Rev:  {result['trades']} trades, {result['trades_per_day']:.1f}/day, Net: ${result['net_pnl']:.2f} ({result['return_pct']:.2f}%)")

    # Strategy 3: Breakout
    trades = run_breakout_scalping(df, STARTING_CAPITAL)
    result = calculate_strategy_stats(trades, f"{symbol} Breakout", STARTING_CAPITAL)
    if result:
        all_results.append(result)
        print(f"Breakout:  {result['trades']} trades, {result['trades_per_day']:.1f}/day, Net: ${result['net_pnl']:.2f} ({result['return_pct']:.2f}%)")


# Summary
print("\n" + "=" * 70)
print("FULL RESULTS TABLE")
print("=" * 70)
print(f"\n{'Strategy':<25} {'Trades':>7} {'Per Day':>8} {'Win%':>7} {'Gross':>10} {'Costs':>10} {'Net':>10}")
print("-" * 85)

for r in sorted(all_results, key=lambda x: x['net_pnl'], reverse=True):
    print(f"{r['name']:<25} {r['trades']:>7} {r['trades_per_day']:>7.1f} {r['win_rate']:>6.1f}% ${r['gross_pnl']:>9.2f} ${r['costs']:>9.2f} ${r['net_pnl']:>9.2f}")

# Reality check
print("\n" + "=" * 70)
print("REALITY CHECK: YOUR 0.25% DAILY TARGET")
print("=" * 70)

days = len(all_data[SYMBOLS[0]]['date'].unique())
target_daily = 0.0025 * STARTING_CAPITAL  # $25 on $10k
target_total = target_daily * days

print(f"\nDays in test: {days}")
print(f"Target daily: ${target_daily:.2f}")
print(f"Target total: ${target_total:.2f}")

best = max(all_results, key=lambda x: x['net_pnl']) if all_results else None
if best:
    daily_achieved = best['net_pnl'] / days
    print(f"\nBest strategy: {best['name']}")
    print(f"Achieved daily: ${daily_achieved:.2f}")
    print(f"Achieved total: ${best['net_pnl']:.2f}")
    print(f"Target met: {'YES' if daily_achieved >= target_daily else 'NO'}")

print("\n" + "=" * 70)
