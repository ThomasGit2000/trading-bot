"""
Backtest recent trading days with current MA(10/30) strategy
"""
import os
from datetime import datetime
from dotenv import load_dotenv
from ib_insync import IB, Stock, util
from src.strategy import SimpleStrategy

load_dotenv()

# Get symbols from .env (test with subset)
symbols_str = os.getenv('SYMBOLS', '')
symbols = [s.strip() for s in symbols_str.split(',') if s.strip()][:15]  # Test with first 15 stocks

print(f"Backtesting {len(symbols)} stocks - Last 5 trading days")
print("=" * 80)

# Connect to IB
ib = IB()
ib.connect('127.0.0.1', 7496, clientId=98)

# Strategy settings
SHORT_MA = 10
LONG_MA = 30
POSITION_SIZE = 10

# Track results
all_trades = []
total_pnl = 0
winning_trades = 0
losing_trades = 0

for symbol in symbols:
    try:
        contract = Stock(symbol, 'SMART', 'USD')
        ib.qualifyContracts(contract)

        # Get 5 days of 15-minute bars
        bars = ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr='5 D',
            barSizeSetting='15 mins',
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1
        )

        if not bars or len(bars) < LONG_MA + 10:
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

        # Simulate trading
        position = 0
        entry_price = 0
        entry_time = None
        symbol_pnl = 0
        symbol_trades = []

        for i, bar in enumerate(bars):
            strategy.add_price(bar.close)

            if i < LONG_MA:
                continue

            signal = strategy.get_signal()

            # Execute trades
            if signal == 'BUY' and position == 0:
                position = POSITION_SIZE
                entry_price = bar.close
                entry_time = bar.date
                strategy.enter_position(bar.close)

            elif signal == 'SELL' and position > 0:
                exit_price = bar.close
                pnl = (exit_price - entry_price) * position
                hold_hours = (bar.date - entry_time).total_seconds() / 3600

                trade_record = {
                    'symbol': symbol,
                    'entry_time': entry_time,
                    'entry_price': entry_price,
                    'exit_time': bar.date,
                    'exit_price': exit_price,
                    'pnl': pnl,
                    'pnl_pct': (exit_price / entry_price - 1) * 100,
                    'hold_hours': hold_hours
                }

                all_trades.append(trade_record)
                symbol_trades.append(trade_record)
                symbol_pnl += pnl

                if pnl > 0:
                    winning_trades += 1
                else:
                    losing_trades += 1

                total_pnl += pnl
                strategy.exit_position("MA crossover")

                position = 0
                entry_price = 0

        # Report for this symbol
        if symbol_trades:
            print(f"\n{symbol:6} - {len(symbol_trades)} trades | Total P/L: ${symbol_pnl:+.2f}")
            for t in symbol_trades[-3:]:  # Show last 3 trades
                print(f"  {t['entry_time'].strftime('%m/%d %H:%M')} -> {t['exit_time'].strftime('%m/%d %H:%M')}: "
                      f"${t['entry_price']:.2f} -> ${t['exit_price']:.2f} = ${t['pnl']:+.2f} ({t['pnl_pct']:+.1f}%)")
        else:
            print(f"{symbol:6} - No completed trades")

    except Exception as e:
        print(f"{symbol:6} - Error: {e}")

ib.disconnect()

# Summary
print("\n" + "=" * 80)
print("BACKTEST SUMMARY - LAST 5 TRADING DAYS")
print("=" * 80)
total_trades = winning_trades + losing_trades

if total_trades > 0:
    win_rate = (winning_trades / total_trades) * 100
    avg_pnl = total_pnl / total_trades

    print(f"Total trades: {total_trades}")
    print(f"  Winning: {winning_trades} ({win_rate:.1f}%)")
    print(f"  Losing: {losing_trades} ({100-win_rate:.1f}%)")
    print(f"\nTotal P/L: ${total_pnl:+.2f}")
    print(f"Average P/L per trade: ${avg_pnl:+.2f}")

    if total_pnl > 0:
        print(f"\n✅ Strategy was PROFITABLE over last 5 days")
    else:
        print(f"\n❌ Strategy had losses over last 5 days")

    # Best and worst trades
    if all_trades:
        best_trade = max(all_trades, key=lambda x: x['pnl'])
        worst_trade = min(all_trades, key=lambda x: x['pnl'])

        print(f"\nBest trade: {best_trade['symbol']} ${best_trade['pnl']:+.2f} ({best_trade['pnl_pct']:+.1f}%)")
        print(f"Worst trade: {worst_trade['symbol']} ${worst_trade['pnl']:+.2f} ({worst_trade['pnl_pct']:+.1f}%)")
else:
    print("No completed trades in the backtest period")
