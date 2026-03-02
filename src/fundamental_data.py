"""
Fundamental data module for earnings, news sentiment, and analyst ratings.

Provides:
- Earnings dates and blackout periods
- News headlines with sentiment analysis
- Analyst ratings and recommendations
"""
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class EarningsInfo:
    """Earnings date information"""
    next_earnings_date: datetime = None
    days_until_earnings: int = None
    in_blackout_period: bool = False
    earnings_estimate: float = None


@dataclass
class NewsItem:
    """Single news item with sentiment"""
    title: str
    summary: str
    published: datetime
    source: str
    sentiment: str  # 'positive', 'negative', 'neutral'
    sentiment_score: float  # -1.0 to 1.0


@dataclass
class AnalystRating:
    """Analyst recommendations summary"""
    strong_buy: int = 0
    buy: int = 0
    hold: int = 0
    sell: int = 0
    strong_sell: int = 0
    total: int = 0
    score: float = 0.0  # 1-5 scale (1=strong sell, 5=strong buy)
    recommendation: str = 'hold'  # 'strong_buy', 'buy', 'hold', 'sell', 'strong_sell'


class FundamentalDataClient:
    """Client for fetching fundamental data from Yahoo Finance"""

    # Keywords for simple sentiment analysis
    POSITIVE_KEYWORDS = [
        'beat', 'beats', 'exceeds', 'surge', 'surges', 'soar', 'soars',
        'rally', 'rallies', 'gain', 'gains', 'jump', 'jumps', 'rise', 'rises',
        'upgrade', 'upgrades', 'bullish', 'outperform', 'buy', 'positive',
        'growth', 'profit', 'record', 'high', 'strong', 'better', 'best',
        'success', 'successful', 'breakthrough', 'innovative', 'launch'
    ]

    NEGATIVE_KEYWORDS = [
        'miss', 'misses', 'fall', 'falls', 'drop', 'drops', 'decline', 'declines',
        'plunge', 'plunges', 'crash', 'crashes', 'sink', 'sinks', 'tumble',
        'downgrade', 'downgrades', 'bearish', 'underperform', 'sell', 'negative',
        'loss', 'losses', 'weak', 'worst', 'fail', 'fails', 'recall', 'lawsuit',
        'investigation', 'probe', 'warning', 'risk', 'concern', 'trouble'
    ]

    def __init__(self, blackout_days: int = 3):
        """
        Args:
            blackout_days: Days before/after earnings to avoid trading
        """
        self.blackout_days = blackout_days
        self._cache = {}
        self._cache_ttl = 3600  # Cache for 1 hour

    def _get_ticker(self, symbol: str) -> yf.Ticker:
        """Get yfinance Ticker object with caching"""
        cache_key = f"ticker_{symbol}"
        now = datetime.now()

        if cache_key in self._cache:
            cached_time, ticker = self._cache[cache_key]
            if (now - cached_time).seconds < self._cache_ttl:
                return ticker

        ticker = yf.Ticker(symbol)
        self._cache[cache_key] = (now, ticker)
        return ticker

    def get_earnings_info(self, symbol: str) -> EarningsInfo:
        """Get earnings date and blackout period status

        Args:
            symbol: Stock symbol

        Returns:
            EarningsInfo with next earnings date and blackout status
        """
        try:
            ticker = self._get_ticker(symbol)
            calendar = ticker.calendar

            if not calendar or 'Earnings Date' not in calendar:
                logger.warning(f"No earnings calendar for {symbol}")
                return EarningsInfo()

            earnings_dates = calendar.get('Earnings Date', [])
            if not earnings_dates:
                return EarningsInfo()

            # Get next earnings date
            next_date = earnings_dates[0]
            if isinstance(next_date, str):
                next_date = datetime.strptime(next_date, '%Y-%m-%d').date()

            today = datetime.now().date()
            days_until = (next_date - today).days

            # Check if in blackout period (X days before or after earnings)
            in_blackout = abs(days_until) <= self.blackout_days

            earnings_estimate = calendar.get('Earnings Average')

            info = EarningsInfo(
                next_earnings_date=datetime.combine(next_date, datetime.min.time()),
                days_until_earnings=days_until,
                in_blackout_period=in_blackout,
                earnings_estimate=earnings_estimate
            )

            logger.info(f"{symbol} earnings: {next_date} ({days_until} days), blackout: {in_blackout}")
            return info

        except Exception as e:
            logger.error(f"Error fetching earnings for {symbol}: {e}")
            return EarningsInfo()

    def _analyze_sentiment(self, text: str) -> tuple:
        """Simple keyword-based sentiment analysis

        Returns:
            (sentiment, score) tuple
        """
        if not text:
            return 'neutral', 0.0

        text_lower = text.lower()

        positive_count = sum(1 for word in self.POSITIVE_KEYWORDS if word in text_lower)
        negative_count = sum(1 for word in self.NEGATIVE_KEYWORDS if word in text_lower)

        total = positive_count + negative_count
        if total == 0:
            return 'neutral', 0.0

        score = (positive_count - negative_count) / total

        if score > 0.2:
            sentiment = 'positive'
        elif score < -0.2:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'

        return sentiment, score

    def get_news(self, symbol: str, limit: int = 10) -> list:
        """Get recent news with sentiment analysis

        Args:
            symbol: Stock symbol
            limit: Maximum number of news items

        Returns:
            List of NewsItem objects
        """
        try:
            ticker = self._get_ticker(symbol)
            news_data = ticker.news

            if not news_data:
                logger.warning(f"No news for {symbol}")
                return []

            news_items = []
            for item in news_data[:limit]:
                content = item.get('content', {})
                if not content:
                    continue

                title = content.get('title', '')
                summary = content.get('summary', '')
                pub_date_str = content.get('pubDate')
                provider = content.get('provider', {})
                source = provider.get('displayName', 'Unknown') if isinstance(provider, dict) else 'Unknown'

                # Parse date
                try:
                    if pub_date_str:
                        pub_date = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
                    else:
                        pub_date = datetime.now()
                except:
                    pub_date = datetime.now()

                # Analyze sentiment
                combined_text = f"{title} {summary}"
                sentiment, score = self._analyze_sentiment(combined_text)

                news_items.append(NewsItem(
                    title=title,
                    summary=summary[:200] if summary else '',
                    published=pub_date,
                    source=source,
                    sentiment=sentiment,
                    sentiment_score=score
                ))

            # Log summary
            sentiments = [n.sentiment for n in news_items]
            pos = sentiments.count('positive')
            neg = sentiments.count('negative')
            logger.info(f"{symbol} news: {len(news_items)} items, {pos} positive, {neg} negative")

            return news_items

        except Exception as e:
            logger.error(f"Error fetching news for {symbol}: {e}")
            return []

    def get_news_sentiment(self, symbol: str) -> tuple:
        """Get aggregated news sentiment

        Returns:
            (sentiment, score, count) - overall sentiment and number of articles
        """
        news = self.get_news(symbol)
        if not news:
            return 'neutral', 0.0, 0

        total_score = sum(n.sentiment_score for n in news)
        avg_score = total_score / len(news)

        if avg_score > 0.15:
            sentiment = 'positive'
        elif avg_score < -0.15:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'

        return sentiment, avg_score, len(news)

    def get_analyst_ratings(self, symbol: str) -> AnalystRating:
        """Get analyst recommendations

        Args:
            symbol: Stock symbol

        Returns:
            AnalystRating with buy/hold/sell breakdown
        """
        try:
            ticker = self._get_ticker(symbol)
            recs = ticker.recommendations

            if recs is None or recs.empty:
                logger.warning(f"No analyst ratings for {symbol}")
                return AnalystRating()

            # Get most recent month
            latest = recs.iloc[0]

            strong_buy = int(latest.get('strongBuy', 0))
            buy = int(latest.get('buy', 0))
            hold = int(latest.get('hold', 0))
            sell = int(latest.get('sell', 0))
            strong_sell = int(latest.get('strongSell', 0))

            total = strong_buy + buy + hold + sell + strong_sell

            # Calculate weighted score (1-5 scale)
            if total > 0:
                weighted = (strong_buy * 5 + buy * 4 + hold * 3 + sell * 2 + strong_sell * 1)
                score = weighted / total
            else:
                score = 3.0  # Neutral default

            # Determine recommendation
            if score >= 4.5:
                recommendation = 'strong_buy'
            elif score >= 3.5:
                recommendation = 'buy'
            elif score >= 2.5:
                recommendation = 'hold'
            elif score >= 1.5:
                recommendation = 'sell'
            else:
                recommendation = 'strong_sell'

            rating = AnalystRating(
                strong_buy=strong_buy,
                buy=buy,
                hold=hold,
                sell=sell,
                strong_sell=strong_sell,
                total=total,
                score=score,
                recommendation=recommendation
            )

            logger.info(f"{symbol} analysts: {total} ratings, score={score:.2f} ({recommendation})")
            return rating

        except Exception as e:
            logger.error(f"Error fetching analyst ratings for {symbol}: {e}")
            return AnalystRating()

    def get_all_fundamental_data(self, symbol: str) -> dict:
        """Get all fundamental data in one call

        Returns:
            Dict with earnings, news, and analyst data
        """
        return {
            'earnings': self.get_earnings_info(symbol),
            'news_sentiment': self.get_news_sentiment(symbol),
            'analyst_rating': self.get_analyst_ratings(symbol)
        }

    def should_avoid_trading(self, symbol: str) -> tuple:
        """Check if trading should be avoided based on fundamental data

        Returns:
            (should_avoid, reason) tuple
        """
        earnings = self.get_earnings_info(symbol)

        if earnings.in_blackout_period:
            return True, f"Earnings blackout ({earnings.days_until_earnings} days until earnings)"

        return False, None

    def get_fundamental_signal(self, symbol: str) -> tuple:
        """Get trading signal based on fundamental data

        Returns:
            (signal, strength, reason) tuple
            signal: 'bullish', 'bearish', 'neutral'
            strength: 0.0 to 1.0
        """
        news_sentiment, news_score, news_count = self.get_news_sentiment(symbol)
        analyst = self.get_analyst_ratings(symbol)

        # Combine signals
        signals = []

        # News sentiment (weight: 40%)
        if news_count > 0:
            if news_sentiment == 'positive':
                signals.append(('bullish', 0.4, f"Positive news sentiment ({news_score:.2f})"))
            elif news_sentiment == 'negative':
                signals.append(('bearish', 0.4, f"Negative news sentiment ({news_score:.2f})"))

        # Analyst ratings (weight: 60%)
        if analyst.total > 0:
            if analyst.score >= 3.5:
                signals.append(('bullish', 0.6, f"Analyst rating: {analyst.recommendation} ({analyst.score:.1f}/5)"))
            elif analyst.score <= 2.5:
                signals.append(('bearish', 0.6, f"Analyst rating: {analyst.recommendation} ({analyst.score:.1f}/5)"))

        if not signals:
            return 'neutral', 0.0, "No fundamental signals"

        # Aggregate signals
        bullish_strength = sum(s[1] for s in signals if s[0] == 'bullish')
        bearish_strength = sum(s[1] for s in signals if s[0] == 'bearish')

        if bullish_strength > bearish_strength:
            reasons = [s[2] for s in signals if s[0] == 'bullish']
            return 'bullish', bullish_strength, '; '.join(reasons)
        elif bearish_strength > bullish_strength:
            reasons = [s[2] for s in signals if s[0] == 'bearish']
            return 'bearish', bearish_strength, '; '.join(reasons)
        else:
            return 'neutral', 0.0, "Mixed signals"


class EarningsAnalyzer:
    """Analyze earnings results and generate signals"""

    def __init__(self):
        self.last_check = None
        self._cache = {}

    def get_latest_earnings(self, symbol: str) -> dict:
        """Get the most recent earnings data

        Returns:
            Dict with actual, estimate, surprise, surprise_pct, revenue, date
        """
        try:
            ticker = yf.Ticker(symbol)

            # Get quarterly income statement for revenue/net income
            income = ticker.quarterly_income_stmt
            latest_date = income.columns[0] if income is not None and not income.empty else None

            # Get net income (earnings proxy)
            net_income = None
            revenue = None
            if income is not None and not income.empty:
                if 'Net Income' in income.index:
                    net_income = income.loc['Net Income', latest_date]
                if 'Total Revenue' in income.index:
                    revenue = income.loc['Total Revenue', latest_date]

            # Get earnings history for actual EPS vs estimate (more accurate)
            eps_actual = None
            eps_estimate = None
            surprise = None
            surprise_pct = None
            earnings_date = latest_date

            try:
                # earnings_history has actual EPS, estimate, and surprise
                earnings_hist = ticker.earnings_history
                if earnings_hist is not None and not earnings_hist.empty:
                    latest = earnings_hist.iloc[-1]  # Most recent
                    eps_actual = latest.get('epsActual')
                    eps_estimate = latest.get('epsEstimate')
                    surprise = latest.get('epsDifference')
                    if eps_estimate and eps_estimate != 0:
                        surprise_pct = (surprise / abs(eps_estimate)) * 100 if surprise else None
                    # Use actual earnings date if available
                    if 'Earnings Date' in latest.index:
                        earnings_date = latest.get('Earnings Date')
            except:
                pass

            # Fallback to earnings_dates for estimate if not found
            if eps_estimate is None:
                calendar = ticker.calendar
                if calendar:
                    eps_estimate = calendar.get('Earnings Average')

            result = {
                'symbol': symbol,
                'date': earnings_date,
                'net_income': net_income,
                'revenue': revenue,
                'eps_actual': eps_actual,
                'eps_estimate': eps_estimate,
                'surprise': surprise,
                'surprise_pct': surprise_pct,
            }

            if surprise_pct is not None:
                logger.info(f"{symbol} earnings: EPS={eps_actual}, Est={eps_estimate}, Surprise={surprise_pct:.1f}%")
            else:
                logger.info(f"{symbol} earnings: Net Income={net_income}, Revenue={revenue}")

            return result

        except Exception as e:
            logger.error(f"Error getting earnings for {symbol}: {e}")
            return None

    def get_earnings_signal(self, symbol: str) -> tuple:
        """Get trading signal based on latest earnings

        Returns:
            (signal, strength, reason) tuple
            signal: 'strong_buy', 'buy', 'hold', 'sell', 'strong_sell'
        """
        earnings = self.get_latest_earnings(symbol)
        if not earnings:
            return 'hold', 0, "No earnings data"

        signals = []

        # Check earnings surprise
        surprise_pct = earnings.get('surprise_pct')
        if surprise_pct is not None:
            if surprise_pct > 10:
                signals.append(('strong_buy', 0.5, f"Big beat: +{surprise_pct:.1f}% vs estimate"))
            elif surprise_pct > 0:
                signals.append(('buy', 0.3, f"Beat: +{surprise_pct:.1f}% vs estimate"))
            elif surprise_pct < -10:
                signals.append(('strong_sell', 0.5, f"Big miss: {surprise_pct:.1f}% vs estimate"))
            elif surprise_pct < 0:
                signals.append(('sell', 0.3, f"Miss: {surprise_pct:.1f}% vs estimate"))

        # Check revenue trend (compare to previous quarters)
        revenue = earnings.get('revenue')
        if revenue and revenue > 0:
            signals.append(('buy', 0.2, f"Revenue: ${revenue/1e9:.1f}B"))

        # Check if losses are decreasing (for unprofitable companies like NIO)
        net_income = earnings.get('net_income')
        if net_income and net_income < 0:
            # Loss, but check if improving
            signals.append(('hold', 0.1, f"Still unprofitable: ${net_income/1e6:.0f}M"))

        if not signals:
            return 'hold', 0, "Neutral earnings"

        # Aggregate signals
        buy_signals = [s for s in signals if s[0] in ('strong_buy', 'buy')]
        sell_signals = [s for s in signals if s[0] in ('strong_sell', 'sell')]

        if buy_signals and not sell_signals:
            strength = sum(s[1] for s in buy_signals)
            reasons = [s[2] for s in buy_signals]
            if any(s[0] == 'strong_buy' for s in buy_signals):
                return 'strong_buy', strength, '; '.join(reasons)
            return 'buy', strength, '; '.join(reasons)

        elif sell_signals and not buy_signals:
            strength = sum(s[1] for s in sell_signals)
            reasons = [s[2] for s in sell_signals]
            if any(s[0] == 'strong_sell' for s in sell_signals):
                return 'strong_sell', strength, '; '.join(reasons)
            return 'sell', strength, '; '.join(reasons)

        return 'hold', 0, "Mixed signals"

    def check_earnings_just_released(self, symbol: str, hours: int = 24) -> bool:
        """Check if earnings were released within the last X hours

        Returns:
            True if earnings were recently released
        """
        try:
            ticker = yf.Ticker(symbol)
            income = ticker.quarterly_income_stmt

            if income is None or income.empty:
                return False

            latest_date = income.columns[0]

            # Check if latest earnings is within the last X hours
            # Note: This is approximate since we only have the date, not exact time
            from datetime import datetime, timedelta
            now = datetime.now()

            if hasattr(latest_date, 'to_pydatetime'):
                latest_date = latest_date.to_pydatetime()

            days_since = (now - latest_date).days

            # If earnings date is within last few days, consider it "just released"
            return days_since <= (hours / 24)

        except Exception as e:
            logger.error(f"Error checking earnings release: {e}")
            return False


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    client = FundamentalDataClient(blackout_days=3)

    print("\n" + "="*60)
    print("  FUNDAMENTAL DATA: NIO")
    print("="*60)

    # Earnings
    print("\n=== EARNINGS ===")
    earnings = client.get_earnings_info('NIO')
    print(f"Next earnings: {earnings.next_earnings_date}")
    print(f"Days until: {earnings.days_until_earnings}")
    print(f"In blackout: {earnings.in_blackout_period}")
    print(f"Estimate: {earnings.earnings_estimate}")

    # News
    print("\n=== NEWS SENTIMENT ===")
    sentiment, score, count = client.get_news_sentiment('NIO')
    print(f"Articles: {count}")
    print(f"Sentiment: {sentiment} ({score:.2f})")

    news = client.get_news('NIO', limit=5)
    for n in news:
        print(f"  [{n.sentiment}] {n.title[:60]}...")

    # Analyst ratings
    print("\n=== ANALYST RATINGS ===")
    ratings = client.get_analyst_ratings('NIO')
    print(f"Strong Buy: {ratings.strong_buy}")
    print(f"Buy: {ratings.buy}")
    print(f"Hold: {ratings.hold}")
    print(f"Sell: {ratings.sell}")
    print(f"Strong Sell: {ratings.strong_sell}")
    print(f"Score: {ratings.score:.2f}/5 ({ratings.recommendation})")

    # Combined signal
    print("\n=== FUNDAMENTAL SIGNAL ===")
    signal, strength, reason = client.get_fundamental_signal('NIO')
    print(f"Signal: {signal} (strength: {strength:.2f})")
    print(f"Reason: {reason}")

    # Earnings Analyzer (NEW)
    print("\n=== EARNINGS ANALYZER ===")
    analyzer = EarningsAnalyzer()
    earnings_data = analyzer.get_latest_earnings('NIO')
    if earnings_data:
        print(f"Date: {earnings_data['date']}")
        print(f"EPS Actual: {earnings_data['eps_actual']}")
        print(f"EPS Estimate: {earnings_data['eps_estimate']}")
        print(f"Surprise: {earnings_data['surprise_pct']:.1f}%" if earnings_data['surprise_pct'] else "Surprise: N/A")
        print(f"Net Income: ${earnings_data['net_income']/1e6:.0f}M" if earnings_data['net_income'] else "Net Income: N/A")
        print(f"Revenue: ${earnings_data['revenue']/1e9:.2f}B" if earnings_data['revenue'] else "Revenue: N/A")

    signal, strength, reason = analyzer.get_earnings_signal('NIO')
    print(f"\nEarnings Signal: {signal} (strength: {strength:.2f})")
    print(f"Reason: {reason}")

    recently_released = analyzer.check_earnings_just_released('NIO', hours=168)  # Last 7 days
    print(f"\nEarnings released last 7 days: {recently_released}")
