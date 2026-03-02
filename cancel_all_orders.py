"""
Cancel all pending orders
"""
import os
from dotenv import load_dotenv
from ib_insync import IB

load_dotenv()

# Connect to IB
ib = IB()
host = os.getenv('IB_HOST', '127.0.0.1')
port = int(os.getenv('IB_PORT', '7496'))
client_id = 99  # Use different client ID to avoid conflict

print(f"Connecting to IB Gateway at {host}:{port}...")
ib.connect(host, port, clientId=client_id)
print("Connected!")

# Get all open orders
open_orders = ib.openOrders()
print(f"\nFound {len(open_orders)} open orders")

if len(open_orders) > 0:
    print("\nCancelling all orders...")
    for trade in open_orders:
        print(f"  - Cancelling order {trade.order.orderId}: {trade.order.action} {trade.order.totalQuantity} {trade.contract.symbol}")
        ib.cancelOrder(trade.order)

    ib.sleep(2)  # Wait for cancellations to process
    print("\n✅ All orders cancelled!")
else:
    print("\n✅ No open orders to cancel")

ib.disconnect()
print("Disconnected from IB Gateway")
