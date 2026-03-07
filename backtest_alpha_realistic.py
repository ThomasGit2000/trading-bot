"""
Realistic Alpha Engine Backtest with Portfolio Simulation

Simulates actual portfolio management:
- Starting capital: $7,246 (based on .env)
- Position sizing: 10% max per position
- Tracks cash, positions, and P&L over time
- Respects capital constraints
- Includes commission costs ($1 per trade)
"""
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict

os.environ['ALPHA_ENGINE_ENABLED'] = 'true'
os.environ['ALPHA_THRESHOLD'] = '0.30'
os.environ['ALPHA_RSI_MAX'] = '70'

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

# Portfolio parameters
STARTING_CAPITAL = 7246.0  # USD
MAX_POSITION_PCT = 0.10    # 10% max per position
COMMISSION = 1.00          # $1 per trade

# Strategy parameters
BREAKOUT_LOOKBACK = 60
BREAKOUT_THRESHOLD = 0.005
ATR_MIN_THRESHOLD = 0.0025
STOP_LOSS_PCT = 0.05
TRAILING_STOP_PCT = 0.03


def fetch_all_data(symbols: list, days: int = 7) -> dict:
    """Fetch 5-minute data for all symbols."""
    print(f"Fetching data for {len(symbols)} symbols...")
    data = {}
    for i, symbol in enumerate(symbols):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=f"{days}d", interval="5m")
            if not df.empty and len(df) >= BREAKOUT_LOOKBACK * 2:
                data[symbol] = df
                print(f"  [{i+1}/{len(symbols)}] {symbol}: {len(df)} bars")
            else:
                print(f"  [{i+1}/{len(symbols)}] {symbol}: SKIP (insufficient data)")
        except Exception as e:
            print(f"  [{i+1}/{len(symbols)}] {symbol}: ERROR - {e}")
    return data


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


class Portfolio:
    """Simulates a trading portfolio with proper capital management."""

    def __init__(self, starting_capital: float, max_position_pct: float = 0.10):
        self.starting_capital = starting_capital
        self.cash = starting_capital
        self.max_position_pct = max_position_pct
        self.positions = {}  # symbol -> {shares, entry_price, entry_time}
        self.trades = []
        self.equity_curve = []
        self.commission = COMMISSION

    def get_equity(self, current_prices: dict) -> float:
        """Calculate total equity (cash + positions value)."""
        position_value = 0
        for symbol, pos in self.positions.items():
            if symbol in current_prices:
                position_value += pos['shares'] * current_prices[symbol]
        return self.cash + position_value

    def can_buy(self, price: float) -> bool:
        """Check if we have enough cash to buy."""
        position_size = self.starting_capital * self.max_position_pct
        return self.cash >= (position_size + self.commission)

    def buy(self, symbol: str, price: float, timestamp) -> bool:
        """Buy a position."""
        if symbol in self.positions:
            return False  # Already have position

        position_value = self.starting_capital * self.max_position_pct
        if self.cash < (position_value + self.commission):
            return False  # Not enough cash

        shares = int(position_value / price)
        if shares <= 0:
            return False

        cost = shares * price + self.commission
        self.cash -= cost
        self.positions[symbol] = {
            'shares': shares,
            'entry_price': price,
            'entry_time': timestamp,
            'peak_price': price
        }
        return True

    def sell(self, symbol: str, price: float, timestamp, reason: str = '') -> dict:
        """Sell a position and return trade result."""
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        shares = pos['shares']
        entry_price = pos['entry_price']

        proceeds = shares * price - self.commission
        self.cash += proceeds

        pnl = (price - entry_price) * shares - (2 * self.commission)  # Entry + exit commission
        pnl_pct = (price - entry_price) / entry_price * 100

        trade = {
            'symbol': symbol,
            'entry_time': pos['entry_time'],
            'exit_time': timestamp,
            'entry_price': entry_price,
            'exit_price': price,
            'shares': shares,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'reason': reason
        }
        self.trades.append(trade)
        del self.positions[symbol]

        return trade

    def update_peaks(self, current_prices: dict):
        """Update peak prices for trailing stop calculation."""
        for symbol, pos in self.positions.items():
            if symbol in current_prices and current_prices[symbol] > pos['peak_price']:
                pos['peak_price'] = current_prices[symbol]


def run_realistic_backtest(data: dict, use_alpha: bool = True) -> Portfolio:
    """Run realistic backtest with portfolio simulation."""

    portfolio = Portfolio(STARTING_CAPITAL, MAX_POSITION_PCT)
    engine = MicroAlphaEngine()

    # Create strategies for each symbol
    strategies = {}
    for symbol in data.keys():
        strategies[symbol] = BreakoutStrategy(
            lookback_periods=BREAKOUT_LOOKBACK,
            breakout_threshold=BREAKOUT_THRESHOLD,
            stop_loss_pct=STOP_LOSS_PCT,
            trailing_stop_pct=TRAILING_STOP_PCT,
            atr_filter=True,
            atr_min_threshold=ATR_MIN_THRESHOLD
        )

    # Get unified timeline (all timestamps across all symbols)
    all_timestamps = set()
    for df in data.values():
        all_timestamps.update(df.index.tolist())
    all_timestamps = sorted(all_timestamps)

    # Volume tracking for relative volume
    volume_history = {symbol: [] for symbol in data.keys()}
    vol_window = 20

    # Simulate trading
    for timestamp in all_timestamps:
        current_prices = {}

        # Update all strategies with current prices
        for symbol, df in data.items():
            if timestamp in df.index:
                row = df.loc[timestamp]
                price = row['Close']
                volume = row['Volume']
                current_prices[symbol] = price

                # Track volume
                volume_history[symbol].append(volume)
                if len(volume_history[symbol]) > vol_window:
                    volume_history[symbol] = volume_history[symbol][-vol_window:]

                # Add price to strategy
                strategies[symbol].add_price(price)

        # Update peak prices for open positions
        portfolio.update_peaks(current_prices)

        # Check for exits first (stop-loss, trailing stop, signals)
        for symbol in list(portfolio.positions.keys()):
            if symbol not in current_prices:
                continue

            price = current_prices[symbol]
            pos = portfolio.positions[symbol]
            strategy = strategies[symbol]

            if len(strategy.prices) < BREAKOUT_LOOKBACK:
                continue

            # Sync strategy state
            if not strategy.in_position:
                strategy.enter_position(pos['entry_price'])

            # Get signal
            raw_signal = strategy.get_signal()

            # Check exits
            if raw_signal in ('STOP_LOSS', 'TRAILING_STOP', 'SELL'):
                trade = portfolio.sell(symbol, price, timestamp, raw_signal)
                if trade:
                    strategy.exit_position()

        # Check for entries
        for symbol, price in current_prices.items():
            if symbol in portfolio.positions:
                continue  # Already have position

            strategy = strategies[symbol]
            if len(strategy.prices) < BREAKOUT_LOOKBACK:
                continue

            raw_signal = strategy.get_signal()

            if raw_signal != 'BUY':
                continue

            # Apply alpha filter if enabled
            if use_alpha:
                rsi = simulate_rsi(list(strategy.prices), 14)
                atr_pct = strategy.get_atr_percent()

                # Relative volume
                vol_hist = volume_history[symbol]
                if len(vol_hist) >= 2:
                    avg_vol = np.mean(vol_hist[:-1])
                    rel_vol = vol_hist[-1] / avg_vol if avg_vol > 0 else 1.0
                else:
                    rel_vol = 1.0

                range_high, range_low = strategy.get_range()
                alpha_ctx = AlphaContext(
                    prices=list(strategy.prices),
                    current_price=price,
                    range_high=range_high,
                    range_low=range_low,
                    rsi=rsi,
                    atr_pct=atr_pct,
                    relative_volume=rel_vol,
                    regime="UNKNOWN",
                    news_sentiment=0.0,
                    in_position=False
                )

                alpha_result = engine.compute_alpha(alpha_ctx)

                # Check hard filters (RSI, volume)
                if not alpha_result.get('hard_filter_passed', True):
                    continue  # Skip - hard filter failed

                # Check alpha threshold
                if alpha_result['score'] < engine.threshold:
                    continue  # Skip - alpha too low

            # Try to buy
            if portfolio.can_buy(price):
                if portfolio.buy(symbol, price, timestamp):
                    strategy.enter_position(price)

        # Record equity
        equity = portfolio.get_equity(current_prices)
        portfolio.equity_curve.append({
            'timestamp': timestamp,
            'equity': equity,
            'cash': portfolio.cash,
            'positions': len(portfolio.positions)
        })

    # Close any remaining positions at end
    for symbol in list(portfolio.positions.keys()):
        if symbol in current_prices:
            portfolio.sell(symbol, current_prices[symbol], all_timestamps[-1], 'END')

    return portfolio


def print_results(portfolio: Portfolio, label: str):
    """Print portfolio results."""
    print(f"\n{'='*60}")
    print(f"{label}")
    print('='*60)

    final_equity = portfolio.equity_curve[-1]['equity'] if portfolio.equity_curve else STARTING_CAPITAL
    total_return = (final_equity - STARTING_CAPITAL) / STARTING_CAPITAL * 100

    trades = portfolio.trades
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]

    print(f"\nPORTFOLIO:")
    print(f"  Starting Capital:  ${STARTING_CAPITAL:,.2f}")
    print(f"  Final Equity:      ${final_equity:,.2f}")
    print(f"  Total Return:      {total_return:+.2f}%")

    print(f"\nTRADES:")
    print(f"  Total Trades:      {len(trades)}")
    print(f"  Wins:              {len(wins)}")
    print(f"  Losses:            {len(losses)}")
    print(f"  Win Rate:          {len(wins)/len(trades)*100:.1f}%" if trades else "  Win Rate:          N/A")

    if trades:
        avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
        avg_loss = np.mean([t['pnl'] for t in losses]) if losses else 0
        total_pnl = sum(t['pnl'] for t in trades)

        print(f"  Avg Win:           ${avg_win:+.2f}")
        print(f"  Avg Loss:          ${avg_loss:+.2f}")
        print(f"  Total P&L:         ${total_pnl:+.2f}")

    # Max drawdown
    if portfolio.equity_curve:
        equities = [e['equity'] for e in portfolio.equity_curve]
        peak = equities[0]
        max_dd = 0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd
        print(f"\nRISK:")
        print(f"  Max Drawdown:      {max_dd:.2f}%")
        print(f"  Max Positions:     {max(e['positions'] for e in portfolio.equity_curve)}")

    return {
        'total_return': total_return,
        'trades': len(trades),
        'win_rate': len(wins)/len(trades)*100 if trades else 0,
        'final_equity': final_equity
    }


def main():
    print("="*60)
    print("REALISTIC ALPHA ENGINE BACKTEST")
    print("="*60)
    print(f"Starting Capital: ${STARTING_CAPITAL:,.2f}")
    print(f"Max Position Size: {MAX_POSITION_PCT*100:.0f}%")
    print(f"Commission: ${COMMISSION:.2f}/trade")
    print(f"Period: Last 7 days")
    print(f"Stocks: {len(SYMBOLS)}")
    print()

    # Fetch data
    data = fetch_all_data(SYMBOLS, days=7)
    print(f"\nLoaded data for {len(data)} stocks")

    # Run backtest WITHOUT alpha
    print("\n" + "-"*60)
    print("Running backtest WITHOUT alpha filter...")
    raw_portfolio = run_realistic_backtest(data, use_alpha=False)
    raw_results = print_results(raw_portfolio, "WITHOUT ALPHA FILTER (Raw Breakout)")

    # Run backtest WITH alpha
    print("\n" + "-"*60)
    print("Running backtest WITH alpha filter...")
    alpha_portfolio = run_realistic_backtest(data, use_alpha=True)
    alpha_results = print_results(alpha_portfolio, "WITH ALPHA FILTER (Alpha >= 0.30)")

    # Comparison
    print("\n" + "="*60)
    print("COMPARISON")
    print("="*60)
    print(f"\n{'Metric':<20} {'Raw':>12} {'Alpha':>12} {'Diff':>12}")
    print("-"*56)
    print(f"{'Total Return':<20} {raw_results['total_return']:>11.2f}% {alpha_results['total_return']:>11.2f}% {alpha_results['total_return']-raw_results['total_return']:>+11.2f}%")
    print(f"{'Trades':<20} {raw_results['trades']:>12} {alpha_results['trades']:>12} {alpha_results['trades']-raw_results['trades']:>+12}")
    print(f"{'Win Rate':<20} {raw_results['win_rate']:>11.1f}% {alpha_results['win_rate']:>11.1f}% {alpha_results['win_rate']-raw_results['win_rate']:>+11.1f}%")
    print(f"{'Final Equity':<20} ${raw_results['final_equity']:>10,.2f} ${alpha_results['final_equity']:>10,.2f} ${alpha_results['final_equity']-raw_results['final_equity']:>+10,.2f}")


if __name__ == '__main__':
    main()
