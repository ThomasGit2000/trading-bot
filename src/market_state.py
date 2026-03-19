"""
Market State Engine
Provides comprehensive market state indicators for the dashboard.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)


class MarketStateEngine:
    """
    Computes and caches market state indicators.

    Market Describers (9):
    - Trend Regime: BULL/BEAR based on SPY MA crossover
    - Volatility Regime: LOW/MEDIUM/HIGH based on VIX or portfolio ATR
    - Liquidity Regime: Manual/default
    - Macro Regime: Manual/default
    - Inflation Regime: Manual/default
    - Rates Regime: From ^TNX or default
    - Correlation Regime: Avg pairwise correlation of stocks
    - Dispersion Regime: Std dev of stock returns
    - Positioning Regime: Manual/default

    Directional Describers (4):
    - Factor Rotation: Manual/default
    - Sector Rotation: Best performing category
    - Duration Rotation: Manual/default
    - Risk Appetite: Derived from Trend + Volatility
    """

    def __init__(self, regime_detector=None, yf_client=None):
        self.regime_detector = regime_detector
        self.yf_client = yf_client
        self.update_interval = 300  # 5 minutes
        self._cache = {}
        self._last_update = None
        self._stock_returns = {}  # symbol -> list of recent returns
        self._category_returns = {}  # category -> avg return
        self._stock_signals = {}  # symbol -> signal (BUY/SELL/HOLD)
        self._stock_sentiment = {}  # symbol -> sentiment score
        self._stock_earnings = {}  # symbol -> days to earnings

        logger.info("MarketStateEngine initialized")

    def set_yf_client(self, client):
        """Set the YFinance client (can be set after init)"""
        self.yf_client = client

    def set_regime_detector(self, detector):
        """Set the regime detector (can be set after init)"""
        self.regime_detector = detector

    def update_stock_data(self, stocks: list):
        """Update internal data from bot_state stocks list"""
        try:
            # Calculate returns from price changes
            for stock in stocks:
                symbol = stock.get('symbol')
                if not symbol:
                    continue

                price = stock.get('price', 0)
                prev_close = stock.get('prev_close', 0)
                category = stock.get('category', 'Unknown')

                if price > 0 and prev_close > 0:
                    ret = (price - prev_close) / prev_close
                    self._stock_returns[symbol] = {
                        'return': ret,
                        'category': category,
                        'price': price
                    }

                # Capture signal data
                signal = stock.get('signal', 'HOLD')
                self._stock_signals[symbol] = signal

                # Capture sentiment data
                sentiment = stock.get('sentiment_score', 0)
                if sentiment == 0:
                    sentiment = stock.get('news_sentiment', 0)
                self._stock_sentiment[symbol] = sentiment

                # Capture earnings data
                days_to_event = stock.get('days_to_event')
                if days_to_event is not None:
                    self._stock_earnings[symbol] = days_to_event

            # Compute category average returns
            category_totals = {}
            category_counts = {}
            for symbol, data in self._stock_returns.items():
                cat = data['category']
                ret = data['return']
                if cat not in category_totals:
                    category_totals[cat] = 0
                    category_counts[cat] = 0
                category_totals[cat] += ret
                category_counts[cat] += 1

            self._category_returns = {
                cat: category_totals[cat] / category_counts[cat]
                for cat in category_totals
                if category_counts[cat] > 0
            }
        except Exception as e:
            logger.warning(f"Error updating stock data: {e}")

    def get_state(self) -> dict:
        """Return full market state with all indicators."""
        now = datetime.now()

        # Get URTH data
        urth_data = self.get_urth_data()

        # Compute all indicators
        market_describers = {
            'trend_regime': self.compute_trend_regime(),
            'volatility_regime': self.compute_volatility_regime(),
            'market_breadth': self.compute_market_breadth(),
            'news_sentiment': self.compute_news_sentiment_aggregate(),
            'earnings_density': self.compute_earnings_density(),
            'rates_regime': self.compute_rates_regime(),
            'yield_curve': self.compute_yield_curve(),
            'correlation_regime': self.compute_correlation_regime(),
            'dispersion_regime': self.compute_dispersion_regime(),
        }

        directional_describers = {
            'factor_rotation': self.compute_factor_rotation(),
            'sector_rotation': self.compute_sector_rotation(),
            'sector_momentum': self.compute_sector_momentum(),
            'risk_appetite': self.compute_risk_appetite(),
        }

        self._last_update = now

        return {
            'urth': urth_data,
            'market_describers': market_describers,
            'directional_describers': directional_describers,
            'last_updated': now.isoformat()
        }

    def get_urth_data(self) -> dict:
        """Get URTH (MSCI World ETF) price data."""
        if not self.yf_client:
            return {
                'price': 0,
                'change': 0,
                'change_pct': 0,
                'volume': 0,
                'error': 'YFinance client not available'
            }

        try:
            quote = self.yf_client.get_quote('URTH')
            if quote:
                price = quote.get('price', 0)
                prev_close = quote.get('previous_close', 0)
                change = price - prev_close if prev_close > 0 else 0
                change_pct = (change / prev_close * 100) if prev_close > 0 else 0

                return {
                    'symbol': 'URTH',
                    'name': 'iShares MSCI World ETF',
                    'price': round(price, 2),
                    'change': round(change, 2),
                    'change_pct': round(change_pct, 2),
                    'volume': quote.get('volume', 0),
                    'high': quote.get('high', 0),
                    'low': quote.get('low', 0),
                    'open': quote.get('open', 0),
                    'prev_close': prev_close
                }
        except Exception as e:
            logger.warning(f"Error fetching URTH data: {e}")

        return {
            'price': 0,
            'change': 0,
            'change_pct': 0,
            'error': 'Failed to fetch data'
        }

    # Market Describers (9)

    def compute_trend_regime(self) -> dict:
        """Get trend regime from RegimeDetector (SPY MA crossover)"""
        if self.regime_detector:
            regime = self.regime_detector.get_regime()
            state = self.regime_detector.get_state()

            if regime == 'BULL':
                return {
                    'value': 'BULL',
                    'color': '#3fb950',
                    'source': f"SPY MA({state.get('short_ma', 0):.0f}/{state.get('long_ma', 0):.0f})",
                    'description': 'Short MA > Long MA'
                }
            elif regime == 'BEAR':
                return {
                    'value': 'BEAR',
                    'color': '#f85149',
                    'source': f"SPY MA({state.get('short_ma', 0):.0f}/{state.get('long_ma', 0):.0f})",
                    'description': 'Short MA < Long MA'
                }

        return {
            'value': 'UNKNOWN',
            'color': '#8b949e',
            'source': 'Insufficient data',
            'description': 'Waiting for MA data'
        }

    def compute_volatility_regime(self) -> dict:
        """Compute volatility regime from VIX or portfolio ATR"""
        if self.yf_client:
            try:
                vix_quote = self.yf_client.get_quote('^VIX')
                if vix_quote and vix_quote.get('price', 0) > 0:
                    vix = vix_quote['price']

                    if vix < 15:
                        return {
                            'value': 'LOW',
                            'color': '#3fb950',
                            'source': f'VIX: {vix:.1f}',
                            'description': 'Low volatility environment'
                        }
                    elif vix < 25:
                        return {
                            'value': 'MEDIUM',
                            'color': '#f0883e',
                            'source': f'VIX: {vix:.1f}',
                            'description': 'Normal volatility'
                        }
                    else:
                        return {
                            'value': 'HIGH',
                            'color': '#f85149',
                            'source': f'VIX: {vix:.1f}',
                            'description': 'Elevated volatility'
                        }
            except Exception as e:
                logger.debug(f"VIX fetch error: {e}")

        return {
            'value': 'MEDIUM',
            'color': '#f0883e',
            'source': 'Default',
            'description': 'VIX data unavailable'
        }

    def compute_market_breadth(self) -> dict:
        """Compute market breadth (% of stocks with BUY signals)"""
        if len(self._stock_signals) < 5:
            return {
                'value': 'N/A',
                'color': '#8b949e',
                'source': 'Insufficient data',
                'description': 'Need more stocks for breadth'
            }

        try:
            total = len(self._stock_signals)
            buy_count = sum(1 for s in self._stock_signals.values() if s == 'BUY')
            sell_count = sum(1 for s in self._stock_signals.values() if s == 'SELL')
            buy_pct = buy_count / total * 100

            if buy_pct >= 70:
                return {
                    'value': 'STRONG',
                    'color': '#3fb950',
                    'source': f'{buy_pct:.0f}% BUY signals',
                    'description': f'{buy_count} buys, {sell_count} sells'
                }
            elif buy_pct >= 50:
                return {
                    'value': 'HEALTHY',
                    'color': '#58a6ff',
                    'source': f'{buy_pct:.0f}% BUY signals',
                    'description': f'{buy_count} buys, {sell_count} sells'
                }
            elif buy_pct >= 30:
                return {
                    'value': 'WEAK',
                    'color': '#f0883e',
                    'source': f'{buy_pct:.0f}% BUY signals',
                    'description': f'{buy_count} buys, {sell_count} sells'
                }
            else:
                return {
                    'value': 'BEARISH',
                    'color': '#f85149',
                    'source': f'{buy_pct:.0f}% BUY signals',
                    'description': f'{buy_count} buys, {sell_count} sells'
                }
        except Exception as e:
            logger.debug(f"Market breadth calc error: {e}")

        return {
            'value': 'N/A',
            'color': '#8b949e',
            'source': 'Calculation error',
            'description': ''
        }

    def compute_news_sentiment_aggregate(self) -> dict:
        """Compute aggregate news sentiment across all stocks"""
        if len(self._stock_sentiment) < 5:
            return {
                'value': 'N/A',
                'color': '#8b949e',
                'source': 'Insufficient data',
                'description': 'Need more sentiment data'
            }

        try:
            sentiments = [s for s in self._stock_sentiment.values() if s != 0]
            if not sentiments:
                return {
                    'value': 'NEUTRAL',
                    'color': '#8b949e',
                    'source': 'No sentiment data',
                    'description': 'Waiting for news analysis'
                }

            avg_sentiment = np.mean(sentiments)

            if avg_sentiment >= 0.15:
                return {
                    'value': 'BULLISH',
                    'color': '#3fb950',
                    'source': f'Avg: {avg_sentiment:+.2f}',
                    'description': f'{len(sentiments)} stocks analyzed'
                }
            elif avg_sentiment >= 0.05:
                return {
                    'value': 'POSITIVE',
                    'color': '#58a6ff',
                    'source': f'Avg: {avg_sentiment:+.2f}',
                    'description': f'{len(sentiments)} stocks analyzed'
                }
            elif avg_sentiment <= -0.15:
                return {
                    'value': 'BEARISH',
                    'color': '#f85149',
                    'source': f'Avg: {avg_sentiment:+.2f}',
                    'description': f'{len(sentiments)} stocks analyzed'
                }
            elif avg_sentiment <= -0.05:
                return {
                    'value': 'NEGATIVE',
                    'color': '#f0883e',
                    'source': f'Avg: {avg_sentiment:+.2f}',
                    'description': f'{len(sentiments)} stocks analyzed'
                }
            else:
                return {
                    'value': 'NEUTRAL',
                    'color': '#8b949e',
                    'source': f'Avg: {avg_sentiment:+.2f}',
                    'description': f'{len(sentiments)} stocks analyzed'
                }
        except Exception as e:
            logger.debug(f"Sentiment aggregate calc error: {e}")

        return {
            'value': 'NEUTRAL',
            'color': '#8b949e',
            'source': 'Default',
            'description': ''
        }

    def compute_earnings_density(self) -> dict:
        """Compute earnings density (stocks with upcoming earnings)"""
        if not self._stock_earnings:
            return {
                'value': 'N/A',
                'color': '#8b949e',
                'source': 'No earnings data',
                'description': 'Waiting for earnings info'
            }

        try:
            # Count stocks with earnings in next 5 days
            imminent = sum(1 for d in self._stock_earnings.values()
                          if d is not None and 0 <= d <= 5)
            upcoming = sum(1 for d in self._stock_earnings.values()
                          if d is not None and 0 <= d <= 14)
            total = len(self._stock_earnings)

            if imminent >= 10:
                return {
                    'value': 'HIGH',
                    'color': '#f85149',
                    'source': f'{imminent} stocks in 5 days',
                    'description': f'{upcoming} in 2 weeks (high vol expected)'
                }
            elif imminent >= 5:
                return {
                    'value': 'ELEVATED',
                    'color': '#f0883e',
                    'source': f'{imminent} stocks in 5 days',
                    'description': f'{upcoming} in 2 weeks'
                }
            elif upcoming >= 5:
                return {
                    'value': 'MODERATE',
                    'color': '#58a6ff',
                    'source': f'{imminent} stocks in 5 days',
                    'description': f'{upcoming} in 2 weeks'
                }
            else:
                return {
                    'value': 'LOW',
                    'color': '#3fb950',
                    'source': f'{imminent} stocks in 5 days',
                    'description': 'Low earnings risk period'
                }
        except Exception as e:
            logger.debug(f"Earnings density calc error: {e}")

        return {
            'value': 'N/A',
            'color': '#8b949e',
            'source': 'Calculation error',
            'description': ''
        }

    def compute_yield_curve(self) -> dict:
        """Compute yield curve health from 2Y and 10Y treasuries"""
        if not self.yf_client:
            return {
                'value': 'N/A',
                'color': '#8b949e',
                'source': 'No data',
                'description': 'YFinance unavailable'
            }

        try:
            # Get 10Y yield
            tnx = self.yf_client.get_quote('^TNX')
            # Get 2Y yield
            twoy = self.yf_client.get_quote('^IRX')  # 13-week T-bill as proxy

            if tnx and twoy:
                ten_yr = tnx.get('price', 0)
                two_yr = twoy.get('price', 0)

                if ten_yr > 0 and two_yr > 0:
                    spread = ten_yr - two_yr

                    if spread < 0:
                        return {
                            'value': 'INVERTED',
                            'color': '#f85149',
                            'source': f'10Y-2Y: {spread:.2f}%',
                            'description': 'Recession signal'
                        }
                    elif spread < 0.5:
                        return {
                            'value': 'FLAT',
                            'color': '#f0883e',
                            'source': f'10Y-2Y: {spread:.2f}%',
                            'description': 'Curve flattening'
                        }
                    else:
                        return {
                            'value': 'NORMAL',
                            'color': '#3fb950',
                            'source': f'10Y-2Y: {spread:.2f}%',
                            'description': 'Healthy curve'
                        }
        except Exception as e:
            logger.debug(f"Yield curve calc error: {e}")

        return {
            'value': 'N/A',
            'color': '#8b949e',
            'source': 'Data unavailable',
            'description': ''
        }

    def compute_rates_regime(self) -> dict:
        """Rates regime from 10Y Treasury yield"""
        if self.yf_client:
            try:
                tnx_quote = self.yf_client.get_quote('^TNX')
                if tnx_quote and tnx_quote.get('price', 0) > 0:
                    rate = tnx_quote['price']
                    prev = tnx_quote.get('previous_close', rate)
                    change = rate - prev

                    if change > 0.05:
                        return {
                            'value': 'RISING',
                            'color': '#f85149',
                            'source': f'10Y: {rate:.2f}% (+{change:.2f})',
                            'description': 'Yields rising'
                        }
                    elif change < -0.05:
                        return {
                            'value': 'FALLING',
                            'color': '#3fb950',
                            'source': f'10Y: {rate:.2f}% ({change:.2f})',
                            'description': 'Yields falling'
                        }
                    else:
                        return {
                            'value': 'STABLE',
                            'color': '#f0883e',
                            'source': f'10Y: {rate:.2f}%',
                            'description': 'Yields stable'
                        }
            except Exception as e:
                logger.debug(f"TNX fetch error: {e}")

        return {
            'value': 'STABLE',
            'color': '#8b949e',
            'source': 'Default',
            'description': 'Treasury data unavailable'
        }

    def compute_correlation_regime(self) -> dict:
        """Compute average pairwise correlation of stock returns"""
        if len(self._stock_returns) < 5:
            return {
                'value': 'N/A',
                'color': '#8b949e',
                'source': 'Insufficient data',
                'description': 'Need more stocks for correlation'
            }

        try:
            returns = [data['return'] for data in self._stock_returns.values()]
            # Simple proxy: use std of returns as correlation indicator
            # Higher std with similar signs = higher correlation
            avg_ret = np.mean(returns)
            std_ret = np.std(returns)

            # If most stocks moving same direction with low dispersion = high correlation
            same_direction = sum(1 for r in returns if (r > 0) == (avg_ret > 0))
            pct_same = same_direction / len(returns)

            if pct_same > 0.8:
                return {
                    'value': 'HIGH',
                    'color': '#f0883e',
                    'source': f'{pct_same:.0%} same direction',
                    'description': 'Stocks highly correlated'
                }
            elif pct_same > 0.6:
                return {
                    'value': 'MODERATE',
                    'color': '#8b949e',
                    'source': f'{pct_same:.0%} same direction',
                    'description': 'Normal correlation'
                }
            else:
                return {
                    'value': 'LOW',
                    'color': '#3fb950',
                    'source': f'{pct_same:.0%} same direction',
                    'description': 'Stocks diverging'
                }
        except Exception as e:
            logger.debug(f"Correlation calc error: {e}")

        return {
            'value': 'MODERATE',
            'color': '#8b949e',
            'source': 'Default',
            'description': 'Calculation error'
        }

    def compute_dispersion_regime(self) -> dict:
        """Compute dispersion (std dev of stock returns)"""
        if len(self._stock_returns) < 5:
            return {
                'value': 'N/A',
                'color': '#8b949e',
                'source': 'Insufficient data',
                'description': 'Need more stocks for dispersion'
            }

        try:
            returns = [data['return'] for data in self._stock_returns.values()]
            std_ret = np.std(returns) * 100  # Convert to percentage

            if std_ret < 1.0:
                return {
                    'value': 'LOW',
                    'color': '#8b949e',
                    'source': f'Std: {std_ret:.2f}%',
                    'description': 'Stocks moving together'
                }
            elif std_ret < 2.5:
                return {
                    'value': 'NORMAL',
                    'color': '#3fb950',
                    'source': f'Std: {std_ret:.2f}%',
                    'description': 'Normal return dispersion'
                }
            else:
                return {
                    'value': 'HIGH',
                    'color': '#f0883e',
                    'source': f'Std: {std_ret:.2f}%',
                    'description': 'Wide return dispersion'
                }
        except Exception as e:
            logger.debug(f"Dispersion calc error: {e}")

        return {
            'value': 'NORMAL',
            'color': '#8b949e',
            'source': 'Default',
            'description': 'Calculation error'
        }

    # Directional Describers (4)

    def compute_factor_rotation(self) -> dict:
        """Compute factor rotation from sector ETF performance"""
        if not self.yf_client:
            return {
                'value': 'N/A',
                'color': '#8b949e',
                'source': 'No data',
                'description': 'YFinance unavailable'
            }

        try:
            # Fetch sector ETF quotes
            etfs = {
                'XLK': 'Tech',
                'XLF': 'Financials',
                'XLE': 'Energy',
                'XLV': 'Healthcare',
                'XLY': 'Consumer Disc',
                'XLP': 'Consumer Staples',
            }

            returns = {}
            for symbol, name in etfs.items():
                quote = self.yf_client.get_quote(symbol)
                if quote and quote.get('price', 0) > 0:
                    price = quote['price']
                    prev = quote.get('previous_close', price)
                    if prev > 0:
                        returns[name] = (price - prev) / prev * 100

            if len(returns) < 3:
                return {
                    'value': 'N/A',
                    'color': '#8b949e',
                    'source': 'Insufficient ETF data',
                    'description': ''
                }

            # Find best/worst sectors
            sorted_sectors = sorted(returns.items(), key=lambda x: x[1], reverse=True)
            best, best_ret = sorted_sectors[0]
            worst, worst_ret = sorted_sectors[-1]

            # Determine rotation type
            growth_sectors = ['Tech', 'Consumer Disc']
            defensive_sectors = ['Healthcare', 'Consumer Staples']

            if best in growth_sectors:
                rotation = 'GROWTH'
                color = '#3fb950'
            elif best in defensive_sectors:
                rotation = 'DEFENSIVE'
                color = '#f0883e'
            else:
                rotation = 'VALUE'
                color = '#58a6ff'

            return {
                'value': rotation,
                'color': color,
                'source': f'{best}: {best_ret:+.2f}%',
                'description': f'Lagging: {worst} ({worst_ret:+.2f}%)'
            }
        except Exception as e:
            logger.debug(f"Factor rotation calc error: {e}")

        return {
            'value': 'N/A',
            'color': '#8b949e',
            'source': 'Calculation error',
            'description': ''
        }

    def compute_sector_rotation(self) -> dict:
        """Compute best performing sector from category returns"""
        if not self._category_returns:
            return {
                'value': 'N/A',
                'color': '#8b949e',
                'source': 'No data',
                'description': 'Waiting for price data'
            }

        try:
            # Find best and worst performing categories
            sorted_cats = sorted(
                self._category_returns.items(),
                key=lambda x: x[1],
                reverse=True
            )

            if sorted_cats:
                best_cat, best_ret = sorted_cats[0]
                worst_cat, worst_ret = sorted_cats[-1]

                # Determine rotation type
                growth_cats = ['AI', 'Semiconductors', 'Tech Giants', 'Cloud', 'Cybersecurity']
                value_cats = ['Finance', 'Healthcare', 'Utilities', 'Consumer']
                defensive_cats = ['Utilities', 'Healthcare', 'Consumer']
                cyclical_cats = ['Semiconductors', 'Industrials', 'Crypto', 'EV/Auto']

                if any(cat in best_cat for cat in growth_cats):
                    rotation_type = 'GROWTH'
                    color = '#3fb950'
                elif any(cat in best_cat for cat in defensive_cats):
                    rotation_type = 'DEFENSIVE'
                    color = '#f0883e'
                elif any(cat in best_cat for cat in cyclical_cats):
                    rotation_type = 'CYCLICAL'
                    color = '#58a6ff'
                else:
                    rotation_type = 'MIXED'
                    color = '#8b949e'

                return {
                    'value': rotation_type,
                    'color': color,
                    'source': f'Best: {best_cat} ({best_ret:+.2%})',
                    'description': f'Worst: {worst_cat} ({worst_ret:+.2%})'
                }
        except Exception as e:
            logger.debug(f"Sector rotation calc error: {e}")

        return {
            'value': 'MIXED',
            'color': '#8b949e',
            'source': 'Default',
            'description': 'No clear rotation'
        }

    def compute_sector_momentum(self) -> dict:
        """Compute sector momentum from category performance"""
        if len(self._category_returns) < 3:
            return {
                'value': 'N/A',
                'color': '#8b949e',
                'source': 'Insufficient data',
                'description': 'Need more category data'
            }

        try:
            # Calculate spread between best and worst
            sorted_cats = sorted(
                self._category_returns.items(),
                key=lambda x: x[1],
                reverse=True
            )

            best_cat, best_ret = sorted_cats[0]
            worst_cat, worst_ret = sorted_cats[-1]
            spread = (best_ret - worst_ret) * 100

            # Average return across all sectors
            avg_ret = np.mean(list(self._category_returns.values())) * 100

            if avg_ret > 0.5:
                momentum = 'STRONG UP'
                color = '#3fb950'
            elif avg_ret > 0:
                momentum = 'WEAK UP'
                color = '#58a6ff'
            elif avg_ret > -0.5:
                momentum = 'WEAK DOWN'
                color = '#f0883e'
            else:
                momentum = 'STRONG DOWN'
                color = '#f85149'

            return {
                'value': momentum,
                'color': color,
                'source': f'Avg: {avg_ret:+.2f}%',
                'description': f'Spread: {spread:.1f}% ({best_cat} vs {worst_cat})'
            }
        except Exception as e:
            logger.debug(f"Sector momentum calc error: {e}")

        return {
            'value': 'N/A',
            'color': '#8b949e',
            'source': 'Calculation error',
            'description': ''
        }

    def compute_risk_appetite(self) -> dict:
        """Derive risk appetite from trend + volatility"""
        trend = self.compute_trend_regime()
        vol = self.compute_volatility_regime()

        trend_val = trend.get('value', 'UNKNOWN')
        vol_val = vol.get('value', 'MEDIUM')

        # Risk-On: Bull + Low/Medium vol
        # Risk-Off: Bear + High vol
        # Neutral: Mixed signals

        if trend_val == 'BULL' and vol_val in ['LOW', 'MEDIUM']:
            return {
                'value': 'RISK-ON',
                'color': '#3fb950',
                'source': f'Trend: {trend_val}, Vol: {vol_val}',
                'description': 'Favorable for risk assets'
            }
        elif trend_val == 'BEAR' or vol_val == 'HIGH':
            return {
                'value': 'RISK-OFF',
                'color': '#f85149',
                'source': f'Trend: {trend_val}, Vol: {vol_val}',
                'description': 'Caution advised'
            }
        else:
            return {
                'value': 'NEUTRAL',
                'color': '#f0883e',
                'source': f'Trend: {trend_val}, Vol: {vol_val}',
                'description': 'Mixed signals'
            }


    def get_historical_indicators(self, period: str = '1y') -> dict:
        """Get historical data for key indicators over the specified period."""
        if not self.yf_client:
            return {'error': 'YFinance client not available'}

        result = {
            'market_describers': {},
            'directional_describers': {},
            'period': period
        }

        try:
            # VIX History (Volatility)
            vix_history = self.yf_client.get_history('^VIX', period=period, interval='1d')
            if vix_history:
                result['market_describers']['volatility'] = {
                    'name': 'VIX (Volatility)',
                    'data': [{'date': h['date'].isoformat() if hasattr(h['date'], 'isoformat') else str(h['date']),
                              'value': h['close']} for h in vix_history],
                    'color': '#f0883e',
                    'unit': ''
                }

            # USD Treasury Yields (2Y, 5Y, 10Y, 30Y)
            treasury_symbols = {
                '5Y': '^FVX',    # 5-Year Treasury
                '10Y': '^TNX',   # 10-Year Treasury
                '30Y': '^TYX'    # 30-Year Treasury
            }
            treasury_yields = {}
            for maturity, symbol in treasury_symbols.items():
                hist = self.yf_client.get_history(symbol, period=period, interval='1d')
                if hist:
                    treasury_yields[maturity] = {
                        'data': [{'date': h['date'].isoformat() if hasattr(h['date'], 'isoformat') else str(h['date']),
                                  'value': h['close']} for h in hist]
                    }

            if treasury_yields:
                result['market_describers']['treasury_yields'] = treasury_yields

            # Keep legacy single-line rates for backward compatibility
            tnx_history = self.yf_client.get_history('^TNX', period=period, interval='1d')
            if tnx_history:
                result['market_describers']['rates'] = {
                    'name': '10Y Treasury Yield',
                    'data': [{'date': h['date'].isoformat() if hasattr(h['date'], 'isoformat') else str(h['date']),
                              'value': h['close']} for h in tnx_history],
                    'color': '#58a6ff',
                    'unit': '%'
                }

            # 13-Week T-Bill (Short rates for yield curve)
            irx_history = self.yf_client.get_history('^IRX', period=period, interval='1d')
            if irx_history and tnx_history:
                # Calculate yield curve spread (10Y - 13W)
                # Align dates
                tnx_by_date = {h['date'].strftime('%Y-%m-%d') if hasattr(h['date'], 'strftime') else str(h['date'])[:10]: h['close'] for h in tnx_history}
                spread_data = []
                for h in irx_history:
                    date_str = h['date'].strftime('%Y-%m-%d') if hasattr(h['date'], 'strftime') else str(h['date'])[:10]
                    if date_str in tnx_by_date:
                        spread = tnx_by_date[date_str] - h['close']
                        spread_data.append({'date': date_str, 'value': spread})

                result['market_describers']['yield_curve'] = {
                    'name': 'Yield Curve (10Y-13W Spread)',
                    'data': spread_data,
                    'color': '#3fb950',
                    'unit': '%'
                }

            # SPY and URTH for trend regime (MA comparison)
            spy_history = self.yf_client.get_history('SPY', period=period, interval='1d')
            urth_history = self.yf_client.get_history('URTH', period=period, interval='1d')

            trend_comparison = {}

            if spy_history:
                # Calculate MA20/MA50 ratio as trend indicator for SPY
                closes = [h['close'] for h in spy_history]
                trend_data = []
                for i, h in enumerate(spy_history):
                    if i >= 50:
                        ma20 = sum(closes[i-19:i+1]) / 20
                        ma50 = sum(closes[i-49:i+1]) / 50
                        ratio = (ma20 / ma50 - 1) * 100  # % above/below
                        date_str = h['date'].strftime('%Y-%m-%d') if hasattr(h['date'], 'strftime') else str(h['date'])[:10]
                        trend_data.append({'date': date_str, 'value': ratio})

                trend_comparison['spy'] = {'data': trend_data}

                # Keep legacy single-line for backward compatibility
                result['market_describers']['trend'] = {
                    'name': 'SPY Trend (MA20/MA50)',
                    'data': trend_data,
                    'color': '#3fb950',
                    'unit': '%'
                }

            if urth_history:
                # Calculate MA20/MA50 ratio for URTH
                closes = [h['close'] for h in urth_history]
                trend_data = []
                for i, h in enumerate(urth_history):
                    if i >= 50:
                        ma20 = sum(closes[i-19:i+1]) / 20
                        ma50 = sum(closes[i-49:i+1]) / 50
                        ratio = (ma20 / ma50 - 1) * 100  # % above/below
                        date_str = h['date'].strftime('%Y-%m-%d') if hasattr(h['date'], 'strftime') else str(h['date'])[:10]
                        trend_data.append({'date': date_str, 'value': ratio})

                trend_comparison['urth'] = {'data': trend_data}

            if trend_comparison:
                result['market_describers']['trend_comparison'] = trend_comparison

            # Sector ETFs for Factor Rotation (all 11 GICS sectors)
            sector_etfs = {
                'XLK': 'Tech',
                'XLF': 'Financials',
                'XLE': 'Energy',
                'XLV': 'Healthcare',
                'XLY': 'Cons Disc',
                'XLP': 'Cons Staples',
                'XLI': 'Industrials',
                'XLB': 'Materials',
                'XLRE': 'Real Estate',
                'XLU': 'Utilities',
                'XLC': 'Comm Svcs'
            }

            sector_histories = {}
            for symbol, name in sector_etfs.items():
                hist = self.yf_client.get_history(symbol, period=period, interval='1d')
                if hist:
                    sector_histories[name] = hist

            if sector_histories:
                # Calculate relative performance vs SPY
                spy_by_date = {}
                if spy_history:
                    for h in spy_history:
                        date_str = h['date'].strftime('%Y-%m-%d') if hasattr(h['date'], 'strftime') else str(h['date'])[:10]
                        spy_by_date[date_str] = h['close']

                for sector_name, hist in sector_histories.items():
                    perf_data = []
                    base_price = hist[0]['close'] if hist else 1
                    base_spy = spy_history[0]['close'] if spy_history else 1

                    for h in hist:
                        date_str = h['date'].strftime('%Y-%m-%d') if hasattr(h['date'], 'strftime') else str(h['date'])[:10]
                        if date_str in spy_by_date and base_price > 0 and base_spy > 0:
                            sector_return = (h['close'] / base_price - 1) * 100
                            spy_return = (spy_by_date[date_str] / base_spy - 1) * 100
                            relative_perf = sector_return - spy_return
                            perf_data.append({'date': date_str, 'value': relative_perf})

                    # Assign distinct colors to each sector
                    sector_colors = {
                        'Tech': '#3fb950', 'Financials': '#58a6ff', 'Energy': '#f0883e', 'Healthcare': '#a371f7',
                        'Cons Disc': '#f85149', 'Cons Staples': '#56d4dd', 'Industrials': '#db61a2',
                        'Materials': '#7ee787', 'Real Estate': '#ffa657', 'Utilities': '#79c0ff', 'Comm Svcs': '#d2a8ff'
                    }
                    color = sector_colors.get(sector_name, '#8b949e')
                    result['directional_describers'][f'sector_{sector_name.lower()}'] = {
                        'name': f'{sector_name} vs SPY',
                        'data': perf_data,
                        'color': color,
                        'unit': '%'
                    }

            # Risk appetite proxy: VIX inverse (lower VIX = higher risk appetite)
            if vix_history:
                risk_data = []
                for h in vix_history:
                    date_str = h['date'].strftime('%Y-%m-%d') if hasattr(h['date'], 'strftime') else str(h['date'])[:10]
                    # Invert VIX: 100 - VIX gives higher values for risk-on
                    risk_score = max(0, min(100, 100 - h['close'] * 2))  # Scale to 0-100
                    risk_data.append({'date': date_str, 'value': risk_score})

                result['directional_describers']['risk_appetite'] = {
                    'name': 'Risk Appetite Index',
                    'data': risk_data,
                    'color': '#3fb950',
                    'unit': ''
                }

            # Buffett Indicator: Market Cap / GDP ratio
            # Use Wilshire 5000 (^W5000) or VTI as proxy for total market cap
            wilshire_history = self.yf_client.get_history('^W5000', period=period, interval='1d')
            if not wilshire_history:
                # Fallback to VTI (Vanguard Total Market ETF)
                wilshire_history = self.yf_client.get_history('VTI', period=period, interval='1d')

            if wilshire_history:
                buffett_data = []
                # US GDP estimate: ~$28.5T in 2024, growing ~2.5%/year
                # Wilshire 5000 index ≈ total market cap in billions
                # For VTI, scale up (VTI price * ~55B shares outstanding / 1000)
                is_vti = wilshire_history[0]['close'] < 1000  # VTI is ~$250, Wilshire is ~50000

                for h in wilshire_history:
                    date_str = h['date'].strftime('%Y-%m-%d') if hasattr(h['date'], 'strftime') else str(h['date'])[:10]

                    # Estimate GDP for this date (quarterly growth approximation)
                    try:
                        date_obj = h['date'] if hasattr(h['date'], 'year') else datetime.strptime(date_str, '%Y-%m-%d')
                        years_from_2024 = (date_obj.year - 2024) + (date_obj.month - 1) / 12
                        gdp_estimate = 28.5 * (1.025 ** years_from_2024)  # GDP in trillions
                    except:
                        gdp_estimate = 28.5

                    # Calculate market cap / GDP ratio
                    if is_vti:
                        # VTI: approximate market cap = price * 220 (scaling factor to get ~$55T market cap)
                        market_cap = h['close'] * 220  # Results in market cap in trillions
                    else:
                        # Wilshire 5000: index value ≈ market cap in billions, divide by 1000 for trillions
                        market_cap = h['close'] / 1000

                    buffett_ratio = (market_cap / gdp_estimate) * 100  # As percentage
                    buffett_data.append({'date': date_str, 'value': round(buffett_ratio, 1)})

                result['directional_describers']['buffett_indicator'] = {
                    'name': 'Buffett Indicator (Market Cap/GDP)',
                    'data': buffett_data,
                    'color': '#ffa657',
                    'unit': '%'
                }

        except Exception as e:
            logger.warning(f"Error fetching historical indicators: {e}")
            result['error'] = str(e)

        return result


# Global instance
market_engine = MarketStateEngine()
