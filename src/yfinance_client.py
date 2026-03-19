"""Yahoo Finance client for historical data with caching"""
import logging
import time
from datetime import datetime, timedelta
from threading import Lock

import yfinance as yf
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)

# Initialize VADER sentiment analyzer (shared across instances)
_sentiment_analyzer = None

def get_sentiment_analyzer():
    """Lazy-load sentiment analyzer"""
    global _sentiment_analyzer
    if _sentiment_analyzer is None:
        _sentiment_analyzer = SentimentIntensityAnalyzer()
    return _sentiment_analyzer


class YFinanceClient:
    """Yahoo Finance client with caching and throttling to avoid rate limits"""

    # Class-level cache shared across instances
    _cache = {}
    _cache_lock = Lock()

    # Rate limiting
    _last_request_time = 0
    _rate_limit_lock = Lock()
    MIN_REQUEST_INTERVAL = 0.5  # Minimum 500ms between requests

    # Rate limit backoff
    _rate_limited_until = 0

    # Cache TTLs in seconds
    CACHE_TTL_QUOTE = 60          # 1 minute for quotes
    CACHE_TTL_INFO = 300          # 5 minutes for company info
    CACHE_TTL_HISTORY = 300       # 5 minutes for history
    CACHE_TTL_NEWS = 600          # 10 minutes for news
    CACHE_TTL_EVENTS = 3600       # 1 hour for events

    def __init__(self):
        logger.info("YFinance client initialized (with caching and throttling)")

    def _throttle(self):
        """Ensure minimum interval between requests"""
        with self._rate_limit_lock:
            # Check if we're in rate limit backoff
            if time.time() < YFinanceClient._rate_limited_until:
                return False  # Still rate limited

            elapsed = time.time() - YFinanceClient._last_request_time
            if elapsed < self.MIN_REQUEST_INTERVAL:
                time.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
            YFinanceClient._last_request_time = time.time()
            return True

    def _handle_rate_limit(self):
        """Set backoff period when rate limited"""
        # Back off for 60 seconds when rate limited
        YFinanceClient._rate_limited_until = time.time() + 60
        logger.warning("YFinance rate limit hit - backing off for 60 seconds")

    def _get_cache(self, key: str):
        """Get cached value if not expired"""
        with self._cache_lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if time.time() < expiry:
                    return value
                del self._cache[key]
        return None

    def _set_cache(self, key: str, value, ttl: int):
        """Set cache with TTL"""
        with self._cache_lock:
            self._cache[key] = (value, time.time() + ttl)

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> list:
        """Get historical prices with caching

        Args:
            symbol: Stock symbol (e.g., 'NIO')
            period: Valid periods: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
            interval: Valid intervals: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo
                      Note: Intraday data limited to last 60 days

        Returns:
            List of dicts with: date, open, high, low, close, volume
        """
        cache_key = f"history:{symbol}:{period}:{interval}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        if not self._throttle():
            return []  # Rate limited, return empty

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
            self._set_cache(cache_key, prices, self.CACHE_TTL_HISTORY)
            return prices

        except Exception as e:
            if 'RateLimit' in str(type(e).__name__) or 'rate' in str(e).lower():
                self._handle_rate_limit()
            else:
                logger.error(f"YFinance error: {e}")
            return []

    def get_quote(self, symbol: str) -> dict:
        """Get current quote with caching"""
        cache_key = f"quote:{symbol}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        if not self._throttle():
            return None  # Rate limited

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            result = {
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
            self._set_cache(cache_key, result, self.CACHE_TTL_QUOTE)
            return result
        except Exception as e:
            if 'RateLimit' in str(type(e).__name__) or 'rate' in str(e).lower():
                self._handle_rate_limit()
            else:
                logger.error(f"YFinance quote error: {e}")
            return None

    def get_info(self, symbol: str) -> dict:
        """Get company info with caching"""
        cache_key = f"info:{symbol}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        if not self._throttle():
            return {}  # Rate limited

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            self._set_cache(cache_key, info, self.CACHE_TTL_INFO)
            return info
        except Exception as e:
            if 'RateLimit' in str(type(e).__name__) or 'rate' in str(e).lower():
                self._handle_rate_limit()
            else:
                logger.error(f"YFinance info error: {e}")
            return {}

    def get_upcoming_events(self, symbol: str) -> dict:
        """Get upcoming events with caching (earnings, dividends, etc.)"""
        cache_key = f"events:{symbol}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        if not self._throttle():
            return {}  # Rate limited

        try:
            ticker = yf.Ticker(symbol)
            events = {}

            # Get earnings date - handle both old and new yfinance formats
            try:
                calendar = ticker.calendar
                if calendar is not None:
                    # New yfinance format: dict with 'Earnings Date' as list
                    if isinstance(calendar, dict):
                        earnings_dates = calendar.get('Earnings Date', [])
                        if earnings_dates and len(earnings_dates) > 0:
                            next_earnings = earnings_dates[0]
                            if hasattr(next_earnings, 'strftime'):
                                events['earnings_date'] = next_earnings.strftime('%Y-%m-%d')
                            else:
                                events['earnings_date'] = str(next_earnings)[:10]
                    # Old format: DataFrame
                    elif hasattr(calendar, 'empty') and not calendar.empty:
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
                # Also check for dividendDate
                elif info.get('dividendDate'):
                    from datetime import datetime
                    div_date = datetime.fromtimestamp(info['dividendDate'])
                    if div_date > datetime.now():
                        events['ex_dividend_date'] = div_date.strftime('%Y-%m-%d')
                        events['dividend_rate'] = info.get('dividendRate', 0)
            except Exception as e:
                logger.debug(f"No dividend data for {symbol}: {e}")

            self._set_cache(cache_key, events, self.CACHE_TTL_EVENTS)
            return events
        except Exception as e:
            if 'RateLimit' in str(type(e).__name__) or 'rate' in str(e).lower():
                self._handle_rate_limit()
            else:
                logger.error(f"YFinance events error for {symbol}: {e}")
            return {}

    def get_news(self, symbol: str, limit: int = 3) -> list:
        """Get latest news with VADER sentiment analysis and caching"""
        cache_key = f"news:{symbol}:{limit}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        if not self._throttle():
            return []  # Rate limited

        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news

            if not news:
                return []

            # Get VADER sentiment analyzer
            analyzer = get_sentiment_analyzer()

            results = []
            for article in news[:limit]:
                # Handle new yfinance format (nested under 'content')
                content = article.get('content', article)

                title = content.get('title', '')
                if not title:
                    continue

                # Use VADER for sentiment analysis
                # VADER returns scores: neg, neu, pos, compound (-1 to +1)
                sentiment_scores = analyzer.polarity_scores(title)
                compound = sentiment_scores['compound']

                # Classify based on compound score
                # Compound > 0.05: positive, < -0.05: negative, else neutral
                if compound >= 0.05:
                    sentiment = 'positive'
                    sentiment_score = compound  # 0.05 to 1.0
                elif compound <= -0.05:
                    sentiment = 'negative'
                    sentiment_score = compound  # -1.0 to -0.05
                else:
                    sentiment = 'neutral'
                    sentiment_score = compound  # -0.05 to 0.05

                # Get publish time (new format uses pubDate string)
                pub_time_str = content.get('pubDate', '')
                time_ago = ''
                if pub_time_str:
                    try:
                        from datetime import datetime
                        pub_date = datetime.fromisoformat(pub_time_str.replace('Z', '+00:00'))
                        pub_date = pub_date.replace(tzinfo=None)
                        time_ago = self._time_ago(pub_date)
                    except:
                        pass

                # Get source from provider
                provider = content.get('provider', {})
                source = provider.get('displayName', 'Unknown') if isinstance(provider, dict) else 'Unknown'

                # Get link from canonicalUrl
                canonical = content.get('canonicalUrl', {})
                link = canonical.get('url', '') if isinstance(canonical, dict) else ''

                results.append({
                    'title': title[:80] + ('...' if len(title) > 80 else ''),
                    'source': source,
                    'sentiment': sentiment,
                    'sentiment_score': round(sentiment_score, 2),  # Add numeric score
                    'time_ago': time_ago,
                    'link': link
                })

            self._set_cache(cache_key, results, self.CACHE_TTL_NEWS)
            return results
        except Exception as e:
            if 'RateLimit' in str(type(e).__name__) or 'rate' in str(e).lower():
                self._handle_rate_limit()
            else:
                logger.error(f"YFinance news error for {symbol}: {e}")
            return []

    def get_analyst_ratings(self, symbol: str) -> dict:
        """Get analyst recommendations (Buy/Hold/Sell counts)"""
        cache_key = f"analyst:{symbol}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        if not self._throttle():
            return {}  # Rate limited

        try:
            ticker = yf.Ticker(symbol)

            # Try to get recommendations summary
            # yfinance provides: strongBuy, buy, hold, sell, strongSell
            info = ticker.info
            if info:
                result = {
                    'buy': (info.get('recommendationKey', '') in ['buy', 'strong_buy']) and 1 or 0,
                    'hold': 0,
                    'sell': 0
                }

                # Try to get detailed analyst counts from recommendations
                try:
                    recs = ticker.recommendations
                    if recs is not None and len(recs) > 0:
                        # Get most recent recommendation summary
                        latest = recs.iloc[-1] if hasattr(recs, 'iloc') else None
                        if latest is not None:
                            result = {
                                'buy': int(latest.get('strongBuy', 0) or 0) + int(latest.get('buy', 0) or 0),
                                'hold': int(latest.get('hold', 0) or 0),
                                'sell': int(latest.get('sell', 0) or 0) + int(latest.get('strongSell', 0) or 0)
                            }
                except Exception:
                    # Fallback: use targetMeanPrice vs currentPrice as proxy
                    target = info.get('targetMeanPrice', 0)
                    current = info.get('currentPrice', 0) or info.get('regularMarketPrice', 0)
                    if target and current and target > 0 and current > 0:
                        upside = (target - current) / current
                        if upside > 0.15:
                            result = {'buy': 1, 'hold': 0, 'sell': 0}
                        elif upside < -0.10:
                            result = {'buy': 0, 'hold': 0, 'sell': 1}
                        else:
                            result = {'buy': 0, 'hold': 1, 'sell': 0}

                self._set_cache(cache_key, result, self.CACHE_TTL_INFO)
                return result

            return {}
        except Exception as e:
            if 'RateLimit' in str(type(e).__name__) or 'rate' in str(e).lower():
                self._handle_rate_limit()
            else:
                logger.debug(f"YFinance analyst error for {symbol}: {e}")
            return {}

    def get_analyst_list(self, symbol: str, limit: int = 20) -> list:
        """Get list of recent analyst ratings with firm names and grades"""
        cache_key = f"analyst_list:{symbol}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        if not self._throttle():
            return []  # Rate limited

        try:
            ticker = yf.Ticker(symbol)
            upgrades = ticker.upgrades_downgrades

            if upgrades is None or len(upgrades) == 0:
                return []

            results = []
            for idx, row in upgrades.head(limit).iterrows():
                # Parse date
                date_str = str(idx)[:10] if idx else ''

                # Map grade to Buy/Hold/Sell
                grade = row.get('ToGrade', '')
                grade_lower = grade.lower()
                if any(x in grade_lower for x in ['buy', 'outperform', 'overweight', 'positive', 'accumulate']):
                    rating = 'Buy'
                    color = '#3fb950'
                elif any(x in grade_lower for x in ['sell', 'underperform', 'underweight', 'negative', 'reduce']):
                    rating = 'Sell'
                    color = '#f85149'
                else:
                    rating = 'Hold'
                    color = '#8b949e'

                # Get action (upgrade/downgrade/maintain)
                action = row.get('Action', '')
                action_display = ''
                if action == 'up':
                    action_display = '↑'
                elif action == 'down':
                    action_display = '↓'
                elif action in ['main', 'reit']:
                    action_display = '→'

                # Price target
                price_target = row.get('currentPriceTarget', 0)

                results.append({
                    'date': date_str,
                    'firm': row.get('Firm', 'Unknown'),
                    'grade': grade,
                    'rating': rating,
                    'color': color,
                    'action': action_display,
                    'price_target': price_target if price_target and price_target > 0 else None
                })

            self._set_cache(cache_key, results, self.CACHE_TTL_INFO)
            return results

        except Exception as e:
            logger.debug(f"YFinance analyst list error for {symbol}: {e}")
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
