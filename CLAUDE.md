# Trading Bot Project

## Overview
Building an automated trading system with Interactive Brokers integration.

## Current State
- Basic project structure created
- Currently using `ccxt` (crypto exchanges) - needs refactoring to use `ib_insync` for Interactive Brokers
- Simple moving average crossover strategy implemented
- Docker setup ready

## Tech Stack
- Python
- Docker
- Interactive Brokers API (planned: `ib_insync`)

## Repository
https://github.com/ThomasGit2000/trading-bot

## Next Steps
1. Refactor `bot.py` to use `ib_insync` instead of `ccxt`
2. Update `requirements.txt` with IB dependencies
3. Implement proper IB connection handling
4. Add real trading strategies
5. Deploy to Raspberry Pi 5 (see DEPLOYMENT.md)

## Deployment
Target: Raspberry Pi 5
See `DEPLOYMENT.md` for full instructions.

## Project Structure
```
trading-bot/
├── src/
│   ├── bot.py        # Main trading bot
│   └── strategy.py   # Trading strategies
├── data/             # Data storage
├── logs/             # Log files
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```
