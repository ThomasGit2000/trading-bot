"""
Calculate position sizes based on 10% max rule
No single position should exceed 10% of total account value
"""
import os
from dotenv import load_dotenv
from ib_insync import IB
import json

load_dotenv()

# Connect to IB
ib = IB()
ib.connect('127.0.0.1', 7496, clientId=98)

# Get account summary
account_summary = ib.accountSummary()
total_liquidity = 0
available_cash = 0

for item in account_summary:
    if item.tag == 'NetLiquidation':
        total_liquidity = float(item.value)
    elif item.tag == 'AvailableFunds':
        available_cash = float(item.value)

print("=" * 80)
print("ACCOUNT SUMMARY")
print("=" * 80)
print(f"Total Account Value (Net Liquidation): ${total_liquidity:,.2f}")
print(f"Available Cash: ${available_cash:,.2f}")

# Calculate max position size (10% of total)
max_position_value = total_liquidity * 0.10

print(f"\nMAX POSITION SIZE (10% rule): ${max_position_value:,.2f}")
print("=" * 80)

# Get current positions
positions = ib.positions()
print("\nCURRENT POSITIONS:")
for pos in positions:
    if pos.position != 0:
        value = pos.position * pos.avgCost
        pct = (value / total_liquidity) * 100
        status = "⚠️ OVER LIMIT" if pct > 10 else "✅ OK"
        print(f"  {pos.contract.symbol:6} | {pos.position:>6.0f} shares | ${value:>10,.2f} | {pct:>5.1f}% {status}")

# Get symbols and current prices
symbols_str = os.getenv('SYMBOLS', '')
symbols = [s.strip() for s in symbols_str.split(',') if s.strip()]

print("\n" + "=" * 80)
print("RECOMMENDED POSITION SIZES (10% MAX RULE)")
print("=" * 80)

position_sizes = {}

print(f"\n{'Symbol':<8} {'Price':<12} {'Max Shares':<12} {'Position Value':<15}")
print("-" * 80)

for symbol in symbols[:20]:  # Sample first 20
    try:
        from ib_insync import Stock
        contract = Stock(symbol, 'SMART', 'USD')
        ib.qualifyContracts(contract)

        # Get current price
        ticker = ib.reqMktData(contract, '', False, False)
        ib.sleep(0.5)

        price = ticker.last if ticker.last and ticker.last > 0 else ticker.close
        if not price or price <= 0:
            continue

        # Calculate max shares for 10% position
        max_shares = int(max_position_value / price)

        # Don't allow 0 shares - minimum 1
        if max_shares < 1:
            max_shares = 1

        position_value = max_shares * price

        position_sizes[symbol] = max_shares

        print(f"{symbol:<8} ${price:<11.2f} {max_shares:<12} ${position_value:<14,.2f}")

        ib.cancelMktData(contract)

    except Exception as e:
        print(f"{symbol:<8} Error: {e}")

ib.disconnect()

# Save to JSON
output_file = 'position_sizes_10pct.json'
with open(output_file, 'w') as f:
    json.dump(position_sizes, f, indent=2)

print("\n" + "=" * 80)
print(f"Position sizes saved to: {output_file}")
print("\nTo apply these to your bot:")
print("1. Copy the JSON content")
print("2. Update POSITION_SIZES in your .env file")
print("=" * 80)
