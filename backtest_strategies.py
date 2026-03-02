"""
Backtest multiple MA strategies vs Buy & Hold
Tests MA(10/30), MA(10/20), MA(8/21), MA(5/15) over 1 year
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
from collections import defaultdict

# Test on a representative sample of stocks (faster than all 70)
TEST_SYMBOLS = [
    'AAPL', 'MSFT', 'NVDA', 'AMD', 'TSLA',  # Tech/Semi
    'META', 'GOOGL', 'AMZN',                # Mega cap
    'PLTR', 'SNOW', 'CRWD',                 # Growth
    'MARA', 'RIOT', 'COIN',                 # Crypto/volatile
    'JPM', 'V', 'MA',                       # Finance
    'COST', 'HD', 'MCD'                     # Consumer
]

# Strategy configurations to test
STRATEGIES = {
    'MA(10/30) - Current': {'short': 10, 'long': 30, 'threshold': 0.01},
    'MA(10/20) - Moderate': {'short': 10, 'long': 20, 'threshold': 0.008},
    'MA(8/21) - Aggressive': {'short': 8, 'long': 21, 'threshold': 0.008},
    'MA(5/15) - Very Aggressive': {'short': 5, 'long': 15, 'threshold': 0.005},
}

# Risk management (same for all strategies)
STOP_LOSS_PCT = 0.05
TRAILING_STOP_PCT = 0.03
INITIAL_CASH = 10000  # $10k per stock

class Backtest:
    def __init__(self, symbol, short_ma, long_ma, threshold, stop_loss, trailing_stop):
        self.symbol = symbol
        self.short_ma = short_ma
        self.long_ma = long_ma
        self.threshold = threshold
        self.stop_loss = stop_loss
        self.trailing_stop = trailing_stop

        self.cash = INITIAL_CASH
        self.position = 0
        self.entry_price = 0
        self.peak_price = 0
        self.trades = []
        self.equity_curve = []

    def calculate_rsi(self, prices, period=14):
        """Calculate RSI"""
        if len(prices) < period + 1:
            return 50

        deltas = np.diff(prices[-period-1:])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def run(self, df):
        """Run backtest on price data"""
        for i in range(self.long_ma, len(df)):
            current_bar = df.iloc[i]
            price = current_bar['Close']

            # Calculate MAs
            short_ma_val = df['Close'].iloc[i-self.short_ma:i].mean()
            long_ma_val = df['Close'].iloc[i-self.long_ma:i].mean()

            # Calculate RSI
            rsi_val = self.calculate_rsi(df['Close'].iloc[:i].values)
            rsi = float(rsi_val) if not np.isnan(rsi_val) else 50

            # Track peak if in position
            if self.position > 0:
                if price > self.peak_price:
                    self.peak_price = price

            # Check stop-loss
            if self.position > 0 and self.entry_price > 0:
                loss_pct = (self.entry_price - price) / self.entry_price
                if loss_pct >= self.stop_loss:
                    # Stop-loss triggered
                    self.cash = self.position * price
                    pnl = self.cash - INITIAL_CASH
                    self.trades.append({
                        'date': current_bar.name,
                        'action': 'SELL (STOP)',
                        'price': price,
                        'pnl': pnl,
                        'pnl_pct': (pnl / INITIAL_CASH) * 100
                    })
                    self.position = 0
                    self.entry_price = 0
                    self.peak_price = 0

            # Check trailing stop
            if self.position > 0 and self.peak_price > 0:
                profit_pct = (self.peak_price - self.entry_price) / self.entry_price
                if profit_pct >= 0.08:  # Only trail after 8% profit
                    drop_pct = (self.peak_price - price) / self.peak_price
                    if drop_pct >= self.trailing_stop:
                        # Trailing stop triggered
                        self.cash = self.position * price
                        pnl = self.cash - INITIAL_CASH
                        self.trades.append({
                            'date': current_bar.name,
                            'action': 'SELL (TRAIL)',
                            'price': price,
                            'pnl': pnl,
                            'pnl_pct': (pnl / INITIAL_CASH) * 100
                        })
                        self.position = 0
                        self.entry_price = 0
                        self.peak_price = 0

            # Check for MA crossover signals
            if self.position == 0:  # Not in position - look for BUY
                if short_ma_val > long_ma_val * (1 + self.threshold):
                    # BUY signal - check RSI filter
                    if rsi <= 70:  # Don't buy overbought
                        shares = self.cash / price
                        self.position = shares
                        self.entry_price = price
                        self.peak_price = price
                        self.trades.append({
                            'date': current_bar.name,
                            'action': 'BUY',
                            'price': price,
                            'pnl': 0,
                            'pnl_pct': 0
                        })
                        self.cash = 0

            elif self.position > 0:  # In position - look for SELL
                if short_ma_val < long_ma_val * (1 - self.threshold):
                    # SELL signal
                    self.cash = self.position * price
                    pnl = self.cash - INITIAL_CASH
                    self.trades.append({
                        'date': current_bar.name,
                        'action': 'SELL',
                        'price': price,
                        'pnl': pnl,
                        'pnl_pct': (pnl / INITIAL_CASH) * 100
                    })
                    self.position = 0
                    self.entry_price = 0
                    self.peak_price = 0

            # Track equity
            if self.position > 0:
                equity = self.position * price
            else:
                equity = self.cash
            self.equity_curve.append(equity)

        # Close any open position at end
        if self.position > 0:
            final_price = df['Close'].iloc[-1]
            self.cash = self.position * final_price
            pnl = self.cash - INITIAL_CASH
            self.trades.append({
                'date': df.index[-1],
                'action': 'SELL (FINAL)',
                'price': final_price,
                'pnl': pnl,
                'pnl_pct': (pnl / INITIAL_CASH) * 100
            })
            self.position = 0

        return self.get_metrics(df)

    def get_metrics(self, df):
        """Calculate performance metrics"""
        final_equity = self.cash if self.position == 0 else self.position * df['Close'].iloc[-1]
        total_return = ((final_equity - INITIAL_CASH) / INITIAL_CASH) * 100

        # Count wins/losses
        completed_trades = [t for t in self.trades if t['action'].startswith('SELL')]
        wins = [t for t in completed_trades if t['pnl'] > 0]
        losses = [t for t in completed_trades if t['pnl'] < 0]

        win_rate = (len(wins) / len(completed_trades) * 100) if completed_trades else 0

        # Average win/loss
        avg_win = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
        avg_loss = np.mean([t['pnl_pct'] for t in losses]) if losses else 0

        # Max drawdown
        equity_curve = np.array(self.equity_curve)
        running_max = np.maximum.accumulate(equity_curve)
        drawdown = (equity_curve - running_max) / running_max * 100
        max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0

        # Sharpe ratio (simplified)
        if len(self.equity_curve) > 1:
            returns = np.diff(self.equity_curve) / self.equity_curve[:-1]
            sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
        else:
            sharpe = 0

        return {
            'total_return': total_return,
            'num_trades': len(completed_trades),
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'max_drawdown': max_drawdown,
            'sharpe': sharpe,
            'final_equity': final_equity
        }

def run_all_backtests():
    """Run backtests for all strategies and symbols"""
    print("=" * 80)
    print("BACKTESTING MA STRATEGIES vs BUY & HOLD")
    print("Period: Last 1 year")
    print(f"Test Symbols: {len(TEST_SYMBOLS)} stocks")
    print(f"Initial Capital: ${INITIAL_CASH:,} per stock")
    print("=" * 80)
    print()

    # Fetch data
    print("Downloading historical data...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)

    all_results = defaultdict(lambda: {
        'returns': [],
        'trades': [],
        'win_rates': [],
        'max_drawdowns': [],
        'sharpes': []
    })

    for symbol in TEST_SYMBOLS:
        try:
            df = yf.download(symbol, start=start_date, end=end_date, progress=False)
            if len(df) < 100:
                print(f"  Skipping {symbol} - insufficient data")
                continue

            print(f"  Testing {symbol}...", end=' ')

            # Buy & Hold baseline
            buy_hold_return = ((df['Close'].iloc[-1] - df['Close'].iloc[0]) / df['Close'].iloc[0]) * 100
            all_results['Buy & Hold']['returns'].append(buy_hold_return)

            # Test each MA strategy
            for name, params in STRATEGIES.items():
                bt = Backtest(
                    symbol,
                    params['short'],
                    params['long'],
                    params['threshold'],
                    STOP_LOSS_PCT,
                    TRAILING_STOP_PCT
                )
                metrics = bt.run(df)

                all_results[name]['returns'].append(metrics['total_return'])
                all_results[name]['trades'].append(metrics['num_trades'])
                all_results[name]['win_rates'].append(metrics['win_rate'])
                all_results[name]['max_drawdowns'].append(metrics['max_drawdown'])
                all_results[name]['sharpes'].append(metrics['sharpe'])

            print("✓")

        except Exception as e:
            print(f"  Error with {symbol}: {e}")

    # Print results
    print()
    print("=" * 80)
    print("RESULTS SUMMARY (Averaged across all stocks)")
    print("=" * 80)
    print()

    # Sort strategies by average return
    strategy_names = ['Buy & Hold'] + list(STRATEGIES.keys())
    results_table = []

    for name in strategy_names:
        if name == 'Buy & Hold':
            avg_return = np.mean(all_results[name]['returns'])
            results_table.append({
                'Strategy': name,
                'Avg Return': avg_return,
                'Trades': 0,
                'Win Rate': 100 if avg_return > 0 else 0,
                'Max DD': 0,  # Not calculated for buy & hold
                'Sharpe': 0
            })
        else:
            results_table.append({
                'Strategy': name,
                'Avg Return': np.mean(all_results[name]['returns']),
                'Trades': np.mean(all_results[name]['trades']),
                'Win Rate': np.mean(all_results[name]['win_rates']),
                'Max DD': np.mean(all_results[name]['max_drawdowns']),
                'Sharpe': np.mean(all_results[name]['sharpes'])
            })

    # Sort by return
    results_table.sort(key=lambda x: x['Avg Return'], reverse=True)

    # Print table
    print(f"{'Strategy':<30} {'Avg Return':<12} {'Trades':<8} {'Win Rate':<10} {'Max DD':<10} {'Sharpe':<8}")
    print("-" * 80)

    for i, row in enumerate(results_table):
        rank = "#1" if i == 0 else "#2" if i == 1 else "#3" if i == 2 else "  "
        print(f"{rank} {row['Strategy']:<28} {row['Avg Return']:>10.2f}%  {row['Trades']:>6.0f}  {row['Win Rate']:>8.1f}%  {row['Max DD']:>8.2f}%  {row['Sharpe']:>6.2f}")

    print()
    print("=" * 80)
    print("DETAILED BREAKDOWN BY STOCK")
    print("=" * 80)
    print()

    # Show per-stock results for winning strategy
    winner = results_table[0]['Strategy']
    print(f"Winner: {winner}")
    print()
    print(f"{'Symbol':<8} {'Buy & Hold':<12} {winner:<15}")
    print("-" * 40)

    for i, symbol in enumerate(TEST_SYMBOLS):
        if i < len(all_results['Buy & Hold']['returns']):
            bh_return = all_results['Buy & Hold']['returns'][i]
            strategy_idx = list(STRATEGIES.keys()).index(winner) if winner != 'Buy & Hold' else -1

            if strategy_idx >= 0:
                strategy_return = all_results[winner]['returns'][i]
                diff = strategy_return - bh_return
                symbol_str = f"{symbol:<8}"
                bh_str = f"{bh_return:>10.2f}%"
                strat_str = f"{strategy_return:>10.2f}%"
                diff_str = f"({diff:+.2f}%)"

                if diff > 0:
                    print(f"{symbol_str} {bh_str}  {strat_str} {diff_str} ✓")
                else:
                    print(f"{symbol_str} {bh_str}  {strat_str} {diff_str}")

    print()
    print("=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    print()

    best = results_table[0]
    print(f"*** BEST STRATEGY: {best['Strategy']}")
    print(f"   Average Return: {best['Avg Return']:.2f}%")
    print(f"   Avg # Trades: {best['Trades']:.0f}")
    print(f"   Win Rate: {best['Win Rate']:.1f}%")
    print(f"   Max Drawdown: {best['Max DD']:.2f}%")
    print(f"   Sharpe Ratio: {best['Sharpe']:.2f}")
    print()

    # Extract parameters if it's an MA strategy
    if best['Strategy'] in STRATEGIES:
        params = STRATEGIES[best['Strategy']]
        print("CONFIGURATION:")
        print(f"  SHORT_MA={params['short']}")
        print(f"  LONG_MA={params['long']}")
        print(f"  MA_THRESHOLD={params['threshold']}")
        print(f"  STOP_LOSS_PCT=0.05")
        print(f"  TRAILING_STOP_PCT=0.03")

if __name__ == '__main__':
    run_all_backtests()
