# Trading Bot Project

## Overview
Building an automated trading system with Interactive Brokers integration.
Target deployment: Raspberry Pi 5 for 24/7 operation.

## Current State (Last updated: 2025-02-03)
- Project structure complete
- Refactored to use `ib_insync` for Interactive Brokers
- Configured for paper trading (port 4002)
- Simple moving average crossover strategy implemented
- Docker setup ready
- Deployment guide created for Raspberry Pi 5

## Tech Stack
- Python 3
- ib_insync (Interactive Brokers API)
- Docker
- pandas, schedule

## Repository
https://github.com/ThomasGit2000/trading-bot

## Next Steps
1. Set up IBKR paper trading account
2. Install IB Gateway or TWS
3. Test bot connection with paper trading
4. Improve trading strategy
5. Deploy to Raspberry Pi 5

## To Continue
1. Download IB Gateway: https://www.interactivebrokers.com/en/trading/ibgateway-stable.php
2. Login with paper trading credentials
3. Enable API connections (port 4002)
4. Run: `cp .env.example .env && python -m src.bot`

## Project Structure
```
trading-bot/
├── src/
│   ├── bot.py          # Main bot (IB connection, order management)
│   └── strategy.py     # MA crossover strategy
├── data/               # Data storage
├── logs/               # Log files
├── DEPLOYMENT.md       # Raspberry Pi 5 deployment guide
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example        # IB connection settings
```

## Key Files
- `src/bot.py` - TradingBot class with IB Gateway connection
- `src/strategy.py` - SimpleStrategy with moving average crossover
- `.env.example` - Configuration template (IB_HOST, IB_PORT, SYMBOL, etc.)
- `DEPLOYMENT.md` - Full Raspberry Pi 5 deployment instructions
