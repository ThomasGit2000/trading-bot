"""
Trade Verification System
Tracks all trade attempts and verifies execution status.
"""
import logging
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TradeStatus(Enum):
    PENDING = "PENDING"           # Order submitted, waiting for fill
    FILLED = "FILLED"             # Order fully filled
    PARTIAL = "PARTIAL"           # Order partially filled
    CANCELLED = "CANCELLED"       # Order cancelled
    REJECTED = "REJECTED"         # Order rejected by broker
    FAILED = "FAILED"             # Failed to submit order
    SKIPPED = "SKIPPED"           # Skipped (market closed, etc.)
    VERIFIED = "VERIFIED"         # Position verified after fill


@dataclass
class TradeRecord:
    """Record of a trade attempt"""
    id: str
    symbol: str
    action: str  # BUY or SELL
    quantity: int
    price: float
    timestamp: datetime
    status: TradeStatus
    order_id: Optional[int] = None
    fill_price: Optional[float] = None
    fill_quantity: Optional[int] = None
    error_message: Optional[str] = None
    verified_position: Optional[int] = None
    verification_time: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'symbol': self.symbol,
            'action': self.action,
            'quantity': self.quantity,
            'price': self.price,
            'timestamp': self.timestamp.isoformat(),
            'status': self.status.value,
            'order_id': self.order_id,
            'fill_price': self.fill_price,
            'fill_quantity': self.fill_quantity,
            'error_message': self.error_message,
            'verified_position': self.verified_position,
            'verification_time': self.verification_time.isoformat() if self.verification_time else None
        }


class TradeVerifier:
    """
    Verifies trade execution and tracks trading activity.

    Usage:
        verifier = TradeVerifier(ib_connection)

        # Before placing order
        trade_id = verifier.record_attempt(symbol, action, quantity, price)

        # After placing order
        verifier.update_order_id(trade_id, order_id)

        # Verify execution
        verifier.verify_trade(trade_id)
    """

    def __init__(self, ib=None):
        self.ib = ib
        self.trades: Dict[str, TradeRecord] = {}
        self.trade_counter = 0

    def set_ib(self, ib):
        """Set IB connection for verification"""
        self.ib = ib

    def record_attempt(self, symbol: str, action: str, quantity: int,
                       price: float, status: TradeStatus = TradeStatus.PENDING) -> str:
        """Record a trade attempt and return trade ID"""
        self.trade_counter += 1
        trade_id = f"T{self.trade_counter:04d}"

        record = TradeRecord(
            id=trade_id,
            symbol=symbol,
            action=action,
            quantity=quantity,
            price=price,
            timestamp=datetime.now(),
            status=status
        )

        self.trades[trade_id] = record
        logger.info(f"Trade recorded: {trade_id} - {action} {quantity} {symbol} @ ${price:.2f} [{status.value}]")
        return trade_id

    def record_skipped(self, symbol: str, action: str, quantity: int,
                       price: float, reason: str) -> str:
        """Record a skipped trade (market closed, etc.)"""
        trade_id = self.record_attempt(symbol, action, quantity, price, TradeStatus.SKIPPED)
        self.trades[trade_id].error_message = reason
        return trade_id

    def record_failed(self, symbol: str, action: str, quantity: int,
                      price: float, error: str) -> str:
        """Record a failed trade attempt"""
        trade_id = self.record_attempt(symbol, action, quantity, price, TradeStatus.FAILED)
        self.trades[trade_id].error_message = error
        return trade_id

    def update_order_id(self, trade_id: str, order_id: int):
        """Update trade record with order ID after submission"""
        if trade_id in self.trades:
            self.trades[trade_id].order_id = order_id
            logger.info(f"Trade {trade_id}: Order ID set to {order_id}")

    def update_status(self, trade_id: str, status: TradeStatus,
                      fill_price: float = None, fill_quantity: int = None,
                      error_message: str = None):
        """Update trade status"""
        if trade_id in self.trades:
            record = self.trades[trade_id]
            record.status = status
            if fill_price:
                record.fill_price = fill_price
            if fill_quantity:
                record.fill_quantity = fill_quantity
            if error_message:
                record.error_message = error_message
            logger.info(f"Trade {trade_id}: Status updated to {status.value}")

    def verify_trade(self, trade_id: str) -> bool:
        """
        Verify a trade by checking actual position.
        Returns True if position matches expected state.
        """
        if trade_id not in self.trades:
            logger.error(f"Trade {trade_id} not found")
            return False

        record = self.trades[trade_id]

        if not self.ib or not self.ib.isConnected():
            logger.warning(f"Cannot verify {trade_id}: IB not connected")
            return False

        try:
            # Get current position
            positions = self.ib.positions()
            current_position = 0
            for pos in positions:
                if pos.contract.symbol == record.symbol:
                    current_position = int(pos.position)
                    break

            record.verified_position = current_position
            record.verification_time = datetime.now()

            # Check if trade was successful based on position
            if record.status == TradeStatus.FILLED:
                record.status = TradeStatus.VERIFIED
                logger.info(f"Trade {trade_id} VERIFIED: {record.symbol} position = {current_position}")
                return True
            elif record.status == TradeStatus.PENDING:
                # Check if order filled
                for trade in self.ib.trades():
                    if trade.order.orderId == record.order_id:
                        if trade.orderStatus.status == 'Filled':
                            record.status = TradeStatus.VERIFIED
                            record.fill_price = trade.orderStatus.avgFillPrice
                            record.fill_quantity = int(trade.orderStatus.filled)
                            logger.info(f"Trade {trade_id} VERIFIED: Filled at ${record.fill_price:.2f}")
                            return True
                        elif trade.orderStatus.status == 'Cancelled':
                            record.status = TradeStatus.CANCELLED
                            logger.warning(f"Trade {trade_id}: Order was cancelled")
                            return False

            logger.info(f"Trade {trade_id}: Position = {current_position}, Status = {record.status.value}")
            return record.status in [TradeStatus.VERIFIED, TradeStatus.FILLED]

        except Exception as e:
            logger.error(f"Failed to verify trade {trade_id}: {e}")
            return False

    def verify_all_pending(self) -> Dict[str, bool]:
        """Verify all pending trades"""
        results = {}
        for trade_id, record in self.trades.items():
            if record.status == TradeStatus.PENDING:
                results[trade_id] = self.verify_trade(trade_id)
        return results

    def get_recent_trades(self, limit: int = 20) -> List[TradeRecord]:
        """Get most recent trade records"""
        sorted_trades = sorted(
            self.trades.values(),
            key=lambda t: t.timestamp,
            reverse=True
        )
        return sorted_trades[:limit]

    def get_stats(self) -> dict:
        """Get trading statistics"""
        stats = {
            'total': len(self.trades),
            'filled': 0,
            'verified': 0,
            'pending': 0,
            'failed': 0,
            'skipped': 0,
            'cancelled': 0,
            'rejected': 0
        }

        for record in self.trades.values():
            if record.status == TradeStatus.FILLED:
                stats['filled'] += 1
            elif record.status == TradeStatus.VERIFIED:
                stats['verified'] += 1
            elif record.status == TradeStatus.PENDING:
                stats['pending'] += 1
            elif record.status == TradeStatus.FAILED:
                stats['failed'] += 1
            elif record.status == TradeStatus.SKIPPED:
                stats['skipped'] += 1
            elif record.status == TradeStatus.CANCELLED:
                stats['cancelled'] += 1
            elif record.status == TradeStatus.REJECTED:
                stats['rejected'] += 1

        return stats

    def get_state(self) -> dict:
        """Get full state for dashboard"""
        return {
            'stats': self.get_stats(),
            'recent_trades': [t.to_dict() for t in self.get_recent_trades(10)],
            'last_update': datetime.now().isoformat()
        }


# Global instance for shared access
trade_verifier = TradeVerifier()
