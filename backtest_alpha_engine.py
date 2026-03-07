"""
Backtest Alpha Engine over the last week for 70 stocks.

Compares:
1. Raw breakout signals (no alpha filter)
2. Alpha-filtered signals (only trades when alpha >= threshold)

Metrics:
- Win rate
- Total trades
- Average return per trade
- Sharpe ratio
"""
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict

# Set alpha engine enabled for this backtest
os.environ['ALPHA_ENGINE_ENABLED'] = 'true'
os.environ['ALPHA_THRESHOLD'] = '0.30'

import yfinance as yf
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()

from src.strategy import BreakoutStrategy
from src.alpha_engine import MicroAlphaEngine, AlphaContext

# Get symbols from .env
SYMBOLS = os.getenv('SYMBOLS', '').split(',')
SYMBOLS = [s.strip() for s in SYMBOLS if s.strip()]

# Backtest parameters
LOOKBACK_DAYS = 7
BREAKOUT_LOOKBACK = 60
BREAKOUT_THRESHOLD = 0.005
ATR_MIN_THRESHOLD = 0.0025
STOP_LOSS_PCT = 0.05
TRAILING_STOP_PCT = 0.03
ALPHA_THRESHOLD = 0.30


def fetch_data(symbol: str, days: int = 7) -> pd.DataFrame:
    """Fetch intraday data for backtesting (5-minute bars)."""
    try:
        ticker = yf.Ticker(symbol)
        # Get 5-minute data for the last week
        df = ticker.history(period=f"{days}d", interval="5m")
        if df.empty:
            return None
        return df
    except Exception as e:
        print(f"  Error fetching {symbol}: {e}")
        return None


def simulate_rsi(prices: list, period: int = 14) -> float:
    """Calculate RSI from price list."""
    if len(prices) < period + 1:
        return 50.0

    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    if len(gains) < period:
        return 50.0

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def run_backtest(symbol: str, df: pd.DataFrame, use_alpha: bool = True) -> dict:
    """Run backtest for a single symbol."""
    engine = MicroAlphaEngine()
    strategy = BreakoutStrategy(
        lookback_periods=BREAKOUT_LOOKBACK,
        breakout_threshold=BREAKOUT_THRESHOLD,
        stop_loss_pct=STOP_LOSS_PCT,
        trailing_stop_pct=TRAILING_STOP_PCT,
        atr_filter=True,
        atr_min_threshold=ATR_MIN_THRESHOLD
    )

    trades = []
    position = 0
    entry_price = 0
    entry_time = None
    peak_price = 0

    prices = df['Close'].values
    volumes = df['Volume'].values

    # Volume average for relative volume
    vol_window = 20

    for i in range(len(prices)):
        price = prices[i]
        volume = volumes[i]

        # Add price to strategy
        strategy.add_price(price)

        if len(strategy.prices) < BREAKOUT_LOOKBACK:
            continue

        # Get raw signal
        raw_signal = strategy.get_signal()

        # Calculate indicators for alpha context
        rsi = simulate_rsi(list(strategy.prices), 14)
        atr_pct = strategy.get_atr_percent()

        # Relative volume
        if i >= vol_window:
            avg_vol = np.mean(volumes[i-vol_window:i])
            rel_vol = volume / avg_vol if avg_vol > 0 else 1.0
        else:
            rel_vol = 1.0

        # Build alpha context
        range_high, range_low = strategy.get_range()
        alpha_ctx = AlphaContext(
            prices=list(strategy.prices),
            current_price=price,
            range_high=range_high,
            range_low=range_low,
            rsi=rsi,
            atr_pct=atr_pct,
            relative_volume=rel_vol,
            regime="UNKNOWN",  # No regime data in backtest
            news_sentiment=0.0,  # No sentiment in backtest
            in_position=position > 0
        )

        # Compute alpha
        alpha_result = engine.compute_alpha(alpha_ctx)
        alpha_score = alpha_result['score']

        # Determine action
        if use_alpha:
            action = engine.get_action_for_signal(alpha_result, raw_signal, position)
        else:
            # Raw signal (no alpha filter)
            if raw_signal in ('BUY', 'SELL', 'STOP_LOSS', 'TRAILING_STOP'):
                action = 'SELL' if raw_signal in ('SELL', 'STOP_LOSS', 'TRAILING_STOP') else raw_signal
            else:
                action = 'HOLD'

        # Execute action
        if action == 'BUY' and position == 0:
            position = 1
            entry_price = price
            entry_time = df.index[i]
            peak_price = price
            strategy.enter_position(price)

        elif action == 'SELL' and position > 0:
            exit_price = price
            exit_time = df.index[i]
            pnl_pct = (exit_price - entry_price) / entry_price * 100

            trades.append({
                'entry_time': entry_time,
                'exit_time': exit_time,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'pnl_pct': pnl_pct,
                'alpha_score': alpha_score,
                'exit_reason': raw_signal
            })

            position = 0
            entry_price = 0
            peak_price = 0
            strategy.exit_position()

        # Track peak for open positions
        if position > 0 and price > peak_price:
            peak_price = price

    # Close any open position at end
    if position > 0:
        exit_price = prices[-1]
        pnl_pct = (exit_price - entry_price) / entry_price * 100
        trades.append({
            'entry_time': entry_time,
            'exit_time': df.index[-1],
            'entry_price': entry_price,
            'exit_price': exit_price,
            'pnl_pct': pnl_pct,
            'alpha_score': 0,
            'exit_reason': 'END'
        })

    return {
        'symbol': symbol,
        'trades': trades,
        'total_trades': len(trades),
        'wins': len([t for t in trades if t['pnl_pct'] > 0]),
        'losses': len([t for t in trades if t['pnl_pct'] <= 0]),
        'total_pnl': sum(t['pnl_pct'] for t in trades),
        'avg_pnl': np.mean([t['pnl_pct'] for t in trades]) if trades else 0,
    }


def main():
    print("=" * 70)
    print("ALPHA ENGINE BACKTEST")
    print(f"Period: Last {LOOKBACK_DAYS} days")
    print(f"Stocks: {len(SYMBOLS)}")
    print(f"Alpha Threshold: {ALPHA_THRESHOLD}")
    print("=" * 70)
    print()

    # Results storage
    raw_results = []
    alpha_results = []

    print(f"Fetching data for {len(SYMBOLS)} stocks...")
    print()

    for i, symbol in enumerate(SYMBOLS):
        print(f"[{i+1}/{len(SYMBOLS)}] {symbol}...", end=" ")

        df = fetch_data(symbol, LOOKBACK_DAYS)
        if df is None or len(df) < BREAKOUT_LOOKBACK * 2:
            print("SKIP (insufficient data)")
            continue

        # Run backtest WITHOUT alpha filter
        raw = run_backtest(symbol, df, use_alpha=False)
        raw_results.append(raw)

        # Run backtest WITH alpha filter
        alpha = run_backtest(symbol, df, use_alpha=True)
        alpha_results.append(alpha)

        raw_trades = raw['total_trades']
        alpha_trades = alpha['total_trades']
        filtered = raw_trades - alpha_trades if raw_trades > alpha_trades else 0

        print(f"Raw: {raw_trades} trades, Alpha: {alpha_trades} trades (filtered {filtered})")

    print()
    print("=" * 70)
    print("AGGREGATE RESULTS")
    print("=" * 70)

    # Aggregate raw results
    raw_total_trades = sum(r['total_trades'] for r in raw_results)
    raw_total_wins = sum(r['wins'] for r in raw_results)
    raw_total_losses = sum(r['losses'] for r in raw_results)
    raw_win_rate = raw_total_wins / raw_total_trades * 100 if raw_total_trades > 0 else 0
    raw_avg_pnl = np.mean([r['avg_pnl'] for r in raw_results if r['total_trades'] > 0])
    raw_total_pnl = sum(r['total_pnl'] for r in raw_results)

    # Aggregate alpha results
    alpha_total_trades = sum(r['total_trades'] for r in alpha_results)
    alpha_total_wins = sum(r['wins'] for r in alpha_results)
    alpha_total_losses = sum(r['losses'] for r in alpha_results)
    alpha_win_rate = alpha_total_wins / alpha_total_trades * 100 if alpha_total_trades > 0 else 0
    alpha_avg_pnl = np.mean([r['avg_pnl'] for r in alpha_results if r['total_trades'] > 0])
    alpha_total_pnl = sum(r['total_pnl'] for r in alpha_results)

    print()
    print("WITHOUT ALPHA FILTER (Raw Breakout):")
    print(f"  Total Trades:    {raw_total_trades}")
    print(f"  Wins/Losses:     {raw_total_wins}/{raw_total_losses}")
    print(f"  Win Rate:        {raw_win_rate:.1f}%")
    print(f"  Avg P&L/Trade:   {raw_avg_pnl:+.2f}%")
    print(f"  Total P&L:       {raw_total_pnl:+.2f}%")

    print()
    print("WITH ALPHA FILTER (Alpha >= 0.30):")
    print(f"  Total Trades:    {alpha_total_trades}")
    print(f"  Wins/Losses:     {alpha_total_wins}/{alpha_total_losses}")
    print(f"  Win Rate:        {alpha_win_rate:.1f}%")
    print(f"  Avg P&L/Trade:   {alpha_avg_pnl:+.2f}%")
    print(f"  Total P&L:       {alpha_total_pnl:+.2f}%")

    print()
    print("IMPROVEMENT:")
    trades_filtered = raw_total_trades - alpha_total_trades
    trades_filtered_pct = trades_filtered / raw_total_trades * 100 if raw_total_trades > 0 else 0
    win_rate_diff = alpha_win_rate - raw_win_rate
    avg_pnl_diff = alpha_avg_pnl - raw_avg_pnl

    print(f"  Trades Filtered: {trades_filtered} ({trades_filtered_pct:.1f}%)")
    print(f"  Win Rate Change: {win_rate_diff:+.1f}%")
    print(f"  Avg P&L Change:  {avg_pnl_diff:+.2f}%")

    print()
    print("=" * 70)

    # Show top performing stocks with alpha
    print()
    print("TOP 10 STOCKS BY ALPHA-FILTERED P&L:")
    sorted_alpha = sorted(alpha_results, key=lambda x: x['total_pnl'], reverse=True)
    for i, r in enumerate(sorted_alpha[:10]):
        win_rate = r['wins'] / r['total_trades'] * 100 if r['total_trades'] > 0 else 0
        print(f"  {i+1}. {r['symbol']:6s} | Trades: {r['total_trades']:2d} | Win Rate: {win_rate:5.1f}% | P&L: {r['total_pnl']:+6.2f}%")

    print()
    print("WORST 10 STOCKS BY ALPHA-FILTERED P&L:")
    for i, r in enumerate(sorted_alpha[-10:]):
        win_rate = r['wins'] / r['total_trades'] * 100 if r['total_trades'] > 0 else 0
        print(f"  {i+1}. {r['symbol']:6s} | Trades: {r['total_trades']:2d} | Win Rate: {win_rate:5.1f}% | P&L: {r['total_pnl']:+6.2f}%")


if __name__ == '__main__':
    main()
