"""
Backtest today's trading with current MA(10/30) strategy
"""
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from ib_insync import IB, Stock, util
from src.strategy import SimpleStrategy
import pytz

load_dotenv()

# Get symbols from .env
symbols_str = os.getenv('SYMBOLS', '')
symbols = [s.strip() for s in symbols_str.split(',') if s.strip()][:10]  # Test with first 10 stocks

print(f"Backtesting {len(symbols)} stocks for today")
print("=" * 80)

# Connect to IB
ib = IB()
ib.connect('127.0.0.1', 7496, clientId=98)

# Strategy settings
SHORT_MA = 10
LONG_MA = 30

# Track results
results = []
total_trades = 0
winning_trades = 0
total_pnl = 0

for symbol in symbols:
    try:
        contract = Stock(symbol, 'SMART', 'USD')
        ib.qualifyContracts(contract)

        # Get today's 5-minute bars
        eastern = pytz.timezone('US/Eastern')
        now = datetime.now(eastern)

        # Fetch intraday data for today
        bars = ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr='1 D',
            barSizeSetting='5 mins',
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1
        )

        if not bars or len(bars) < LONG_MA:
            print(f"{symbol:6} - Insufficient data ({len(bars) if bars else 0} bars)")
            continue

        # Initialize strategy
        strategy = SimpleStrategy(
            short_window=SHORT_MA,
            long_window=LONG_MA,
            threshold=0.01,
            stop_loss_pct=None,
            trailing_stop_pct=None,
            min_hold_periods=0,
            volume_confirm_threshold=0,
            volume_min_threshold=0
        )

        # Simulate trading through the day
        trades = []
        position = 0
        entry_price = 0

        for i, bar in enumerate(bars):
            strategy.add_price(bar.close)

            if i < LONG_MA:
                continue

            signal = strategy.get_signal()

            # Simulate trades
            if signal == 'BUY' and position == 0:
                position = 10  # Position size
                entry_price = bar.close
                trades.append({
                    'time': bar.date,
                    'action': 'BUY',
                    'price': bar.close,
                    'position': position
                })
                strategy.enter_position(bar.close)

            elif signal == 'SELL' and position > 0:
                exit_price = bar.close
                pnl = (exit_price - entry_price) * position
                trades.append({
                    'time': bar.date,
                    'action': 'SELL',
                    'price': bar.close,
                    'pnl': pnl,
                    'position': 0
                })
                strategy.exit_position("MA crossover")

                total_trades += 1
                if pnl > 0:
                    winning_trades += 1
                total_pnl += pnl

                position = 0
                entry_price = 0

        # Report for this symbol
        if trades:
            print(f"\n{symbol:6} - {len(trades)} signals:")
            for trade in trades:
                if trade['action'] == 'BUY':
                    print(f"  {trade['time'].strftime('%H:%M')} BUY  @ ${trade['price']:.2f}")
                else:
                    pnl_str = f"${trade['pnl']:+.2f}"
                    print(f"  {trade['time'].strftime('%H:%M')} SELL @ ${trade['price']:.2f} - P/L: {pnl_str}")

            results.append({
                'symbol': symbol,
                'trades': trades,
                'signals': len(trades)
            })
        else:
            print(f"{symbol:6} - No signals today")

    except Exception as e:
        print(f"{symbol:6} - Error: {e}")

ib.disconnect()

# Summary
print("\n" + "=" * 80)
print("BACKTEST SUMMARY")
print("=" * 80)
print(f"Total completed trades: {total_trades}")
if total_trades > 0:
    print(f"Winning trades: {winning_trades} ({winning_trades/total_trades*100:.1f}%)")
    print(f"Total P/L: ${total_pnl:+.2f}")
    print(f"Average P/L per trade: ${total_pnl/total_trades:+.2f}")
else:
    print("No completed trades today")
