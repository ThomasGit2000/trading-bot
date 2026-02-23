# Trading Bot Project

## Overview
Automated multi-stock trading bot for Interactive Brokers.
Uses **NO STOPS strategy** (MA crossover only) - proven to beat buy & hold.

## Current State (Last updated: 2026-02-23)
- **Multi-stock trading**: TSLA + NIO
- **Strategy**: NO STOPS MA(10/30) - beats buy & hold on both stocks
- Live trading mode configured (port 7496 for TWS)
- Scalable dashboard for multiple stocks
- Near-real-time price collection via Yahoo Finance

## Backtest Results (2-year, 2026-02-23)
| Stock | Strategy | Buy & Hold | Beat By | Win% | Sharpe |
|-------|----------|------------|---------|------|--------|
| **TSLA** | +133.9% | +111.4% | **+22.5%** | 71.4% | 1.28 |
| **NIO** | +40.2% | +23.4% | **+16.8%** | 33.3% | 1.07 |

**Key Insight**: Stop losses hurt performance in bull markets. Let winners run!

## Current Positions
- **NIO**: 41 shares @ ~$5.05 avg cost
- **TSLA**: No position yet

## Configuration (.env)
```
# Multi-Stock Trading
SYMBOLS=TSLA,NIO
POSITION_SIZES={"TSLA": 5, "NIO": 200}

# Strategy: NO STOPS (best performer)
STRATEGY_TYPE=NO_STOPS
SHORT_MA=10
LONG_MA=30
STOP_LOSS_PCT=0
TRAILING_STOP_PCT=0

# Filters disabled for clean signals
RSI_FILTER=false
VOLUME_FILTER=false
FUNDAMENTAL_FILTER=false
```

## Strategy: NO STOPS MA(10/30)
Simple but effective - MA crossover without stop losses.

**Entry Signal:**
- Short MA (10) crosses above Long MA (30)

**Exit Signal:**
- Short MA (10) crosses below Long MA (30)

**Why it works:**
- Stop losses kick you out during temporary dips
- In uptrending markets, dips recover
- Fewer trades = less friction and taxes
- Let the trend do the work

## To Run

### Multi-Stock Bot (recommended)
```bash
cd C:\ClaudeSpace\trading-bot && python multi_bot.py
```

### Single-Stock Bot (legacy)
```bash
cd C:\ClaudeSpace\trading-bot && python -m src.bot
```

## Web Dashboard
Multi-stock dashboard at http://localhost:8080

**Features:**
- Real-time prices for all stocks
- Position tracking per stock
- Buy/Sell signals with MA values
- Data collection progress
- Live/Dry run status

## Project Structure
```
trading-bot/
├── multi_bot.py            # Multi-stock trading bot (NEW)
├── src/
│   ├── bot.py              # Single-stock bot (legacy)
│   ├── strategy.py         # Trading strategy logic
│   ├── multi_dashboard.py  # Scalable dashboard (NEW)
│   ├── dashboard.py        # Single-stock dashboard
│   ├── dashboard_state.py  # Shared state (multi-stock support)
│   ├── backtest.py         # Backtesting engine
│   ├── yfinance_client.py  # Yahoo Finance data
│   └── ...
├── backtest_both.py        # Multi-stock backtest script
├── beat_buyhold.py         # Strategy comparison script
├── .env                    # Configuration
└── logs/                   # Log files
```

## Adding More Stocks
1. Add symbol to SYMBOLS in .env: `SYMBOLS=TSLA,NIO,AAPL`
2. Add position size: `POSITION_SIZES={"TSLA": 5, "NIO": 200, "AAPL": 10}`
3. Restart bot - dashboard auto-scales

## Risk Management
- No stop losses (by design - better performance)
- Position sizes limit exposure per stock
- Diversification across multiple stocks
- MA crossover provides natural exit points

## Repository
https://github.com/ThomasGit2000/trading-bot
