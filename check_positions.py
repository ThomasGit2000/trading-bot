"""
Check current positions
"""
import os
from dotenv import load_dotenv
from ib_insync import IB

load_dotenv()

# Connect to IB
ib = IB()
host = os.getenv('IB_HOST', '127.0.0.1')
port = int(os.getenv('IB_PORT', '7496'))
client_id = 99

print(f"Connecting to IB Gateway at {host}:{port}...")
ib.connect(host, port, clientId=client_id)
print("Connected!\n")

# Get all positions
positions = ib.positions()
print(f"Current Positions: {len(positions)}")
print("=" * 60)

if len(positions) > 0:
    for pos in positions:
        if pos.position != 0:  # Only show non-zero positions
            print(f"{pos.contract.symbol:8} | Shares: {pos.position:>8.0f} | Avg Cost: ${pos.avgCost:>8.2f}")
else:
    print("No open positions")

ib.disconnect()
