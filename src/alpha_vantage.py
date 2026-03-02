import os
import logging
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class AlphaVantageClient:
    """Alpha Vantage API client for market data"""

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('ALPHA_VANTAGE_API_KEY')
        if not self.api_key:
            raise ValueError("Alpha Vantage API key not found. Set ALPHA_VANTAGE_API_KEY in .env")
        self._cache = {}
        self._cache_ttl = 60  # Cache for 60 seconds

    def _request(self, params: dict) -> dict:
        """Make API request with error handling"""
        params['apikey'] = self.api_key
        try:
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Check for API errors
            if 'Error Message' in data:
                logger.error(f"Alpha Vantage error: {data['Error Message']}")
                return None
            if 'Note' in data:
                logger.warning(f"Alpha Vantage rate limit: {data['Note']}")
                return None

            return data
        except requests.RequestException as e:
            logger.error(f"Alpha Vantage request failed: {e}")
            return None

    def get_quote(self, symbol: str) -> dict:
        """Get real-time quote for a symbol

        Returns:
            dict with keys: price, open, high, low, volume, change, change_percent
        """
        cache_key = f"quote_{symbol}"
        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if datetime.now() - cached_time < timedelta(seconds=self._cache_ttl):
                return cached_data

        data = self._request({
            'function': 'GLOBAL_QUOTE',
            'symbol': symbol
        })

        if not data or 'Global Quote' not in data:
            return None

        quote = data['Global Quote']
        result = {
            'symbol': quote.get('01. symbol'),
            'price': float(quote.get('05. price', 0)),
            'open': float(quote.get('02. open', 0)),
            'high': float(quote.get('03. high', 0)),
            'low': float(quote.get('04. low', 0)),
            'volume': int(quote.get('06. volume', 0)),
            'previous_close': float(quote.get('08. previous close', 0)),
            'change': float(quote.get('09. change', 0)),
            'change_percent': quote.get('10. change percent', '0%'),
            'timestamp': datetime.now()
        }

        self._cache[cache_key] = (datetime.now(), result)
        logger.info(f"Alpha Vantage quote for {symbol}: ${result['price']:.2f} ({result['change_percent']})")
        return result

    def get_intraday(self, symbol: str, interval: str = '5min') -> list:
        """Get intraday price data

        Args:
            symbol: Stock symbol
            interval: 1min, 5min, 15min, 30min, 60min

        Returns:
            List of dicts with: datetime, open, high, low, close, volume
        """
        data = self._request({
            'function': 'TIME_SERIES_INTRADAY',
            'symbol': symbol,
            'interval': interval,
            'outputsize': 'compact'  # Last 100 data points
        })

        if not data:
            return []

        time_series_key = f'Time Series ({interval})'
        if time_series_key not in data:
            logger.error(f"No intraday data found for {symbol}")
            return []

        prices = []
        for timestamp, values in data[time_series_key].items():
            prices.append({
                'datetime': datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S'),
                'open': float(values['1. open']),
                'high': float(values['2. high']),
                'low': float(values['3. low']),
                'close': float(values['4. close']),
                'volume': int(values['5. volume'])
            })

        # Sort by datetime (oldest first)
        prices.sort(key=lambda x: x['datetime'])
        logger.info(f"Alpha Vantage intraday: {len(prices)} bars for {symbol}")
        return prices

    def get_rsi(self, symbol: str, interval: str = 'daily', period: int = 14) -> list:
        """Get RSI indicator values

        Returns:
            List of dicts with: datetime, rsi
        """
        data = self._request({
            'function': 'RSI',
            'symbol': symbol,
            'interval': interval,
            'time_period': period,
            'series_type': 'close'
        })

        if not data or 'Technical Analysis: RSI' not in data:
            return []

        rsi_values = []
        for timestamp, values in data['Technical Analysis: RSI'].items():
            rsi_values.append({
                'datetime': datetime.strptime(timestamp, '%Y-%m-%d'),
                'rsi': float(values['RSI'])
            })

        rsi_values.sort(key=lambda x: x['datetime'])
        logger.info(f"Alpha Vantage RSI: {len(rsi_values)} values for {symbol}")
        return rsi_values

    def get_sma(self, symbol: str, interval: str = 'daily', period: int = 20) -> list:
        """Get Simple Moving Average values

        Returns:
            List of dicts with: datetime, sma
        """
        data = self._request({
            'function': 'SMA',
            'symbol': symbol,
            'interval': interval,
            'time_period': period,
            'series_type': 'close'
        })

        if not data or 'Technical Analysis: SMA' not in data:
            return []

        sma_values = []
        for timestamp, values in data['Technical Analysis: SMA'].items():
            sma_values.append({
                'datetime': datetime.strptime(timestamp, '%Y-%m-%d'),
                'sma': float(values['SMA'])
            })

        sma_values.sort(key=lambda x: x['datetime'])
        return sma_values

    def get_company_overview(self, symbol: str) -> dict:
        """Get fundamental data for a company"""
        data = self._request({
            'function': 'OVERVIEW',
            'symbol': symbol
        })

        if not data or 'Symbol' not in data:
            return None

        return {
            'symbol': data.get('Symbol'),
            'name': data.get('Name'),
            'sector': data.get('Sector'),
            'industry': data.get('Industry'),
            'market_cap': data.get('MarketCapitalization'),
            'pe_ratio': data.get('PERatio'),
            'eps': data.get('EPS'),
            '52_week_high': data.get('52WeekHigh'),
            '52_week_low': data.get('52WeekLow'),
            'dividend_yield': data.get('DividendYield'),
            'description': data.get('Description')
        }


# Convenience function for quick price checks
def get_price(symbol: str) -> float:
    """Quick helper to get current price"""
    client = AlphaVantageClient()
    quote = client.get_quote(symbol)
    return quote['price'] if quote else None


if __name__ == '__main__':
    # Test the client
    logging.basicConfig(level=logging.INFO)

    client = AlphaVantageClient()

    print("\n=== Testing Alpha Vantage API ===\n")

    # Test quote
    quote = client.get_quote('NIO')
    if quote:
        print(f"NIO Quote: ${quote['price']:.2f} ({quote['change_percent']})")
        print(f"  Open: ${quote['open']:.2f}, High: ${quote['high']:.2f}, Low: ${quote['low']:.2f}")
        print(f"  Volume: {quote['volume']:,}")

    # Test intraday
    print("\nFetching intraday data...")
    intraday = client.get_intraday('NIO', '5min')
    if intraday:
        latest = intraday[-1]
        print(f"Latest bar: {latest['datetime']} - Close: ${latest['close']:.2f}")
