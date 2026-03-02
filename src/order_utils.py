"""
Order Utilities - Reliable order placement with confirmation
"""
from ib_insync import IB, Stock, LimitOrder, MarketOrder
import logging
from typing import Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class OrderConfirmation:
    """Handles order placement with double-check confirmation"""

    def __init__(self, ib: IB):
        self.ib = ib

    def get_position(self, symbol: str) -> float:
        """Get current position for a symbol"""
        positions = self.ib.positions()
        for pos in positions:
            if pos.contract.symbol == symbol:
                return float(pos.position)
        return 0.0

    def place_and_confirm(
        self,
        symbol: str,
        action: str,  # 'BUY' or 'SELL'
        quantity: int,
        price: Optional[float] = None,  # None for market order
        timeout: int = 60
    ) -> Tuple[bool, str, dict]:
        """
        Place order and confirm execution.

        Returns:
            (success: bool, message: str, details: dict)
        """
        # Get position BEFORE order
        position_before = self.get_position(symbol)
        logger.info(f"Position before: {position_before} shares")

        # Create contract
        contract = Stock(symbol, 'SMART', 'USD')
        self.ib.qualifyContracts(contract)

        # Create order
        if price:
            order = LimitOrder(action, quantity, price)
            order_type = f"LIMIT @ ${price}"
        else:
            order = MarketOrder(action, quantity)
            order_type = "MARKET"

        # Place order
        logger.info(f"Placing order: {action} {quantity} {symbol} {order_type}")
        trade = self.ib.placeOrder(contract, order)

        # Wait for fill
        fill_price = 0.0
        filled_qty = 0.0
        status = "Unknown"

        for i in range(timeout):
            self.ib.sleep(1)
            status = trade.orderStatus.status

            if status == 'Filled':
                fill_price = trade.orderStatus.avgFillPrice
                filled_qty = trade.orderStatus.filled
                logger.info(f"Order FILLED: {filled_qty} @ ${fill_price:.4f}")
                break
            elif status == 'Cancelled':
                logger.warning(f"Order CANCELLED")
                break
            elif status in ['Submitted', 'PreSubmitted']:
                if i % 10 == 0:  # Log every 10 seconds
                    logger.info(f"Waiting... Status: {status}")

        # CONFIRMATION CHECK: Verify position changed
        self.ib.sleep(2)  # Wait for position update
        position_after = self.get_position(symbol)
        logger.info(f"Position after: {position_after} shares")

        expected_change = quantity if action == 'BUY' else -quantity
        actual_change = position_after - position_before

        # Build result
        details = {
            'symbol': symbol,
            'action': action,
            'quantity': quantity,
            'order_type': order_type,
            'status': status,
            'fill_price': fill_price,
            'filled_qty': filled_qty,
            'position_before': position_before,
            'position_after': position_after,
            'position_change': actual_change,
            'expected_change': expected_change,
            'timestamp': datetime.now().isoformat()
        }

        # Verify execution
        if status == 'Filled':
            if abs(actual_change - expected_change) < 0.01:  # Allow small float diff
                message = f"CONFIRMED: {action} {filled_qty} {symbol} @ ${fill_price:.2f}"
                logger.info(f"✓ {message}")
                logger.info(f"✓ Position verified: {position_before} -> {position_after}")
                return True, message, details
            else:
                message = f"WARNING: Order filled but position mismatch! Expected change: {expected_change}, Actual: {actual_change}"
                logger.warning(message)
                return False, message, details
        else:
            message = f"Order not filled. Status: {status}"
            logger.warning(message)
            return False, message, details


def execute_order(
    symbol: str,
    action: str,
    quantity: int,
    price: Optional[float] = None,
    client_id: int = 5
) -> Tuple[bool, str, dict]:
    """
    Standalone function to execute and confirm an order.

    Example:
        success, msg, details = execute_order('NIO', 'BUY', 10, price=5.00)
    """
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7496, clientId=client_id)
        ib.sleep(2)

        confirmer = OrderConfirmation(ib)
        return confirmer.place_and_confirm(symbol, action, quantity, price)

    except Exception as e:
        return False, f"Error: {str(e)}", {}
    finally:
        if ib.isConnected():
            ib.disconnect()


# Command line usage
if __name__ == '__main__':
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(message)s'
    )

    if len(sys.argv) < 4:
        print("Usage: python order_utils.py <ACTION> <QUANTITY> <SYMBOL> [PRICE]")
        print("Example: python order_utils.py BUY 10 NIO 5.00")
        print("Example: python order_utils.py SELL 5 NIO  (market order)")
        sys.exit(1)

    action = sys.argv[1].upper()
    quantity = int(sys.argv[2])
    symbol = sys.argv[3].upper()
    price = float(sys.argv[4]) if len(sys.argv) > 4 else None

    print(f"\n{'='*50}")
    print(f"ORDER: {action} {quantity} {symbol}" + (f" @ ${price}" if price else " (MARKET)"))
    print(f"{'='*50}\n")

    success, message, details = execute_order(symbol, action, quantity, price)

    print(f"\n{'='*50}")
    print(f"RESULT: {'SUCCESS' if success else 'FAILED'}")
    print(f"Message: {message}")
    print(f"{'='*50}")

    if details:
        print(f"\nDetails:")
        for k, v in details.items():
            print(f"  {k}: {v}")
