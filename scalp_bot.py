"""
Intraday Scalping Bot - High-frequency trading for NIO

Runs during market hours (9:30 AM - 4:00 PM ET).
Uses 5-minute RSI scalping strategy for quick trades.

Expected: ~2 trades/day, 80%+ win rate, small gains

Run: python scalp_bot.py
"""
import os
import sys
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.scalp_strategy import ScalpStrategy
from src.yfinance_client import YFinanceClient

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/scalp_bot.log')
    ]
)
logger = logging.getLogger(__name__)

# Configuration
SYMBOL = os.getenv('SYMBOL', 'NIO')
DRY_RUN = os.getenv('DRY_RUN', 'true').lower() == 'true'
POLL_INTERVAL = int(os.getenv('SCALP_POLL_SEC', '30'))  # Check every 30 seconds
MAX_POSITION_VALUE = float(os.getenv('SCALP_MAX_VALUE', '1000'))  # Max $1000 per trade


def is_market_hours() -> bool:
    """Check if within US market hours (9:30 AM - 4:00 PM ET)"""
    now = datetime.now()
    # Simple check - assumes local time is ET
    # For production, use pytz for proper timezone handling
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    weekday = now.weekday()

    if weekday >= 5:  # Weekend
        return False

    return market_open <= now <= market_close


def get_current_price(client: YFinanceClient) -> float:
    """Get latest price from yfinance"""
    try:
        quote = client.get_quote(SYMBOL)
        if quote and quote.get('price'):
            return quote['price']
    except Exception as e:
        logger.error(f"Error getting price: {e}")
    return 0


def warm_up_strategy(strategy: ScalpStrategy, client: YFinanceClient):
    """Load recent prices to warm up indicators"""
    logger.info("Warming up strategy with recent data...")
    try:
        # Get last 2 hours of 5-min bars
        history = client.get_history(SYMBOL, '1d', interval='5m')
        if history:
            # Use last 50 bars
            recent = history[-50:]
            for bar in recent:
                strategy.add_price(bar['close'])
            logger.info(f"Loaded {len(recent)} bars for warm-up")
            return True
    except Exception as e:
        logger.error(f"Warm-up failed: {e}")
    return False


def execute_buy(price: float, shares: int) -> bool:
    """Execute buy order (simulated or real)"""
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would BUY {shares} {SYMBOL} @ ${price:.2f}")
        return True

    try:
        # Import IB client for real trading
        from ib_insync import IB, Stock, MarketOrder

        ib = IB()
        host = os.getenv('IB_HOST', '127.0.0.1')
        port = int(os.getenv('IB_PORT', '7496'))
        client_id = int(os.getenv('IB_CLIENT_ID', '2')) + 10  # Different client ID

        ib.connect(host, port, clientId=client_id)
        contract = Stock(SYMBOL, 'SMART', 'USD')
        ib.qualifyContracts(contract)

        order = MarketOrder('BUY', shares)
        trade = ib.placeOrder(contract, order)

        # Wait for fill
        for _ in range(10):
            ib.sleep(1)
            if trade.isDone():
                break

        ib.disconnect()

        if trade.orderStatus.status == 'Filled':
            logger.info(f"BUY FILLED: {shares} {SYMBOL} @ ${trade.orderStatus.avgFillPrice:.2f}")
            return True
        else:
            logger.warning(f"Order status: {trade.orderStatus.status}")
            return False

    except Exception as e:
        logger.error(f"Buy order failed: {e}")
        return False


def execute_sell(price: float, shares: int) -> bool:
    """Execute sell order (simulated or real)"""
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would SELL {shares} {SYMBOL} @ ${price:.2f}")
        return True

    try:
        from ib_insync import IB, Stock, MarketOrder

        ib = IB()
        host = os.getenv('IB_HOST', '127.0.0.1')
        port = int(os.getenv('IB_PORT', '7496'))
        client_id = int(os.getenv('IB_CLIENT_ID', '2')) + 10

        ib.connect(host, port, clientId=client_id)
        contract = Stock(SYMBOL, 'SMART', 'USD')
        ib.qualifyContracts(contract)

        order = MarketOrder('SELL', shares)
        trade = ib.placeOrder(contract, order)

        for _ in range(10):
            ib.sleep(1)
            if trade.isDone():
                break

        ib.disconnect()

        if trade.orderStatus.status == 'Filled':
            logger.info(f"SELL FILLED: {shares} {SYMBOL} @ ${trade.orderStatus.avgFillPrice:.2f}")
            return True
        else:
            logger.warning(f"Order status: {trade.orderStatus.status}")
            return False

    except Exception as e:
        logger.error(f"Sell order failed: {e}")
        return False


def run_scalp_bot():
    """Main bot loop"""
    print("="*60)
    print("  INTRADAY SCALP BOT")
    print("="*60)
    print(f"  Symbol: {SYMBOL}")
    print(f"  Mode: {'DRY RUN' if DRY_RUN else 'LIVE TRADING'}")
    print(f"  Poll Interval: {POLL_INTERVAL}s")
    print(f"  Max Position: ${MAX_POSITION_VALUE}")
    print("="*60)

    if not DRY_RUN:
        print("\n  *** LIVE TRADING MODE - REAL MONEY AT RISK ***\n")
        confirm = input("  Type 'CONFIRM' to proceed: ")
        if confirm != 'CONFIRM':
            print("  Aborted.")
            return

    client = YFinanceClient()
    strategy = ScalpStrategy()

    # Warm up
    if not warm_up_strategy(strategy, client):
        logger.error("Failed to warm up strategy")
        return

    logger.info(f"Strategy: {strategy.name}")
    logger.info("Bot started. Press Ctrl+C to stop.")

    capital = MAX_POSITION_VALUE
    last_price_time = None

    try:
        while True:
            # Check market hours
            if not is_market_hours():
                logger.info("Outside market hours. Waiting...")
                time.sleep(60)
                continue

            # Get current price
            price = get_current_price(client)
            if price <= 0:
                logger.warning("Could not get price, retrying...")
                time.sleep(10)
                continue

            # Add price to strategy
            strategy.add_price(price)
            rsi = strategy.calculate_rsi()

            # Get signal
            signal = strategy.get_signal()
            status = strategy.get_status()

            # Log status
            logger.info(
                f"Price: ${price:.2f} | RSI: {rsi:.1f} | "
                f"Position: {status['position']} | Signal: {signal}"
            )

            # Execute trades
            if signal == 'BUY' and strategy.position == 0:
                shares = min(strategy.max_shares, int(capital / price))
                if shares > 0:
                    if execute_buy(price, shares):
                        cost = shares * price
                        capital -= cost
                        strategy.enter_position(price, shares)

            elif signal.startswith('SELL') and strategy.position > 0:
                shares = strategy.position
                if execute_sell(price, shares):
                    proceeds = shares * price
                    strategy.exit_position(price, signal.replace('SELL_', ''))
                    capital += proceeds

            # Show stats periodically
            if status['total_trades'] > 0:
                logger.info(
                    f"Stats: {status['total_trades']} trades | "
                    f"Win Rate: {status['win_rate']:.0f}% | "
                    f"W/L: {status['wins']}/{status['losses']}"
                )

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        logger.info("\nStopping bot...")

        # Close any open position
        if strategy.position > 0:
            price = get_current_price(client)
            if price > 0:
                logger.info(f"Closing open position at ${price:.2f}")
                if execute_sell(price, strategy.position):
                    strategy.exit_position(price, 'CLOSE')

        # Final stats
        status = strategy.get_status()
        print("\n" + "="*60)
        print("  FINAL STATS")
        print("="*60)
        print(f"  Total Trades: {status['total_trades']}")
        print(f"  Win Rate: {status['win_rate']:.0f}%")
        print(f"  Wins/Losses: {status['wins']}/{status['losses']}")
        print("="*60)


if __name__ == '__main__':
    # Ensure logs directory exists
    Path('logs').mkdir(exist_ok=True)

    run_scalp_bot()
