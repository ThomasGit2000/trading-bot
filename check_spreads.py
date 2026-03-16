"""Check bid-ask spreads for all stocks"""
import json
import os
import time

# Read from bot_state.json with retries
state_file = os.path.join(os.path.dirname(__file__), 'data', 'bot_state.json')

for attempt in range(3):
    try:
        with open(state_file, 'r', encoding='utf-8') as f:
            content = f.read()
        data = json.loads(content)
        break
    except (json.JSONDecodeError, IOError):
        time.sleep(0.1)
        continue
else:
    print("Could not read bot_state.json")
    exit(1)

stocks = data.get('stocks', [])
spreads = []

for s in stocks:
    bid = s.get('bid', 0) or 0
    ask = s.get('ask', 0) or 0
    price = s.get('price', 0) or 0
    if bid > 0 and ask > 0 and price > 0:
        spread_pct = (ask - bid) / price * 100
        spreads.append((s['symbol'], spread_pct, bid, ask, price))

# Sort by spread (tightest first for easy reading)
spreads.sort(key=lambda x: x[1])

print("ALL STOCKS BY SPREAD (tightest to widest):")
print("=" * 60)
for i, (sym, spread, bid, ask, price) in enumerate(spreads):
    flag = " << WIDE" if spread > 0.15 else ""
    print(f"{i+1:>2}. {sym:<8} {spread:>6.3f}% @ ${price:>8.2f}{flag}")

# Recommendations
wide = [s[0] for s in spreads if s[1] > 0.15]
tight = [s[0] for s in spreads if s[1] < 0.05]
print()
print(f"REMOVE (spread > 0.15%): {', '.join(wide)}")
print(f"BEST FOR SCALPING (spread < 0.05%): {', '.join(tight)}")
