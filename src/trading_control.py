"""
Master Trading Control
Controls whether live trading is enabled or disabled.
"""
import os
import json
import logging
from datetime import datetime
from threading import Lock

logger = logging.getLogger(__name__)

STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'trading_control.json')


class TradingControl:
    """
    Master switch for live trading.
    Trading only occurs when:
    1. Market is open
    2. Trading is enabled (this control)
    3. Not in dry run mode
    """

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
        self._enabled = False  # Default to disabled for safety
        self._last_changed = None
        self._changed_by = None
        self._load_state()

    def _load_state(self):
        """Load state from file (silent - no logging to avoid spam)"""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                    self._enabled = data.get('enabled', False)
                    self._last_changed = data.get('last_changed')
                    self._changed_by = data.get('changed_by')
        except Exception as e:
            logger.error(f"Failed to load trading control state: {e}")
            self._enabled = False  # Default to safe state

    def _save_state(self):
        """Save state to file"""
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with open(STATE_FILE, 'w') as f:
                json.dump({
                    'enabled': self._enabled,
                    'last_changed': self._last_changed,
                    'changed_by': self._changed_by
                }, f)
        except Exception as e:
            logger.error(f"Failed to save trading control state: {e}")

    def is_enabled(self) -> bool:
        """Check if trading is enabled (reloads from file for cross-process sync)"""
        self._load_state()  # Reload to pick up changes from dashboard
        return self._enabled

    def enable(self, by: str = "dashboard"):
        """Enable live trading"""
        with self._lock:
            self._enabled = True
            self._last_changed = datetime.now().isoformat()
            self._changed_by = by
            self._save_state()
            logger.warning(f"TRADING ENABLED by {by}")

    def disable(self, by: str = "dashboard"):
        """Disable live trading"""
        with self._lock:
            self._enabled = False
            self._last_changed = datetime.now().isoformat()
            self._changed_by = by
            self._save_state()
            logger.warning(f"TRADING DISABLED by {by}")

    def toggle(self, by: str = "dashboard") -> bool:
        """Toggle trading state, returns new state"""
        with self._lock:
            self._enabled = not self._enabled
            self._last_changed = datetime.now().isoformat()
            self._changed_by = by
            self._save_state()
            state = "ENABLED" if self._enabled else "DISABLED"
            logger.warning(f"TRADING {state} by {by}")
            return self._enabled

    def get_state(self) -> dict:
        """Get full state for dashboard (reloads from file for cross-process sync)"""
        self._load_state()  # Reload to pick up changes from dashboard
        return {
            'enabled': self._enabled,
            'last_changed': self._last_changed,
            'changed_by': self._changed_by
        }


# Global singleton instance
trading_control = TradingControl()
