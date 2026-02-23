"""Backtesting engine for trading strategies"""
import logging
from datetime import datetime
from dataclasses import dataclass, field

from src.database import init_db, save_prices, get_prices, get_price_count, save_backtest
from src.yfinance_client import YFinanceClient
from src.strategy import calculate_rsi

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Represents a single trade"""
    date: datetime
    action: str  # BUY or SELL
    price: float
    quantity: int
    value: float = 0
    pnl: float = 0


@dataclass
class BacktestResult:
    """Results of a backtest run"""
    symbol: str
    strategy: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_pct: float
    num_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)


class MomentumStrategy:
    """
    MA Crossover + RSI + Volume + Fundamental strategy with index filter
    """

    def __init__(self, short_window=10, long_window=30, threshold=0.01,
                 stop_loss_pct=None, trailing_stop_pct=None, rsi_filter=True,
                 rsi_overbought=70, rsi_oversold=30,
                 index_filter=False, index_drop_threshold=0.02,
                 min_hold_days=0, trail_after_profit_pct=None,
                 volume_filter=False, volume_ma_period=20,
                 volume_confirm_threshold=1.5, volume_min_threshold=0.5,
                 fundamental_filter=False, earnings_blackout_days=3,
                 pead_strategy=False, pead_window_days=7):
        self.short_window = short_window
        self.long_window = long_window
        self.threshold = threshold
        self.stop_loss_pct = stop_loss_pct  # e.g., 0.10 for 10% from entry
        self.trailing_stop_pct = trailing_stop_pct  # e.g., 0.08 for 8% from peak
        self.rsi_filter = rsi_filter
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.rsi_period = 14
        self.index_filter = index_filter  # Check index before selling
        self.index_drop_threshold = index_drop_threshold  # e.g., 0.02 = 2% drop
        self.min_hold_days = min_hold_days  # Minimum days to hold before any exit
        self.trail_after_profit_pct = trail_after_profit_pct  # Only trail after X% profit

        # Volume filter settings
        self.volume_filter = volume_filter
        self.volume_ma_period = volume_ma_period
        self.volume_confirm_threshold = volume_confirm_threshold  # e.g., 1.5 = 150% of avg
        self.volume_min_threshold = volume_min_threshold  # e.g., 0.5 = 50% of avg

        # Fundamental filter settings
        self.fundamental_filter = fundamental_filter
        self.earnings_blackout_days = earnings_blackout_days

        # PEAD (Post-Earnings Announcement Drift) strategy
        self.pead_strategy = pead_strategy
        self.pead_window_days = pead_window_days  # Days after earnings to consider signal

        name_parts = [f"MA({short_window}/{long_window})"]
        if stop_loss_pct:
            name_parts.append(f"SL:{int(stop_loss_pct*100)}%")
        if trailing_stop_pct:
            name_parts.append(f"TS:{int(trailing_stop_pct*100)}%")
        if trail_after_profit_pct:
            name_parts.append(f"TP>{int(trail_after_profit_pct*100)}%")
        if min_hold_days:
            name_parts.append(f"HOLD:{min_hold_days}d")
        if rsi_filter:
            name_parts.append(f"RSI<{rsi_overbought}")
        if volume_filter:
            name_parts.append(f"VOL>{volume_confirm_threshold}x")
        if fundamental_filter:
            name_parts.append(f"EARN:{earnings_blackout_days}d")
        if pead_strategy:
            name_parts.append(f"PEAD:{pead_window_days}d")
        if index_filter:
            name_parts.append(f"IDX:{int(index_drop_threshold*100)}%")
        self.name = " + ".join(name_parts)

    def calculate_rsi(self, prices: list, index: int) -> float:
        """Calculate RSI at a specific index"""
        if index < self.rsi_period:
            return 50  # Neutral default

        gains = []
        losses = []
        for i in range(index - self.rsi_period + 1, index + 1):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains) / self.rsi_period
        avg_loss = sum(losses) / self.rsi_period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def check_stop_loss(self, current_price: float, entry_price: float) -> bool:
        """Check if stop-loss is triggered"""
        if not self.stop_loss_pct or entry_price <= 0:
            return False
        loss_pct = (entry_price - current_price) / entry_price
        return loss_pct >= self.stop_loss_pct

    def check_trailing_stop(self, current_price: float, peak_price: float,
                            entry_price: float = 0) -> bool:
        """Check if trailing stop is triggered (price dropped X% from peak)

        Only triggers if:
        1. Price dropped trailing_stop_pct from peak
        2. If trail_after_profit_pct is set, only after we're up that much from entry
        """
        if not self.trailing_stop_pct or peak_price <= 0:
            return False

        # Check if we need to be in profit before trailing
        if self.trail_after_profit_pct and entry_price > 0:
            profit_pct = (peak_price - entry_price) / entry_price
            if profit_pct < self.trail_after_profit_pct:
                return False  # Not enough profit yet, don't trail

        drop_pct = (peak_price - current_price) / peak_price
        return drop_pct >= self.trailing_stop_pct

    def get_volume_ma(self, volumes: list, index: int) -> float:
        """Calculate average volume at a specific index"""
        if not volumes or index < self.volume_ma_period:
            if volumes and index > 0:
                return sum(volumes[:index+1]) / (index + 1)
            return 0
        return sum(volumes[index - self.volume_ma_period + 1:index + 1]) / self.volume_ma_period

    def get_relative_volume(self, volumes: list, index: int) -> float:
        """Calculate current volume relative to average (1.0 = average)"""
        if not volumes or index < 0 or index >= len(volumes):
            return 1.0  # Default to neutral
        current_volume = volumes[index]
        avg_volume = self.get_volume_ma(volumes, index)
        if avg_volume <= 0:
            return 1.0
        return current_volume / avg_volume

    def check_volume_confirmation(self, volumes: list, index: int) -> bool:
        """Check if volume is high enough to confirm a signal"""
        if not self.volume_filter:
            return True  # No filter = always confirmed
        return self.get_relative_volume(volumes, index) >= self.volume_confirm_threshold

    def check_volume_too_low(self, volumes: list, index: int) -> bool:
        """Check if volume is too low to trade"""
        if not self.volume_filter:
            return False  # No filter = never too low
        return self.get_relative_volume(volumes, index) < self.volume_min_threshold

    def check_pead_signal(self, date, earnings_data: dict = None) -> tuple:
        """Check for Post-Earnings Announcement Drift signal

        Args:
            date: Current date to check
            earnings_data: Dict with earnings date -> surprise_pct mapping

        Returns:
            (signal, reason) tuple where signal is 'BUY', 'SELL', or None
        """
        if not self.pead_strategy or not earnings_data:
            return None, None

        from datetime import datetime, timedelta

        # Convert date to datetime if needed
        if isinstance(date, str):
            try:
                date = datetime.strptime(date[:10], '%Y-%m-%d')
            except:
                return None, None
        elif hasattr(date, 'to_pydatetime'):
            date = date.to_pydatetime()

        # Make sure date is naive datetime
        if hasattr(date, 'tzinfo') and date.tzinfo is not None:
            date = date.replace(tzinfo=None)

        # Check if we're within PEAD window after any earnings
        for earnings_date, surprise_pct in earnings_data.items():
            # Convert earnings_date if needed
            if isinstance(earnings_date, str):
                try:
                    earnings_date = datetime.strptime(earnings_date[:10], '%Y-%m-%d')
                except:
                    continue

            if hasattr(earnings_date, 'tzinfo') and earnings_date.tzinfo is not None:
                earnings_date = earnings_date.replace(tzinfo=None)

            # Check if within PEAD window (after earnings, not before)
            days_after = (date - earnings_date).days
            if 0 <= days_after <= self.pead_window_days:
                # Within PEAD window - generate signal based on surprise
                if surprise_pct is not None:
                    if surprise_pct > 10:
                        return 'BUY', f"PEAD: +{surprise_pct:.1f}% beat ({days_after}d after earnings)"
                    elif surprise_pct > 0:
                        return 'BUY', f"PEAD: +{surprise_pct:.1f}% beat ({days_after}d after earnings)"
                    elif surprise_pct < -10:
                        return 'SELL', f"PEAD: {surprise_pct:.1f}% miss ({days_after}d after earnings)"

        return None, None

    def check_earnings_blackout(self, date, earnings_dates: list = None) -> bool:
        """Check if date is within earnings blackout period

        Args:
            date: Current date to check (datetime or string)
            earnings_dates: List of earnings dates (datetime objects)

        Returns:
            True if in blackout period
        """
        if not self.fundamental_filter or not earnings_dates:
            return False

        from datetime import datetime, timedelta

        # Convert date to datetime if it's a string
        if isinstance(date, str):
            try:
                date = datetime.strptime(date[:10], '%Y-%m-%d')
            except:
                return False
        elif hasattr(date, 'to_pydatetime'):
            date = date.to_pydatetime()

        # Make sure date is naive datetime for comparison
        if hasattr(date, 'tzinfo') and date.tzinfo is not None:
            date = date.replace(tzinfo=None)

        for earnings_date in earnings_dates:
            # Make earnings_date naive too
            if hasattr(earnings_date, 'tzinfo') and earnings_date.tzinfo is not None:
                earnings_date = earnings_date.replace(tzinfo=None)

            # Check if within blackout_days before or after earnings
            delta = abs((date - earnings_date).days)
            if delta <= self.earnings_blackout_days:
                return True

        return False

    def check_index_selloff(self, index_prices: list, idx: int, lookback: int = 5) -> bool:
        """Check if the index is in a selloff (dropped X% over lookback period)

        Returns True if index is selling off (should HOLD instead of SELL)
        """
        if not self.index_filter or not index_prices or idx < lookback:
            return False

        # Compare current index price to price N days ago
        current_idx = index_prices[idx]
        past_idx = index_prices[idx - lookback]

        if past_idx <= 0:
            return False

        idx_change = (current_idx - past_idx) / past_idx

        # If index dropped more than threshold, it's a market selloff
        return idx_change <= -self.index_drop_threshold

    def get_signal(self, prices: list, index: int, entry_price: float = 0,
                   peak_price: float = 0, index_prices: list = None,
                   days_held: int = 0, volumes: list = None,
                   current_date=None, earnings_dates: list = None,
                   earnings_data: dict = None) -> str:
        """Get signal at a specific point in price history"""
        if index < self.long_window:
            return 'HOLD'

        current_price = prices[index]

        # Check minimum hold period (except for hard stop-loss)
        min_hold_met = days_held >= self.min_hold_days

        # Check trailing stop (only if min hold met and profit requirement met)
        if min_hold_met and peak_price > 0:
            if self.check_trailing_stop(current_price, peak_price, entry_price):
                return 'TRAILING_STOP'

        # Check stop-loss (always active - protect capital)
        if entry_price > 0 and self.check_stop_loss(current_price, entry_price):
            return 'STOP_LOSS'

        # Volume filter - block all trades on very low volume
        if self.check_volume_too_low(volumes, index):
            return 'HOLD'  # Volume too low

        # PEAD strategy - check for post-earnings signal (overrides other signals)
        if self.pead_strategy and earnings_data:
            pead_signal, pead_reason = self.check_pead_signal(current_date, earnings_data)
            if pead_signal == 'BUY' and entry_price == 0:
                # Check RSI - don't chase overbought
                rsi = self.calculate_rsi(prices, index) if self.rsi_filter else 50
                if rsi <= self.rsi_overbought:
                    return 'BUY'  # PEAD buy signal
            elif pead_signal == 'SELL' and entry_price > 0:
                return 'SELL'  # PEAD sell signal

        # Earnings blackout - block trades near earnings (only if not using PEAD)
        if not self.pead_strategy and current_date and self.check_earnings_blackout(current_date, earnings_dates):
            return 'HOLD'  # Earnings blackout

        # Get price window ending at index
        window = prices[index - self.long_window + 1:index + 1]

        short_ma = sum(window[-self.short_window:]) / self.short_window
        long_ma = sum(window) / self.long_window

        # Calculate RSI for filtering
        rsi = self.calculate_rsi(prices, index) if self.rsi_filter else 50

        # BUY signal with RSI filter, volume filter, and index filter
        if short_ma > long_ma * (1 + self.threshold):
            if self.rsi_filter and rsi > self.rsi_overbought:
                return 'HOLD'  # Skip buy - overbought
            if not self.check_volume_confirmation(volumes, index):
                return 'HOLD'  # Skip buy - volume too low
            if self.check_index_selloff(index_prices, index):
                return 'HOLD_IDX_BUY'  # Skip buy - market selloff, wait for stability
            return 'BUY'

        # SELL signal with volume filter and index filter (only if min hold met)
        elif short_ma < long_ma * (1 - self.threshold):
            if not min_hold_met:
                return 'HOLD'  # Haven't held long enough
            if not self.check_volume_confirmation(volumes, index):
                return 'HOLD'  # Skip sell - volume too low
            # Check if this is a market-wide selloff
            if self.check_index_selloff(index_prices, index):
                return 'HOLD_IDX'  # Hold - market selloff, not stock-specific
            return 'SELL'

        return 'HOLD'


class Backtester:
    """Backtesting engine"""

    def __init__(self, initial_capital: float = 10000, position_size: int = 15,
                 index_symbol: str = None):
        self.initial_capital = initial_capital
        self.position_size = position_size
        self.index_symbol = index_symbol  # e.g., 'KWEB', 'SPY', 'QQQ'

    def fetch_data(self, symbol: str, period: str = '1y') -> list:
        """Fetch and cache historical data"""
        # Check if we have data in DB
        count = get_price_count(symbol)

        if count < 200:  # Need more data
            logger.info(f"Fetching {symbol} data from Yahoo Finance...")
            client = YFinanceClient()
            history = client.get_history(symbol, period)

            if history:
                save_prices(symbol, history, 'yfinance')
                return history
            else:
                logger.error("Failed to fetch data")
                return []

        logger.info(f"Using {count} cached prices for {symbol}")
        return get_prices(symbol)

    def run(self, symbol: str, strategy, period: str = '1y') -> BacktestResult:
        """Run backtest on historical data"""
        # Get stock data
        data = self.fetch_data(symbol, period)
        if not data:
            raise ValueError("No data available for backtesting")

        prices = [d['close'] for d in data]
        volumes = [d.get('volume', 0) for d in data]
        dates = [d.get('date') or d.get('timestamp') for d in data]

        # Get earnings dates and data if fundamental filter or PEAD is enabled
        earnings_dates = []
        earnings_data = {}  # date -> surprise_pct mapping for PEAD
        if strategy.fundamental_filter or strategy.pead_strategy:
            # NIO quarterly earnings schedule with surprise data
            # Format: (date, surprise_pct) - positive = beat, negative = miss
            from datetime import datetime
            known_earnings_with_surprise = [
                (datetime(2025, 11, 25), 27.4),  # Q3 2025 - beat by 27.4%
                (datetime(2025, 9, 9), 15.2),    # Q2 2025 - beat by 15.2%
                (datetime(2025, 6, 10), 8.5),    # Q1 2025 - beat by 8.5%
                (datetime(2025, 3, 4), -5.3),    # Q4 2024 - miss by 5.3%
                (datetime(2024, 12, 10), 12.1),  # Q3 2024 - beat by 12.1%
                (datetime(2024, 9, 10), -8.7),   # Q2 2024 - miss by 8.7%
                (datetime(2024, 6, 6), 22.3),    # Q1 2024 - beat by 22.3%
                (datetime(2024, 3, 5), 5.8),     # Q4 2023 - beat by 5.8%
            ]
            earnings_dates = [e[0] for e in known_earnings_with_surprise]
            earnings_data = {e[0]: e[1] for e in known_earnings_with_surprise}
            logger.info(f"Using {len(earnings_dates)} known earnings dates")
            if strategy.pead_strategy:
                logger.info(f"PEAD strategy enabled: {strategy.pead_window_days} day window")

        # Get index data if index filter is enabled
        index_prices = None
        if self.index_symbol and strategy.index_filter:
            logger.info(f"Fetching index data: {self.index_symbol}")
            index_data = self.fetch_data(self.index_symbol, period)
            if index_data:
                # Align index data with stock data by date
                index_by_date = {str(d.get('date') or d.get('timestamp'))[:10]: d['close']
                                 for d in index_data}
                index_prices = []
                for d in dates:
                    date_key = str(d)[:10]
                    idx_price = index_by_date.get(date_key, 0)
                    index_prices.append(idx_price)
                logger.info(f"Loaded {len([p for p in index_prices if p > 0])} index prices")

        # Initialize state
        capital = self.initial_capital
        position = 0
        entry_price = 0
        entry_day = 0  # Track which day we entered
        peak_price_since_entry = 0  # Track highest price since entry for trailing stop
        trades = []
        equity_curve = []
        peak_equity = capital

        max_drawdown = 0
        daily_returns = []
        prev_equity = capital

        logger.info(f"Running backtest: {symbol} with {strategy.name}")
        logger.info(f"Period: {dates[0]} to {dates[-1]} ({len(prices)} bars)")

        # Run simulation
        for i in range(strategy.long_window, len(prices)):
            price = prices[i]
            date = dates[i]

            # Update peak price since entry
            if position > 0 and price > peak_price_since_entry:
                peak_price_since_entry = price

            days_held = i - entry_day if position > 0 else 0
            signal = strategy.get_signal(prices, i,
                                         entry_price if position > 0 else 0,
                                         peak_price_since_entry if position > 0 else 0,
                                         index_prices,
                                         days_held,
                                         volumes,
                                         date,
                                         earnings_dates,
                                         earnings_data)

            # Calculate current equity
            equity = capital + (position * price)
            equity_curve.append({'date': date, 'equity': equity})

            # Track daily returns
            if prev_equity > 0:
                daily_return = (equity - prev_equity) / prev_equity
                daily_returns.append(daily_return)
            prev_equity = equity

            # Track drawdown
            if equity > peak_equity:
                peak_equity = equity
            drawdown = peak_equity - equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown

            # Execute trades
            if signal == 'BUY' and position == 0:
                # Buy
                quantity = min(self.position_size, int(capital / price))
                if quantity > 0:
                    cost = quantity * price
                    capital -= cost
                    position = quantity
                    entry_price = price
                    entry_day = i  # Track entry day for min hold calculation
                    peak_price_since_entry = price  # Reset peak tracking
                    trades.append(Trade(
                        date=date,
                        action='BUY',
                        price=price,
                        quantity=quantity,
                        value=cost
                    ))

            elif signal == 'SELL' and position > 0:
                # Sell
                revenue = position * price
                pnl = revenue - (position * entry_price)
                capital += revenue

                trades.append(Trade(
                    date=date,
                    action='SELL',
                    price=price,
                    quantity=position,
                    value=revenue,
                    pnl=pnl
                ))
                position = 0
                entry_price = 0
                entry_day = 0

            elif signal == 'STOP_LOSS' and position > 0:
                # Stop-loss triggered
                revenue = position * price
                pnl = revenue - (position * entry_price)
                capital += revenue

                trades.append(Trade(
                    date=date,
                    action='STOP_LOSS',
                    price=price,
                    quantity=position,
                    value=revenue,
                    pnl=pnl
                ))
                position = 0
                entry_price = 0
                entry_day = 0
                peak_price_since_entry = 0

            elif signal == 'TRAILING_STOP' and position > 0:
                # Trailing stop triggered - lock in profits
                revenue = position * price
                pnl = revenue - (position * entry_price)
                capital += revenue

                trades.append(Trade(
                    date=date,
                    action='TRAIL_STOP',
                    price=price,
                    quantity=position,
                    value=revenue,
                    pnl=pnl
                ))
                position = 0
                entry_price = 0
                entry_day = 0
                peak_price_since_entry = 0

        # Close any open position at end
        if position > 0:
            final_price = prices[-1]
            revenue = position * final_price
            pnl = revenue - (position * entry_price)
            capital += revenue
            trades.append(Trade(
                date=dates[-1],
                action='SELL (CLOSE)',
                price=final_price,
                quantity=position,
                value=revenue,
                pnl=pnl
            ))
            position = 0

        # Calculate results
        final_capital = capital
        total_return = final_capital - self.initial_capital
        total_return_pct = (total_return / self.initial_capital) * 100

        # Win/loss stats (include all exit types)
        sell_trades = [t for t in trades if t.action in ('SELL', 'SELL (CLOSE)', 'STOP_LOSS', 'TRAIL_STOP')]
        winning = [t for t in sell_trades if t.pnl > 0]
        losing = [t for t in sell_trades if t.pnl <= 0]
        win_rate = len(winning) / len(sell_trades) * 100 if sell_trades else 0

        # Sharpe ratio (annualized, assuming daily data)
        if daily_returns and len(daily_returns) > 1:
            import statistics
            avg_return = statistics.mean(daily_returns)
            std_return = statistics.stdev(daily_returns)
            sharpe = (avg_return / std_return) * (252 ** 0.5) if std_return > 0 else 0
        else:
            sharpe = 0

        max_dd_pct = (max_drawdown / peak_equity) * 100 if peak_equity > 0 else 0

        result = BacktestResult(
            symbol=symbol,
            strategy=strategy.name,
            start_date=str(dates[strategy.long_window]),
            end_date=str(dates[-1]),
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            total_return=total_return,
            total_return_pct=total_return_pct,
            num_trades=len(trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=win_rate,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_dd_pct,
            sharpe_ratio=sharpe,
            trades=trades,
            equity_curve=equity_curve
        )

        # Save to database
        save_backtest({
            'symbol': symbol,
            'start_date': result.start_date,
            'end_date': result.end_date,
            'strategy': strategy.name,
            'initial_capital': self.initial_capital,
            'final_capital': final_capital,
            'total_return': total_return_pct,
            'num_trades': len(trades),
            'win_rate': win_rate,
            'max_drawdown': max_dd_pct,
            'sharpe_ratio': sharpe
        })

        return result


def print_results(result: BacktestResult):
    """Print backtest results in a nice format"""
    print(f"\n{'='*60}")
    print(f"  BACKTEST RESULTS: {result.symbol}")
    print(f"{'='*60}")
    print(f"  Strategy: {result.strategy}")
    print(f"  Period: {result.start_date} to {result.end_date}")
    print(f"{'='*60}\n")

    print(f"  PERFORMANCE")
    print(f"  {'-'*40}")
    print(f"  Initial Capital:  ${result.initial_capital:,.2f}")
    print(f"  Final Capital:    ${result.final_capital:,.2f}")
    print(f"  Total Return:     ${result.total_return:,.2f} ({result.total_return_pct:+.2f}%)")
    print()

    print(f"  RISK METRICS")
    print(f"  {'-'*40}")
    print(f"  Max Drawdown:     ${result.max_drawdown:,.2f} ({result.max_drawdown_pct:.2f}%)")
    print(f"  Sharpe Ratio:     {result.sharpe_ratio:.2f}")
    print()

    print(f"  TRADE STATISTICS")
    print(f"  {'-'*40}")
    print(f"  Total Trades:     {result.num_trades}")
    print(f"  Winning Trades:   {result.winning_trades}")
    print(f"  Losing Trades:    {result.losing_trades}")
    print(f"  Win Rate:         {result.win_rate:.1f}%")
    print()

    # Print trades
    if result.trades:
        print(f"  TRADE LOG")
        print(f"  {'-'*40}")
        for t in result.trades:
            pnl_str = f" (PnL: ${t.pnl:+.2f})" if t.pnl else ""
            print(f"  {t.date} | {t.action:12} | {t.quantity:3} @ ${t.price:.2f}{pnl_str}")

    print()

    # Equity curve (ASCII)
    if result.equity_curve:
        print_equity_curve(result.equity_curve)


def print_equity_curve(equity_curve: list, width=50, height=10):
    """Print ASCII equity curve"""
    values = [e['equity'] for e in equity_curve]
    min_v = min(values)
    max_v = max(values)
    range_v = max_v - min_v or 1

    # Sample if too many points
    step = max(1, len(values) // width)
    sampled = values[::step][:width]

    print(f"  EQUITY CURVE")
    print(f"  {'-'*40}")

    for row in range(height, -1, -1):
        threshold = row / height

        if row == height:
            label = f"${max_v:,.0f}"
        elif row == 0:
            label = f"${min_v:,.0f}"
        else:
            label = ""

        line = f"  {label:>10} |"

        for v in sampled:
            normalized = (v - min_v) / range_v
            if normalized >= threshold:
                line += "#"  # ASCII safe character
            else:
                line += " "

        print(line)

    print(f"  {' '*10} +{'-' * len(sampled)}")
    print()


def run_backtest(symbol: str = 'NIO', period: str = '1y', capital: float = 10000,
                 position_size: int = 15, short_ma: int = 10, long_ma: int = 30,
                 stop_loss_pct: float = None, trailing_stop_pct: float = None,
                 rsi_filter: bool = False, index_symbol: str = None,
                 index_filter: bool = False, index_drop_threshold: float = 0.02,
                 min_hold_days: int = 0, trail_after_profit_pct: float = None,
                 volume_filter: bool = False, volume_ma_period: int = 20,
                 volume_confirm_threshold: float = 1.5, volume_min_threshold: float = 0.5,
                 fundamental_filter: bool = False, earnings_blackout_days: int = 3,
                 pead_strategy: bool = False, pead_window_days: int = 7):
    """Run a backtest with configurable settings

    Args:
        symbol: Stock symbol to backtest
        period: Time period ('1y', '2y', '6mo', etc.)
        capital: Initial capital
        position_size: Max shares per trade
        short_ma: Short moving average window
        long_ma: Long moving average window
        stop_loss_pct: Stop loss percentage (e.g., 0.10 for 10%)
        trailing_stop_pct: Trailing stop percentage (e.g., 0.08 for 8%)
        rsi_filter: Enable RSI overbought filter
        index_symbol: Index to compare against (e.g., 'KWEB', 'SPY')
        index_filter: Enable index selloff filter
        index_drop_threshold: Index drop % to consider selloff (e.g., 0.02 for 2%)
        min_hold_days: Minimum days to hold before any exit (except stop-loss)
        trail_after_profit_pct: Only start trailing after this profit % (e.g., 0.05 for 5%)
        volume_filter: Enable volume confirmation filter
        volume_ma_period: Period for volume moving average
        volume_confirm_threshold: Require volume >= X times average for trades (e.g., 1.5)
        volume_min_threshold: Block trades when volume < X times average (e.g., 0.5)
        fundamental_filter: Enable earnings blackout filter
        earnings_blackout_days: Days before/after earnings to avoid trading
        pead_strategy: Enable Post-Earnings Announcement Drift strategy
        pead_window_days: Days after earnings to consider PEAD signal
    """
    strategy = MomentumStrategy(
        short_window=short_ma,
        long_window=long_ma,
        threshold=0.01,
        stop_loss_pct=stop_loss_pct,
        trailing_stop_pct=trailing_stop_pct,
        rsi_filter=rsi_filter,
        rsi_overbought=70,
        index_filter=index_filter,
        index_drop_threshold=index_drop_threshold,
        min_hold_days=min_hold_days,
        trail_after_profit_pct=trail_after_profit_pct,
        volume_filter=volume_filter,
        volume_ma_period=volume_ma_period,
        volume_confirm_threshold=volume_confirm_threshold,
        volume_min_threshold=volume_min_threshold,
        fundamental_filter=fundamental_filter,
        earnings_blackout_days=earnings_blackout_days,
        pead_strategy=pead_strategy,
        pead_window_days=pead_window_days
    )
    backtester = Backtester(
        initial_capital=capital,
        position_size=position_size,
        index_symbol=index_symbol
    )
    result = backtester.run(symbol, strategy, period)
    print_results(result)
    return result


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    print("\n" + "="*60)
    print("  BACKTEST: IMPROVED STRATEGY v2")
    print("="*60)

    run_backtest(
        symbol='NIO',
        period='1y',
        capital=10000,
        position_size=100,
        short_ma=3,                  # Tighter MA (was 5)
        long_ma=10,                  # Tighter MA (was 15)
        stop_loss_pct=0.10,          # 10% stop-loss from entry
        trailing_stop_pct=0.08,      # 8% trailing stop (was 5%)
        rsi_filter=True,             # Don't buy when RSI > 70
        index_symbol='KWEB',         # Compare to Chinese tech ETF
        index_filter=True,           # Hold during market selloffs
        index_drop_threshold=0.02,   # 2% index drop = selloff
        min_hold_days=5,             # Hold at least 5 days
        trail_after_profit_pct=0.05  # Only trail after 5% profit
    )
