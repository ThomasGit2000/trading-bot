# Trading Bot Project

## Overview
Automated multi-stock trading bot for Interactive Brokers.
Uses **BREAKOUT strategy** optimized for 1-second tick data.
Now supports **70 momentum stocks** with intelligent news sentiment analysis.

## Current State (Last updated: 2026-03-07)
- **Strategy**: BREAKOUT with Alpha Engine (confluence filtering)
- **Active Model**: ALPHA_ENGINE (see models.json)
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

## Strategy: BREAKOUT

**Price breakout detection** optimized for 1-second tick data.

### Entry/Exit Rules:
- **BUY Signal**: Price breaks **0.5% above** 60-period high
- **SELL Signal**: Price breaks **0.5% below** 60-period low (or stop-loss/trailing stop triggers)
- **ATR Filter**: Only trades when ATR > 0.20% (filters low volatility)

### Risk Management (ACTIVE):
- **5% Stop-Loss**: Cuts losses at -5% per trade
- **3% Trailing Stop**: Locks in profits after gains
- **Minimum Hold**: 5 periods

### Circuit Breakers:
- **Max Daily Loss**: $1,000 (14% of account)
- **Max Daily Trades**: 100 trades

## Models System

Trading strategies are stored in `models.json` and viewable at http://localhost:8080/models

### models.json Structure
```json
{
  "models": {
    "MODEL_KEY": {
      "name": "Human readable name",
      "description": "What the model does",
      "status": "active|saved",
      "parameters": { ... },
      "backtest_results": { ... }
    }
  },
  "active_model": "MODEL_KEY"
}
```

### Current Models
| Model | Description | Status |
|-------|-------------|--------|
| **ALPHA_ENGINE** | 6-signal confluence filter (breakout, volume, ATR, RSI, regime, sentiment) | Active |
| **BREAKOUT** | Raw price breakout detection | Saved |
| **RSI_SWING** | Buy oversold, sell overbought | Saved |
| **BOLLINGER** | Mean reversion at bands | Saved |
| **MACD** | Classic trend following | Saved |
| **DONCHIAN** | Turtle trading method | Saved |

### Adding New Models
1. Add model entry to `models.json` with parameters and backtest results
2. If model needs new code, create in `src/` (e.g., `src/alpha_engine.py`)
3. Integrate into `multi_bot.py` (import, build context, apply to signals)
4. Add config to `.env` if needed
5. Update dashboard column in `src/multi_dashboard.py` if displaying new data

### Alpha Engine (Current Active Model)
Combines 6 weighted signals for confluence-based filtering:
- **Breakout** (0.35): Distance from range midpoint
- **Volume** (0.20): Relative volume confirmation
- **ATR** (0.12): Volatility momentum
- **RSI** (0.12): Oversold/overbought levels
- **Regime** (0.11): BULL/BEAR market detection
- **Sentiment** (0.10): VADER news score

**Scoring**: alpha_score >= 0.30 required for BUY
**Hard Filters**: RSI < 70 (blocks overbought entries)
**Backtest**: 65% win rate, +1.40% return (vs 54.5% baseline)

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
# BREAKOUT Strategy
STRATEGY_TYPE=BREAKOUT
BREAKOUT_LOOKBACK=60        # 60-period range for breakout detection
BREAKOUT_THRESHOLD=0.005    # 0.5% above/below range
ATR_FILTER=true             # Filter low volatility
ATR_MIN_THRESHOLD=0.002    # Minimum 0.20% ATR

# Speed Optimizations
PRICE_INTERVAL_SEC=1   # Price updates every 1 second
TRADE_INTERVAL_SEC=30  # Trade checks every 30 seconds

# Risk Management (ENABLED)
STOP_LOSS_PCT=0.05          # 5% maximum loss per trade
TRAILING_STOP_PCT=0.03      # 3% trailing stop from peak
MIN_HOLD_PERIODS=5          # Minimum 5 bars hold

# Filters (DISABLED for BREAKOUT)
RSI_FILTER=false
VOLUME_FILTER=false

# Alpha Engine (Confluence Filter)
ALPHA_ENGINE_ENABLED=true
ALPHA_THRESHOLD=0.30         # Minimum score for BUY
ALPHA_RSI_MAX=70             # Block if RSI >= 70
ALPHA_WEIGHT_BREAKOUT=0.35
ALPHA_WEIGHT_VOLUME=0.20
ALPHA_WEIGHT_ATR=0.12
ALPHA_WEIGHT_RSI=0.12
ALPHA_WEIGHT_REGIME=0.11
ALPHA_WEIGHT_SENTIMENT=0.10
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
- **Data**: Price bars collected (X/60)
- **Signal**: BUY/SELL/HOLD with visual bar
- **Range High**: 60-period high (breakout level)
- **Range Low**: 60-period low (breakdown level)
- **News**: Sentiment bar (red=negative, green=positive)

## Project Structure
```
trading-bot/
├── multi_bot.py                   # Multi-stock trading bot
├── models.json                    # Trading models/strategies config
├── simple_backtest.py             # Strategy backtesting script
├── backtest_alpha_realistic.py    # Alpha engine backtest with portfolio sim
├── .env                           # Configuration file
├── CLAUDE.md                      # This file
├── SENTIMENT_UPGRADE.md           # VADER sentiment documentation
├── OPTIMIZATION_CHANGELOG.md      # Full changelog of optimizations
├── src/
│   ├── alpha_engine.py            # Alpha confluence filter (6 signals)
│   ├── strategy.py                # Breakout/MA strategy logic
│   ├── multi_dashboard.py         # FastAPI dashboard server
│   ├── yfinance_client.py         # Yahoo Finance + VADER sentiment
│   ├── regime_detector.py         # Market regime detection (SPY)
│   ├── trading_control.py         # Master trading on/off switch
│   └── ...
└── logs/                          # Trading logs
```

## Performance Summary

### Risk Controls:
- **Max Loss/Trade**: 5% (stop-loss)
- **Max Daily Loss**: $1,000 (circuit breaker)
- **Trailing Stop**: 3% from peak
- **ATR Filter**: 0.20% minimum volatility
- **Sentiment**: VADER-powered news analysis

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

### BREAKOUT Strategy
- 60-period price range detection
- 0.5% threshold for breakout confirmation
- ATR filter ensures sufficient volatility
- Optimized for 1-second tick data
- Captures momentum breakouts

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
- Price breaks 0.5% above 60-period high (BUY)
- Price breaks 0.5% below 60-period low (SELL)
- ATR > 0.20% (sufficient volatility)

### When Bot Doesn't Trade:
- Market closed (after-hours, weekends, holidays)
- Price within consolidation range
- ATR too low (< 0.20% - low volatility)
- Daily loss limit reached ($1,000)
- Daily trade limit reached (100 trades)

## Repository

**GitHub**: https://github.com/ThomasGit2000/trading-bot

**Last Updated**: 2026-03-07 (Alpha Engine added)

---

**Status**: ✅ Ready to trade - Alpha Engine active (65% win rate, confluence filtering)
