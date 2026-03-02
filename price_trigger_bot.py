"""
Price Trigger Bot - Monitors price and places order when target is reached
"""
from ib_insync import IB, Stock, LimitOrder
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
SYMBOL = 'NIO'
TARGET_PRICE = 5.10
ACTION = 'SELL'
QUANTITY = 9
CHECK_INTERVAL = 10  # seconds between price checks

def get_current_price(ib, contract):
    """Fetch latest price from historical data"""
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr='1 D',
        barSizeSetting='5 mins',
        whatToShow='TRADES',
        useRTH=True,
        formatDate=1
    )
    if bars:
        return bars[-1].close
    return None

def run_trigger_bot():
    ib = IB()
    ib.connect('127.0.0.1', 7496, clientId=4)

    contract = Stock(SYMBOL, 'SMART', 'USD')
    ib.qualifyContracts(contract)

    logger.info(f"=== PRICE TRIGGER BOT ===")
    logger.info(f"Monitoring {SYMBOL}")
    logger.info(f"Action: {ACTION} {QUANTITY} shares when price >= ${TARGET_PRICE}")
    logger.info(f"Checking every {CHECK_INTERVAL} seconds")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 30)

    order_placed = False

    try:
        while not order_placed:
            price = get_current_price(ib, contract)

            if price:
                status = "WAITING" if price < TARGET_PRICE else "TRIGGERED!"
                logger.info(f"Price: ${price:.2f} | Target: ${TARGET_PRICE} | {status}")

                if price >= TARGET_PRICE:
                    logger.info(f">>> TARGET REACHED! Price ${price:.2f} >= ${TARGET_PRICE}")

                    # Place limit order at current price
                    order = LimitOrder(ACTION, QUANTITY, round(price, 2))
                    trade = ib.placeOrder(contract, order)

                    logger.info(f">>> Order placed: {ACTION} {QUANTITY} {SYMBOL} @ ${price:.2f}")

                    # Wait for fill
                    for _ in range(30):
                        ib.sleep(1)
                        stat = trade.orderStatus.status
                        if stat == 'Filled':
                            logger.info(f">>> FILLED at ${trade.orderStatus.avgFillPrice:.2f}")
                            order_placed = True
                            break
                        elif stat in ['Submitted', 'PreSubmitted']:
                            continue

                    if not order_placed:
                        logger.info(f"Order status: {trade.orderStatus.status}")
                        order_placed = True
            else:
                logger.info("Could not get price data")

            if not order_placed:
                ib.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        ib.disconnect()
        logger.info("Disconnected")

if __name__ == '__main__':
    run_trigger_bot()
