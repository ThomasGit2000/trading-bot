"""Yahoo Finance client for historical data"""
import logging
from datetime import datetime, timedelta

import yfinance as yf

logger = logging.getLogger(__name__)


class YFinanceClient:
    """Yahoo Finance client for free historical data"""

    def __init__(self):
        logger.info("YFinance client initialized")

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> list:
        """Get historical prices

        Args:
            symbol: Stock symbol (e.g., 'NIO')
            period: Valid periods: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
            interval: Valid intervals: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo
                      Note: Intraday data limited to last 60 days

        Returns:
            List of dicts with: date, open, high, low, close, volume
        """
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)

            if df.empty:
                logger.warning(f"No data returned for {symbol}")
                return []

            prices = []
            for date, row in df.iterrows():
                prices.append({
                    'date': date.to_pydatetime().replace(tzinfo=None),
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': int(row['Volume'])
                })

            logger.info(f"YFinance: {len(prices)} bars for {symbol} ({period})")
            return prices

        except Exception as e:
            logger.error(f"YFinance error: {e}")
            return []

    def get_quote(self, symbol: str) -> dict:
        """Get current quote"""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            return {
                'symbol': symbol,
                'price': info.get('currentPrice') or info.get('regularMarketPrice', 0),
                'open': info.get('open') or info.get('regularMarketOpen', 0),
                'high': info.get('dayHigh') or info.get('regularMarketDayHigh', 0),
                'low': info.get('dayLow') or info.get('regularMarketDayLow', 0),
                'volume': info.get('volume') or info.get('regularMarketVolume', 0),
                'previous_close': info.get('previousClose', 0),
                'market_cap': info.get('marketCap', 0),
                'name': info.get('shortName', symbol),
                'timestamp': datetime.now()
            }
        except Exception as e:
            logger.error(f"YFinance quote error: {e}")
            return None

    def get_info(self, symbol: str) -> dict:
        """Get company info"""
        try:
            ticker = yf.Ticker(symbol)
            return ticker.info
        except Exception as e:
            logger.error(f"YFinance info error: {e}")
            return {}

    def get_upcoming_events(self, symbol: str) -> dict:
        """Get upcoming events (earnings, dividends, etc.)"""
        try:
            ticker = yf.Ticker(symbol)
            events = {}

            # Get earnings date
            try:
                calendar = ticker.calendar
                if calendar is not None and not calendar.empty:
                    if 'Earnings Date' in calendar.index:
                        earnings_dates = calendar.loc['Earnings Date']
                        if hasattr(earnings_dates, 'iloc') and len(earnings_dates) > 0:
                            next_earnings = earnings_dates.iloc[0]
                            if hasattr(next_earnings, 'strftime'):
                                events['earnings_date'] = next_earnings.strftime('%Y-%m-%d')
                            else:
                                events['earnings_date'] = str(next_earnings)
            except Exception as e:
                logger.debug(f"No calendar data for {symbol}: {e}")

            # Get ex-dividend date from info
            try:
                info = ticker.info
                if info.get('exDividendDate'):
                    from datetime import datetime
                    ex_div = datetime.fromtimestamp(info['exDividendDate'])
                    if ex_div > datetime.now():
                        events['ex_dividend_date'] = ex_div.strftime('%Y-%m-%d')
                        events['dividend_rate'] = info.get('dividendRate', 0)
            except Exception as e:
                logger.debug(f"No dividend data for {symbol}: {e}")

            return events
        except Exception as e:
            logger.error(f"YFinance events error for {symbol}: {e}")
            return {}

    def get_news(self, symbol: str, limit: int = 3) -> list:
        """Get latest news with basic sentiment analysis"""
        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news

            if not news:
                return []

            # Simple sentiment keywords
            positive_words = ['surge', 'jump', 'gain', 'rise', 'soar', 'rally', 'beat', 'profit',
                            'growth', 'upgrade', 'buy', 'bullish', 'record', 'strong', 'boost']
            negative_words = ['fall', 'drop', 'crash', 'decline', 'loss', 'miss', 'cut', 'sell',
                            'downgrade', 'bearish', 'weak', 'warning', 'concern', 'risk', 'lawsuit']

            results = []
            for article in news[:limit]:
                title = article.get('title', '')
                title_lower = title.lower()

                # Simple sentiment scoring
                pos_count = sum(1 for w in positive_words if w in title_lower)
                neg_count = sum(1 for w in negative_words if w in title_lower)

                if pos_count > neg_count:
                    sentiment = 'positive'
                elif neg_count > pos_count:
                    sentiment = 'negative'
                else:
                    sentiment = 'neutral'

                # Get publish time
                pub_time = article.get('providerPublishTime', 0)
                if pub_time:
                    from datetime import datetime
                    pub_date = datetime.fromtimestamp(pub_time)
                    time_ago = self._time_ago(pub_date)
                else:
                    time_ago = ''

                results.append({
                    'title': title[:80] + ('...' if len(title) > 80 else ''),
                    'source': article.get('publisher', 'Unknown'),
                    'sentiment': sentiment,
                    'time_ago': time_ago,
                    'link': article.get('link', '')
                })

            return results
        except Exception as e:
            logger.error(f"YFinance news error for {symbol}: {e}")
            return []

    def _time_ago(self, dt) -> str:
        """Convert datetime to relative time string"""
        from datetime import datetime
        now = datetime.now()
        diff = now - dt

        if diff.days > 0:
            return f"{diff.days}d ago"
        elif diff.seconds >= 3600:
            return f"{diff.seconds // 3600}h ago"
        elif diff.seconds >= 60:
            return f"{diff.seconds // 60}m ago"
        else:
            return "just now"


def show_chart(symbol: str = 'NIO', period: str = '1y'):
    """Display ASCII chart of stock price history"""
    client = YFinanceClient()
    history = client.get_history(symbol, period)

    if not history:
        print(f"No data for {symbol}")
        return

    prices = [bar['close'] for bar in history]
    dates = [bar['date'] for bar in history]

    min_p = min(prices)
    max_p = max(prices)
    range_p = max_p - min_p or 1
    height = 15
    width = 70

    # Sample if too many points
    step = max(1, len(prices) // width)
    sampled = prices[::step][:width]

    print(f"\n{'='*74}")
    print(f"  {symbol} STOCK PRICE - {period.upper()} HISTORY")
    print(f"{'='*74}")
    print(f"  High: ${max_p:.2f}  |  Low: ${min_p:.2f}  |  Latest: ${prices[-1]:.2f}")
    print(f"  Period: {dates[0].strftime('%Y-%m-%d')} to {dates[-1].strftime('%Y-%m-%d')}")
    print(f"{'='*74}\n")

    for row in range(height, -1, -1):
        threshold = row / height

        if row == height:
            label = f"${max_p:.2f}"
        elif row == height // 2:
            label = f"${(min_p + max_p) / 2:.2f}"
        elif row == 0:
            label = f"${min_p:.2f}"
        else:
            label = "       "

        line = f"{label:>7} |"

        for p in sampled:
            normalized = (p - min_p) / range_p
            if normalized >= threshold:
                line += "\u2588"
            else:
                line += " "

        print(line)

    print("        +" + "-" * len(sampled))
    print(f"         {dates[0].strftime('%b %Y')}{' ' * (len(sampled) - 16)}{dates[-1].strftime('%b %Y')}")
    print()

    # Stats
    change = prices[-1] - prices[0]
    change_pct = (change / prices[0]) * 100
    print(f"  Change: ${change:+.2f} ({change_pct:+.1f}%)")
    print()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    show_chart('NIO', '1y')
