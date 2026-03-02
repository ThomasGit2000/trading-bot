"""
IMPROVED INTRADAY MOMENTUM - Multiple Strategy Comparison
Testing different momentum approaches to find what works
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import warnings
warnings.filterwarnings('ignore')

# Focused universe - remove ultra-volatile names that just create noise
STOCK_UNIVERSE = [
    # Mega cap (most liquid, predictable momentum)
    "NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "TSLA", "AMD",
    # Large cap tech
    "AVGO", "CRM", "ORCL", "ADBE", "NFLX", "QCOM", "INTC",
    # Financials
    "V", "MA", "JPM", "GS", "MS", "BAC",
    # Consumer
    "WMT", "COST", "HD", "NKE", "SBUX", "MCD",
    # Industrial
    "CAT", "DE", "BA", "GE", "HON", "UPS",
    # Healthcare
    "UNH", "JNJ", "LLY", "ABBV", "PFE", "TMO",
    # Energy
    "XOM", "CVX", "COP", "SLB",
    # High-beta but tradeable
    "COIN", "PLTR", "SOFI", "HOOD",
    # ETFs
    "SPY", "QQQ", "IWM"
]

STARTING_CAPITAL = 10000
POSITION_SIZE_PCT = 0.10
MAX_POSITIONS = 10
COMMISSION_PER_TRADE = 1.00

print("=" * 70)
print("IMPROVED MOMENTUM STRATEGY COMPARISON")
print("=" * 70)

# Download data
print(f"\nDownloading data for {len(STOCK_UNIVERSE)} stocks...")

def download_stock(symbol):
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="60d", interval="5m")
        if len(data) > 100:
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

# Prepare data
combined = []
for symbol, df in all_data.items():
    df = df.copy()
    df['symbol'] = symbol
    df['date'] = df.index.date
    df['hour'] = df.index.hour
    combined.append(df)

full_df = pd.concat(combined)
trading_days = sorted(full_df['date'].unique())
print(f"Trading days: {len(trading_days)}")


def run_strategy(strategy_name, entry_func, exit_bars=6):
    """Run a strategy and return results"""
    capital = STARTING_CAPITAL
    trades = []

    for day in trading_days:
        day_data = full_df[full_df['date'] == day]

        for symbol in all_data.keys():
            stock_data = day_data[day_data['symbol'] == symbol].copy()
            if len(stock_data) < 30:
                continue

            # Calculate indicators
            stock_data['sma10'] = stock_data['Close'].rolling(10).mean()
            stock_data['sma30'] = stock_data['Close'].rolling(30).mean()
            stock_data['momentum_5'] = stock_data['Close'].pct_change(5)
            stock_data['momentum_10'] = stock_data['Close'].pct_change(10)
            stock_data['rsi'] = calculate_rsi(stock_data['Close'], 14)
            stock_data['vol_ratio'] = stock_data['Volume'] / stock_data['Volume'].rolling(20).mean()

            # Find entry signals
            for i in range(30, len(stock_data) - exit_bars):
                row = stock_data.iloc[i]

                # Skip first and last hour
                if row['hour'] < 10 or row['hour'] >= 15:
                    continue

                # Check entry signal
                signal = entry_func(stock_data, i)
                if signal is None:
                    continue

                # Entry
                entry_price = row['Close']
                exit_price = stock_data.iloc[i + exit_bars]['Close']
                shares = int((capital * POSITION_SIZE_PCT) / entry_price)

                if shares == 0:
                    continue

                if signal == 'LONG':
                    gross_pnl = shares * (exit_price - entry_price)
                else:
                    gross_pnl = shares * (entry_price - exit_price)

                net_pnl = gross_pnl - (COMMISSION_PER_TRADE * 2)

                trades.append({
                    'date': day,
                    'symbol': symbol,
                    'direction': signal,
                    'entry': entry_price,
                    'exit': exit_price,
                    'net_pnl': net_pnl
                })

                break  # One trade per stock per day

    return pd.DataFrame(trades)


def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


# Strategy 1: Momentum Continuation (original)
def strategy_momentum_chase(data, i):
    """Buy after strong momentum move"""
    row = data.iloc[i]
    if pd.isna(row['momentum_5']):
        return None
    if row['momentum_5'] > 0.01:
        return 'LONG'
    if row['momentum_5'] < -0.01:
        return 'SHORT'
    return None


# Strategy 2: Momentum + Pullback
def strategy_pullback(data, i):
    """Buy pullback in momentum trend"""
    row = data.iloc[i]
    prev = data.iloc[i-1]

    if pd.isna(row['sma10']) or pd.isna(row['sma30']):
        return None

    # Uptrend: SMA10 > SMA30
    uptrend = row['sma10'] > row['sma30']
    downtrend = row['sma10'] < row['sma30']

    # Pullback: price dipped below SMA10 but now recovering
    pullback_up = prev['Close'] < prev['sma10'] and row['Close'] > row['sma10']
    pullback_down = prev['Close'] > prev['sma10'] and row['Close'] < row['sma10']

    if uptrend and pullback_up:
        return 'LONG'
    if downtrend and pullback_down:
        return 'SHORT'
    return None


# Strategy 3: RSI Reversal in Trend
def strategy_rsi_trend(data, i):
    """Buy oversold in uptrend, sell overbought in downtrend"""
    row = data.iloc[i]
    prev = data.iloc[i-1]

    if pd.isna(row['rsi']) or pd.isna(row['sma30']):
        return None

    uptrend = row['Close'] > row['sma30']
    downtrend = row['Close'] < row['sma30']

    # RSI crossing out of oversold in uptrend
    if uptrend and prev['rsi'] < 35 and row['rsi'] > 35:
        return 'LONG'
    # RSI crossing out of overbought in downtrend
    if downtrend and prev['rsi'] > 65 and row['rsi'] < 65:
        return 'SHORT'
    return None


# Strategy 4: Volume Breakout
def strategy_volume_breakout(data, i):
    """Trade breakouts with volume confirmation"""
    row = data.iloc[i]

    if pd.isna(row['vol_ratio']):
        return None

    # Need volume surge
    if row['vol_ratio'] < 2.0:
        return None

    # Price breaking above recent high
    recent_high = data.iloc[i-10:i]['High'].max()
    recent_low = data.iloc[i-10:i]['Low'].min()

    if row['Close'] > recent_high:
        return 'LONG'
    if row['Close'] < recent_low:
        return 'SHORT'
    return None


# Strategy 5: Opening Range Breakout
def strategy_orb(data, i):
    """Opening range breakout - trade after 10:00"""
    row = data.iloc[i]

    if row['hour'] != 10 or data.iloc[i].name.minute > 15:
        return None

    # Get first 30 min range (9:30-10:00)
    first_30 = data[data['hour'] == 9]
    if len(first_30) < 3:
        return None

    orb_high = first_30['High'].max()
    orb_low = first_30['Low'].min()

    if row['Close'] > orb_high:
        return 'LONG'
    if row['Close'] < orb_low:
        return 'SHORT'
    return None


# Strategy 6: Trend + Momentum Confirmation
def strategy_trend_momentum(data, i):
    """Only trade momentum in direction of trend"""
    row = data.iloc[i]

    if pd.isna(row['sma10']) or pd.isna(row['sma30']) or pd.isna(row['momentum_5']):
        return None

    # Strong trend
    uptrend = row['sma10'] > row['sma30'] * 1.002
    downtrend = row['sma10'] < row['sma30'] * 0.998

    # Momentum confirmation
    if uptrend and row['momentum_5'] > 0.005:
        return 'LONG'
    if downtrend and row['momentum_5'] < -0.005:
        return 'SHORT'
    return None


# Run all strategies
strategies = [
    ("1. Momentum Chase (baseline)", strategy_momentum_chase),
    ("2. Pullback in Trend", strategy_pullback),
    ("3. RSI Reversal + Trend", strategy_rsi_trend),
    ("4. Volume Breakout", strategy_volume_breakout),
    ("5. Opening Range Breakout", strategy_orb),
    ("6. Trend + Momentum", strategy_trend_momentum),
]

print("\n" + "=" * 70)
print("STRATEGY COMPARISON")
print("=" * 70)

results = []

for name, func in strategies:
    trades_df = run_strategy(name, func, exit_bars=6)

    if len(trades_df) == 0:
        print(f"{name}: No trades")
        continue

    total_trades = len(trades_df)
    winners = len(trades_df[trades_df['net_pnl'] > 0])
    win_rate = winners / total_trades * 100
    total_pnl = trades_df['net_pnl'].sum()
    daily_pnl = total_pnl / len(trading_days)

    results.append({
        'name': name,
        'trades': total_trades,
        'per_day': total_trades / len(trading_days),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'daily_pnl': daily_pnl,
        'daily_pct': (daily_pnl / STARTING_CAPITAL) * 100
    })

# Print results table
print(f"\n{'Strategy':<35} {'Trades':>7} {'/Day':>6} {'Win%':>7} {'Total $':>10} {'Daily $':>9} {'Daily%':>8}")
print("-" * 90)

for r in sorted(results, key=lambda x: x['total_pnl'], reverse=True):
    print(f"{r['name']:<35} {r['trades']:>7} {r['per_day']:>5.1f} {r['win_rate']:>6.1f}% ${r['total_pnl']:>9.2f} ${r['daily_pnl']:>8.2f} {r['daily_pct']:>7.3f}%")

# Target check
print(f"\n" + "=" * 70)
print("TARGET: 0.25% daily = $25/day on $10,000")
print("=" * 70)

best = max(results, key=lambda x: x['daily_pnl']) if results else None
if best:
    print(f"\nBest Strategy: {best['name']}")
    print(f"Daily P&L: ${best['daily_pnl']:.2f} ({best['daily_pct']:.3f}%)")
    print(f"Target Met: {'YES' if best['daily_pnl'] >= 25 else 'NO'}")

print("\n" + "=" * 70)
