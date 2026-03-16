"""
Activity Logger for Trading Bot
Tracks trading activity and system events for dashboard display.
"""
import os
import json
import logging
from datetime import datetime
from collections import deque
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)

# Store logs in memory with max size (also persist to file)
MAX_TRADE_LOGS = 100
MAX_SYSTEM_LOGS = 100

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
TRADE_LOG_FILE = os.path.join(LOG_DIR, 'trade_activity.json')
SYSTEM_LOG_FILE = os.path.join(LOG_DIR, 'system_activity.json')


class ActivityLogger:
    """Logs trading and system activity for dashboard display."""

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.trade_logs = deque(maxlen=MAX_TRADE_LOGS)
        self.system_logs = deque(maxlen=MAX_SYSTEM_LOGS)

        os.makedirs(LOG_DIR, exist_ok=True)
        self._load_logs()

    def _load_logs(self):
        """Load existing logs from files."""
        try:
            if os.path.exists(TRADE_LOG_FILE):
                with open(TRADE_LOG_FILE, 'r') as f:
                    data = json.load(f)
                    for entry in data[-MAX_TRADE_LOGS:]:
                        self.trade_logs.append(entry)
        except Exception as e:
            logger.error(f"Failed to load trade logs: {e}")

        try:
            if os.path.exists(SYSTEM_LOG_FILE):
                with open(SYSTEM_LOG_FILE, 'r') as f:
                    data = json.load(f)
                    for entry in data[-MAX_SYSTEM_LOGS:]:
                        self.system_logs.append(entry)
        except Exception as e:
            logger.error(f"Failed to load system logs: {e}")

    def _save_trade_logs(self):
        """Save trade logs to file."""
        try:
            with open(TRADE_LOG_FILE, 'w') as f:
                json.dump(list(self.trade_logs), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save trade logs: {e}")

    def _save_system_logs(self):
        """Save system logs to file."""
        try:
            with open(SYSTEM_LOG_FILE, 'w') as f:
                json.dump(list(self.system_logs), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save system logs: {e}")

    # ===== TRADE ACTIVITY =====

    def log_order_placed(self, symbol: str, action: str, quantity: int, price: float, order_id: Optional[int] = None):
        """Log when an order is placed."""
        with self._lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'type': 'ORDER_PLACED',
                'symbol': symbol,
                'action': action,
                'quantity': quantity,
                'price': price,
                'order_id': order_id,
                'status': 'pending'
            }
            self.trade_logs.append(entry)
            self._save_trade_logs()
            logger.info(f"[TRADE] Order placed: {action} {quantity} {symbol} @ ${price:.2f}")

    def log_order_filled(self, symbol: str, action: str, quantity: int, fill_price: float, order_id: Optional[int] = None):
        """Log when an order is filled."""
        with self._lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'type': 'ORDER_FILLED',
                'symbol': symbol,
                'action': action,
                'quantity': quantity,
                'price': fill_price,
                'order_id': order_id,
                'status': 'filled'
            }
            self.trade_logs.append(entry)
            self._save_trade_logs()
            logger.info(f"[TRADE] Order filled: {action} {quantity} {symbol} @ ${fill_price:.2f}")

    def log_order_cancelled(self, symbol: str, action: str, quantity: int, reason: str = "", order_id: Optional[int] = None):
        """Log when an order is cancelled."""
        with self._lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'type': 'ORDER_CANCELLED',
                'symbol': symbol,
                'action': action,
                'quantity': quantity,
                'reason': reason,
                'order_id': order_id,
                'status': 'cancelled'
            }
            self.trade_logs.append(entry)
            self._save_trade_logs()
            logger.info(f"[TRADE] Order cancelled: {action} {quantity} {symbol} - {reason}")

    def log_order_rejected(self, symbol: str, action: str, quantity: int, reason: str, order_id: Optional[int] = None):
        """Log when an order is rejected."""
        with self._lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'type': 'ORDER_REJECTED',
                'symbol': symbol,
                'action': action,
                'quantity': quantity,
                'reason': reason,
                'order_id': order_id,
                'status': 'rejected'
            }
            self.trade_logs.append(entry)
            self._save_trade_logs()
            logger.warning(f"[TRADE] Order rejected: {action} {quantity} {symbol} - {reason}")

    def log_signal(self, symbol: str, signal: str, price: float, alpha_score: Optional[float] = None):
        """Log when a trading signal is generated."""
        with self._lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'type': 'SIGNAL',
                'symbol': symbol,
                'signal': signal,
                'price': price,
                'alpha_score': alpha_score,
                'status': 'signal'
            }
            self.trade_logs.append(entry)
            self._save_trade_logs()

    # ===== SYSTEM ACTIVITY =====

    def log_bot_start(self):
        """Log bot startup."""
        with self._lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'type': 'BOT_START',
                'message': 'Trading bot started',
                'level': 'info'
            }
            self.system_logs.append(entry)
            self._save_system_logs()

    def log_bot_stop(self):
        """Log bot shutdown."""
        with self._lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'type': 'BOT_STOP',
                'message': 'Trading bot stopped',
                'level': 'info'
            }
            self.system_logs.append(entry)
            self._save_system_logs()

    def log_connection(self, status: str, details: str = ""):
        """Log IBKR connection events."""
        with self._lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'type': 'CONNECTION',
                'message': f'IBKR {status}',
                'details': details,
                'level': 'info' if status == 'connected' else 'warning'
            }
            self.system_logs.append(entry)
            self._save_system_logs()

    def log_reconnect(self, success: bool, reason: str = ""):
        """Log reconnection attempts."""
        with self._lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'type': 'RECONNECT',
                'message': f'Reconnect {"successful" if success else "failed"}',
                'details': reason,
                'level': 'info' if success else 'error'
            }
            self.system_logs.append(entry)
            self._save_system_logs()

    def log_dashboard_restart(self, reason: str = "crashed"):
        """Log dashboard restart."""
        with self._lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'type': 'DASHBOARD_RESTART',
                'message': f'Dashboard restarted ({reason})',
                'level': 'warning'
            }
            self.system_logs.append(entry)
            self._save_system_logs()

    def log_trading_toggle(self, enabled: bool, by: str):
        """Log trading enabled/disabled."""
        with self._lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'type': 'TRADING_TOGGLE',
                'message': f'Trading {"ENABLED" if enabled else "DISABLED"} by {by}',
                'level': 'warning'
            }
            self.system_logs.append(entry)
            self._save_system_logs()

    def log_error(self, component: str, error: str):
        """Log system errors."""
        with self._lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'type': 'ERROR',
                'message': f'{component}: {error}',
                'level': 'error'
            }
            self.system_logs.append(entry)
            self._save_system_logs()

    def log_health_issue(self, component: str, issue: str):
        """Log health check issues."""
        with self._lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'type': 'HEALTH',
                'message': f'{component}: {issue}',
                'level': 'warning'
            }
            self.system_logs.append(entry)
            self._save_system_logs()

    def log_circuit_breaker(self, reason: str):
        """Log circuit breaker triggers."""
        with self._lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'type': 'CIRCUIT_BREAKER',
                'message': f'Circuit breaker triggered: {reason}',
                'level': 'error'
            }
            self.system_logs.append(entry)
            self._save_system_logs()

    # ===== GETTERS =====

    def get_trade_logs(self, limit: int = 50) -> list:
        """Get recent trade logs."""
        with self._lock:
            logs = list(self.trade_logs)
            return logs[-limit:][::-1]  # Most recent first

    def get_system_logs(self, limit: int = 50) -> list:
        """Get recent system logs."""
        with self._lock:
            logs = list(self.system_logs)
            return logs[-limit:][::-1]  # Most recent first

    def get_all_logs(self, limit: int = 50) -> dict:
        """Get both trade and system logs."""
        return {
            'trade_logs': self.get_trade_logs(limit),
            'system_logs': self.get_system_logs(limit)
        }


# Global singleton instance
activity_logger = ActivityLogger()
