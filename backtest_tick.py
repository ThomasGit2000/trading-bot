"""
Tick-Based Backtest using IBKR Historical Tick Data
This matches how the live bot actually trades.
"""
import os
import sys
from datetime import datetime, timedelta
from collections import deque
from dotenv import load_dotenv
from ib_insync import IB, Stock, util
import time

load_dotenv()

# Connect to IBKR
ib = IB()
host = os.getenv('IB_HOST', '127.0.0.1')
port = int(os.getenv('IB_PORT', '7496'))
client_id = int(os.getenv('IB_CLIENT_ID', '1')) + 10  # Different client ID

print('='*80)
print('TICK-BASED BACKTEST - MA(8/21) Strategy')
print('Using IBKR Historical Tick Data (matches live trading)')
print('='*80)
print()

# Symbols to test - all 70 stocks
symbols = ['AAPL','MSFT','GOOGL','META','NVDA','AMD','AVGO','QCOM','TSM','ASML','MU','ARM','PLTR','AI','SNOW','DDOG','CRM','NOW','NET','PANW','V','MA','XYZ','COIN','PYPL','TSLA','MARA','MSTR','CRWD','ZS','LLY','UNH','ABBV','ISRG','DHR','AMZN','COST','HD','MCD','CMG','SBUX','BKNG','NFLX','DIS','SPOT','DHI','JPM','GS','BLK','GE','CAT','HON','RTX','LMT','BA','UPS','PGR','NEE','CEG','PLD','AMT','LIN','FCX','XOM','CVX','ENPH','BABA','TMUS','ORLY','RIOT']
thresholds = [0.003, 0.005, 0.008]  # 0.3%, 0.5%, 0.8%

print(f"Connecting to IBKR at {host}:{port}...")
try:
    ib.connect(host, port, clientId=client_id)
    print("Connected!")
except Exception as e:
    print(f"Failed to connect: {e}")
    sys.exit(1)

print()

def run_ma_strategy(prices, threshold):
    """Run MA(8/21) strategy on tick prices"""
    if len(prices) < 21:
        return {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0, 'pnl_pct': 0, 'signals': 0}

    ma8_window = deque(maxlen=8)
    ma21_window = deque(maxlen=21)

    position = 0
    entry_price = 0
    total_pnl = 0
    total_pnl_pct = 0
    trades = 0
    wins = 0
    losses = 0
    signals = 0

    prev_ma8 = None
    prev_ma21 = None

    for price in prices:
        ma8_window.append(price)
        ma21_window.append(price)

        if len(ma21_window) < 21:
            continue

        ma8 = sum(ma8_window) / len(ma8_window)
        ma21 = sum(ma21_window) / len(ma21_window)

        if prev_ma8 is not None and prev_ma21 is not None:
            buy_threshold = ma21 * (1 + threshold)
            sell_threshold = ma21 * (1 - threshold)
            prev_buy_threshold = prev_ma21 * (1 + threshold)
            prev_sell_threshold = prev_ma21 * (1 - threshold)

            # BUY signal
            if prev_ma8 <= prev_buy_threshold and ma8 > buy_threshold:
                signals += 1
                if position == 0:
                    position = 1
                    entry_price = price

            # SELL signal
            elif prev_ma8 >= prev_sell_threshold and ma8 < sell_threshold:
                signals += 1
                if position == 1:
                    pnl = price - entry_price
                    pnl_pct = (pnl / entry_price) * 100
                    total_pnl += pnl
                    total_pnl_pct += pnl_pct
                    trades += 1
                    if pnl > 0:
                        wins += 1
                    else:
                        losses += 1
                    position = 0

        prev_ma8 = ma8
        prev_ma21 = ma21

    # Close open position at end
    if position == 1:
        pnl = prices[-1] - entry_price
        pnl_pct = (pnl / entry_price) * 100
        total_pnl += pnl
        total_pnl_pct += pnl_pct
        trades += 1
        if pnl > 0:
            wins += 1
        else:
            losses += 1

    return {
        'trades': trades,
        'wins': wins,
        'losses': losses,
        'pnl': total_pnl,
        'pnl_pct': total_pnl_pct,
        'signals': signals
    }

results = []

for symbol in symbols:
    print(f"Fetching tick data for {symbol}...")

    try:
        contract = Stock(symbol, 'SMART', 'USD')
        ib.qualifyContracts(contract)

        # Fetch historical ticks for last trading day
        # IBKR allows up to 1000 ticks per request
        all_ticks = []

        # Get end time as now
        end_dt = datetime.now()

        # Get ticks for multiple periods to build up data
        # Request last 1000 ticks multiple times going back
        for _ in range(10):  # Get up to 10000 ticks
            end_time_str = end_dt.strftime('%Y%m%d %H:%M:%S')

            ticks = ib.reqHistoricalTicks(
                contract,
                startDateTime='',
                endDateTime=end_time_str,
                numberOfTicks=1000,
                whatToShow='TRADES',
                useRth=True  # Regular trading hours only (best performance)
            )

            if not ticks:
                break

            all_ticks = ticks + all_ticks

            # Move end time back to before first tick
            if ticks:
                end_dt = ticks[0].time - timedelta(seconds=1)

            time.sleep(0.5)  # Rate limiting

        if len(all_ticks) < 100:
            print(f"  Insufficient tick data ({len(all_ticks)} ticks)")
            continue

        # Extract prices
        prices = [tick.price for tick in all_ticks]

        # Calculate time range
        start_time = all_ticks[0].time
        end_time_dt = all_ticks[-1].time
        duration = end_time_dt - start_time

        print(f"  Got {len(prices)} ticks from {start_time} to {end_time_dt}")
        print(f"  Duration: {duration}")

        # Buy and Hold
        bh_pnl = prices[-1] - prices[0]
        bh_pct = (bh_pnl / prices[0]) * 100

        result = {
            'symbol': symbol,
            'ticks': len(prices),
            'start_price': prices[0],
            'end_price': prices[-1],
            'bh_pnl': bh_pnl,
            'bh_pct': bh_pct,
            'duration': str(duration)
        }

        # Test each threshold
        for threshold in thresholds:
            strat_result = run_ma_strategy(prices, threshold)
            result[f't{threshold}'] = strat_result

        results.append(result)
        print(f"  B&H: {bh_pct:+.2f}% | 0.3%: {result['t0.003']['pnl_pct']:+.2f}% | 0.5%: {result['t0.005']['pnl_pct']:+.2f}% | 0.8%: {result['t0.008']['pnl_pct']:+.2f}%")

    except Exception as e:
        print(f"  Error: {e}")

    time.sleep(1)  # Rate limiting between symbols

ib.disconnect()

# Print results
print()
print('='*80)
print('RESULTS - TICK-BASED BACKTEST')
print('='*80)
print()

print(f"{'Symbol':<8} {'Ticks':>8} {'Duration':<20} {'Buy&Hold':>10} {'0.3%':>10} {'0.5%':>10} {'0.8%':>10}")
print('-'*80)

for r in results:
    bh = f"{r['bh_pct']:+.2f}%"
    t03 = f"{r['t0.003']['pnl_pct']:+.2f}%"
    t05 = f"{r['t0.005']['pnl_pct']:+.2f}%"
    t08 = f"{r['t0.008']['pnl_pct']:+.2f}%"
    print(f"{r['symbol']:<8} {r['ticks']:>8} {r['duration']:<20} {bh:>10} {t03:>10} {t05:>10} {t08:>10}")

print()
print('='*80)
print('TRADE STATISTICS')
print('='*80)
print()

print(f"{'Symbol':<8} {'0.3% Signals':>12} {'0.3% Trades':>12} {'0.5% Signals':>12} {'0.5% Trades':>12} {'0.8% Signals':>12} {'0.8% Trades':>12}")
print('-'*90)

for r in results:
    print(f"{r['symbol']:<8} {r['t0.003']['signals']:>12} {r['t0.003']['trades']:>12} {r['t0.005']['signals']:>12} {r['t0.005']['trades']:>12} {r['t0.008']['signals']:>12} {r['t0.008']['trades']:>12}")

# Summary
print()
print('='*80)
print('SUMMARY')
print('='*80)
print()

if results:
    avg_bh = sum(r['bh_pct'] for r in results) / len(results)
    avg_03 = sum(r['t0.003']['pnl_pct'] for r in results) / len(results)
    avg_05 = sum(r['t0.005']['pnl_pct'] for r in results) / len(results)
    avg_08 = sum(r['t0.008']['pnl_pct'] for r in results) / len(results)

    total_trades_03 = sum(r['t0.003']['trades'] for r in results)
    total_trades_05 = sum(r['t0.005']['trades'] for r in results)
    total_trades_08 = sum(r['t0.008']['trades'] for r in results)

    total_wins_03 = sum(r['t0.003']['wins'] for r in results)
    total_wins_05 = sum(r['t0.005']['wins'] for r in results)
    total_wins_08 = sum(r['t0.008']['wins'] for r in results)

    print(f"{'Strategy':<15} {'Avg Return':>12} {'Total Trades':>15} {'Win Rate':>12}")
    print('-'*55)
    print(f"{'Buy & Hold':<15} {avg_bh:>+11.2f}% {'N/A':>15} {'N/A':>12}")

    wr_03 = total_wins_03 / total_trades_03 * 100 if total_trades_03 > 0 else 0
    wr_05 = total_wins_05 / total_trades_05 * 100 if total_trades_05 > 0 else 0
    wr_08 = total_wins_08 / total_trades_08 * 100 if total_trades_08 > 0 else 0

    print(f"{'MA 0.3%':<15} {avg_03:>+11.2f}% {total_trades_03:>15} {wr_03:>11.1f}%")
    print(f"{'MA 0.5%':<15} {avg_05:>+11.2f}% {total_trades_05:>15} {wr_05:>11.1f}%")
    print(f"{'MA 0.8%':<15} {avg_08:>+11.2f}% {total_trades_08:>15} {wr_08:>11.1f}%")

    print()
    strategies = {'Buy & Hold': avg_bh, 'MA 0.3%': avg_03, 'MA 0.5%': avg_05, 'MA 0.8%': avg_08}
    best = max(strategies, key=strategies.get)
    worst = min(strategies, key=strategies.get)

    print(f"BEST:  {best} ({strategies[best]:+.2f}%)")
    print(f"WORST: {worst} ({strategies[worst]:+.2f}%)")
