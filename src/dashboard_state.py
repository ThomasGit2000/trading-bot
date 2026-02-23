from dataclasses import dataclass, field
from threading import Lock
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class BotState:
    """Thread-safe state container for dashboard - supports single and multi-stock"""
    # Price data (single stock - backward compatible)
    last_price: float = 0.0
    last_bid: float = 0.0
    last_ask: float = 0.0

    # Position data (single stock)
    position: int = 0
    position_size: int = 0
    symbol: str = ""

    # Strategy data (single stock)
    prices: List[float] = field(default_factory=list)
    short_window: int = 10
    long_window: int = 30
    short_ma: float = 0.0
    long_ma: float = 0.0
    current_signal: str = "HOLD"

    # Historical data (single stock)
    historical_prices: List[float] = field(default_factory=list)
    historical_times: List[str] = field(default_factory=list)
    rsi_values: List[float] = field(default_factory=list)

    # Status
    is_connected: bool = False
    dry_run: bool = True
    data_mode: str = "UNKNOWN"
    last_update: Optional[datetime] = None
    last_price_update: Optional[datetime] = None
    is_live_streaming: bool = False

    # Multi-stock support
    multi_stock: bool = False
    stocks: List[Dict[str, Any]] = field(default_factory=list)

    # Lock for thread safety
    _lock: Lock = field(default_factory=Lock, repr=False)

    def update(self, **kwargs):
        """Thread-safe update of multiple fields"""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self, key) and not key.startswith('_'):
                    setattr(self, key, value)
            self.last_update = datetime.now()

    def get_state(self) -> dict:
        """Get current state for multi-stock dashboard"""
        with self._lock:
            if self.multi_stock:
                return {
                    "multi_stock": True,
                    "stocks": self.stocks,
                    "is_connected": self.is_connected,
                    "dry_run": self.dry_run,
                    "last_update": self.last_update.isoformat() if self.last_update else None
                }
            else:
                return self.to_dict()

    def to_dict(self) -> dict:
        """Thread-safe export for JSON serialization (single stock)"""
        with self._lock:
            return {
                "multi_stock": False,
                "price": {
                    "current": self.last_price,
                    "bid": self.last_bid,
                    "ask": self.last_ask,
                    "spread": round(self.last_ask - self.last_bid, 4) if self.last_bid > 0 else 0
                },
                "position": {
                    "current": self.position,
                    "size": self.position_size,
                    "symbol": self.symbol
                },
                "strategy": {
                    "short_ma": round(self.short_ma, 4),
                    "long_ma": round(self.long_ma, 4),
                    "short_window": self.short_window,
                    "long_window": self.long_window,
                    "signal": self.current_signal,
                    "prices_collected": len(self.prices)
                },
                "status": {
                    "connected": self.is_connected,
                    "dry_run": self.dry_run,
                    "data_mode": self.data_mode,
                    "last_update": self.last_update.isoformat() if self.last_update else None,
                    "is_live_streaming": self.is_live_streaming,
                    "price_age_seconds": (datetime.now() - self.last_price_update).total_seconds() if self.last_price_update else 9999
                },
                "chart_data": {
                    "prices": list(self.prices[-60:]),
                    "historical_prices": list(self.historical_prices),
                    "historical_times": list(self.historical_times),
                    "rsi": list(self.rsi_values)
                },
                # Multi-stock compatibility
                "stocks": [{
                    "symbol": self.symbol,
                    "price": self.last_price,
                    "position": self.position,
                    "position_size": self.position_size,
                    "signal": self.current_signal,
                    "short_ma": self.short_ma,
                    "long_ma": self.long_ma,
                    "prices_collected": len(self.prices),
                    "data_source": self.data_mode
                }] if self.symbol else [],
                "dry_run": self.dry_run,
                "is_connected": self.is_connected
            }


# Global singleton instance
bot_state = BotState()
