import os
import time
import logging
from dotenv import load_dotenv
import ccxt
import schedule

from src.strategy import SimpleStrategy

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()


class TradingBot:
    def __init__(self):
        self.exchange_id = os.getenv('EXCHANGE', 'binance')
        self.symbol = os.getenv('SYMBOL', 'BTC/USDT')
        self.dry_run = os.getenv('DRY_RUN', 'true').lower() == 'true'

        # Initialize exchange
        exchange_class = getattr(ccxt, self.exchange_id)
        self.exchange = exchange_class({
            'apiKey': os.getenv('API_KEY'),
            'secret': os.getenv('API_SECRET'),
            'sandbox': self.dry_run,  # Use testnet if dry_run
        })

        self.strategy = SimpleStrategy()

        logger.info(f"Bot initialized - Exchange: {self.exchange_id}, Symbol: {self.symbol}, Dry run: {self.dry_run}")

    def fetch_price(self):
        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            return ticker['last']
        except Exception as e:
            logger.error(f"Error fetching price: {e}")
            return None

    def run_cycle(self):
        logger.info("Running trading cycle...")

        price = self.fetch_price()
        if price is None:
            return

        logger.info(f"{self.symbol} price: {price}")

        # Get signal from strategy
        signal = self.strategy.analyze(price)

        if signal == 'BUY':
            logger.info("Signal: BUY")
            if not self.dry_run:
                # Implement actual buy logic here
                pass
        elif signal == 'SELL':
            logger.info("Signal: SELL")
            if not self.dry_run:
                # Implement actual sell logic here
                pass
        else:
            logger.info("Signal: HOLD")

    def start(self):
        logger.info("Starting trading bot...")

        # Run immediately on start
        self.run_cycle()

        # Schedule to run every minute
        interval = int(os.getenv('INTERVAL_MINUTES', '5'))
        schedule.every(interval).minutes.do(self.run_cycle)

        logger.info(f"Scheduled to run every {interval} minutes")

        while True:
            schedule.run_pending()
            time.sleep(1)


if __name__ == '__main__':
    bot = TradingBot()
    bot.start()
