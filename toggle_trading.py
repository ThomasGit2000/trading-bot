"""
Toggle trading ON/OFF
"""
from src.trading_control import trading_control

current_state = trading_control.is_enabled()
print(f"Current state: {'ENABLED' if current_state else 'DISABLED'}")

new_state = trading_control.toggle(by="manual_script")
print(f"New state: {'ENABLED' if new_state else 'DISABLED'}")

if new_state:
    print("\nWARNING: Live trading is now ACTIVE!")
    print("The bot will execute real trades when signals are detected.")
else:
    print("\nTrading is now DISABLED.")
    print("The bot will monitor signals but skip all orders.")
