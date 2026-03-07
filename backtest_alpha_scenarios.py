"""
Alpha Engine Scenario Analysis

Tests multiple configurations:
1. Alpha thresholds: 0.20, 0.30, 0.40, 0.50, 0.60
2. RSI filters: None, <70, <60, 30-70
3. Volume filters: None, >1.2x, >1.5x, >2.0x
4. Regime simulation: Random, Trending Bull, Trending Bear
5. Sentiment simulation: None, Random, Correlated with price
"""
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
import random

os.environ['ALPHA_ENGINE_ENABLED'] = 'true'

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
STARTING_CAPITAL = 7246.0
MAX_POSITION_PCT = 0.10
COMMISSION = 1.00

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
        except:
            pass
    print(f"Loaded {len(data)} stocks")
    return data


def simulate_rsi(prices: list, period: int = 14) -> float:
    """Calculate RSI from price list."""
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        gains.append(change if change > 0 else 0)
        losses.append(abs(change) if change < 0 else 0)
    if len(gains) < period:
        return 50.0
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def simulate_regime(timestamp, mode='random'):
    """Simulate market regime."""
    if mode == 'random':
        return random.choice(['BULL', 'BEAR', 'UNKNOWN'])
    elif mode == 'bull':
        return 'BULL'
    elif mode == 'bear':
        return 'BEAR'
    elif mode == 'trending':
        # Bull in morning, Bear in afternoon
        hour = timestamp.hour if hasattr(timestamp, 'hour') else 12
        return 'BULL' if hour < 12 else 'BEAR'
    return 'UNKNOWN'


def simulate_sentiment(symbol, price_change_pct, mode='none'):
    """Simulate news sentiment."""
    if mode == 'none':
        return 0.0
    elif mode == 'random':
        return random.uniform(-0.5, 0.5)
    elif mode == 'correlated':
        # Sentiment correlates with recent price movement
        return max(-1.0, min(1.0, price_change_pct * 10))
    elif mode == 'contrarian':
        # Sentiment inversely correlated
        return max(-1.0, min(1.0, -price_change_pct * 10))
    return 0.0


class Portfolio:
    def __init__(self, starting_capital: float):
        self.starting_capital = starting_capital
        self.cash = starting_capital
        self.positions = {}
        self.trades = []
        self.equity_curve = []

    def get_equity(self, current_prices: dict) -> float:
        position_value = sum(
            pos['shares'] * current_prices.get(sym, pos['entry_price'])
            for sym, pos in self.positions.items()
        )
        return self.cash + position_value

    def buy(self, symbol: str, price: float, timestamp) -> bool:
        if symbol in self.positions:
            return False
        position_value = self.starting_capital * MAX_POSITION_PCT
        if self.cash < (position_value + COMMISSION):
            return False
        shares = int(position_value / price)
        if shares <= 0:
            return False
        self.cash -= shares * price + COMMISSION
        self.positions[symbol] = {
            'shares': shares, 'entry_price': price,
            'entry_time': timestamp, 'peak_price': price
        }
        return True

    def sell(self, symbol: str, price: float, timestamp, reason: str = '') -> dict:
        if symbol not in self.positions:
            return None
        pos = self.positions[symbol]
        self.cash += pos['shares'] * price - COMMISSION
        pnl = (price - pos['entry_price']) * pos['shares'] - 2 * COMMISSION
        pnl_pct = (price - pos['entry_price']) / pos['entry_price'] * 100
        trade = {
            'symbol': symbol, 'pnl': pnl, 'pnl_pct': pnl_pct, 'reason': reason
        }
        self.trades.append(trade)
        del self.positions[symbol]
        return trade

    def update_peaks(self, current_prices: dict):
        for sym, pos in self.positions.items():
            if sym in current_prices and current_prices[sym] > pos['peak_price']:
                pos['peak_price'] = current_prices[sym]


def run_scenario(data: dict, config: dict) -> dict:
    """Run a single scenario with given configuration."""

    # Override alpha engine settings
    os.environ['ALPHA_THRESHOLD'] = str(config.get('alpha_threshold', 0.30))

    # Create fresh engine with new threshold
    engine = MicroAlphaEngine()
    engine.threshold = config.get('alpha_threshold', 0.30)
    engine.enabled = True

    portfolio = Portfolio(STARTING_CAPITAL)
    strategies = {sym: BreakoutStrategy(
        lookback_periods=BREAKOUT_LOOKBACK,
        breakout_threshold=BREAKOUT_THRESHOLD,
        stop_loss_pct=STOP_LOSS_PCT,
        trailing_stop_pct=TRAILING_STOP_PCT,
        atr_filter=True,
        atr_min_threshold=ATR_MIN_THRESHOLD
    ) for sym in data.keys()}

    # Get unified timeline
    all_timestamps = sorted(set(ts for df in data.values() for ts in df.index.tolist()))

    volume_history = {sym: [] for sym in data.keys()}
    price_history = {sym: [] for sym in data.keys()}

    signals_generated = 0
    signals_filtered = 0
    filter_reasons = defaultdict(int)

    for timestamp in all_timestamps:
        current_prices = {}

        for symbol, df in data.items():
            if timestamp in df.index:
                row = df.loc[timestamp]
                price = row['Close']
                volume = row['Volume']
                current_prices[symbol] = price

                volume_history[symbol].append(volume)
                price_history[symbol].append(price)
                if len(volume_history[symbol]) > 20:
                    volume_history[symbol] = volume_history[symbol][-20:]
                if len(price_history[symbol]) > 20:
                    price_history[symbol] = price_history[symbol][-20:]

                strategies[symbol].add_price(price)

        portfolio.update_peaks(current_prices)

        # Check exits
        for symbol in list(portfolio.positions.keys()):
            if symbol not in current_prices:
                continue
            price = current_prices[symbol]
            strategy = strategies[symbol]
            if len(strategy.prices) < BREAKOUT_LOOKBACK:
                continue
            if not strategy.in_position:
                strategy.enter_position(portfolio.positions[symbol]['entry_price'])
            raw_signal = strategy.get_signal()
            if raw_signal in ('STOP_LOSS', 'TRAILING_STOP', 'SELL'):
                if portfolio.sell(symbol, price, timestamp, raw_signal):
                    strategy.exit_position()

        # Check entries
        for symbol, price in current_prices.items():
            if symbol in portfolio.positions:
                continue
            strategy = strategies[symbol]
            if len(strategy.prices) < BREAKOUT_LOOKBACK:
                continue

            raw_signal = strategy.get_signal()
            if raw_signal != 'BUY':
                continue

            signals_generated += 1

            # Calculate indicators
            rsi = simulate_rsi(list(strategy.prices), 14)
            atr_pct = strategy.get_atr_percent()

            vol_hist = volume_history[symbol]
            rel_vol = vol_hist[-1] / np.mean(vol_hist[:-1]) if len(vol_hist) > 1 and np.mean(vol_hist[:-1]) > 0 else 1.0

            price_hist = price_history[symbol]
            price_change = (price_hist[-1] - price_hist[0]) / price_hist[0] if len(price_hist) > 1 and price_hist[0] > 0 else 0

            # Apply filters

            # RSI filter
            rsi_filter = config.get('rsi_filter', 'none')
            if rsi_filter == '<70' and rsi >= 70:
                signals_filtered += 1
                filter_reasons['RSI >= 70'] += 1
                continue
            elif rsi_filter == '<60' and rsi >= 60:
                signals_filtered += 1
                filter_reasons['RSI >= 60'] += 1
                continue
            elif rsi_filter == '30-70' and (rsi < 30 or rsi > 70):
                signals_filtered += 1
                filter_reasons['RSI outside 30-70'] += 1
                continue

            # Volume filter
            vol_filter = config.get('volume_filter', 'none')
            if vol_filter == '>1.2x' and rel_vol < 1.2:
                signals_filtered += 1
                filter_reasons['Volume < 1.2x'] += 1
                continue
            elif vol_filter == '>1.5x' and rel_vol < 1.5:
                signals_filtered += 1
                filter_reasons['Volume < 1.5x'] += 1
                continue
            elif vol_filter == '>2.0x' and rel_vol < 2.0:
                signals_filtered += 1
                filter_reasons['Volume < 2.0x'] += 1
                continue

            # Regime and sentiment
            regime = simulate_regime(timestamp, config.get('regime_mode', 'unknown'))
            sentiment = simulate_sentiment(symbol, price_change, config.get('sentiment_mode', 'none'))

            # Alpha context
            range_high, range_low = strategy.get_range()
            alpha_ctx = AlphaContext(
                prices=list(strategy.prices),
                current_price=price,
                range_high=range_high,
                range_low=range_low,
                rsi=rsi,
                atr_pct=atr_pct,
                relative_volume=rel_vol,
                regime=regime,
                news_sentiment=sentiment,
                in_position=False
            )

            alpha_result = engine.compute_alpha(alpha_ctx)
            alpha_score = alpha_result['score']

            # Alpha threshold filter
            if alpha_score < engine.threshold:
                signals_filtered += 1
                filter_reasons[f'Alpha < {engine.threshold}'] += 1
                continue

            # Execute trade
            if portfolio.buy(symbol, price, timestamp):
                strategy.enter_position(price)

        equity = portfolio.get_equity(current_prices)
        portfolio.equity_curve.append({'equity': equity, 'positions': len(portfolio.positions)})

    # Close remaining positions
    for symbol in list(portfolio.positions.keys()):
        if symbol in current_prices:
            portfolio.sell(symbol, current_prices[symbol], all_timestamps[-1], 'END')

    # Calculate results
    final_equity = portfolio.equity_curve[-1]['equity'] if portfolio.equity_curve else STARTING_CAPITAL
    total_return = (final_equity - STARTING_CAPITAL) / STARTING_CAPITAL * 100
    trades = portfolio.trades
    wins = [t for t in trades if t['pnl'] > 0]

    # Max drawdown
    max_dd = 0
    if portfolio.equity_curve:
        equities = [e['equity'] for e in portfolio.equity_curve]
        peak = equities[0]
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd

    return {
        'config': config,
        'total_return': total_return,
        'trades': len(trades),
        'wins': len(wins),
        'win_rate': len(wins) / len(trades) * 100 if trades else 0,
        'avg_pnl': np.mean([t['pnl'] for t in trades]) if trades else 0,
        'max_drawdown': max_dd,
        'signals_generated': signals_generated,
        'signals_filtered': signals_filtered,
        'filter_rate': signals_filtered / signals_generated * 100 if signals_generated > 0 else 0,
        'filter_reasons': dict(filter_reasons)
    }


def main():
    print("=" * 80)
    print("ALPHA ENGINE SCENARIO ANALYSIS")
    print("=" * 80)
    print()

    # Fetch data once
    data = fetch_all_data(SYMBOLS, days=7)
    if not data:
        print("No data available!")
        return

    results = []

    # ========================================
    # SCENARIO 1: Alpha Threshold Variations
    # ========================================
    print("\n" + "=" * 80)
    print("SCENARIO 1: ALPHA THRESHOLD VARIATIONS")
    print("=" * 80)

    thresholds = [0.0, 0.20, 0.30, 0.40, 0.50, 0.60]
    for threshold in thresholds:
        config = {
            'name': f'Alpha >= {threshold}',
            'alpha_threshold': threshold,
            'rsi_filter': 'none',
            'volume_filter': 'none',
            'regime_mode': 'unknown',
            'sentiment_mode': 'none'
        }
        result = run_scenario(data, config)
        results.append(result)
        print(f"  {config['name']:20s} | Return: {result['total_return']:+6.2f}% | Trades: {result['trades']:3d} | Win Rate: {result['win_rate']:5.1f}% | Filtered: {result['filter_rate']:5.1f}%")

    # ========================================
    # SCENARIO 2: RSI Filter Variations
    # ========================================
    print("\n" + "=" * 80)
    print("SCENARIO 2: RSI FILTER VARIATIONS (Alpha >= 0.30)")
    print("=" * 80)

    rsi_filters = ['none', '<70', '<60', '30-70']
    for rsi_filter in rsi_filters:
        config = {
            'name': f'RSI {rsi_filter}',
            'alpha_threshold': 0.30,
            'rsi_filter': rsi_filter,
            'volume_filter': 'none',
            'regime_mode': 'unknown',
            'sentiment_mode': 'none'
        }
        result = run_scenario(data, config)
        results.append(result)
        print(f"  {config['name']:20s} | Return: {result['total_return']:+6.2f}% | Trades: {result['trades']:3d} | Win Rate: {result['win_rate']:5.1f}% | Filtered: {result['filter_rate']:5.1f}%")

    # ========================================
    # SCENARIO 3: Volume Filter Variations
    # ========================================
    print("\n" + "=" * 80)
    print("SCENARIO 3: VOLUME FILTER VARIATIONS (Alpha >= 0.30)")
    print("=" * 80)

    vol_filters = ['none', '>1.2x', '>1.5x', '>2.0x']
    for vol_filter in vol_filters:
        config = {
            'name': f'Volume {vol_filter}',
            'alpha_threshold': 0.30,
            'rsi_filter': 'none',
            'volume_filter': vol_filter,
            'regime_mode': 'unknown',
            'sentiment_mode': 'none'
        }
        result = run_scenario(data, config)
        results.append(result)
        print(f"  {config['name']:20s} | Return: {result['total_return']:+6.2f}% | Trades: {result['trades']:3d} | Win Rate: {result['win_rate']:5.1f}% | Filtered: {result['filter_rate']:5.1f}%")

    # ========================================
    # SCENARIO 4: Regime Variations
    # ========================================
    print("\n" + "=" * 80)
    print("SCENARIO 4: REGIME SIMULATION (Alpha >= 0.30)")
    print("=" * 80)

    regime_modes = ['unknown', 'bull', 'bear', 'random', 'trending']
    for regime_mode in regime_modes:
        config = {
            'name': f'Regime: {regime_mode}',
            'alpha_threshold': 0.30,
            'rsi_filter': 'none',
            'volume_filter': 'none',
            'regime_mode': regime_mode,
            'sentiment_mode': 'none'
        }
        result = run_scenario(data, config)
        results.append(result)
        print(f"  {config['name']:20s} | Return: {result['total_return']:+6.2f}% | Trades: {result['trades']:3d} | Win Rate: {result['win_rate']:5.1f}% | Filtered: {result['filter_rate']:5.1f}%")

    # ========================================
    # SCENARIO 5: Sentiment Variations
    # ========================================
    print("\n" + "=" * 80)
    print("SCENARIO 5: SENTIMENT SIMULATION (Alpha >= 0.30)")
    print("=" * 80)

    sentiment_modes = ['none', 'random', 'correlated', 'contrarian']
    for sent_mode in sentiment_modes:
        config = {
            'name': f'Sentiment: {sent_mode}',
            'alpha_threshold': 0.30,
            'rsi_filter': 'none',
            'volume_filter': 'none',
            'regime_mode': 'unknown',
            'sentiment_mode': sent_mode
        }
        result = run_scenario(data, config)
        results.append(result)
        print(f"  {config['name']:20s} | Return: {result['total_return']:+6.2f}% | Trades: {result['trades']:3d} | Win Rate: {result['win_rate']:5.1f}% | Filtered: {result['filter_rate']:5.1f}%")

    # ========================================
    # SCENARIO 6: Combined Best Configs
    # ========================================
    print("\n" + "=" * 80)
    print("SCENARIO 6: COMBINED CONFIGURATIONS")
    print("=" * 80)

    combined_configs = [
        {'name': 'Baseline (no filters)', 'alpha_threshold': 0.0, 'rsi_filter': 'none', 'volume_filter': 'none', 'regime_mode': 'unknown', 'sentiment_mode': 'none'},
        {'name': 'Alpha 0.30 only', 'alpha_threshold': 0.30, 'rsi_filter': 'none', 'volume_filter': 'none', 'regime_mode': 'unknown', 'sentiment_mode': 'none'},
        {'name': 'Alpha 0.40 + RSI<70', 'alpha_threshold': 0.40, 'rsi_filter': '<70', 'volume_filter': 'none', 'regime_mode': 'unknown', 'sentiment_mode': 'none'},
        {'name': 'Alpha 0.40 + Vol>1.5x', 'alpha_threshold': 0.40, 'rsi_filter': 'none', 'volume_filter': '>1.5x', 'regime_mode': 'unknown', 'sentiment_mode': 'none'},
        {'name': 'Alpha 0.50 + RSI + Vol', 'alpha_threshold': 0.50, 'rsi_filter': '<70', 'volume_filter': '>1.2x', 'regime_mode': 'unknown', 'sentiment_mode': 'none'},
        {'name': 'Full Stack (all filters)', 'alpha_threshold': 0.40, 'rsi_filter': '<70', 'volume_filter': '>1.2x', 'regime_mode': 'bull', 'sentiment_mode': 'correlated'},
        {'name': 'Conservative', 'alpha_threshold': 0.60, 'rsi_filter': '30-70', 'volume_filter': '>1.5x', 'regime_mode': 'bull', 'sentiment_mode': 'none'},
    ]

    for config in combined_configs:
        result = run_scenario(data, config)
        results.append(result)
        print(f"  {config['name']:25s} | Return: {result['total_return']:+6.2f}% | Trades: {result['trades']:3d} | Win Rate: {result['win_rate']:5.1f}% | MaxDD: {result['max_drawdown']:5.2f}%")

    # ========================================
    # SUMMARY: Best Configurations
    # ========================================
    print("\n" + "=" * 80)
    print("SUMMARY: TOP 5 CONFIGURATIONS BY RETURN")
    print("=" * 80)

    # Sort by return
    sorted_results = sorted(results, key=lambda x: x['total_return'], reverse=True)
    for i, r in enumerate(sorted_results[:5]):
        print(f"  {i+1}. {r['config']['name']:30s} | Return: {r['total_return']:+6.2f}% | Win Rate: {r['win_rate']:5.1f}% | Trades: {r['trades']:3d}")

    print("\n" + "=" * 80)
    print("SUMMARY: TOP 5 CONFIGURATIONS BY WIN RATE (min 10 trades)")
    print("=" * 80)

    sorted_by_winrate = sorted([r for r in results if r['trades'] >= 10], key=lambda x: x['win_rate'], reverse=True)
    for i, r in enumerate(sorted_by_winrate[:5]):
        print(f"  {i+1}. {r['config']['name']:30s} | Win Rate: {r['win_rate']:5.1f}% | Return: {r['total_return']:+6.2f}% | Trades: {r['trades']:3d}")

    print("\n" + "=" * 80)
    print("SUMMARY: TOP 5 BY RISK-ADJUSTED (Return / MaxDD, min 10 trades)")
    print("=" * 80)

    for r in results:
        r['risk_adjusted'] = r['total_return'] / r['max_drawdown'] if r['max_drawdown'] > 0 else 0

    sorted_by_risk = sorted([r for r in results if r['trades'] >= 10 and r['max_drawdown'] > 0], key=lambda x: x['risk_adjusted'], reverse=True)
    for i, r in enumerate(sorted_by_risk[:5]):
        print(f"  {i+1}. {r['config']['name']:30s} | Return/DD: {r['risk_adjusted']:5.2f} | Return: {r['total_return']:+6.2f}% | MaxDD: {r['max_drawdown']:5.2f}%")


if __name__ == '__main__':
    main()
