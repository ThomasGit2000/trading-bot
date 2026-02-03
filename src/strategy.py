import logging

logger = logging.getLogger(__name__)


class SimpleStrategy:
    """
    Simple example strategy - replace with your own logic.
    This is a basic moving average crossover example.
    """

    def __init__(self, short_window=10, long_window=30):
        self.short_window = short_window
        self.long_window = long_window
        self.prices = []

    def analyze(self, current_price):
        self.prices.append(current_price)

        # Keep only what we need
        if len(self.prices) > self.long_window:
            self.prices = self.prices[-self.long_window:]

        # Not enough data yet
        if len(self.prices) < self.long_window:
            logger.info(f"Collecting data: {len(self.prices)}/{self.long_window}")
            return 'HOLD'

        # Calculate moving averages
        short_ma = sum(self.prices[-self.short_window:]) / self.short_window
        long_ma = sum(self.prices) / self.long_window

        logger.info(f"Short MA: {short_ma:.2f}, Long MA: {long_ma:.2f}")

        # Generate signal
        if short_ma > long_ma * 1.01:  # Short MA 1% above long MA
            return 'BUY'
        elif short_ma < long_ma * 0.99:  # Short MA 1% below long MA
            return 'SELL'

        return 'HOLD'
