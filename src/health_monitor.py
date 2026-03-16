"""
Health Monitor for Trading Bot
Monitors critical components and provides auto-recovery.
"""
import os
import time
import logging
import threading
import requests
from datetime import datetime, timedelta
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Monitors bot health and handles recovery."""

    def __init__(self, check_interval: int = 30):
        self.check_interval = check_interval
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # Component status
        self.components = {
            'ibkr_connection': {'healthy': False, 'last_check': None, 'failures': 0},
            'dashboard': {'healthy': False, 'last_check': None, 'failures': 0},
            'price_feed': {'healthy': False, 'last_check': None, 'failures': 0},
            'tick_collection': {'healthy': False, 'last_check': None, 'failures': 0},
        }

        # Callbacks for recovery actions
        self.recovery_callbacks: dict[str, Callable] = {}

        # Metrics
        self.last_price_update = None
        self.last_tick_write = None
        self.prices_collected = 0
        self.ticks_written = 0
        self.errors_count = 0
        self.start_time = datetime.now()

        # Alert thresholds
        self.max_failures_before_alert = 3
        self.price_stale_seconds = 30
        self.dashboard_url = "http://localhost:8080"

    def set_recovery_callback(self, component: str, callback: Callable):
        """Set a recovery callback for a component."""
        self.recovery_callbacks[component] = callback

    def record_price_update(self, count: int = 1):
        """Record that prices were updated."""
        self.last_price_update = datetime.now()
        self.prices_collected += count

    def record_tick_write(self, count: int = 1):
        """Record that ticks were written."""
        self.last_tick_write = datetime.now()
        self.ticks_written += count

    def record_error(self, component: str, error: str):
        """Record an error for a component."""
        self.errors_count += 1
        self.components[component]['failures'] += 1
        logger.error(f"Health Monitor - {component} error: {error}")

        # Write to error log
        try:
            with open('logs/errors.log', 'a') as f:
                f.write(f"{datetime.now().isoformat()} | {component} | {error}\n")
        except Exception:
            pass

    def check_ibkr_connection(self, ib) -> bool:
        """Check if IBKR connection is healthy."""
        try:
            if ib and ib.isConnected():
                self.components['ibkr_connection']['healthy'] = True
                self.components['ibkr_connection']['failures'] = 0
                return True
        except Exception as e:
            self.record_error('ibkr_connection', str(e))

        self.components['ibkr_connection']['healthy'] = False
        return False

    def check_dashboard(self) -> bool:
        """Check if dashboard is responding."""
        try:
            response = requests.get(f"{self.dashboard_url}/health", timeout=5)
            if response.status_code == 200:
                self.components['dashboard']['healthy'] = True
                self.components['dashboard']['failures'] = 0
                return True
        except requests.exceptions.ConnectionError:
            pass  # Dashboard not reachable
        except Exception as e:
            self.record_error('dashboard', str(e))

        self.components['dashboard']['healthy'] = False
        return False

    def check_price_feed(self) -> bool:
        """Check if price feed is current."""
        if self.last_price_update:
            age = (datetime.now() - self.last_price_update).total_seconds()
            if age < self.price_stale_seconds:
                self.components['price_feed']['healthy'] = True
                self.components['price_feed']['failures'] = 0
                return True

        self.components['price_feed']['healthy'] = False
        return False

    def check_tick_collection(self, enabled: bool) -> bool:
        """Check if tick collection is working."""
        if not enabled:
            self.components['tick_collection']['healthy'] = True
            return True

        if self.last_tick_write:
            age = (datetime.now() - self.last_tick_write).total_seconds()
            if age < 60:  # Ticks should be written at least every minute
                self.components['tick_collection']['healthy'] = True
                self.components['tick_collection']['failures'] = 0
                return True

        self.components['tick_collection']['healthy'] = False
        return False

    def get_status(self) -> dict:
        """Get current health status."""
        uptime = datetime.now() - self.start_time
        return {
            'timestamp': datetime.now().isoformat(),
            'uptime_seconds': int(uptime.total_seconds()),
            'uptime_human': str(timedelta(seconds=int(uptime.total_seconds()))),
            'components': {
                name: {
                    'healthy': info['healthy'],
                    'failures': info['failures'],
                    'last_check': info['last_check'].isoformat() if info['last_check'] else None
                }
                for name, info in self.components.items()
            },
            'metrics': {
                'prices_collected': self.prices_collected,
                'ticks_written': self.ticks_written,
                'errors_count': self.errors_count,
                'last_price_update': self.last_price_update.isoformat() if self.last_price_update else None,
                'last_tick_write': self.last_tick_write.isoformat() if self.last_tick_write else None,
            },
            'overall_healthy': all(c['healthy'] for c in self.components.values())
        }

    def run_checks(self, ib=None, tick_collection_enabled: bool = False):
        """Run all health checks."""
        now = datetime.now()

        # Update last check times
        for component in self.components:
            self.components[component]['last_check'] = now

        # Run checks
        if ib:
            self.check_ibkr_connection(ib)
        self.check_dashboard()
        self.check_price_feed()
        self.check_tick_collection(tick_collection_enabled)

        # Log status
        unhealthy = [name for name, info in self.components.items() if not info['healthy']]
        if unhealthy:
            logger.warning(f"Health Check - Unhealthy components: {', '.join(unhealthy)}")

            # Attempt recovery for components with too many failures
            for component in unhealthy:
                if self.components[component]['failures'] >= self.max_failures_before_alert:
                    if component in self.recovery_callbacks:
                        logger.info(f"Attempting recovery for {component}...")
                        try:
                            self.recovery_callbacks[component]()
                            self.components[component]['failures'] = 0
                        except Exception as e:
                            logger.error(f"Recovery failed for {component}: {e}")
        else:
            logger.debug("Health Check - All components healthy")

        return self.get_status()

    def start_background_monitoring(self, ib=None, tick_collection_enabled: bool = False):
        """Start background health monitoring thread."""
        if self.running:
            return

        self.running = True

        def monitor_loop():
            while self.running:
                try:
                    self.run_checks(ib, tick_collection_enabled)
                except Exception as e:
                    logger.error(f"Health monitor error: {e}")
                time.sleep(self.check_interval)

        self.thread = threading.Thread(target=monitor_loop, daemon=True)
        self.thread.start()
        logger.info(f"Health monitor started (checking every {self.check_interval}s)")

    def stop(self):
        """Stop background monitoring."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Health monitor stopped")


# Global instance
health_monitor = HealthMonitor()
