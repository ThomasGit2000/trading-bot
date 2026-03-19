# Trading Bot Project

## Overview
Automated multi-stock trading bot for Interactive Brokers.
Now supports **70 momentum stocks** with multiple trading strategies.

## Current State (Last updated: 2026-03-18)
- **Active Model**: SELECTIVE_RSI (mean-reversion with volume confirmation)
- **Strategy**: Buy oversold (RSI<25) with volume spike + ATR filter, target +12%, stop -8%
- **Backtest**: 65.2% win rate, +$192/14 days = $14/day = 48% annualized
- **Stock Universe**: 71 momentum stocks
- **Processing**: Per-tick with multi-core parallel computation (12 workers)
- **News Analysis**: VADER sentiment (industry-standard NLP)
- **Risk Controls**: 8% stop-loss, 12% profit target, max 5 concurrent positions
- **Trading Hours**: Regular market only (9:30 AM - 4:00 PM ET)
- **Dashboard**: http://localhost:8080 (updated columns for SELECTIVE_RSI)
- **Model Switching**: http://localhost:8080/models
- **Market Overview**: http://localhost:8080/market
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

## Strategy: SELECTIVE_RSI (Active)

**Mean reversion strategy** buying oversold stocks with volume confirmation.

### Entry Rules:
- **RSI < 25**: Stock is oversold (buy zone)
- **Relative Volume > 1.0x**: Volume confirmation vs average
- **ATR > 1%**: Sufficient volatility for profitable moves
- **Max 5 positions**: Capital allocation limit

### Exit Rules:
- **RSI > 70**: Stock is overbought (sell)
- **+12% Profit Target**: Take profits
- **-8% Stop Loss**: Cut losses

### Dashboard Columns:
| Column | Description | Color Coding |
|--------|-------------|--------------|
| RSI | Current RSI value | Green < 25, Red > 70 |
| Rel Vol | Volume vs average | Green ≥ 1.0x |
| ATR% | Volatility % | Green ≥ 1% |
| P&L | Position profit/loss | Green/Red |

### Backtest Results:
- **Period**: 14 days (March 2026)
- **Trades**: 23
- **Win Rate**: 65.2%
- **Net Return**: +$192.66 (+2.66%)
- **Daily P&L**: $13.76/day
- **Annualized**: ~48%

## Tick Mode & Multi-Core Processing

The bot processes every tick from IBKR (~54 ticks/sec/stock) and evaluates signals in parallel across multiple CPU cores.

### Architecture:
```
Tick Callback (Main Thread)
├── Phase 1: Update prices (sequential)
└── Phase 2: Evaluate signals (parallel via ProcessPoolExecutor)
    └── 12 worker processes compute alpha scores simultaneously
```

### Configuration (.env):
```bash
TICK_MODE=true              # Per-tick processing (vs per-second polling)
USE_MULTIPROCESSING=true    # Enable multi-core alpha computation
PARALLEL_WORKERS=12         # Number of CPU cores to use
SIGNAL_THROTTLE_SEC=0.1     # Min time between signal checks per stock
TRADE_COOLDOWN_SEC=60       # Min time between trades per stock
```

### Benefits:
- **Faster entry**: Signals evaluated on every tick, not every 30 seconds
- **CPU efficiency**: Alpha computation distributed across 12 cores
- **Throttling**: Prevents over-trading while maintaining responsiveness

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
| **SELECTIVE_RSI** | Mean reversion: Buy oversold (RSI<25) + volume spike + ATR filter | **Active** |
| **ALPHA_ENGINE** | 6-signal confluence filter (breakout, volume, ATR, RSI, regime, sentiment) | Saved |
| **SCALP_TICK** | DEPRECATED - Not profitable with $2 commission costs | Deprecated |
| **SCALP_ML_V1** | LightGBM ML scalping (12 features, 30s prediction) | Saved |
| **BREAKOUT** | Raw price breakout detection | Saved |
| **RSI_SWING** | Buy oversold, sell overbought | Saved |
| **BOLLINGER** | Mean reversion at bands | Saved |
| **MACD** | Classic trend following | Saved |
| **DONCHIAN** | Turtle trading method | Saved |

### Switching Models
1. Go to http://localhost:8080/models
2. Click "Activate Model" on desired strategy
3. Restart the bot: `Ctrl+C` then `python multi_bot.py`

### Adding New Models
1. Add model entry to `models.json` with parameters and backtest results
2. If model needs new code, create in `src/` (e.g., `src/alpha_engine.py`)
3. Integrate into `multi_bot.py` (import, build context, apply to signals)
4. Add config to `.env` if needed
5. Update dashboard column in `src/multi_dashboard.py` if displaying new data

### SELECTIVE_RSI (Current Active Model)
Selective mean reversion strategy with multiple confirmation filters.

**Entry Logic:**
- BUY when RSI < 25 (oversold)
- AND relative volume > 1.0x average (volume confirmation)
- AND ATR > 1% (sufficient volatility)
- Max 5 concurrent positions
- Prioritize most oversold stocks first

**Exit Logic:**
- SELL when RSI > 70 (overbought)
- OR profit target +12% reached
- OR stop loss -8% hit

**Backtest Results (14 days, 71 stocks):**
- 23 trades, 65.2% win rate
- +$192.66 profit ($13.76/day)
- ~48% annualized return
- Commission: $46 total

**Parameters:**
```bash
STRATEGY_TYPE=SELECTIVE_RSI
SELECTIVE_RSI_PERIOD=14
SELECTIVE_RSI_OVERSOLD=25
SELECTIVE_RSI_OVERBOUGHT=70
SELECTIVE_VOLUME_MULT=1.0
SELECTIVE_ATR_MIN=0.01
SELECTIVE_STOP_LOSS=0.08
SELECTIVE_PROFIT_TARGET=0.12
SELECTIVE_MAX_POSITIONS=5
```

**Files:**
- `src/selective_rsi_strategy.py` - Strategy implementation
- `backtest_selective.py` - Backtest script

### Why Scalping Failed
SCALP_TICK was deprecated because transaction costs (0.25% = $2 commission + spread per trade) exceeded the strategy edge:
- Original scalp: 697 trades, 0.7% win rate, -$1,725 loss
- Even optimized swing: 37 trades, 43% win rate, only $6 profit
- **Conclusion**: Scalping with $2 commission on $1000 positions cannot overcome costs

### Alpha Engine
Generates BUY signals based on 6 weighted alpha signals:
- **Breakout** (0.35): Distance from range midpoint
- **Volume** (0.20): Relative volume confirmation
- **ATR** (0.12): Volatility momentum
- **RSI** (0.12): Oversold/overbought levels
- **Regime** (0.11): BULL/BEAR market detection
- **Sentiment** (0.10): VADER news score

**Scoring**: alpha_score >= 0.45 triggers BUY signal
**Prioritization**: BUY orders executed highest alpha first (capital efficiency)
**Hard Filters**: RSI < 70 (blocks overbought entries)
**Backtest**: 65% win rate, +1.40% return (vs 54.5% baseline)

### Scalp ML Strategy (SCALP_ML_V1)
LightGBM-based ML scalping strategy predicting 30-second forward returns.

**12 Features:**
- `return_5s`, `return_10s`, `return_30s` - Price momentum
- `orderbook_imbalance`, `weighted_imbalance` - Order flow
- `microprice_diff`, `queue_ratio`, `spread` - Microstructure
- `volume_ratio`, `trade_rate` - Volume signals
- `vwap_distance`, `volatility_10s` - Price context

**Trading Logic:**
- Entry: predicted_return > 0.04%
- Take Profit: 0.07%
- Stop Loss: 0.04%
- Max Hold: 60 seconds

**Files:**
- `src/scalp_ml_strategy.py` - Strategy class
- `src/scalp_feature_extractor.py` - Feature computation
- `train_scalp_model.py` - Model training
- `collect_tick_data.py` - Data collection

**Setup:**
1. Collect tick data: `python collect_tick_data.py` (5-10 trading days)
2. Train model: `python train_scalp_model.py`
3. Enable: Set `STRATEGY_TYPE=SCALP_ML` in .env

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
ALPHA_THRESHOLD=0.45         # Minimum score for BUY
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
# Auto-generated from stock_universe.py based on category
# Override specific symbols in SYMBOL_POSITION_OVERRIDES dict
```

**To override a symbol's position size:**
Edit `stock_universe.py` and add to `SYMBOL_POSITION_OVERRIDES`:
```python
SYMBOL_POSITION_OVERRIDES = {
    "PLTR": 10,  # Lower size for high-volatility
}
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
- **Symbol**: Stock ticker with company name
- **Category**: Sector classification
- **Event**: Days until earnings
- **Price**: Current price with change %
- **Pos**: Current position (shares held)
- **Target**: Target position size
- **Data**: Warmup status (ticks/required)
- **StopOut**: Stop loss or trailing stop status
- **Signal**: BUY/SELL/HOLD with visual bar
- **RSI**: RSI value (green < 25, red > 70)
- **Rel Vol**: Relative volume vs average (green ≥ 1.0x)
- **ATR%**: ATR as % of price (green ≥ 1%)
- **P&L**: Position profit/loss %
- **Sentiment**: News sentiment (VADER)
- **MSI Beta**: Beta vs MSCI World (URTH)

## Project Structure
```
trading-bot/
├── multi_bot.py                   # Multi-stock trading bot
├── models.json                    # Trading models/strategies config
├── collect_tick_data.py           # Tick data collection for ML training
├── train_scalp_model.py           # LightGBM model training
├── simple_backtest.py             # Strategy backtesting script
├── backtest_alpha_realistic.py    # Alpha engine backtest with portfolio sim
├── .env                           # Configuration file
├── CLAUDE.md                      # This file
├── SENTIMENT_UPGRADE.md           # VADER sentiment documentation
├── OPTIMIZATION_CHANGELOG.md      # Full changelog of optimizations
├── src/
│   ├── alpha_engine.py            # Alpha confluence filter (6 signals)
│   ├── scalp_ml_strategy.py       # LightGBM ML scalping strategy
│   ├── scalp_feature_extractor.py # 12-feature extraction for ML
│   ├── strategy.py                # Breakout/MA strategy logic
│   ├── multi_dashboard.py         # FastAPI dashboard server
│   ├── yfinance_client.py         # Yahoo Finance + VADER sentiment
│   ├── regime_detector.py         # Market regime detection (SPY)
│   ├── trading_control.py         # Master trading on/off switch
│   └── ...
├── models/                        # Trained ML models
│   └── scalp_lgbm_v1.txt          # LightGBM model (after training)
├── data/ticks/                    # Tick data CSVs (for training)
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

**Last Updated**: 2026-03-12 (Multi-core tick processing, 12 parallel workers)

---

**Status**: ✅ Ready to trade - Alpha Engine active (65% win rate, confluence filtering)
