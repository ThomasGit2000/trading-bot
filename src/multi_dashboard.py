"""
Compact Multi-Stock Trading Dashboard
One stock per row with all key metrics.
"""
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from typing import List
import uvicorn
import json

from src.dashboard_state import bot_state
from src.yfinance_client import YFinanceClient
from src.trading_control import trading_control

yf_client = YFinanceClient()

app = FastAPI(title="Multi-Stock Trading Dashboard")


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)


manager = ConnectionManager()

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Master Board</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
            background: #0d1117; color: #c9d1d9; padding: 12px;
            font-size: 13px;
        }
        .header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #30363d;
        }
        .header h1 { font-size: 16px; font-weight: 600; }
        .status-badge {
            padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600;
        }
        .status-live { background: #238636; }
        .status-dry { background: #f0883e; }
        .status-disconnected { background: #da3633; }

        .master-btn {
            padding: 6px 16px; border-radius: 6px; font-size: 12px; font-weight: 700;
            border: 2px solid; cursor: pointer; transition: all 0.2s;
            text-transform: uppercase; letter-spacing: 0.5px;
        }
        .master-btn.trading-live {
            background: #238636; border-color: #2ea043; color: white;
            box-shadow: 0 0 10px rgba(35, 134, 54, 0.5);
        }
        .master-btn.trading-live:hover {
            background: #2ea043; box-shadow: 0 0 15px rgba(35, 134, 54, 0.7);
        }
        .master-btn.trading-stopped {
            background: #9e6a03; border-color: #bb8009; color: white;
        }
        .master-btn.trading-stopped:hover {
            background: #bb8009;
        }
        .master-btn:disabled {
            opacity: 0.5; cursor: not-allowed;
        }

        table { width: 100%; border-collapse: collapse; }
        th {
            text-align: left; padding: 6px 8px; font-size: 10px;
            color: #8b949e; text-transform: uppercase; border-bottom: 1px solid #30363d;
        }
        th.sortable { cursor: pointer; user-select: none; }
        th.sortable:hover { color: #58a6ff; }
        th.sortable .sort-arrow { font-size: 8px; margin-left: 2px; }
        th.sortable.asc .sort-arrow::after { content: ' ▲'; }
        th.sortable.desc .sort-arrow::after { content: ' ▼'; }
        td { padding: 8px; border-bottom: 1px solid #21262d; vertical-align: middle; }
        tr:hover { background: #161b22; cursor: pointer; }
        tr.has-position { border-left: 3px solid #238636; }

        .symbol { font-weight: 700; color: #58a6ff; font-size: 14px; }
        .category-cell { font-size: 10px; color: #8b949e; max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .price { font-weight: 600; }
        .price-up { color: #3fb950; }
        .price-down { color: #f85149; }
        .price-change-sm { font-size: 11px; margin-left: 4px; }
        .position { color: #3fb950; }
        .no-position { color: #8b949e; }

        .signal-bar {
            width: 80px; height: 8px;
            background: linear-gradient(90deg, #da3633 0%, #8b949e 50%, #238636 100%);
            border-radius: 4px; position: relative; display: inline-block;
        }
        .signal-indicator {
            position: absolute; top: -2px; width: 3px; height: 12px;
            background: #fff; border-radius: 1px;
            transform: translateX(-50%);
            box-shadow: 0 0 3px rgba(255,255,255,0.8);
        }
        .signal-label {
            display: inline-block; width: 45px; font-size: 11px; font-weight: 600;
            text-align: center; padding: 2px 4px; border-radius: 3px;
        }
        .signal-buy { background: #238636; color: white; }
        .signal-sell { background: #da3633; color: white; }
        .signal-hold { background: #30363d; color: #8b949e; }

        .ma-val { font-size: 12px; }
        .ma-short { color: #58a6ff; }
        .ma-long { color: #f0883e; }

        .news-bar {
            width: 60px; height: 6px;
            background: linear-gradient(90deg, #da3633 0%, #8b949e 50%, #238636 100%);
            border-radius: 3px; position: relative; display: inline-block;
        }
        .news-indicator {
            position: absolute; top: -1px; width: 2px; height: 8px;
            background: #fff; border-radius: 1px;
            transform: translateX(-50%);
        }

        .footer {
            margin-top: 12px; padding-top: 8px; border-top: 1px solid #30363d;
            display: flex; justify-content: space-between; color: #8b949e; font-size: 11px;
        }

        /* Modal Styles */
        .modal-overlay {
            display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.8); z-index: 1000; justify-content: center; align-items: center;
        }
        .modal-overlay.active { display: flex; }
        .modal {
            background: #161b22; border-radius: 8px; width: 95%; max-width: 1200px;
            max-height: 90vh; overflow: auto; border: 1px solid #30363d;
        }
        .modal-header {
            display: flex; justify-content: space-between; align-items: center;
            padding: 16px 20px; border-bottom: 1px solid #30363d; position: sticky; top: 0;
            background: #161b22; z-index: 10;
        }
        .modal-header h2 { font-size: 18px; font-weight: 600; }
        .modal-close {
            background: none; border: none; color: #8b949e; font-size: 24px;
            cursor: pointer; padding: 0 8px;
        }
        .modal-close:hover { color: #c9d1d9; }
        .modal-body { padding: 20px; }

        .modal-grid {
            display: grid; grid-template-columns: 280px 1fr; gap: 20px; margin-bottom: 20px;
        }
        .modal-bottom {
            display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
        }
        @media (max-width: 900px) {
            .modal-grid { grid-template-columns: 1fr; }
            .modal-bottom { grid-template-columns: repeat(2, 1fr); }
        }

        .card {
            background: #0d1117; border-radius: 6px; padding: 16px;
            border: 1px solid #30363d;
        }
        .card-title {
            font-size: 11px; color: #8b949e; text-transform: uppercase;
            margin-bottom: 12px; font-weight: 600;
        }

        .price-main { font-size: 32px; font-weight: 700; margin-bottom: 8px; }
        .price-change { font-size: 14px; margin-bottom: 16px; }
        .price-change.positive { color: #3fb950; }
        .price-change.negative { color: #f85149; }
        .price-detail { font-size: 12px; color: #8b949e; margin-bottom: 6px; }
        .price-detail span { color: #c9d1d9; }

        .chart-container { position: relative; height: 300px; }
        .period-buttons {
            display: flex; gap: 8px; margin-bottom: 12px;
        }
        .period-btn {
            padding: 4px 12px; border: 1px solid #30363d; border-radius: 4px;
            background: #0d1117; color: #8b949e; cursor: pointer; font-size: 12px;
        }
        .period-btn:hover { border-color: #58a6ff; color: #58a6ff; }
        .period-btn.active { background: #238636; border-color: #238636; color: white; }

        .info-row { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 12px; }
        .info-label { color: #8b949e; }
        .info-value { color: #c9d1d9; font-weight: 500; }
        .info-value.positive { color: #3fb950; }
        .info-value.negative { color: #f85149; }

        .news-item {
            padding: 10px 0; border-bottom: 1px solid #21262d;
        }
        .news-item:last-child { border-bottom: none; }
        .news-title { font-size: 12px; color: #c9d1d9; margin-bottom: 4px; line-height: 1.4; }
        .news-meta { font-size: 10px; color: #8b949e; }
        .news-sentiment {
            display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 9px;
            margin-left: 6px; font-weight: 600;
        }
        .news-sentiment.positive { background: #238636; color: white; }
        .news-sentiment.negative { background: #da3633; color: white; }
        .news-sentiment.neutral { background: #30363d; color: #8b949e; }

        .event-item { margin-bottom: 12px; }
        .event-date { font-size: 14px; font-weight: 600; color: #58a6ff; }
        .event-label { font-size: 11px; color: #8b949e; }
        .event-days { font-size: 11px; color: #f0883e; }

        .nav-btn {
            padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 600;
            background: #21262d; border: 1px solid #30363d; color: #c9d1d9;
            text-decoration: none; transition: all 0.2s;
        }
        .nav-btn:hover { background: #30363d; border-color: #58a6ff; color: #58a6ff; }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <div class="header">
        <div style="display: flex; align-items: center; gap: 12px;">
            <h1>Master Board - AGGRESSIVE MA(8/21)</h1>
            <a href="/sectors" class="nav-btn">Sectors</a>
        </div>
        <div style="display: flex; gap: 8px; align-items: center;">
            <span id="net-liq" class="status-badge" style="background:#1f6feb;font-weight:700;" title="Net Liquidation Value">
                Net: -- DKK
            </span>
            <span id="excess-liq" class="status-badge" style="background:#238636;font-weight:700;" title="Excess Liquidity / Available Cash">
                Cash: -- DKK
            </span>
            <button id="master-trading-btn" class="master-btn trading-stopped" onclick="toggleTrading()" title="Click to toggle trading">
                TRADING STOPPED
            </button>
            <span id="market-status" class="status-badge" style="background:#6e7681;">MKT: --</span>
            <span id="trade-stats" class="status-badge" style="background:#30363d;font-size:10px;" title="Verified/Pending/Failed trades">
                Trades: <span id="trades-filled" style="color:#3fb950;">0</span>/<span id="trades-pending" style="color:#f0883e;">0</span>/<span id="trades-failed" style="color:#f85149;">0</span>
            </span>
            <span id="connection-status" class="status-badge status-disconnected" title="WebSocket Connection">WS: ...</span>
            <span id="trading-mode" class="status-badge status-dry" title="Trading Mode">MODE: DRY</span>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width:30px;text-align:center;">#</th>
                <th class="sortable" data-sort="symbol" onclick="sortTable('symbol')">Symbol <span class="sort-arrow"></span></th>
                <th class="sortable" data-sort="category" onclick="sortTable('category')">Category <span class="sort-arrow"></span></th>
                <th class="sortable" data-sort="days_to_event" onclick="sortTable('days_to_event')">Event <span class="sort-arrow"></span></th>
                <th class="sortable" data-sort="price" onclick="sortTable('price')">Price <span class="sort-arrow"></span></th>
                <th>24H</th>
                <th class="sortable" data-sort="position" onclick="sortTable('position')">Pos <span class="sort-arrow"></span></th>
                <th class="sortable" data-sort="position_size" onclick="sortTable('position_size')">Target <span class="sort-arrow"></span></th>
                <th class="sortable" data-sort="prices_collected" onclick="sortTable('prices_collected')">Data <span class="sort-arrow"></span></th>
                <th class="sortable" data-sort="signal" onclick="sortTable('signal')">Signal <span class="sort-arrow"></span></th>
                <th class="sortable" data-sort="short_ma" onclick="sortTable('short_ma')">MA(8) <span class="sort-arrow"></span></th>
                <th class="sortable" data-sort="long_ma" onclick="sortTable('long_ma')">MA(21) <span class="sort-arrow"></span></th>
                <th class="sortable" data-sort="signal_strength" onclick="sortTable('signal_strength')">News <span class="sort-arrow"></span></th>
            </tr>
        </thead>
        <tbody id="stocks-body">
            <tr><td colspan="13" style="text-align:center;color:#8b949e;">Loading...</td></tr>
        </tbody>
    </table>

    <div class="footer">
        <span id="last-update">--</span>
        <span id="stock-count">0 stocks</span>
        <span id="trade-summary" style="cursor:pointer;" onclick="toggleTradeHistory()">Trades: <span id="total-trades">0</span></span>
    </div>

    <!-- Trade History Panel -->
    <div id="trade-history" style="display:none; margin-top:12px; background:#161b22; border-radius:6px; padding:12px; border:1px solid #30363d;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <span style="font-size:12px; font-weight:600;">Recent Trading Activity</span>
            <span style="font-size:10px; color:#8b949e;">
                Verified: <span id="stat-verified" style="color:#3fb950;">0</span> |
                Pending: <span id="stat-pending" style="color:#f0883e;">0</span> |
                Failed: <span id="stat-failed" style="color:#f85149;">0</span> |
                Skipped: <span id="stat-skipped" style="color:#6e7681;">0</span>
            </span>
        </div>
        <table style="width:100%; font-size:11px;">
            <thead>
                <tr>
                    <th style="width:60px;">Time</th>
                    <th>ID</th>
                    <th>Symbol</th>
                    <th>Action</th>
                    <th>Qty</th>
                    <th>Price</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody id="trade-history-body">
                <tr><td colspan="7" style="text-align:center; color:#8b949e;">No trades yet</td></tr>
            </tbody>
        </table>
    </div>

    <!-- Stock Detail Modal -->
    <div id="stock-modal" class="modal-overlay" onclick="if(event.target===this)closeModal()">
        <div class="modal">
            <div class="modal-header">
                <h2 id="modal-title">TSLA - Tesla Inc</h2>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="modal-grid">
                    <div class="card">
                        <div class="card-title">Price</div>
                        <div id="modal-price" class="price-main">$--</div>
                        <div id="modal-change" class="price-change">--</div>
                        <div class="price-detail">Bid: <span id="modal-bid">--</span> x <span id="modal-bid-size">--</span></div>
                        <div class="price-detail">Ask: <span id="modal-ask">--</span> x <span id="modal-ask-size">--</span></div>
                        <div class="price-detail">Day Range: <span id="modal-day-range">--</span></div>
                        <div class="price-detail">Volume: <span id="modal-volume">--</span></div>
                        <div style="margin-top: 16px;">
                            <div class="card-title">Signal</div>
                            <span id="modal-signal" class="signal-label signal-hold">HOLD</span>
                            <div class="signal-bar" style="margin-top: 8px;">
                                <div id="modal-signal-indicator" class="signal-indicator" style="left:50%"></div>
                            </div>
                        </div>
                    </div>
                    <div class="card">
                        <div class="card-title">Price History</div>
                        <div class="period-buttons">
                            <button class="period-btn" data-period="1d" data-interval="5m">1D</button>
                            <button class="period-btn" data-period="5d" data-interval="15m">1W</button>
                            <button class="period-btn active" data-period="1mo" data-interval="1d">1M</button>
                            <button class="period-btn" data-period="3mo" data-interval="1d">3M</button>
                            <button class="period-btn" data-period="1y" data-interval="1d">1Y</button>
                        </div>
                        <div class="chart-container">
                            <canvas id="price-chart"></canvas>
                        </div>
                    </div>
                </div>
                <div class="modal-bottom">
                    <div class="card">
                        <div class="card-title">Position & P/L</div>
                        <div class="info-row"><span class="info-label">Shares</span><span id="modal-shares" class="info-value">0</span></div>
                        <div class="info-row"><span class="info-label">Avg Cost</span><span id="modal-avg-cost" class="info-value">--</span></div>
                        <div class="info-row"><span class="info-label">Market Value</span><span id="modal-market-value" class="info-value">--</span></div>
                        <div class="info-row"><span class="info-label">Unrealized P/L</span><span id="modal-pnl" class="info-value">--</span></div>
                    </div>
                    <div class="card">
                        <div class="card-title">Fundamentals</div>
                        <div class="info-row"><span class="info-label">Market Cap</span><span id="modal-mcap" class="info-value">--</span></div>
                        <div class="info-row"><span class="info-label">P/E Ratio</span><span id="modal-pe" class="info-value">--</span></div>
                        <div class="info-row"><span class="info-label">EPS</span><span id="modal-eps" class="info-value">--</span></div>
                        <div class="info-row"><span class="info-label">52W Range</span><span id="modal-52w" class="info-value">--</span></div>
                        <div class="info-row"><span class="info-label">Beta</span><span id="modal-beta" class="info-value">--</span></div>
                        <div class="info-row"><span class="info-label">Sector</span><span id="modal-sector" class="info-value">--</span></div>
                    </div>
                    <div class="card">
                        <div class="card-title">Upcoming Events</div>
                        <div id="modal-events">
                            <div class="event-item">
                                <div class="event-label">Next Earnings</div>
                                <div id="modal-earnings-date" class="event-date">--</div>
                                <div id="modal-earnings-days" class="event-days"></div>
                            </div>
                            <div class="event-item">
                                <div class="event-label">Ex-Dividend Date</div>
                                <div id="modal-dividend-date" class="event-date">--</div>
                            </div>
                        </div>
                    </div>
                    <div class="card" style="max-height: 300px; overflow-y: auto;">
                        <div class="card-title">News</div>
                        <div id="modal-news">Loading...</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let ws;
        let modalOpen = false;
        let modalSymbol = null;
        let modalStockData = null;
        let priceChart = null;
        let latestStocksData = [];
        let currentSort = { column: null, direction: 'asc' };

        function connect() {
            ws = new WebSocket(`ws://${window.location.host}/ws`);
            ws.onopen = () => {
                document.getElementById('connection-status').textContent = 'WS: LIVE';
                document.getElementById('connection-status').className = 'status-badge status-live';
            };
            ws.onmessage = (e) => {
                const data = JSON.parse(e.data);
                latestStocksData = data.stocks || [];
                updateDashboard(data);
                if (modalOpen && modalSymbol) {
                    const stock = data.stocks?.find(s => s.symbol === modalSymbol);
                    if (stock) updateModalRealtime(stock);
                }
            };
            ws.onclose = () => {
                document.getElementById('connection-status').textContent = 'WS: OFF';
                document.getElementById('connection-status').className = 'status-badge status-disconnected';
                setTimeout(connect, 2000);
            };
        }

        function updateDashboard(data) {
            const mode = document.getElementById('trading-mode');
            mode.textContent = data.dry_run ? 'MODE: DRY' : 'MODE: LIVE';
            mode.className = 'status-badge ' + (data.dry_run ? 'status-dry' : 'status-live');

            // Update liquidity displays
            if (data.net_liquidation_dkk !== undefined) {
                document.getElementById('net-liq').textContent = `Net: ${data.net_liquidation_dkk.toLocaleString()} DKK`;
            }
            if (data.excess_liquidity_dkk !== undefined) {
                document.getElementById('excess-liq').textContent = `Cash: ${data.excess_liquidity_dkk.toLocaleString()} DKK`;
            }

            // Master trading control
            const masterBtn = document.getElementById('master-trading-btn');
            if (data.trading_control) {
                const enabled = data.trading_control.enabled;
                masterBtn.textContent = enabled ? 'LIVE TRADING' : 'TRADING STOPPED';
                masterBtn.className = 'master-btn ' + (enabled ? 'trading-live' : 'trading-stopped');
            }

            // Market status (with debounce to prevent flickering)
            const mktStatus = document.getElementById('market-status');
            const newMarketState = data.market_open ? 'OPEN' : 'CLOSED';
            if (!window.lastMarketState) window.lastMarketState = newMarketState;
            if (!window.marketStateCount) window.marketStateCount = 0;

            // Only change if we get 3 consecutive same values
            if (newMarketState === window.lastMarketState) {
                window.marketStateCount++;
            } else {
                window.marketStateCount = 1;
                window.lastMarketState = newMarketState;
            }

            if (window.marketStateCount >= 3) {
                if (newMarketState === 'OPEN') {
                    mktStatus.textContent = 'MKT: OPEN';
                    mktStatus.style.background = '#238636';
                } else {
                    mktStatus.textContent = 'MKT: CLOSED';
                    mktStatus.style.background = '#6e7681';
                }
            }

            // Trading stats
            if (data.trading && data.trading.stats) {
                const stats = data.trading.stats;
                document.getElementById('trades-filled').textContent = stats.verified || 0;
                document.getElementById('trades-pending').textContent = stats.pending || 0;
                document.getElementById('trades-failed').textContent = stats.failed || 0;
                document.getElementById('total-trades').textContent = stats.total || 0;

                // Update trade history panel stats
                document.getElementById('stat-verified').textContent = stats.verified || 0;
                document.getElementById('stat-pending').textContent = stats.pending || 0;
                document.getElementById('stat-failed').textContent = stats.failed || 0;
                document.getElementById('stat-skipped').textContent = stats.skipped || 0;
            }

            // Trade history
            if (data.trading && data.trading.recent_trades) {
                updateTradeHistory(data.trading.recent_trades);
            }

            const body = document.getElementById('stocks-body');
            if (data.stocks && data.stocks.length > 0) {
                let stocks = [...data.stocks];
                if (currentSort.column) {
                    stocks = sortStocks(stocks, currentSort.column, currentSort.direction);
                }
                body.innerHTML = stocks.map((s, i) => createRow(s, i + 1)).join('');
            }

            document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
            document.getElementById('stock-count').textContent = (data.stocks?.length || 0) + ' stocks';
        }

        function sortTable(column) {
            // Toggle direction if same column
            if (currentSort.column === column) {
                currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
            } else {
                currentSort.column = column;
                currentSort.direction = 'asc';
            }

            // Update header arrows
            document.querySelectorAll('th.sortable').forEach(th => {
                th.classList.remove('asc', 'desc');
                if (th.dataset.sort === column) {
                    th.classList.add(currentSort.direction);
                }
            });

            // Re-render with sorted data
            if (latestStocksData.length > 0) {
                const sorted = sortStocks([...latestStocksData], column, currentSort.direction);
                document.getElementById('stocks-body').innerHTML = sorted.map((s, i) => createRow(s, i + 1)).join('');
            }
        }

        function sortStocks(stocks, column, direction) {
            return stocks.sort((a, b) => {
                let valA = a[column];
                let valB = b[column];

                // Handle special cases
                if (column === 'signal') {
                    const order = { 'BUY': 3, 'SELL': 2, 'HOLD': 1, 'WAIT': 0 };
                    valA = order[valA] || 0;
                    valB = order[valB] || 0;
                }

                if (column === 'days_to_event') {
                    // Calculate days from upcoming_events
                    valA = getDaysToEvent(a.upcoming_events);
                    valB = getDaysToEvent(b.upcoming_events);
                }

                // Handle null/undefined
                if (valA == null) valA = '';
                if (valB == null) valB = '';

                // Compare
                let result;
                if (typeof valA === 'number' && typeof valB === 'number') {
                    result = valA - valB;
                } else {
                    result = String(valA).localeCompare(String(valB));
                }

                return direction === 'desc' ? -result : result;
            });
        }

        function toggleTradeHistory() {
            const panel = document.getElementById('trade-history');
            panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
        }

        async function toggleTrading() {
            const btn = document.getElementById('master-trading-btn');
            const currentlyEnabled = btn.classList.contains('trading-live');

            // Confirm before enabling
            if (!currentlyEnabled) {
                if (!confirm('Enable LIVE TRADING?\\n\\nThis will allow the bot to place real orders when market is open.')) {
                    return;
                }
            }

            btn.disabled = true;
            btn.textContent = 'UPDATING...';

            try {
                const res = await fetch('/api/trading/toggle', { method: 'POST' });
                const data = await res.json();

                btn.textContent = data.enabled ? 'LIVE TRADING' : 'TRADING STOPPED';
                btn.className = 'master-btn ' + (data.enabled ? 'trading-live' : 'trading-stopped');
            } catch (e) {
                console.error('Failed to toggle trading:', e);
                alert('Failed to toggle trading state');
            } finally {
                btn.disabled = false;
            }
        }

        function updateTradeHistory(trades) {
            const tbody = document.getElementById('trade-history-body');
            if (!trades || trades.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:#8b949e;">No trades yet</td></tr>';
                return;
            }

            tbody.innerHTML = trades.map(t => {
                const time = new Date(t.timestamp).toLocaleTimeString();
                const statusColor = {
                    'VERIFIED': '#3fb950', 'FILLED': '#3fb950',
                    'PENDING': '#f0883e',
                    'FAILED': '#f85149', 'REJECTED': '#f85149', 'CANCELLED': '#f85149',
                    'SKIPPED': '#6e7681'
                }[t.status] || '#8b949e';
                const actionColor = t.action === 'BUY' ? '#3fb950' : '#f85149';

                return `<tr>
                    <td>${time}</td>
                    <td style="color:#58a6ff;">${t.id}</td>
                    <td style="font-weight:600;">${t.symbol}</td>
                    <td style="color:${actionColor};">${t.action}</td>
                    <td>${t.quantity}</td>
                    <td>$${t.price?.toFixed(2) || '--'}</td>
                    <td style="color:${statusColor};">${t.status}${t.error_message ? ' (' + t.error_message + ')' : ''}</td>
                </tr>`;
            }).join('');
        }

        function createRow(s, rowNum) {
            const hasPos = s.position > 0;
            const sigPos = ((s.signal_strength || 0) + 100) / 200 * 100;
            const newsScore = getNewsSentiment(s.news);
            const newsPos = ((newsScore + 100) / 200) * 100;

            let sigClass = 'signal-hold';
            if (s.signal === 'BUY') sigClass = 'signal-buy';
            else if (s.signal === 'SELL') sigClass = 'signal-sell';

            // Calculate price change
            const price = s.price || 0;
            const prevClose = s.previous_close || price;
            const change = price - prevClose;
            const changePct = prevClose ? (change / prevClose * 100) : 0;
            const isUp = change >= 0;
            const priceClass = isUp ? 'price-up' : 'price-down';
            const arrow = isUp ? '▲' : '▼';
            const changeStr = changePct !== 0 ? `<span class="price-change-sm ${priceClass}">${arrow}${Math.abs(changePct).toFixed(2)}%</span>` : '';

            // Format category name
            const catName = (s.category || 'N/A').replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase());

            return `
                <tr class="${hasPos ? 'has-position' : ''}" onclick="openModal('${s.symbol}', ${JSON.stringify(s).replace(/"/g, '&quot;')})">
                    <td style="text-align:center;color:#8b949e;font-size:11px;">${rowNum}</td>
                    <td><span class="symbol">${s.symbol}</span></td>
                    <td class="category-cell">${catName}</td>
                    <td>${formatEventDays(s.upcoming_events)}</td>
                    <td class="price ${priceClass}">$${s.price?.toFixed(2) || '--'}${changeStr}</td>
                    <td>${createSparkline(s.price_history || [], s.price)}</td>
                    <td class="${hasPos ? 'position' : 'no-position'}">${s.position || 0}</td>
                    <td>${s.position_size}</td>
                    <td>${s.prices_collected}/21</td>
                    <td>
                        <span class="signal-label ${sigClass}">${s.signal || 'WAIT'}</span>
                        <div class="signal-bar"><div class="signal-indicator" style="left:${sigPos}%"></div></div>
                    </td>
                    <td class="ma-val ma-short">$${s.short_ma?.toFixed(2) || '--'}</td>
                    <td class="ma-val ma-long">$${s.long_ma?.toFixed(2) || '--'}</td>
                    <td>
                        <div class="news-bar"><div class="news-indicator" style="left:${newsPos}%"></div></div>
                    </td>
                </tr>
            `;
        }

        function formatEventDays(events) {
            if (!events || !events.earnings_date) return '<span style="color:#8b949e;">--</span>';

            // Calculate days until earnings
            const earningsDate = new Date(events.earnings_date);
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            earningsDate.setHours(0, 0, 0, 0);
            const diffTime = earningsDate - today;
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

            let color, label;
            if (diffDays < 0) {
                return '<span style="color:#8b949e;">--</span>';
            } else if (diffDays === 0) {
                color = '#f85149';  // Red
                label = 'TODAY';
            } else if (diffDays <= 10) {
                color = '#f0883e';  // Yellow/Orange
                label = diffDays + 'D';
            } else {
                color = '#3fb950';  // Green
                label = diffDays + 'D';
            }

            return `<span style="color:${color};font-weight:600;font-size:11px;" title="Earnings: ${events.earnings_date}">${label}</span>`;
        }

        function getDaysToEvent(events) {
            if (!events || !events.earnings_date) return 9999;  // No event = sort to end
            const earningsDate = new Date(events.earnings_date);
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            earningsDate.setHours(0, 0, 0, 0);
            const diffTime = earningsDate - today;
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            return diffDays < 0 ? 9999 : diffDays;
        }

        function createSparkline(prices, currentPrice) {
            if (!prices || prices.length < 2) {
                return '<span style="color:#8b949e;font-size:10px;">--</span>';
            }

            const width = 60;
            const height = 20;
            const data = prices.slice(-30);  // Last 30 data points

            const min = Math.min(...data);
            const max = Math.max(...data);
            const range = max - min || 1;

            // Build SVG path
            const points = data.map((p, i) => {
                const x = (i / (data.length - 1)) * width;
                const y = height - ((p - min) / range) * height;
                return `${x},${y}`;
            }).join(' ');

            // Determine color: green if up, red if down
            const isUp = data[data.length - 1] >= data[0];
            const color = isUp ? '#3fb950' : '#f85149';

            return `<svg width="${width}" height="${height}" style="vertical-align:middle;">
                <polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.5"/>
            </svg>`;
        }

        function getNewsSentiment(news) {
            if (!news || news.length === 0) return 0;

            // Use VADER sentiment_score if available (returns -1 to +1)
            // Otherwise fall back to simple positive/negative counting
            let totalScore = 0;
            let count = 0;

            news.forEach(n => {
                if (n.sentiment_score !== undefined) {
                    // VADER compound score (-1 to +1), convert to -100 to +100
                    totalScore += n.sentiment_score * 100;
                    count++;
                } else {
                    // Fallback: simple counting
                    if (n.sentiment === 'positive') totalScore += 50;
                    else if (n.sentiment === 'negative') totalScore -= 50;
                    count++;
                }
            });

            // Average the sentiment scores
            const avgScore = count > 0 ? totalScore / count : 0;
            return Math.max(-100, Math.min(100, avgScore));
        }

        // Modal Functions
        async function openModal(symbol, stockData) {
            modalSymbol = symbol;
            modalStockData = stockData;
            modalOpen = true;

            document.getElementById('stock-modal').classList.add('active');
            document.getElementById('modal-title').textContent = symbol + ' - Loading...';

            // Update with initial data
            updateModalRealtime(stockData);

            // Fetch additional data
            await Promise.all([
                loadStockInfo(symbol),
                loadStockNews(symbol),
                loadStockEvents(symbol),
                loadChart(symbol, '1mo', '1d')
            ]);

            // Setup period buttons
            document.querySelectorAll('.period-btn').forEach(btn => {
                btn.onclick = () => {
                    document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    loadChart(symbol, btn.dataset.period, btn.dataset.interval);
                };
            });
        }

        function closeModal() {
            modalOpen = false;
            modalSymbol = null;
            document.getElementById('stock-modal').classList.remove('active');
            if (priceChart) {
                priceChart.destroy();
                priceChart = null;
            }
        }

        function updateModalRealtime(stock) {
            const price = stock.price || 0;
            const prevClose = stock.previous_close || price;
            const change = price - prevClose;
            const changePct = prevClose ? (change / prevClose * 100) : 0;

            document.getElementById('modal-price').textContent = '$' + price.toFixed(2);

            const changeEl = document.getElementById('modal-change');
            changeEl.textContent = (change >= 0 ? '+' : '') + change.toFixed(2) + ' (' + (change >= 0 ? '+' : '') + changePct.toFixed(2) + '%)';
            changeEl.className = 'price-change ' + (change >= 0 ? 'positive' : 'negative');

            // Signal
            const sigEl = document.getElementById('modal-signal');
            sigEl.textContent = stock.signal || 'HOLD';
            sigEl.className = 'signal-label signal-' + (stock.signal?.toLowerCase() || 'hold');

            const sigPos = ((stock.signal_strength || 0) + 100) / 200 * 100;
            document.getElementById('modal-signal-indicator').style.left = sigPos + '%';

            // Position
            const hasPos = stock.position > 0;
            document.getElementById('modal-shares').textContent = stock.position || 0;

            if (hasPos && stock.avg_cost) {
                const avgCost = stock.avg_cost;
                const marketValue = price * stock.position;
                const costBasis = avgCost * stock.position;
                const pnl = marketValue - costBasis;
                const pnlPct = costBasis ? (pnl / costBasis * 100) : 0;

                document.getElementById('modal-avg-cost').textContent = '$' + avgCost.toFixed(2);
                document.getElementById('modal-market-value').textContent = '$' + marketValue.toFixed(2);

                const pnlEl = document.getElementById('modal-pnl');
                pnlEl.textContent = (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2) + ' (' + (pnl >= 0 ? '+' : '') + pnlPct.toFixed(1) + '%)';
                pnlEl.className = 'info-value ' + (pnl >= 0 ? 'positive' : 'negative');
            } else {
                document.getElementById('modal-avg-cost').textContent = '--';
                document.getElementById('modal-market-value').textContent = '--';
                document.getElementById('modal-pnl').textContent = '--';
                document.getElementById('modal-pnl').className = 'info-value';
            }
        }

        async function loadStockInfo(symbol) {
            try {
                const res = await fetch('/api/stock/' + symbol + '/info');
                const data = await res.json();

                document.getElementById('modal-title').textContent = symbol + ' - ' + (data.name || symbol);

                // Price details
                document.getElementById('modal-bid').textContent = data.bid ? '$' + data.bid.toFixed(2) : '--';
                document.getElementById('modal-bid-size').textContent = data.bidSize || '--';
                document.getElementById('modal-ask').textContent = data.ask ? '$' + data.ask.toFixed(2) : '--';
                document.getElementById('modal-ask-size').textContent = data.askSize || '--';
                document.getElementById('modal-day-range').textContent = (data.dayLow ? '$' + data.dayLow.toFixed(2) : '--') + ' - ' + (data.dayHigh ? '$' + data.dayHigh.toFixed(2) : '--');
                document.getElementById('modal-volume').textContent = data.volume ? formatNumber(data.volume) : '--';

                // Fundamentals
                document.getElementById('modal-mcap').textContent = data.marketCap ? formatLargeNumber(data.marketCap) : '--';
                document.getElementById('modal-pe').textContent = data.pe ? data.pe.toFixed(2) : '--';
                document.getElementById('modal-eps').textContent = data.eps ? '$' + data.eps.toFixed(2) : '--';
                document.getElementById('modal-52w').textContent = (data.fiftyTwoWeekLow ? '$' + data.fiftyTwoWeekLow.toFixed(2) : '--') + ' - ' + (data.fiftyTwoWeekHigh ? '$' + data.fiftyTwoWeekHigh.toFixed(2) : '--');
                document.getElementById('modal-beta').textContent = data.beta ? data.beta.toFixed(2) : '--';
                document.getElementById('modal-sector').textContent = data.sector || '--';
            } catch (e) {
                console.error('Error loading stock info:', e);
            }
        }

        async function loadStockNews(symbol) {
            try {
                const res = await fetch('/api/stock/' + symbol + '/news?limit=10');
                const data = await res.json();

                const newsEl = document.getElementById('modal-news');
                if (!data.news || data.news.length === 0) {
                    newsEl.innerHTML = '<div style="color:#8b949e;">No recent news</div>';
                    return;
                }

                newsEl.innerHTML = data.news.map(n => `
                    <div class="news-item">
                        <div class="news-title">${n.link ? '<a href="' + n.link + '" target="_blank" style="color:inherit;text-decoration:none;">' + n.title + '</a>' : n.title}</div>
                        <div class="news-meta">
                            ${n.source} ${n.time_ago ? '• ' + n.time_ago : ''}
                            <span class="news-sentiment ${n.sentiment}">${n.sentiment}</span>
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                console.error('Error loading news:', e);
                document.getElementById('modal-news').innerHTML = '<div style="color:#8b949e;">Error loading news</div>';
            }
        }

        async function loadStockEvents(symbol) {
            try {
                const res = await fetch('/api/stock/' + symbol + '/events');
                const data = await res.json();
                const events = data.events || {};

                document.getElementById('modal-earnings-date').textContent = events.earnings_date || '--';
                document.getElementById('modal-earnings-days').textContent = events.days_until_earnings !== undefined && events.days_until_earnings !== null ? 'In ' + events.days_until_earnings + ' days' : '';
                document.getElementById('modal-dividend-date').textContent = events.ex_dividend_date || '--';
            } catch (e) {
                console.error('Error loading events:', e);
            }
        }

        async function loadChart(symbol, period, interval) {
            try {
                const res = await fetch('/api/stock/' + symbol + '/history?period=' + period + '&interval=' + interval);
                const data = await res.json();

                if (!data.data || data.data.length === 0) {
                    console.warn('No chart data');
                    return;
                }

                const labels = data.data.map(d => {
                    const dt = new Date(d.date);
                    if (interval.includes('m') || interval === '1h') {
                        return dt.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                    }
                    return dt.toLocaleDateString([], {month: 'short', day: 'numeric'});
                });
                const prices = data.data.map(d => d.close);
                const ma8 = data.data.map(d => d.ma8);
                const ma21 = data.data.map(d => d.ma21);

                // Extract algo trading signals
                const buySignals = new Array(data.data.length).fill(null);
                const sellSignals = new Array(data.data.length).fill(null);

                if (data.algo_signals && data.algo_signals.buy) {
                    data.algo_signals.buy.forEach(signal => {
                        if (signal.index < buySignals.length) {
                            buySignals[signal.index] = signal.price;
                        }
                    });
                }

                if (data.algo_signals && data.algo_signals.sell) {
                    data.algo_signals.sell.forEach(signal => {
                        if (signal.index < sellSignals.length) {
                            sellSignals[signal.index] = signal.price;
                        }
                    });
                }

                const ctx = document.getElementById('price-chart').getContext('2d');

                if (priceChart) {
                    priceChart.destroy();
                }

                priceChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [
                            {
                                label: 'Price',
                                data: prices,
                                borderColor: '#3fb950',
                                backgroundColor: 'rgba(63, 185, 80, 0.1)',
                                borderWidth: 2,
                                fill: true,
                                tension: 0.1,
                                pointRadius: 0
                            },
                            {
                                label: 'MA(8)',
                                data: ma8,
                                borderColor: '#f0883e',
                                borderWidth: 1.5,
                                borderDash: [5, 5],
                                fill: false,
                                tension: 0.1,
                                pointRadius: 0
                            },
                            {
                                label: 'MA(21)',
                                data: ma21,
                                borderColor: '#58a6ff',
                                borderWidth: 1.5,
                                borderDash: [5, 5],
                                fill: false,
                                tension: 0.1,
                                pointRadius: 0
                            },
                            {
                                label: 'Algo Buy Signals',
                                data: buySignals,
                                type: 'scatter',
                                backgroundColor: '#3fb950',
                                borderColor: '#3fb950',
                                pointRadius: 8,
                                pointStyle: 'triangle',
                                pointHoverRadius: 10,
                                showLine: false
                            },
                            {
                                label: 'Algo Sell Signals',
                                data: sellSignals,
                                type: 'scatter',
                                backgroundColor: '#f85149',
                                borderColor: '#f85149',
                                pointRadius: 8,
                                pointStyle: 'triangle',
                                pointRotation: 180,
                                pointHoverRadius: 10,
                                showLine: false
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: {
                            intersect: false,
                            mode: 'index'
                        },
                        plugins: {
                            legend: {
                                display: true,
                                position: 'top',
                                labels: { color: '#8b949e', boxWidth: 12, padding: 8 }
                            }
                        },
                        scales: {
                            x: {
                                grid: { color: '#21262d' },
                                ticks: { color: '#8b949e', maxTicksLimit: 8 }
                            },
                            y: {
                                grid: { color: '#21262d' },
                                ticks: { color: '#8b949e' }
                            }
                        }
                    }
                });
            } catch (e) {
                console.error('Error loading chart:', e);
            }
        }

        function formatNumber(n) {
            return new Intl.NumberFormat().format(n);
        }

        function formatLargeNumber(n) {
            if (n >= 1e12) return (n / 1e12).toFixed(2) + 'T';
            if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
            if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
            return formatNumber(n);
        }

        // Close modal on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modalOpen) closeModal();
        });

        connect();
    </script>
</body>
</html>
"""

SECTORS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sector Analysis</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
            background: #0d1117; color: #c9d1d9; padding: 20px;
            font-size: 13px;
        }
        .header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 20px; padding-bottom: 12px; border-bottom: 1px solid #30363d;
        }
        .header h1 { font-size: 18px; font-weight: 600; }
        .nav-btn {
            padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 600;
            background: #21262d; border: 1px solid #30363d; color: #c9d1d9;
            text-decoration: none; transition: all 0.2s;
        }
        .nav-btn:hover { background: #30363d; border-color: #58a6ff; color: #58a6ff; }

        .charts-container {
            display: grid; grid-template-columns: 1fr 1fr; gap: 24px;
            margin-bottom: 24px;
        }
        @media (max-width: 900px) {
            .charts-container { grid-template-columns: 1fr; }
        }

        .chart-card {
            background: #161b22; border-radius: 8px; padding: 20px;
            border: 1px solid #30363d;
        }
        .chart-title {
            font-size: 14px; font-weight: 600; margin-bottom: 16px;
            color: #c9d1d9;
        }
        .chart-wrapper {
            position: relative; height: 350px;
        }

        .summary-stats {
            display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
            margin-bottom: 24px;
        }
        .stat-card {
            background: #161b22; border-radius: 8px; padding: 16px;
            border: 1px solid #30363d; text-align: center;
        }
        .stat-value { font-size: 28px; font-weight: 700; color: #58a6ff; }
        .stat-label { font-size: 11px; color: #8b949e; margin-top: 4px; }

        .sector-table {
            background: #161b22; border-radius: 8px; padding: 16px;
            border: 1px solid #30363d;
        }
        .sector-table h3 { font-size: 14px; margin-bottom: 12px; }
        table { width: 100%; border-collapse: collapse; }
        th { text-align: left; padding: 8px; font-size: 10px; color: #8b949e;
             text-transform: uppercase; border-bottom: 1px solid #30363d; }
        td { padding: 10px 8px; border-bottom: 1px solid #21262d; }
        tr:hover { background: #21262d; }
        .sector-name { font-weight: 600; color: #58a6ff; }
        .sector-bar {
            height: 8px; background: #238636; border-radius: 4px;
            min-width: 4px;
        }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <div class="header">
        <h1>Sector Analysis</h1>
        <a href="/" class="nav-btn">← Back to Dashboard</a>
    </div>

    <div class="summary-stats">
        <div class="stat-card">
            <div class="stat-value" id="total-stocks">--</div>
            <div class="stat-label">Total Stocks</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" id="total-sectors">--</div>
            <div class="stat-label">Sectors</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" id="total-invested">--</div>
            <div class="stat-label">Total Invested</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" id="total-positions">--</div>
            <div class="stat-label">Open Positions</div>
        </div>
    </div>

    <div class="charts-container">
        <div class="chart-card">
            <div class="chart-title">Stocks per Sector</div>
            <div class="chart-wrapper">
                <canvas id="stocks-chart"></canvas>
            </div>
        </div>
        <div class="chart-card">
            <div class="chart-title">Invested Capital by Sector</div>
            <div class="chart-wrapper">
                <canvas id="capital-chart"></canvas>
            </div>
        </div>
    </div>

    <div class="sector-table">
        <h3>Sector Breakdown</h3>
        <table>
            <thead>
                <tr>
                    <th>Sector</th>
                    <th>Stocks</th>
                    <th>Distribution</th>
                    <th>Invested Capital</th>
                    <th>Open Positions</th>
                </tr>
            </thead>
            <tbody id="sector-body">
                <tr><td colspan="5" style="text-align:center;color:#8b949e;">Loading...</td></tr>
            </tbody>
        </table>
    </div>

    <script>
        let stocksChart = null;
        let capitalChart = null;

        const COLORS = [
            '#58a6ff', '#3fb950', '#f0883e', '#a371f7', '#f85149',
            '#56d4dd', '#db61a2', '#7ee787', '#ffa657', '#ff7b72',
            '#79c0ff', '#d2a8ff', '#ffc658', '#6cb6ff', '#b392f0',
            '#9ecbff', '#c9d1d9', '#8b949e', '#238636', '#da3633',
            '#1f6feb', '#bf8700', '#0d419d', '#8957e5', '#ec6547'
        ];

        async function loadData() {
            try {
                const res = await fetch('/api/stocks');
                const data = await res.json();

                if (!data.stocks || data.stocks.length === 0) {
                    return;
                }

                // Aggregate by sector
                const sectorData = {};
                let totalInvested = 0;
                let totalPositions = 0;

                data.stocks.forEach(stock => {
                    const sector = stock.category || 'UNCATEGORIZED';
                    if (!sectorData[sector]) {
                        sectorData[sector] = {
                            count: 0,
                            invested: 0,
                            positions: 0,
                            stocks: []
                        };
                    }
                    sectorData[sector].count++;
                    sectorData[sector].stocks.push(stock.symbol);

                    // Calculate invested capital (position * price)
                    const invested = (stock.position || 0) * (stock.price || 0);
                    sectorData[sector].invested += invested;
                    totalInvested += invested;

                    if (stock.position > 0) {
                        sectorData[sector].positions++;
                        totalPositions++;
                    }
                });

                // Update summary stats
                document.getElementById('total-stocks').textContent = data.stocks.length;
                document.getElementById('total-sectors').textContent = Object.keys(sectorData).length;
                document.getElementById('total-invested').textContent = '$' + formatNumber(totalInvested);
                document.getElementById('total-positions').textContent = totalPositions;

                // Sort sectors by count
                const sortedSectors = Object.entries(sectorData)
                    .sort((a, b) => b[1].count - a[1].count);

                // Create charts
                createStocksChart(sortedSectors);
                createCapitalChart(sortedSectors);
                createTable(sortedSectors, data.stocks.length);

            } catch (e) {
                console.error('Error loading data:', e);
            }
        }

        function createStocksChart(sectors) {
            const ctx = document.getElementById('stocks-chart').getContext('2d');

            if (stocksChart) stocksChart.destroy();

            stocksChart = new Chart(ctx, {
                type: 'pie',
                data: {
                    labels: sectors.map(([name]) => formatSectorName(name)),
                    datasets: [{
                        data: sectors.map(([, data]) => data.count),
                        backgroundColor: COLORS.slice(0, sectors.length),
                        borderColor: '#0d1117',
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'right',
                            labels: {
                                color: '#c9d1d9',
                                padding: 8,
                                font: { size: 10 },
                                boxWidth: 12
                            }
                        },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => {
                                    const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                                    const pct = ((ctx.raw / total) * 100).toFixed(1);
                                    return `${ctx.raw} stocks (${pct}%)`;
                                }
                            }
                        }
                    }
                }
            });
        }

        function createCapitalChart(sectors) {
            const ctx = document.getElementById('capital-chart').getContext('2d');

            if (capitalChart) capitalChart.destroy();

            // Filter out sectors with no invested capital
            const sectorsWithCapital = sectors.filter(([, data]) => data.invested > 0);

            if (sectorsWithCapital.length === 0) {
                // Show message if no positions
                ctx.font = '14px sans-serif';
                ctx.fillStyle = '#8b949e';
                ctx.textAlign = 'center';
                ctx.fillText('No open positions', ctx.canvas.width / 2, ctx.canvas.height / 2);
                return;
            }

            capitalChart = new Chart(ctx, {
                type: 'pie',
                data: {
                    labels: sectorsWithCapital.map(([name]) => formatSectorName(name)),
                    datasets: [{
                        data: sectorsWithCapital.map(([, data]) => data.invested),
                        backgroundColor: COLORS.slice(0, sectorsWithCapital.length),
                        borderColor: '#0d1117',
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'right',
                            labels: {
                                color: '#c9d1d9',
                                padding: 8,
                                font: { size: 10 },
                                boxWidth: 12
                            }
                        },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => {
                                    const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                                    const pct = ((ctx.raw / total) * 100).toFixed(1);
                                    return `$${formatNumber(ctx.raw)} (${pct}%)`;
                                }
                            }
                        }
                    }
                }
            });
        }

        function createTable(sectors, totalStocks) {
            const tbody = document.getElementById('sector-body');
            const maxCount = Math.max(...sectors.map(([, d]) => d.count));

            tbody.innerHTML = sectors.map(([name, data], idx) => {
                const pct = ((data.count / totalStocks) * 100).toFixed(1);
                const barWidth = (data.count / maxCount) * 100;

                return `
                    <tr>
                        <td>
                            <span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${COLORS[idx % COLORS.length]};margin-right:8px;"></span>
                            <span class="sector-name">${formatSectorName(name)}</span>
                        </td>
                        <td>${data.count} <span style="color:#8b949e;">(${pct}%)</span></td>
                        <td style="width:200px;">
                            <div class="sector-bar" style="width:${barWidth}%;background:${COLORS[idx % COLORS.length]};"></div>
                        </td>
                        <td>${data.invested > 0 ? '$' + formatNumber(data.invested) : '<span style="color:#8b949e;">--</span>'}</td>
                        <td>${data.positions > 0 ? '<span style="color:#3fb950;">' + data.positions + '</span>' : '<span style="color:#8b949e;">0</span>'}</td>
                    </tr>
                `;
            }).join('');
        }

        function formatSectorName(name) {
            return name.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
        }

        function formatNumber(n) {
            if (n >= 1000000) return (n / 1000000).toFixed(2) + 'M';
            if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
            return n.toFixed(0);
        }

        // Load data on page load
        loadData();

        // Refresh every 30 seconds
        setInterval(loadData, 30000);
    </script>
</body>
</html>
"""


def read_state_file():
    """Read state from JSON file (written by bot process)"""
    import os
    state_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'bot_state.json')
    try:
        with open(state_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Fall back to in-memory state if file not available
        return bot_state.get_state()


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    return DASHBOARD_HTML


@app.get("/sectors", response_class=HTMLResponse)
async def get_sectors():
    return SECTORS_HTML


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            state = read_state_file()
            await websocket.send_json(state)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@app.get("/api/stocks")
async def get_stocks():
    return read_state_file()


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": bot_state.last_update}


@app.get("/api/trading/status")
async def get_trading_status():
    """Get current trading control status"""
    return trading_control.get_state()


@app.post("/api/trading/toggle")
async def toggle_trading():
    """Toggle trading enabled/disabled"""
    new_state = trading_control.toggle(by="dashboard")
    return {"enabled": new_state, "message": f"Trading {'enabled' if new_state else 'disabled'}"}


@app.get("/api/stock/{symbol}/history")
async def get_stock_history(symbol: str, period: str = "1mo", interval: str = "1d"):
    """Get historical OHLCV data with pre-calculated MAs for charting"""
    history = yf_client.get_history(symbol.upper(), period=period, interval=interval)

    # Calculate MAs and Algo Trading Signals
    closes = [bar['close'] for bar in history]
    buy_signals = []
    sell_signals = []

    for i, bar in enumerate(history):
        bar['date'] = bar['date'].isoformat() if hasattr(bar['date'], 'isoformat') else str(bar['date'])
        # Calculate MA8 (short-term)
        if i >= 7:
            bar['ma8'] = sum(closes[i-7:i+1]) / 8
        else:
            bar['ma8'] = None
        # Calculate MA21 (long-term)
        if i >= 20:
            bar['ma21'] = sum(closes[i-20:i+1]) / 21
        else:
            bar['ma21'] = None

        # Calculate algo trading signals (MA crossover with 0.8% threshold)
        if i >= 20 and i > 0:  # Need MA21 and previous bar
            prev_bar = history[i-1]
            if prev_bar.get('ma8') and prev_bar.get('ma21') and bar['ma8'] and bar['ma21']:
                threshold = 0.008  # 0.8% threshold matching AGGRESSIVE strategy

                # BUY signal: MA8 crosses above MA21 * 1.008
                if (prev_bar['ma8'] <= prev_bar['ma21'] * (1 + threshold) and
                    bar['ma8'] > bar['ma21'] * (1 + threshold)):
                    buy_signals.append({
                        'date': bar['date'],
                        'price': bar['close'],
                        'index': i
                    })

                # SELL signal: MA8 crosses below MA21 * 0.992
                elif (prev_bar['ma8'] >= prev_bar['ma21'] * (1 - threshold) and
                      bar['ma8'] < bar['ma21'] * (1 - threshold)):
                    sell_signals.append({
                        'date': bar['date'],
                        'price': bar['close'],
                        'index': i
                    })

    return {
        "symbol": symbol.upper(),
        "period": period,
        "interval": interval,
        "data": history,
        "algo_signals": {
            "buy": buy_signals,
            "sell": sell_signals
        }
    }


@app.get("/api/stock/{symbol}/info")
async def get_stock_info(symbol: str):
    """Get company fundamentals"""
    info = yf_client.get_info(symbol.upper())
    return {
        "symbol": symbol.upper(),
        "name": info.get("shortName", symbol),
        "marketCap": info.get("marketCap"),
        "pe": info.get("trailingPE"),
        "eps": info.get("trailingEps"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
        "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
        "beta": info.get("beta"),
        "bid": info.get("bid"),
        "ask": info.get("ask"),
        "bidSize": info.get("bidSize"),
        "askSize": info.get("askSize"),
        "previousClose": info.get("previousClose"),
        "dayHigh": info.get("dayHigh"),
        "dayLow": info.get("dayLow"),
        "volume": info.get("volume"),
        "avgVolume": info.get("averageVolume")
    }


@app.get("/api/stock/{symbol}/news")
async def get_stock_news(symbol: str, limit: int = 10):
    """Get extended news list"""
    news = yf_client.get_news(symbol.upper(), limit=limit)
    return {"symbol": symbol.upper(), "news": news}


@app.get("/api/stock/{symbol}/events")
async def get_stock_events(symbol: str):
    """Get upcoming events (earnings, dividends)"""
    events = yf_client.get_upcoming_events(symbol.upper())

    # Calculate days until earnings
    if events.get('earnings_date'):
        from datetime import datetime
        try:
            earnings_dt = datetime.strptime(events['earnings_date'], '%Y-%m-%d')
            days_until = (earnings_dt - datetime.now()).days
            events['days_until_earnings'] = max(0, days_until)
        except:
            events['days_until_earnings'] = None

    return {"symbol": symbol.upper(), "events": events}


def run_multi_dashboard(host: str = '0.0.0.0', port: int = 8080):
    uvicorn.run(
        app, host=host, port=port, log_level="warning",
        timeout_keep_alive=5, ws_ping_interval=20, ws_ping_timeout=20
    )


if __name__ == '__main__':
    run_multi_dashboard()
