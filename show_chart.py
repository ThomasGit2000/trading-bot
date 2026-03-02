"""Quick script to display NIO price chart"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.alpha_vantage import AlphaVantageClient

def ascii_chart(prices, times, width=60, height=15):
    """Create ASCII chart of prices"""
    if not prices:
        print("No data to display")
        return

    min_p = min(prices)
    max_p = max(prices)
    range_p = max_p - min_p or 1

    # Sample data if too many points
    step = max(1, len(prices) // width)
    sampled_prices = prices[::step][:width]
    sampled_times = times[::step][:width]

    print(f"\n{'='*70}")
    print(f"  NIO STOCK PRICE - Intraday (5min bars)")
    print(f"{'='*70}")
    print(f"  High: ${max_p:.2f}  |  Low: ${min_p:.2f}  |  Latest: ${prices[-1]:.2f}")
    print(f"{'='*70}\n")

    # Build chart
    for row in range(height, -1, -1):
        threshold = min_p + (range_p * row / height)

        # Y-axis label
        if row == height:
            label = f"${max_p:.2f}"
        elif row == height // 2:
            label = f"${(min_p + max_p) / 2:.2f}"
        elif row == 0:
            label = f"${min_p:.2f}"
        else:
            label = "       "

        line = f"{label:>7} |"

        for p in sampled_prices:
            normalized = (p - min_p) / range_p * height
            if normalized >= row:
                line += "\u2588"  # Full block
            else:
                line += " "

        print(line)

    # X-axis
    print("        +" + "-" * len(sampled_prices))

    # Time labels
    if sampled_times:
        first_time = sampled_times[0]
        last_time = sampled_times[-1]
        padding = len(sampled_prices) - len(first_time) - len(last_time)
        print(f"         {first_time}{' ' * max(0, padding)}{last_time}")

    print()

def main():
    print("\nFetching NIO price data from Alpha Vantage...")

    client = AlphaVantageClient()

    # Get intraday data
    intraday = client.get_intraday('NIO', '5min')

    if intraday:
        prices = [bar['close'] for bar in intraday]
        times = [bar['datetime'].strftime('%H:%M') for bar in intraday]
        ascii_chart(prices, times)

        # Show recent prices
        print("Recent prices:")
        for bar in intraday[-10:]:
            print(f"  {bar['datetime'].strftime('%H:%M')} - ${bar['close']:.2f}")
    else:
        print("Failed to fetch intraday data")

        # Try quote instead
        quote = client.get_quote('NIO')
        if quote:
            print(f"\nCurrent quote: ${quote['price']:.2f} ({quote['change_percent']})")

if __name__ == '__main__':
    main()
