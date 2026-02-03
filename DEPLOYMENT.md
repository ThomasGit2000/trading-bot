# Raspberry Pi 5 Deployment Guide

## Prerequisites
- Raspberry Pi 5 with Raspberry Pi OS (64-bit)
- SSH access configured
- Stable internet connection
- (Recommended) UPS for power backup

## Option 1: Docker Deployment (Recommended)

### 1. Install Docker on Pi
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
# Log out and back in for group changes to take effect
```

### 2. Clone and Run
```bash
git clone https://github.com/ThomasGit2000/trading-bot.git
cd trading-bot
cp .env.example .env
# Edit .env with your settings
nano .env
```

### 3. Build and Start
```bash
docker-compose up -d --build
```

### 4. View Logs
```bash
docker-compose logs -f
```

### 5. Stop
```bash
docker-compose down
```

## Option 2: Direct Python Installation

### 1. Install Python and Dependencies
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

### 2. Clone Repository
```bash
git clone https://github.com/ThomasGit2000/trading-bot.git
cd trading-bot
```

### 3. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure Environment
```bash
cp .env.example .env
nano .env
```

### 5. Run the Bot
```bash
python -m src.bot
```

## Running as a System Service (Auto-start on boot)

### Create Service File
```bash
sudo nano /etc/systemd/system/trading-bot.service
```

### Add this content:
```ini
[Unit]
Description=Trading Bot
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/trading-bot
Environment=PATH=/home/pi/trading-bot/venv/bin
ExecStart=/home/pi/trading-bot/venv/bin/python -m src.bot
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Enable and Start
```bash
sudo systemctl daemon-reload
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
```

### Check Status
```bash
sudo systemctl status trading-bot
journalctl -u trading-bot -f
```

## Interactive Brokers Setup

### IB Gateway (Headless)
For automated trading, use IB Gateway instead of TWS:

1. Download IB Gateway from: https://www.interactivebrokers.com/en/trading/ibgateway-stable.php
2. Install on Pi or a separate machine
3. Configure for paper trading first
4. Update .env with IB Gateway connection details

### Connection Settings
```
IB_HOST=127.0.0.1  # or IP of machine running IB Gateway
IB_PORT=4002       # Paper trading port (4001 for live)
IB_CLIENT_ID=1
```

## Monitoring

### View Logs
```bash
# Docker
docker-compose logs -f

# Systemd service
journalctl -u trading-bot -f

# Log file
tail -f logs/bot.log
```

## Updating the Bot

```bash
cd trading-bot
git pull
# If using Docker:
docker-compose down && docker-compose up -d --build
# If using systemd:
sudo systemctl restart trading-bot
```
