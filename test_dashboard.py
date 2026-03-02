"""Test dashboard standalone"""
import threading
import time
from src.multi_dashboard import run_multi_dashboard
from src.dashboard_state import bot_state

# Set some test data
bot_state.update(
    multi_stock=True,
    stocks=[
        {
            'symbol': 'TSLA',
            'price': 411.82,
            'bid': 411.80,
            'ask': 411.85,
            'position': 0,
            'position_size': 5,
            'short_ma': 410.50,
            'long_ma': 408.20,
            'signal': 'HOLD',
            'prices_collected': 15,
            'data_source': 'TEST',
            'in_position': False
        },
        {
            'symbol': 'NIO',
            'price': 5.07,
            'bid': 5.06,
            'ask': 5.08,
            'position': 41,
            'position_size': 200,
            'short_ma': 5.05,
            'long_ma': 5.02,
            'signal': 'HOLD',
            'prices_collected': 20,
            'data_source': 'TEST',
            'in_position': True
        }
    ],
    is_connected=True,
    dry_run=False
)

print("Starting dashboard on http://localhost:8080")
print("Press Ctrl+C to stop")
run_multi_dashboard(host='127.0.0.1', port=8080)
