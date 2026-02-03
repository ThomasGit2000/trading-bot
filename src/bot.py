import os
import time
import logging
from dotenv import load_dotenv
from ib_insync import IB, Stock, MarketOrder
import schedule

from src.strategy import SimpleStrategy

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()


class TradingBot:
    def __init__(self):
        self.ib = IB()
        self.host = os.getenv('IB_HOST', '127.0.0.1')
        self.port = int(os.getenv('IB_PORT', '4002'))  # 4002 = paper trading
        self.client_id = int(os.getenv('IB_CLIENT_ID', '1'))

        self.symbol = os.getenv('SYMBOL', 'AAPL')
        self.exchange = os.getenv('EXCHANGE', 'SMART')
        self.currency = os.getenv('CURRENCY', 'USD')
        self.position_size = int(os.getenv('POSITION_SIZE', '100'))
        self.dry_run = os.getenv('DRY_RUN', 'true').lower() == 'true'

        self.contract = Stock(self.symbol, self.exchange, self.currency)
        self.strategy = SimpleStrategy()
        self.position = 0

        logger.info(f"Bot initialized - Symbol: {self.symbol}, Paper trading port: {self.port}")

    def connect(self):
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            logger.info(f"Connected to IB Gateway at {self.host}:{self.port}")

            # Qualify the contract
            self.ib.qualifyContracts(self.contract)
            logger.info(f"Contract qualified: {self.contract}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to IB: {e}")
            return False

    def disconnect(self):
        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Disconnected from IB")

    def fetch_price(self):
        try:
            ticker = self.ib.reqMktData(self.contract, '', False, False)
            self.ib.sleep(2)  # Wait for data

            price = ticker.marketPrice()
            self.ib.cancelMktData(self.contract)

            if price and price > 0:
                return price
            else:
                logger.warning("Invalid price received")
                return None
        except Exception as e:
            logger.error(f"Error fetching price: {e}")
            return None

    def get_position(self):
        positions = self.ib.positions()
        for pos in positions:
            if pos.contract.symbol == self.symbol:
                return pos.position
        return 0

    def place_order(self, action, quantity):
        if self.dry_run:
            logger.info(f"[DRY RUN] Would place {action} order for {quantity} shares of {self.symbol}")
            return None

        try:
            order = MarketOrder(action, quantity)
            trade = self.ib.placeOrder(self.contract, order)
            self.ib.sleep(1)
            logger.info(f"Order placed: {action} {quantity} {self.symbol} - Status: {trade.orderStatus.status}")
            return trade
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None

    def run_cycle(self):
        logger.info("Running trading cycle...")

        if not self.ib.isConnected():
            logger.warning("Not connected to IB, attempting reconnect...")
            if not self.connect():
                return

        price = self.fetch_price()
        if price is None:
            return

        logger.info(f"{self.symbol} price: ${price:.2f}")

        # Get current position
        self.position = self.get_position()
        logger.info(f"Current position: {self.position} shares")

        # Get signal from strategy
        signal = self.strategy.analyze(price)

        if signal == 'BUY' and self.position == 0:
            logger.info(f"Signal: BUY - Opening position")
            self.place_order('BUY', self.position_size)
        elif signal == 'SELL' and self.position > 0:
            logger.info(f"Signal: SELL - Closing position")
            self.place_order('SELL', abs(self.position))
        else:
            logger.info(f"Signal: {signal} - No action (Position: {self.position})")

    def start(self):
        logger.info("Starting trading bot...")

        if not self.connect():
            logger.error("Failed to connect. Exiting.")
            return

        # Run immediately on start
        self.run_cycle()

        # Schedule to run every X minutes
        interval = int(os.getenv('INTERVAL_MINUTES', '5'))
        schedule.every(interval).minutes.do(self.run_cycle)

        logger.info(f"Scheduled to run every {interval} minutes")

        try:
            while True:
                schedule.run_pending()
                self.ib.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            self.disconnect()


if __name__ == '__main__':
    bot = TradingBot()
    bot.start()
