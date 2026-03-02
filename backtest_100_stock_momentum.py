"""
INTRADAY MOMENTUM SCANNER
Scan 100 stocks, trade when momentum appears
Target: 0.25% daily
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import warnings
warnings.filterwarnings('ignore')

# High-momentum stock universe (your current stocks + more)
STOCK_UNIVERSE = [
    # Mega cap tech
    "NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "TSLA", "AMD",
    # Semiconductors
    "AVGO", "MU", "QCOM", "INTC", "AMAT", "LRCX", "KLAC", "MRVL",
    # Software
    "CRM", "NOW", "SNOW", "DDOG", "NET", "ZS", "CRWD", "PANW",
    # Fintech
    "V", "MA", "PYPL", "SQ", "COIN", "HOOD",
    # Banks
    "JPM", "BAC", "GS", "MS", "WFC", "C",
    # EV & Auto
    "RIVN", "LCID", "NIO", "XPEV", "GM", "F",
    # Energy
    "XOM", "CVX", "COP", "OXY", "SLB",
    # Retail
    "WMT", "COST", "TGT", "HD", "LOW",
    # Healthcare
    "UNH", "JNJ", "LLY", "PFE", "MRNA", "ABBV",
    # Media/Entertainment
    "DIS", "NFLX", "SPOT", "ROKU",
    # Airlines/Travel
    "DAL", "UAL", "LUV", "AAL", "MAR", "ABNB",
    # Crypto-related
    "MARA", "RIOT", "MSTR",
    # Meme/Retail favorites
    "GME", "AMC", "PLTR", "SOFI",
    # High-beta ETFs
    "TQQQ", "SOXL", "LABU", "TNA",
    # Industrial
    "CAT", "DE", "BA", "GE", "HON",
    # More tech
    "ORCL", "IBM", "CSCO", "ADBE", "INTU"
]

STARTING_CAPITAL = 10000
POSITION_SIZE_PCT = 0.10  # 10% of capital per trade
MAX_POSITIONS = 10  # Max simultaneous positions
COMMISSION_PER_TRADE = 1.00  # Flat $1 per trade (IB estimate)

print("=" * 70)
print("100-STOCK INTRADAY MOMENTUM SCANNER")
print("=" * 70)
print(f"Universe: {len(STOCK_UNIVERSE)} stocks")
print(f"Capital: ${STARTING_CAPITAL:,}")
print(f"Position size: {POSITION_SIZE_PCT*100:.0f}% (${STARTING_CAPITAL * POSITION_SIZE_PCT:,.0f})")
print(f"Max positions: {MAX_POSITIONS}")
print("=" * 70)

# Download data
print(f"\nDownloading 5-min data for {len(STOCK_UNIVERSE)} stocks...")

def download_stock(symbol):
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="60d", interval="5m")
        if len(data) > 100:
            data['symbol'] = symbol
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

print(f"Successfully downloaded: {len(all_data)} stocks")

# Combine all data
combined = []
for symbol, df in all_data.items():
    df = df.copy()
    df['symbol'] = symbol
    df['date'] = df.index.date
    df['time'] = df.index.time
    df['hour'] = df.index.hour
    df['minute'] = df.index.minute
    combined.append(df)

full_df = pd.concat(combined)
trading_days = full_df['date'].unique()
print(f"Trading days: {len(trading_days)}")


def calculate_momentum_signals(day_data, lookback=6, threshold=0.015):
    """
    Calculate momentum signals for all stocks at each bar

    Momentum signal: Price moved +X% in last 30 min (6 bars)
    """
    signals = []

    for symbol in day_data['symbol'].unique():
        stock_data = day_data[day_data['symbol'] == symbol].copy()

        if len(stock_data) < lookback + 1:
            continue

        # Calculate rolling momentum
        stock_data['momentum'] = stock_data['Close'].pct_change(lookback)
        stock_data['volume_surge'] = stock_data['Volume'] / stock_data['Volume'].rolling(20).mean()

        for i in range(lookback, len(stock_data)):
            row = stock_data.iloc[i]

            # Skip first and last 30 min of day
            if row['hour'] < 10 or row['hour'] >= 15:
                continue

            mom = row['momentum']
            vol_surge = row['volume_surge']

            # Strong momentum + volume confirmation
            if abs(mom) > threshold and vol_surge > 1.2:
                signals.append({
                    'time': row.name,
                    'symbol': symbol,
                    'price': row['Close'],
                    'momentum': mom,
                    'volume_surge': vol_surge,
                    'direction': 'LONG' if mom > 0 else 'SHORT'
                })

    return pd.DataFrame(signals)


def run_backtest(momentum_threshold=0.015, hold_bars=6, use_volume_filter=True):
    """
    Run the momentum scanner backtest
    """
    capital = STARTING_CAPITAL
    trades = []
    daily_pnl = []

    for day in trading_days:
        day_data = full_df[full_df['date'] == day]

        # Get all momentum signals for the day
        signals = calculate_momentum_signals(day_data, threshold=momentum_threshold)

        if len(signals) == 0:
            daily_pnl.append({'date': day, 'pnl': 0, 'trades': 0})
            continue

        # Sort by momentum strength
        signals = signals.sort_values('momentum', key=abs, ascending=False)

        # Take top N signals
        top_signals = signals.head(MAX_POSITIONS)

        day_pnl = 0
        day_trades = 0

        for _, signal in top_signals.iterrows():
            symbol = signal['symbol']
            entry_price = signal['price']
            direction = signal['direction']
            entry_time = signal['time']

            # Get future bars for exit
            stock_day_data = day_data[day_data['symbol'] == symbol]
            entry_idx = stock_day_data.index.get_loc(entry_time)

            # Exit after hold_bars or at end of day
            exit_idx = min(entry_idx + hold_bars, len(stock_day_data) - 1)
            exit_price = stock_day_data.iloc[exit_idx]['Close']

            # Calculate P&L
            position_size = capital * POSITION_SIZE_PCT
            shares = int(position_size / entry_price)

            if shares == 0:
                continue

            if direction == 'LONG':
                gross_pnl = shares * (exit_price - entry_price)
            else:
                gross_pnl = shares * (entry_price - exit_price)

            net_pnl = gross_pnl - (COMMISSION_PER_TRADE * 2)  # Entry + exit

            trades.append({
                'date': day,
                'symbol': symbol,
                'direction': direction,
                'entry': entry_price,
                'exit': exit_price,
                'momentum': signal['momentum'] * 100,
                'shares': shares,
                'gross_pnl': gross_pnl,
                'net_pnl': net_pnl
            })

            day_pnl += net_pnl
            day_trades += 1

        capital += day_pnl
        daily_pnl.append({'date': day, 'pnl': day_pnl, 'trades': day_trades, 'capital': capital})

    return pd.DataFrame(trades), pd.DataFrame(daily_pnl)


# Run backtest
print("\n" + "=" * 70)
print("RUNNING MOMENTUM SCANNER BACKTEST")
print("=" * 70)

trades_df, daily_df = run_backtest(momentum_threshold=0.015, hold_bars=6)

if len(trades_df) == 0:
    print("No trades generated!")
else:
    # Results
    total_trades = len(trades_df)
    winners = len(trades_df[trades_df['net_pnl'] > 0])
    win_rate = winners / total_trades * 100

    total_pnl = trades_df['net_pnl'].sum()
    total_return = total_pnl / STARTING_CAPITAL * 100

    avg_trades_per_day = daily_df['trades'].mean()
    profitable_days = len(daily_df[daily_df['pnl'] > 0])

    print(f"\n--- OVERALL RESULTS ---")
    print(f"Total Trades:        {total_trades}")
    print(f"Trades per Day:      {avg_trades_per_day:.1f}")
    print(f"Win Rate:            {win_rate:.1f}%")
    print(f"Total P&L:           ${total_pnl:,.2f}")
    print(f"Total Return:        {total_return:.2f}%")
    print(f"Profitable Days:     {profitable_days}/{len(daily_df)} ({profitable_days/len(daily_df)*100:.1f}%)")

    # Daily stats
    avg_daily_pnl = daily_df['pnl'].mean()
    avg_daily_return = avg_daily_pnl / STARTING_CAPITAL * 100

    print(f"\n--- DAILY STATS ---")
    print(f"Avg Daily P&L:       ${avg_daily_pnl:.2f}")
    print(f"Avg Daily Return:    {avg_daily_return:.3f}%")
    print(f"Best Day:            ${daily_df['pnl'].max():.2f}")
    print(f"Worst Day:           ${daily_df['pnl'].min():.2f}")

    # Target check
    target_daily = 0.0025 * STARTING_CAPITAL
    print(f"\n--- TARGET CHECK ---")
    print(f"Your Target:         ${target_daily:.2f}/day (0.25%)")
    print(f"Achieved:            ${avg_daily_pnl:.2f}/day ({avg_daily_return:.3f}%)")
    print(f"Target Met:          {'YES' if avg_daily_pnl >= target_daily else 'NO'}")

    # Top performing stocks
    print(f"\n--- TOP STOCKS BY P&L ---")
    stock_pnl = trades_df.groupby('symbol')['net_pnl'].agg(['sum', 'count', 'mean'])
    stock_pnl = stock_pnl.sort_values('sum', ascending=False)
    print(stock_pnl.head(10).to_string())

    # Worst stocks
    print(f"\n--- WORST STOCKS BY P&L ---")
    print(stock_pnl.tail(5).to_string())

    # Long vs Short
    print(f"\n--- LONG vs SHORT ---")
    long_trades = trades_df[trades_df['direction'] == 'LONG']
    short_trades = trades_df[trades_df['direction'] == 'SHORT']
    print(f"Long:  {len(long_trades)} trades, ${long_trades['net_pnl'].sum():.2f} P&L")
    print(f"Short: {len(short_trades)} trades, ${short_trades['net_pnl'].sum():.2f} P&L")

    # Sample trades
    print(f"\n--- SAMPLE TRADES ---")
    print(trades_df[['date', 'symbol', 'direction', 'momentum', 'entry', 'exit', 'net_pnl']].head(15).to_string(index=False))

print("\n" + "=" * 70)
