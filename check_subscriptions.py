"""
Check active market data subscriptions
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

# Get all active tickers (market data subscriptions)
tickers = ib.tickers()
print(f"Total active market data subscriptions: {len(tickers)}")
print("=" * 60)

if len(tickers) > 0:
    symbols = [t.contract.symbol for t in tickers]
    # Count unique symbols
    unique_symbols = set(symbols)
    print(f"Unique symbols: {len(unique_symbols)}")
    print(f"Total tickers (including duplicates): {len(symbols)}\n")

    # Show all symbols
    print("Subscribed symbols:")
    for i, symbol in enumerate(sorted(unique_symbols), 1):
        count = symbols.count(symbol)
        dup_marker = f" (x{count} DUPLICATE!)" if count > 1 else ""
        print(f"  {i:3}. {symbol}{dup_marker}")

    # Check for duplicates
    duplicates = [sym for sym in unique_symbols if symbols.count(sym) > 1]
    if duplicates:
        print(f"\nWARNING: Found {len(duplicates)} duplicated subscriptions:")
        for sym in duplicates:
            print(f"  - {sym}: subscribed {symbols.count(sym)} times")
else:
    print("No active market data subscriptions from this client")

print(f"\n{'='*60}")
print(f"Client ID {client_id} subscriptions: {len(tickers)}")
print(f"IBKR reports total across all clients: 116")
print(f"Difference (other clients/TWS): {116 - len(tickers)}")

ib.disconnect()
