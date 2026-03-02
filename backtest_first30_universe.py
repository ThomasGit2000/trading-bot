"""
FIRST 30 / LAST 30 ACROSS STOCK UNIVERSE
Apply the proven intraday momentum pattern across 100 stocks
At 10:00 AM, find stocks with strongest first-hour momentum, ride to close
"""

import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import warnings
warnings.filterwarnings('ignore')

# Large universe
STOCK_UNIVERSE = [
    # Mega cap
    "NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "TSLA", "AMD",
    # Tech
    "AVGO", "CRM", "ORCL", "ADBE", "NFLX", "QCOM", "INTC", "MU",
    "NOW", "SNOW", "DDOG", "NET", "ZS", "CRWD", "PANW",
    # Financials
    "V", "MA", "JPM", "GS", "MS", "BAC", "WFC", "C", "BLK", "SCHW",
    # Consumer
    "WMT", "COST", "HD", "NKE", "SBUX", "MCD", "TGT", "LOW",
    # Industrial
    "CAT", "DE", "BA", "GE", "HON", "UPS", "FDX", "RTX", "LMT",
    # Healthcare
    "UNH", "JNJ", "LLY", "ABBV", "PFE", "TMO", "DHR", "BMY",
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "OXY",
    # High beta
    "COIN", "PLTR", "SOFI", "HOOD", "RIVN", "LCID",
    # ETFs
    "SPY", "QQQ", "IWM", "XLF", "XLK", "XLE", "XLV",
    # Additional
    "PYPL", "SQ", "DIS", "CMCSA", "T", "VZ", "PEP", "KO",
    "IBM", "CSCO", "INTU", "ADP", "AMAT", "LRCX", "KLAC"
]

STARTING_CAPITAL = 10000
POSITION_SIZE_PCT = 0.10  # 10% per position
MAX_POSITIONS = 10  # Top 10 movers
COMMISSION = 1.00

print("=" * 70)
print("FIRST 30 / LAST 30 - APPLIED TO FULL UNIVERSE")
print("=" * 70)
print(f"Universe: {len(STOCK_UNIVERSE)} stocks")
print(f"Strategy: At 10AM, buy top movers from first 30 min, hold to 3:30PM")
print(f"Capital: ${STARTING_CAPITAL:,}")
print("=" * 70)

# Download data
print(f"\nDownloading hourly data...")

def download_stock(symbol):
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="60d", interval="1h")
        if len(data) > 50:
            return symbol, data
    except:
        pass
    return symbol, None

all_data = {}
with ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(download_stock, STOCK_UNIVERSE))

for symbol, data in results:
    if data is not None:
        all_data[symbol] = data

print(f"Downloaded: {len(all_data)} stocks")

# Get trading days
sample = list(all_data.values())[0]
sample['date'] = sample.index.date
trading_days = sorted(sample['date'].unique())
print(f"Trading days: {len(trading_days)}")


def run_backtest(threshold=0.003, top_n=10, long_only_bull=True):
    """
    At 10AM each day:
    1. Calculate first-hour return for all stocks
    2. Select top N with strongest momentum (>threshold)
    3. Enter in direction of momentum
    4. Exit at 3:30 PM
    """
    capital = STARTING_CAPITAL
    trades = []
    daily_pnl = []

    for day in trading_days:
        first_hour_moves = []

        # Calculate first hour momentum for each stock
        for symbol, df in all_data.items():
            day_data = df[df.index.date == day]

            if len(day_data) < 5:
                continue

            # First hour bar (9:30-10:30)
            first_bar = day_data[day_data.index.hour == 9]
            if len(first_bar) == 0:
                first_bar = day_data[day_data.index.hour == 10]

            # Entry bar (10:00-11:00)
            entry_bar = day_data[day_data.index.hour == 10]
            if len(entry_bar) == 0:
                entry_bar = day_data[day_data.index.hour == 11]

            # Exit bar (15:00-16:00)
            exit_bar = day_data[day_data.index.hour == 15]

            if len(first_bar) == 0 or len(entry_bar) == 0 or len(exit_bar) == 0:
                continue

            # First hour return
            open_price = first_bar.iloc[0]['Open']
            first_close = first_bar.iloc[0]['Close']
            first_hour_ret = (first_close - open_price) / open_price

            entry_price = entry_bar.iloc[0]['Open']
            exit_price = exit_bar.iloc[0]['Close']

            first_hour_moves.append({
                'symbol': symbol,
                'first_hour_ret': first_hour_ret,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'direction': 'LONG' if first_hour_ret > 0 else 'SHORT'
            })

        if len(first_hour_moves) == 0:
            daily_pnl.append({'date': day, 'pnl': 0, 'trades': 0})
            continue

        moves_df = pd.DataFrame(first_hour_moves)

        # Filter by threshold
        strong_moves = moves_df[moves_df['first_hour_ret'].abs() > threshold]

        if len(strong_moves) == 0:
            daily_pnl.append({'date': day, 'pnl': 0, 'trades': 0})
            continue

        # Sort by absolute momentum, take top N
        strong_moves = strong_moves.sort_values('first_hour_ret', key=abs, ascending=False)
        top_movers = strong_moves.head(top_n)

        day_pnl = 0
        day_trades = 0

        for _, row in top_movers.iterrows():
            position_size = capital * POSITION_SIZE_PCT
            shares = int(position_size / row['entry_price'])

            if shares == 0:
                continue

            # Optional: Long only in general (skip shorts)
            if long_only_bull and row['direction'] == 'SHORT':
                continue

            if row['direction'] == 'LONG':
                gross_pnl = shares * (row['exit_price'] - row['entry_price'])
            else:
                gross_pnl = shares * (row['entry_price'] - row['exit_price'])

            net_pnl = gross_pnl - (COMMISSION * 2)

            trades.append({
                'date': day,
                'symbol': row['symbol'],
                'direction': row['direction'],
                'first_hour_ret': row['first_hour_ret'] * 100,
                'entry': row['entry_price'],
                'exit': row['exit_price'],
                'net_pnl': net_pnl
            })

            day_pnl += net_pnl
            day_trades += 1

        capital += day_pnl
        daily_pnl.append({'date': day, 'pnl': day_pnl, 'trades': day_trades, 'capital': capital})

    return pd.DataFrame(trades), pd.DataFrame(daily_pnl)


# Test different configurations
configs = [
    ("Baseline: Top 10, 0.3% threshold", 0.003, 10, False),
    ("Top 5 movers only", 0.003, 5, False),
    ("Higher threshold (0.5%)", 0.005, 10, False),
    ("Long only (no shorts)", 0.003, 10, True),
    ("Top 5 + Long only", 0.003, 5, True),
    ("Higher thresh + Long only", 0.005, 10, True),
]

print("\n" + "=" * 70)
print("TESTING CONFIGURATIONS")
print("=" * 70)

all_results = []

for name, thresh, top_n, long_only in configs:
    trades_df, daily_df = run_backtest(threshold=thresh, top_n=top_n, long_only_bull=long_only)

    if len(trades_df) == 0:
        print(f"{name}: No trades")
        continue

    total_trades = len(trades_df)
    winners = len(trades_df[trades_df['net_pnl'] > 0])
    win_rate = winners / total_trades * 100
    total_pnl = trades_df['net_pnl'].sum()
    avg_daily_pnl = daily_df['pnl'].mean()
    avg_daily_pct = (avg_daily_pnl / STARTING_CAPITAL) * 100
    profitable_days = len(daily_df[daily_df['pnl'] > 0])

    all_results.append({
        'name': name,
        'trades': total_trades,
        'per_day': total_trades / len(trading_days),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'daily_pnl': avg_daily_pnl,
        'daily_pct': avg_daily_pct,
        'profit_days': profitable_days,
        'trades_df': trades_df
    })

# Results table
print(f"\n{'Config':<35} {'Trades':>6} {'/Day':>5} {'Win%':>6} {'Total':>10} {'Daily':>9} {'D%':>7} {'ProfDays':>9}")
print("-" * 95)

for r in sorted(all_results, key=lambda x: x['daily_pnl'], reverse=True):
    print(f"{r['name']:<35} {r['trades']:>6} {r['per_day']:>4.1f} {r['win_rate']:>5.1f}% ${r['total_pnl']:>9.2f} ${r['daily_pnl']:>8.2f} {r['daily_pct']:>6.2f}% {r['profit_days']:>5}/60")

# Best config details
best = max(all_results, key=lambda x: x['daily_pnl'])
print(f"\n" + "=" * 70)
print(f"BEST: {best['name']}")
print("=" * 70)
print(f"Daily P&L: ${best['daily_pnl']:.2f} ({best['daily_pct']:.2f}%)")
print(f"Win Rate: {best['win_rate']:.1f}%")
print(f"Profitable Days: {best['profit_days']}/60")

# Top stocks
print(f"\n--- Top Performing Stocks ---")
stock_stats = best['trades_df'].groupby('symbol')['net_pnl'].agg(['sum', 'count', 'mean'])
stock_stats = stock_stats.sort_values('sum', ascending=False)
print(stock_stats.head(10).to_string())

# Target check
print(f"\n" + "=" * 70)
print("TARGET CHECK: 0.25% daily = $25/day")
print("=" * 70)
print(f"Target: $25.00/day")
print(f"Achieved: ${best['daily_pnl']:.2f}/day")
print(f"Target Met: {'YES' if best['daily_pnl'] >= 25 else 'NO'}")

# Sample trades
print(f"\n--- Sample Trades ---")
print(best['trades_df'][['date', 'symbol', 'direction', 'first_hour_ret', 'entry', 'exit', 'net_pnl']].head(15).to_string(index=False))

print("\n" + "=" * 70)
