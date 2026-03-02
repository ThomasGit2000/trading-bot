"""
Sell 5 shares of MU to free up capital
"""
import os
from dotenv import load_dotenv
from ib_insync import IB, Stock, LimitOrder

load_dotenv()

ib = IB()
ib.connect('127.0.0.1', 7496, clientId=99)

# Get MU contract
mu = Stock('MU', 'SMART', 'USD')
ib.qualifyContracts(mu)

# Get current price
ticker = ib.reqMktData(mu, '', False, False)
ib.sleep(1)

price = ticker.last if ticker.last and ticker.last > 0 else ticker.close
sell_price = round(price * 0.999, 2)  # Slightly below market

print(f"MU current price: ${price:.2f}")
print(f"Selling 5 shares at limit: ${sell_price:.2f}")
print(f"Will free up: ~${price * 5:.2f}")

# Place sell order
order = LimitOrder('SELL', 5, sell_price)
trade = ib.placeOrder(mu, order)

print(f"\nOrder placed: {trade.order.orderId}")
print("Check your IBKR account for confirmation")

ib.disconnect()
