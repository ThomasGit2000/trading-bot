"""Backtest regime-aware strategy on NVDA"""
from src.backtest import Backtester
from src.yfinance_client import YFinanceClient
import yfinance as yf
import logging
logging.basicConfig(level=logging.WARNING)

print('='*70)
print('  REGIME-AWARE STRATEGY BACKTEST')
print('  NVDA with SPY regime detection')
print('='*70)

# Fetch NVDA and SPY data for 2 years
nvda = yf.Ticker('NVDA')
spy = yf.Ticker('SPY')

nvda_hist = nvda.history(period='2y')
spy_hist = spy.history(period='2y')

# Convert to lists
nvda_prices = nvda_hist['Close'].tolist()
nvda_dates = nvda_hist.index.tolist()
spy_prices = spy_hist['Close'].tolist()

# Align data by ensuring same length
min_len = min(len(nvda_prices), len(spy_prices))
nvda_prices = nvda_prices[:min_len]
nvda_dates = nvda_dates[:min_len]
spy_prices = spy_prices[:min_len]

# Buy and hold benchmark
start_price = nvda_prices[0]
end_price = nvda_prices[-1]
buy_hold_pct = ((end_price - start_price) / start_price) * 100

print(f"\nNVDA: ${start_price:.2f} -> ${end_price:.2f}")
print(f"Buy & Hold return: {buy_hold_pct:+.1f}%")

# Strategy parameters
capital = 10000
pos_size = 75  # shares
nvda_short_ma = 10
nvda_long_ma = 30
spy_short_ma = 20
spy_long_ma = 50
threshold = 0.01

# Simulate regime-aware strategy
position = 0
cash = capital
entry_price = 0
trades = []

# Track regime
def get_regime(spy_prices, i, short=20, long=50, thresh=0.01):
    if i < long:
        return 'UNKNOWN'
    short_ma = sum(spy_prices[i-short:i]) / short
    long_ma = sum(spy_prices[i-long:i]) / long
    if short_ma > long_ma * (1 + thresh):
        return 'BULL'
    elif short_ma < long_ma * (1 - thresh):
        return 'BEAR'
    return 'NEUTRAL'

def get_nvda_signal(prices, i, short=10, long=30, thresh=0.01):
    if i < long:
        return 'HOLD'
    short_ma = sum(prices[i-short:i]) / short
    long_ma = sum(prices[i-long:i]) / long
    if short_ma > long_ma * (1 + thresh):
        return 'BUY'
    elif short_ma < long_ma * (1 - thresh):
        return 'SELL'
    return 'HOLD'

regime_changes = []
current_regime = 'UNKNOWN'

for i in range(spy_long_ma, len(nvda_prices)):
    price = nvda_prices[i]
    date = nvda_dates[i]

    regime = get_regime(spy_prices, i, spy_short_ma, spy_long_ma)
    nvda_signal = get_nvda_signal(nvda_prices, i, nvda_short_ma, nvda_long_ma)

    # Track regime changes
    if regime != current_regime:
        regime_changes.append((date, current_regime, regime))
        current_regime = regime

    # Regime-aware logic
    if position == 0:
        # Not in position - enter on BUY signal
        if nvda_signal == 'BUY':
            qty = min(pos_size, int(cash / price))
            if qty > 0:
                cash -= qty * price
                position = qty
                entry_price = price
                trades.append({
                    'date': date, 'action': 'BUY', 'price': price,
                    'qty': qty, 'regime': regime
                })
    else:
        # In position - regime determines exit
        if regime == 'BULL':
            # BULL market: IGNORE sell signals, hold
            pass
        elif regime == 'BEAR' and nvda_signal == 'SELL':
            # BEAR market: Follow sell signals
            cash += position * price
            pnl = (price - entry_price) * position
            trades.append({
                'date': date, 'action': 'SELL', 'price': price,
                'qty': position, 'regime': regime, 'pnl': pnl
            })
            position = 0
        # UNKNOWN/NEUTRAL: Follow sell signals (conservative)
        elif regime == 'UNKNOWN' and nvda_signal == 'SELL':
            cash += position * price
            pnl = (price - entry_price) * position
            trades.append({
                'date': date, 'action': 'SELL', 'price': price,
                'qty': position, 'regime': regime, 'pnl': pnl
            })
            position = 0

# Close position at end if still open
if position > 0:
    cash += position * end_price
    pnl = (end_price - entry_price) * position
    trades.append({
        'date': nvda_dates[-1], 'action': 'SELL (END)', 'price': end_price,
        'qty': position, 'regime': current_regime, 'pnl': pnl
    })

final_value = cash
strategy_return = ((final_value - capital) / capital) * 100
diff = strategy_return - buy_hold_pct

print(f"\n{'='*70}")
print(f"  REGIME-AWARE STRATEGY RESULTS")
print(f"{'='*70}")
print(f"\nStrategy return: {strategy_return:+.1f}%")
print(f"Buy & Hold return: {buy_hold_pct:+.1f}%")
print(f"Outperformance: {diff:+.1f}%")
print(f"Final value: ${final_value:,.2f}")

beat = "BEATS BUY & HOLD!" if diff > 0 else "Does not beat B&H"
print(f"\n>>> {beat} <<<")

print(f"\n{'='*70}")
print(f"  TRADE LOG ({len(trades)} trades)")
print(f"{'='*70}")
for t in trades:
    pnl_str = f" (PnL: ${t.get('pnl', 0):+,.0f})" if 'pnl' in t else ""
    print(f"  {str(t['date'])[:10]}: {t['action']:<12} {t['qty']} @ ${t['price']:.2f} [{t['regime']}]{pnl_str}")

print(f"\n{'='*70}")
print(f"  REGIME CHANGES")
print(f"{'='*70}")
for date, old, new in regime_changes[:15]:  # Show first 15
    print(f"  {str(date)[:10]}: {old} -> {new}")
if len(regime_changes) > 15:
    print(f"  ... and {len(regime_changes) - 15} more")

# Compare to standard MA strategy
print(f"\n{'='*70}")
print(f"  COMPARISON: REGIME-AWARE vs STANDARD MA")
print(f"{'='*70}")

# Standard MA (always follow signals)
std_position = 0
std_cash = capital

for i in range(nvda_long_ma, len(nvda_prices)):
    price = nvda_prices[i]
    signal = get_nvda_signal(nvda_prices, i, nvda_short_ma, nvda_long_ma)

    if std_position == 0 and signal == 'BUY':
        qty = min(pos_size, int(std_cash / price))
        if qty > 0:
            std_cash -= qty * price
            std_position = qty

    elif std_position > 0 and signal == 'SELL':
        std_cash += std_position * price
        std_position = 0

if std_position > 0:
    std_cash += std_position * end_price

std_return = ((std_cash - capital) / capital) * 100

print(f"\n{'Strategy':<25} {'Return':>12} {'vs B&H':>12}")
print(f"{'-'*50}")
print(f"{'Buy & Hold':<25} {buy_hold_pct:>+11.1f}% {'-':>12}")
print(f"{'Standard MA(10/30)':<25} {std_return:>+11.1f}% {std_return - buy_hold_pct:>+11.1f}%")
print(f"{'Regime-Aware MA':<25} {strategy_return:>+11.1f}% {diff:>+11.1f}%")

improvement = strategy_return - std_return
print(f"\nRegime-aware improvement over standard MA: {improvement:+.1f}%")
