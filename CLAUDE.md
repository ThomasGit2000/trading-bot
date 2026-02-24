# Trading Bot Project

## Overview
Automated multi-stock trading bot for Interactive Brokers.
Uses **NO STOPS strategy** (MA crossover only) - proven to beat buy & hold.
Now supports **739 momentum stocks** across **41 categories**.

## Current State (Last updated: 2026-02-24)
- **Stock Universe**: 739 momentum stocks in 41 categories
- **Strategy**: NO STOPS MA(10/30) - beats buy & hold
- Live trading mode configured (port 7496 for TWS)
- Category-based stock selection
- Auto-generated position sizes

## Stock Universe Categories (41 total)

| Category | Stocks | Description |
|----------|--------|-------------|
| MEGA_CAP_TECH | 16 | Apple, Microsoft, Google, Meta, etc. |
| SEMICONDUCTORS | 22 | NVDA, AMD, AVGO, MU, etc. |
| SOFTWARE_CLOUD | 24 | CRM, NOW, SNOW, DDOG, etc. |
| CYBERSECURITY | 16 | PANW, CRWD, ZS, FTNT, etc. |
| FINTECH | 22 | V, MA, PYPL, SQ, COIN, etc. |
| BANKS_MAJOR | 24 | JPM, BAC, GS, MS, etc. |
| ASSET_MANAGERS | 22 | BLK, KKR, APO, BX, etc. |
| INSURANCE | 24 | PGR, TRV, ALL, MET, etc. |
| HEALTHCARE_PHARMA | 24 | LLY, UNH, JNJ, MRK, etc. |
| MEDICAL_DEVICES | 23 | TMO, DHR, ISRG, SYK, etc. |
| BIOTECH | 21 | MRNA, CRSP, EDIT, BEAM, etc. |
| INDUSTRIALS_DIVERSIFIED | 22 | GE, HON, CAT, DE, etc. |
| AEROSPACE_DEFENSE | 20 | RTX, LMT, NOC, BA, etc. |
| TRANSPORTATION | 20 | UNP, UPS, FDX, ODFL, etc. |
| AIRLINES | 14 | DAL, UAL, LUV, AAL, etc. |
| CONSUMER_RETAIL | 24 | AMZN, WMT, COST, HD, etc. |
| AUTO_RETAIL | 16 | ORLY, AZO, AAP, GPC, etc. |
| RESTAURANTS | 16 | MCD, SBUX, CMG, YUM, etc. |
| FOOD_BEVERAGE | 23 | KO, PEP, MDLZ, HSY, etc. |
| HOTELS_LEISURE | 21 | MAR, HLT, CCL, RCL, DKNG, etc. |
| ENERGY_OIL_GAS | 22 | XOM, CVX, COP, EOG, etc. |
| ENERGY_SERVICES | 15 | SLB, BKR, HAL, etc. |
| ENERGY_MIDSTREAM | 15 | WMB, KMI, OKE, TRGP, etc. |
| REFINING | 8 | PSX, MPC, VLO, etc. |
| UTILITIES | 30 | NEE, SO, DUK, AEP, etc. |
| REITS_DIVERSIFIED | 24 | PLD, AMT, SPG, PSA, etc. |
| MATERIALS_CHEMICALS | 23 | LIN, APD, SHW, DD, etc. |
| METALS_MINING | 22 | NEM, FCX, NUE, CLF, etc. |
| EV_AUTOMAKERS | 15 | TSLA, RIVN, LCID, NIO, etc. |
| TRADITIONAL_AUTO | 8 | GM, F, TM, RACE, etc. |
| CLEAN_ENERGY | 21 | ENPH, FSLR, PLUG, CHPT, etc. |
| CHINA_ADR | 23 | BABA, JD, PDD, NIO, etc. |
| CRYPTO_BLOCKCHAIN | 20 | COIN, MARA, RIOT, MSTR, etc. |
| AI_DATA | 14 | NVDA, PLTR, AI, SNOW, etc. |
| GAMING_ESPORTS | 14 | RBLX, EA, DKNG, TTWO, etc. |
| CANNABIS | 14 | TLRY, CGC, ACB, etc. |
| MEME_RETAIL | 13 | GME, AMC, BB, HOOD, etc. |
| TELECOM | 14 | T, VZ, TMUS, etc. |
| MEDIA_ENTERTAINMENT | 14 | DIS, NFLX, SPOT, ROKU, etc. |
| HOMEBUILDERS | 15 | DHI, LEN, NVR, PHM, etc. |
| BUILDING_MATERIALS | 15 | MLM, VMC, BLDR, etc. |

## Configuration (.env)

### Category-Based Selection (Recommended)
```
# Trade specific categories
CATEGORIES=MEGA_CAP_TECH,SEMICONDUCTORS,FINTECH,AI_DATA

# Or trade ALL 739 stocks
CATEGORIES=ALL
```

### Direct Symbol Selection
```
CATEGORIES=
SYMBOLS=TSLA,NIO,PLTR,AMD,NVDA
POSITION_SIZES={"TSLA": 5, "NIO": 200, "PLTR": 10}
```

### Position Sizes
Leave `POSITION_SIZES` empty to auto-generate based on category defaults:
- Mega cap: 5 shares
- Mid cap tech: 10-15 shares
- Volatile (crypto, meme): 50-100 shares
- Cannabis: 100 shares

## Strategy: NO STOPS MA(10/30)
Simple but effective - MA crossover without stop losses.

**Entry Signal:** Short MA (10) crosses above Long MA (30)
**Exit Signal:** Short MA (10) crosses below Long MA (30)

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
- Category grouping
- Position tracking per stock
- Buy/Sell signals with MA values
- Signal strength indicator

## Project Structure
```
trading-bot/
├── multi_bot.py            # Multi-stock trading bot
├── stock_universe.py       # 739 stocks in 41 categories (NEW)
├── momentum_symbols.py     # Flat momentum stock list
├── src/
│   ├── bot.py              # Single-stock bot (legacy)
│   ├── strategy.py         # Trading strategy logic
│   ├── multi_dashboard.py  # Scalable dashboard
│   ├── dashboard.py        # Single-stock dashboard
│   ├── dashboard_state.py  # Shared state
│   ├── yfinance_client.py  # Yahoo Finance data
│   └── ...
├── .env                    # Configuration
└── logs/                   # Log files
```

## Quick Start Examples

### Trade Top Tech + Semiconductors
```
CATEGORIES=MEGA_CAP_TECH,SEMICONDUCTORS
```

### Trade High-Risk Momentum
```
CATEGORIES=CRYPTO_BLOCKCHAIN,MEME_RETAIL,CANNABIS,EV_AUTOMAKERS
```

### Trade Defensive Sectors
```
CATEGORIES=UTILITIES,HEALTHCARE_PHARMA,FOOD_BEVERAGE,INSURANCE
```

### Trade Everything
```
CATEGORIES=ALL
```

## Risk Management
- No stop losses (by design - better performance)
- Position sizes auto-adjusted by category volatility
- Diversification across categories
- MA crossover provides natural exit points

## Repository
https://github.com/ThomasGit2000/trading-bot
