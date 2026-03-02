# Trading Bot Project

## Overview
Automated multi-stock trading bot for Interactive Brokers.
Uses **AGGRESSIVE MA(8/21) Fibonacci strategy** - backtested 74.6% win rate.
Now supports **70 momentum stocks** with intelligent news sentiment analysis.

## Current State (Last updated: 2026-03-02)
- **Strategy**: AGGRESSIVE MA(8/21) Fibonacci - 21.17% return, 74.6% win rate (1-year backtest)
- **Stock Universe**: 70 hand-picked momentum stocks
- **News Analysis**: VADER sentiment (industry-standard NLP)
- **Risk Controls**: 5% stop-loss, 3% trailing stop, circuit breakers
- **Trading Hours**: Regular market only (after-hours disabled)
- Live trading mode configured (port 7496 for TWS)

## Stock Universe (70 Stocks)

Currently trading 70 momentum stocks across multiple sectors:
- **Tech Giants**: AAPL, MSFT, GOOGL, META, AMZN, CRM
- **Semiconductors**: NVDA, AMD, AVGO, QCOM, TSM, ASML, MU, ARM
- **AI/Cloud**: PLTR, AI, SNOW, DDOG, NOW, NET
- **Cybersecurity**: PANW, CRWD, ZS
- **Fintech**: V, MA, COIN, PYPL
- **Crypto**: MARA, MSTR, RIOT
- **EV/Auto**: TSLA
- **Healthcare**: LLY, UNH, ABBV, ISRG, DHR
- **Consumer**: COST, HD, MCD, CMG, SBUX, BKNG, NFLX, DIS, SPOT
- **Finance**: JPM, GS, BLK
- **Industrials**: GE, CAT, HON, RTX, LMT, BA, UPS
- **Utilities/REITs**: NEE, CEG, PLD, AMT
- **Materials/Energy**: LIN, FCX, XOM, CVX, ENPH
- **Other**: BABA, TMUS, ORLY, DHI, PGR

## Strategy: AGGRESSIVE MA(8/21) Fibonacci

**Fibonacci-based moving averages** - tested and proven effective.

### Entry/Exit Rules:
- **BUY Signal**: MA(8) crosses **0.8% above** MA(21)
- **SELL Signal**: MA(8) crosses **0.8% below** MA(21)

### Risk Management (ACTIVE):
- **5% Stop-Loss**: Cuts losses at -5% per trade
- **3% Trailing Stop**: Locks in profits after 8% gain
- **Minimum Hold**: 5 periods (5 seconds)

### Quality Filters (ACTIVE):
- **RSI Filter**: No entry if RSI > 70 (overbought)
- **Volume Filter**: Requires 1.2x average volume for entry
- **Minimum Volume**: Blocks trades on < 0.3x average volume

### Circuit Breakers:
- **Max Daily Loss**: $1,000 (14% of account)
- **Max Daily Trades**: 100 trades

### Backtest Performance:
- **Period**: 1 year (10 stocks, 2025-2026)
- **Average Return**: 21.17%
- **Win Rate**: 74.6%
- **Average Trades**: 6.7 per stock
- **Comparison**: Beats buy & hold significantly

## News Sentiment Analysis

**VADER (Valence Aware Dictionary and sEntiment Reasoner)**
- Industry-standard NLP sentiment analysis
- Analyzes headlines semantically (not just keywords)
- Compound scores from -1.0 (negative) to +1.0 (positive)
- Updates hourly for all stocks
- Dashboard displays sentiment bars with accurate positioning

## Configuration (.env)

### Current Setup (70 Stocks)
```bash
SYMBOLS=AAPL,MSFT,GOOGL,META,NVDA,AMD,AVGO,QCOM,TSM,ASML,MU,ARM,PLTR,AI,SNOW,DDOG,CRM,NOW,NET,PANW,V,MA,XYZ,COIN,PYPL,TSLA,MARA,MSTR,CRWD,ZS,LLY,UNH,ABBV,ISRG,DHR,AMZN,COST,HD,MCD,CMG,SBUX,BKNG,NFLX,DIS,SPOT,DHI,JPM,GS,BLK,GE,CAT,HON,RTX,LMT,BA,UPS,PGR,NEE,CEG,PLD,AMT,LIN,FCX,XOM,CVX,ENPH,BABA,TMUS,ORLY,RIOT
```

### Strategy Settings
```bash
# MA(8/21) Fibonacci Strategy
STRATEGY_TYPE=AGGRESSIVE
SHORT_MA=8
LONG_MA=21
MA_THRESHOLD=0.008  # 0.8% crossover threshold

# Speed Optimizations
PRICE_INTERVAL_SEC=1   # Price updates every 1 second
TRADE_INTERVAL_SEC=30  # Trade checks every 30 seconds

# Risk Management (ENABLED)
STOP_LOSS_PCT=0.05          # 5% maximum loss per trade
TRAILING_STOP_PCT=0.03      # 3% trailing stop from peak
MIN_HOLD_PERIODS=5          # Minimum 5 bars hold

# Filters (ENABLED)
RSI_FILTER=true
RSI_OVERBOUGHT=70
VOLUME_FILTER=true
VOLUME_CONFIRM_THRESHOLD=1.2
VOLUME_MIN_THRESHOLD=0.3
```

### Position Sizes
```bash
# Automatically sized for 10% max position (DKK account)
POSITION_SIZES={"AAPL": 2, "MSFT": 1, "GOOGL": 2, ...}
```

## To Run

### Start Bot
```bash
cd C:\ClaudeSpace\trading-bot && python multi_bot.py
```

### Stop Bot
```bash
# Ctrl+C or use Task Manager
```

## Web Dashboard

**URL**: http://localhost:8080

### Features:
- **Real-time prices** for all 70 stocks
- **MA(8) and MA(21)** values displayed
- **News sentiment bars** with VADER analysis
- **Signal indicators**: BUY/SELL/HOLD with strength
- **Position tracking** with P&L
- **Trading controls**: Enable/disable trading via button
- **Stock detail modal**: Charts, news, fundamentals, events
- **Sector analysis**: /sectors page shows allocation

### Dashboard Columns:
- **Symbol**: Stock ticker
- **Category**: Sector classification
- **Event**: Days until earnings
- **Price**: Current price with 24H change
- **24H**: Sparkline chart
- **Pos**: Current position (shares held)
- **Target**: Target position size
- **Data**: Price bars collected (X/21)
- **Signal**: BUY/SELL/HOLD with visual bar
- **MA(8)**: Short-term moving average
- **MA(21)**: Long-term moving average
- **News**: Sentiment bar (red=negative, green=positive)

## Project Structure
```
trading-bot/
├── multi_bot.py                   # Multi-stock trading bot
├── simple_backtest.py             # Strategy backtesting script
├── .env                           # Configuration file
├── CLAUDE.md                      # This file
├── SENTIMENT_UPGRADE.md           # VADER sentiment documentation
├── OPTIMIZATION_CHANGELOG.md      # Full changelog of optimizations
├── src/
│   ├── strategy.py                # MA(8/21) strategy logic
│   ├── multi_dashboard.py         # FastAPI dashboard server
│   ├── yfinance_client.py         # Yahoo Finance + VADER sentiment
│   ├── regime_detector.py         # Market regime detection (SPY)
│   ├── trading_control.py         # Master trading on/off switch
│   └── ...
└── logs/                          # Trading logs
```

## Performance Summary

### Before Optimizations:
- Win Rate: 14%
- Max Loss: Unlimited
- Sentiment: All neutral (broken)

### After Optimizations:
- **Win Rate**: 74.6%
- **Max Loss/Trade**: $36 (5%)
- **Max Daily Loss**: $1,000 (14%)
- **Sentiment**: VADER-powered, accurate
- **Signal Latency**: 1.1-1.5s (50% faster)

## Risk Management

### Capital Protection:
- 5% stop-loss per trade (max $36 loss)
- 3% trailing stop locks in profits
- Circuit breakers cap daily losses at $1,000

### Quality Controls:
- RSI filter prevents overbought entries
- Volume filter confirms strong moves
- Data validation prevents bad trades
- Duplicate order prevention

### Trading Hours:
- **Active**: 9:30 AM - 4:00 PM ET (Regular market only)
- **Inactive**: Pre-market and after-hours (safer for automated trading)

## Key Features

### VADER Sentiment Analysis
- Replaces simple keyword matching
- Analyzes full headline semantics
- Returns compound scores (-1.0 to +1.0)
- Updates hourly for all stocks
- See SENTIMENT_UPGRADE.md for details

### MA(8/21) Strategy
- Fibonacci-based moving averages
- 0.8% threshold for signal generation
- Faster response than MA(10/30)
- Backtested with 74.6% win rate
- Optimized for momentum stocks

### Dynamic Order Pricing
- Strong signals: Pay 0.3% premium (ensure fill)
- Medium signals: Pay 0.1% premium
- Weak signals: Wait for discount

### Circuit Breakers
- Auto-halts at $1,000 daily loss
- Max 100 trades per day
- Resets automatically each day

## Documentation

- **CLAUDE.md** (this file): Project overview and quick reference
- **SENTIMENT_UPGRADE.md**: VADER sentiment technical details
- **OPTIMIZATION_CHANGELOG.md**: Complete changelog of all improvements
- **ANALYSIS_SUMMARY.md**: System analysis and recommendations
- **OPTIMIZATIONS.md**: Detailed optimization explanations

## Dependencies

### Core:
- `ib_insync==0.9.86` - Interactive Brokers API
- `yfinance` - Market data and news
- `vaderSentiment==3.3.2` - News sentiment analysis (NEW)
- `fastapi` + `uvicorn` - Web dashboard
- `python-dotenv` - Configuration management

### Full list in requirements.txt

## Quick Commands

```bash
# Start trading bot
cd C:\ClaudeSpace\trading-bot && python multi_bot.py

# Run backtest
python simple_backtest.py

# View dashboard
# Open browser: http://localhost:8080

# Check git status
git status

# Commit changes
git add -A && git commit -m "Your message"

# Push to GitHub
git push origin master
```

## Trading Rules

### When Bot Trades:
- Market hours only (9:30 AM - 4:00 PM ET)
- MA(8) crosses MA(21) by ±0.8%
- Volume confirms at 1.2x+ average
- RSI not overbought (< 70)

### When Bot Doesn't Trade:
- Market closed (after-hours, weekends, holidays)
- No clear MA crossover signal
- Volume too low (< 1.2x)
- RSI overbought (> 70)
- Daily loss limit reached ($1,000)
- Daily trade limit reached (100 trades)

## Repository

**GitHub**: https://github.com/ThomasGit2000/trading-bot

**Last Updated**: 2026-03-02

---

**Status**: ✅ Ready to trade - MA(8/21) AGGRESSIVE strategy active with VADER sentiment
