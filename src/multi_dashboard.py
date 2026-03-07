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
from src.alpha_vantage import AlphaVantageClient

yf_client = YFinanceClient()

# Initialize Alpha Vantage client for news
try:
    av_client = AlphaVantageClient()
    av_news_available = True
except Exception as e:
    av_client = None
    av_news_available = False
    print(f"Alpha Vantage news not available: {e}")

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
    <title>Master Board - Breakout Strategy | 60-tick Range</title>
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
        <div style="display: flex; align-items: center; gap: 16px;">
            <div style="display: flex; flex-direction: column; gap: 2px;">
                <h1 style="font-size: 20px;">Master Board</h1>
                <span style="font-size: 14px; color: #8b949e;">Breakout Strategy | 60-tick Range | 0.2% Threshold | ATR >= 0.05% | 24/7</span>
            </div>
            <a href="/models" class="nav-btn" style="padding:8px 16px;font-size:12px;background:linear-gradient(135deg,#58a6ff,#a371f7);border:none;color:#fff;font-weight:700;">Models</a>
            <a href="/alpha-cake" class="nav-btn" style="padding:8px 16px;font-size:12px;background:linear-gradient(135deg,#ffd700,#ff6b6b);border:none;color:#000;font-weight:700;">Alpha Cake</a>
        </div>
        <div style="display: flex; gap: 8px; align-items: flex-end;">
            <div style="display:flex;gap:4px;align-items:center;height:100%;">
                <div id="traffic-light" style="display:flex;gap:2px;padding:2px 6px;background:#21262d;border-radius:8px;" title="Price updates">
                    <span id="tl-green" style="width:10px;height:10px;border-radius:50%;background:#6e7681;"></span>
                    <span id="tl-yellow" style="width:10px;height:10px;border-radius:50%;background:#6e7681;"></span>
                    <span id="tl-red" style="width:10px;height:10px;border-radius:50%;background:#6e7681;"></span>
                </div>
                <span id="net-liq" class="status-badge" style="background:#1f6feb;font-weight:700;font-size:12px;" title="Net Liquidation Value">
                    Net: -- DKK
                </span>
                <span id="excess-liq" class="status-badge" style="background:#238636;font-weight:700;font-size:12px;" title="Excess Liquidity / Available Cash">
                    Cash: -- DKK
                </span>
            </div>
            <div style="display:flex;flex-direction:column;gap:4px;align-items:stretch;">
                <a href="/market-hours" class="nav-btn" style="text-align:center;padding:3px 8px;font-size:12px;">MKT Hours</a>
                <div style="display:flex;gap:4px;">
                    <span id="market-pre" class="status-badge" style="background:#da3633;font-size:12px;padding:3px 8px;cursor:help;" title="Pre-market: Closed">PRE</span>
                    <span id="market-regular" class="status-badge" style="background:#da3633;font-size:12px;padding:3px 8px;cursor:help;" title="Regular market: Closed">MKT</span>
                    <span id="market-after" class="status-badge" style="background:#da3633;font-size:12px;padding:3px 8px;cursor:help;" title="After-hours: Closed">AFTER</span>
                </div>
            </div>
            <div style="display:flex;flex-direction:column;gap:4px;align-items:stretch;">
                <a href="/sectors" class="nav-btn" style="text-align:center;padding:3px 8px;font-size:12px;width:100%;">Sectors</a>
                <span id="trade-stats" class="status-badge" style="background:#30363d;font-size:12px;" title="Verified/Pending/Failed trades">
                    Trades: <span id="trades-filled" style="color:#3fb950;">0</span>/<span id="trades-pending" style="color:#f0883e;">0</span>/<span id="trades-failed" style="color:#f85149;">0</span>
                </span>
            </div>
            <div style="display:flex;flex-direction:column;gap:4px;align-items:stretch;">
                <button id="master-trading-btn" class="master-btn trading-stopped" onclick="toggleTrading()" title="Click to toggle trading" style="width:100%;padding:4px 8px;font-size:12px;">
                    TRADING STOPPED
                </button>
                <div style="display:flex;gap:4px;">
                    <span id="connection-status" class="status-badge status-disconnected" style="font-size:12px;" title="WebSocket Connection">WS: ...</span>
                    <span id="trading-mode" class="status-badge status-dry" style="font-size:12px;" title="Trading Mode">MODE: DRY</span>
                </div>
            </div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width:30px;text-align:center;">#</th>
                <th class="sortable" data-sort="symbol" onclick="sortTable('symbol')" style="width:140px;">Symbol <span class="sort-arrow"></span></th>
                <th class="sortable" data-sort="category" onclick="sortTable('category')">Category <span class="sort-arrow"></span></th>
                <th class="sortable" data-sort="days_to_event" onclick="sortTable('days_to_event')">Event <span class="sort-arrow"></span></th>
                <th class="sortable" data-sort="price" onclick="sortTable('price')">Price <span class="sort-arrow"></span></th>
                <th>Trend</th>
                <th class="sortable" data-sort="position" onclick="sortTable('position')">Pos <span class="sort-arrow"></span></th>
                <th class="sortable" data-sort="position_size" onclick="sortTable('position_size')">Target <span class="sort-arrow"></span></th>
                <th style="width:80px;">Ticks</th>
                <th class="sortable" data-sort="prices_collected" onclick="sortTable('prices_collected')">Data <span class="sort-arrow"></span></th>
                <th>ATR</th>
                <th>StopOut</th>
                <th class="sortable" data-sort="signal" onclick="sortTable('signal')">Signal <span class="sort-arrow"></span></th>
                <th class="sortable" data-sort="alpha_score" onclick="sortTable('alpha_score')">Alpha <span class="sort-arrow"></span></th>
                <th id="col-short" class="sortable" data-sort="short_ma" onclick="sortTable('short_ma')">Range Hi <span class="sort-arrow"></span></th>
                <th id="col-long" class="sortable" data-sort="long_ma" onclick="sortTable('long_ma')">Range Lo <span class="sort-arrow"></span></th>
                <th class="sortable" data-sort="rsi" onclick="sortTable('rsi')">RSI <span class="sort-arrow"></span></th>
                <th class="sortable" data-sort="signal_strength" onclick="sortTable('signal_strength')">Sentiment <span class="sort-arrow"></span></th>
            </tr>
        </thead>
        <tbody id="stocks-body">
            <tr><td colspan="18" style="text-align:center;color:#8b949e;">Loading...</td></tr>
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
                <h2 style="display:flex;align-items:center;gap:12px;">
                    <div id="modal-logo" style="width:40px;height:40px;border-radius:6px;background:#21262d;display:flex;align-items:center;justify-content:center;overflow:hidden;flex-shrink:0;">
                        <img src="" alt="" style="width:36px;height:36px;object-fit:contain;" onerror="this.style.display='none';this.nextElementSibling.style.display='flex';">
                        <div style="display:none;width:40px;height:40px;border-radius:6px;background:#1f6feb;align-items:center;justify-content:center;font-weight:700;font-size:16px;color:white;position:absolute;">T</div>
                    </div>
                    <span id="modal-title">TSLA - Tesla Inc</span>
                </h2>
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
        let lastDataHash = '';  // Track data changes to avoid unnecessary DOM updates

        // Traffic light tracking
        let lastHeartbeatPrice = null;
        let lastHeartbeatTime = Date.now();

        // Update traffic light every second
        setInterval(() => {
            const green = document.getElementById('tl-green');
            const yellow = document.getElementById('tl-yellow');
            const red = document.getElementById('tl-red');
            const elapsed = (Date.now() - lastHeartbeatTime) / 1000;

            // Reset all to grey
            green.style.background = '#6e7681';
            yellow.style.background = '#6e7681';
            red.style.background = '#6e7681';

            if (elapsed <= 5) {
                green.style.background = '#3fb950'; // Green - updating
            } else if (elapsed <= 10) {
                yellow.style.background = '#f0883e'; // Yellow - slow
            } else {
                red.style.background = '#da3633'; // Red - stale
            }

            document.getElementById('traffic-light').title = 'Last update: ' + Math.round(elapsed) + 's ago';
        }, 1000);

        async function fetchData() {
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 4000);  // 4s timeout
                const res = await fetch('/api/stocks', { signal: controller.signal });
                clearTimeout(timeoutId);
                const data = await res.json();

                document.getElementById('connection-status').textContent = 'POLL: OK';
                document.getElementById('connection-status').className = 'status-badge status-live';

                latestStocksData = data.stocks || [];
                window.dataRequirement = data.data_requirement || 60;
                window.strategyType = data.strategy_type || 'BREAKOUT';

                // Traffic light - check first stock price
                if (data.stocks && data.stocks.length > 0) {
                    const price = data.stocks[0].price;
                    if (price !== lastHeartbeatPrice) {
                        lastHeartbeatPrice = price;
                        lastHeartbeatTime = Date.now();
                    }
                }

                updateDashboard(data);
                if (modalOpen && modalSymbol) {
                    const stock = data.stocks?.find(s => s.symbol === modalSymbol);
                    if (stock) updateModalRealtime(stock);
                }
            } catch (e) {
                console.error('Fetch error:', e);
                const status = document.getElementById('connection-status');
                status.textContent = e.name === 'AbortError' ? 'POLL: TIMEOUT' : 'POLL: ERR';
                status.className = 'status-badge status-disconnected';
            }
        }

        function connect() {
            // Poll every 5 seconds (reduced from 2 to prevent browser freeze)
            fetchData();
            setInterval(fetchData, 5000);
        }

        function updateMarketStatus() {
            // Get current time in ET (US/Eastern)
            const now = new Date();
            const etTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
            const hours = etTime.getHours();
            const minutes = etTime.getMinutes();
            const currentMinutes = hours * 60 + minutes;

            // Market hours in ET (minutes from midnight)
            const preMarketStart = 4 * 60;       // 4:00 AM
            const preMarketEnd = 9 * 60 + 30;    // 9:30 AM
            const regularMarketStart = 9 * 60 + 30;   // 9:30 AM
            const regularMarketEnd = 16 * 60;    // 4:00 PM
            const afterHoursStart = 16 * 60;     // 4:00 PM
            const afterHoursEnd = 20 * 60;       // 8:00 PM

            // Check if it's a weekend
            const dayOfWeek = etTime.getDay();
            const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;

            const preEl = document.getElementById('market-pre');
            const regEl = document.getElementById('market-regular');
            const aftEl = document.getElementById('market-after');

            // Safety check - elements might not exist yet
            if (!preEl || !regEl || !aftEl) return;

            if (isWeekend) {
                // All closed on weekends
                preEl.style.background = '#da3633';
                regEl.style.background = '#da3633';
                aftEl.style.background = '#da3633';
                preEl.title = 'Pre-market: Closed (Weekend)';
                regEl.title = 'Regular market: Closed (Weekend)';
                aftEl.title = 'After-hours: Closed (Weekend)';
            } else {
                // Pre-market
                if (currentMinutes >= preMarketStart && currentMinutes < preMarketEnd) {
                    preEl.style.background = '#238636';
                    preEl.title = 'Pre-market: OPEN';
                } else {
                    preEl.style.background = '#da3633';
                    preEl.title = 'Pre-market: Closed';
                }

                // Regular market
                if (currentMinutes >= regularMarketStart && currentMinutes < regularMarketEnd) {
                    regEl.style.background = '#238636';
                    regEl.title = 'Regular market: OPEN';
                } else {
                    regEl.style.background = '#da3633';
                    regEl.title = 'Regular market: Closed';
                }

                // After-hours
                if (currentMinutes >= afterHoursStart && currentMinutes < afterHoursEnd) {
                    aftEl.style.background = '#238636';
                    aftEl.title = 'After-hours: OPEN';
                } else {
                    aftEl.style.background = '#da3633';
                    aftEl.title = 'After-hours: Closed';
                }

                // Check if all closed
                const allClosed = currentMinutes < preMarketStart || currentMinutes >= afterHoursEnd;
                if (allClosed) {
                    preEl.title = 'All markets closed';
                    regEl.title = 'All markets closed';
                    aftEl.title = 'All markets closed';
                }
            }
        }

        function updateDashboard(data) {
            const mode = document.getElementById('trading-mode');
            mode.textContent = data.dry_run ? 'MODE: DRY' : 'MODE: LIVE';
            mode.className = 'status-badge ' + (data.dry_run ? 'status-dry' : 'status-live');

            // Update liquidity displays
            if (data.net_liquidation_dkk !== undefined) {
                document.getElementById('net-liq').textContent = `Net: ${Math.round(data.net_liquidation_dkk).toLocaleString()} DKK`;
            }
            if (data.excess_liquidity_dkk !== undefined) {
                document.getElementById('excess-liq').textContent = `Cash: ${Math.round(data.excess_liquidity_dkk).toLocaleString()} DKK`;
            }

            // Master trading control
            const masterBtn = document.getElementById('master-trading-btn');
            if (data.trading_control) {
                const enabled = data.trading_control.enabled;
                masterBtn.textContent = enabled ? 'LIVE TRADING' : 'TRADING STOPPED';
                masterBtn.className = 'master-btn ' + (enabled ? 'trading-live' : 'trading-stopped');
            }

            // Market status - three sessions (Pre, Regular, After)
            updateMarketStatus();

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
                // Create a simple hash of key data to detect changes
                const dataHash = data.stocks.map(s => `${s.symbol}:${s.price}:${s.signal}:${s.position}`).join('|');

                // Only rebuild table if data actually changed
                if (dataHash !== lastDataHash) {
                    lastDataHash = dataHash;
                    let stocks = [...data.stocks];
                    if (currentSort.column) {
                        stocks = sortStocks(stocks, currentSort.column, currentSort.direction);
                    }
                    body.innerHTML = stocks.map((s, i) => createRow(s, i + 1)).join('');
                }
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

        function getCompanyName(symbol) {
            const companyNames = {
                "AAPL": "Apple Inc.", "MSFT": "Microsoft Corp.", "GOOGL": "Alphabet Inc.", "META": "Meta Platforms",
                "NVDA": "NVIDIA Corp.", "AMD": "Advanced Micro Devices", "AVGO": "Broadcom Inc.", "QCOM": "Qualcomm Inc.",
                "TSM": "Taiwan Semiconductor", "ASML": "ASML Holding", "MU": "Micron Technology", "ARM": "Arm Holdings",
                "PLTR": "Palantir Technologies", "AI": "C3.ai Inc.", "SNOW": "Snowflake Inc.", "DDOG": "Datadog Inc.",
                "CRM": "Salesforce Inc.", "NOW": "ServiceNow Inc.", "NET": "Cloudflare Inc.", "PANW": "Palo Alto Networks",
                "V": "Visa Inc.", "MA": "Mastercard Inc.", "XYZ": "Excelerate Energy", "COIN": "Coinbase Global",
                "PYPL": "PayPal Holdings", "TSLA": "Tesla Inc.", "MARA": "Marathon Digital", "MSTR": "MicroStrategy Inc.",
                "CRWD": "CrowdStrike Holdings", "ZS": "Zscaler Inc.", "LLY": "Eli Lilly and Co.", "UNH": "UnitedHealth Group",
                "ABBV": "AbbVie Inc.", "ISRG": "Intuitive Surgical", "DHR": "Danaher Corp.", "AMZN": "Amazon.com Inc.",
                "COST": "Costco Wholesale", "HD": "Home Depot Inc.", "MCD": "McDonald's Corp.", "CMG": "Chipotle Mexican Grill",
                "SBUX": "Starbucks Corp.", "BKNG": "Booking Holdings", "NFLX": "Netflix Inc.", "DIS": "Walt Disney Co.",
                "SPOT": "Spotify Technology", "DHI": "D.R. Horton Inc.", "JPM": "JPMorgan Chase", "GS": "Goldman Sachs",
                "BLK": "BlackRock Inc.", "GE": "General Electric", "CAT": "Caterpillar Inc.", "HON": "Honeywell International",
                "RTX": "RTX Corp.", "LMT": "Lockheed Martin", "BA": "Boeing Co.", "UPS": "United Parcel Service",
                "PGR": "Progressive Corp.", "NEE": "NextEra Energy", "CEG": "Constellation Energy", "PLD": "Prologis Inc.",
                "AMT": "American Tower", "LIN": "Linde PLC", "FCX": "Freeport-McMoRan", "XOM": "Exxon Mobil",
                "CVX": "Chevron Corp.", "ENPH": "Enphase Energy", "BABA": "Alibaba Group", "TMUS": "T-Mobile US",
                "ORLY": "O'Reilly Automotive", "RIOT": "Riot Platforms"
            };
            return companyNames[symbol] || symbol;
        }

        function getLogoColor(symbol) {
            // Generate consistent color for each ticker based on hash
            let hash = 0;
            for (let i = 0; i < symbol.length; i++) {
                hash = symbol.charCodeAt(i) + ((hash << 5) - hash);
            }

            // Color palette with good contrast on dark background
            const colors = [
                '#1f6feb', '#58a6ff', '#3fb950', '#f0883e', '#f85149',
                '#a371f7', '#d73a49', '#0969da', '#1a7f37', '#bf8700',
                '#8250df', '#cf222e', '#0550ae', '#0a3069', '#744210'
            ];

            return colors[Math.abs(hash) % colors.length];
        }

        function createRow(s, rowNum) {
            const hasPos = s.position > 0;
            const sigPos = ((s.signal_strength || 0) + 100) / 200 * 100;
            // Use pre-calculated news_sentiment if available, otherwise calculate from news
            const newsScore = s.news_sentiment !== undefined ? s.news_sentiment : getNewsSentiment(s.news);
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
            const changeStr = changePct !== 0 ? '<span class="price-change-sm ' + priceClass + '">' + arrow + ' ' + Math.abs(changePct).toFixed(2) + '%</span>' : '';

            // Format category name
            const catName = (s.category || 'N/A').replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase());

            // Generate logo URL and fallback
            const logoUrl = `https://assets.parqet.com/logos/symbol/${s.symbol}`;
            const logoColor = getLogoColor(s.symbol);
            const logoLetter = s.symbol.charAt(0);
            const companyName = getCompanyName(s.symbol);

            return `
                <tr class="${hasPos ? 'has-position' : ''}" onclick="openModal('${s.symbol}')">
                    <td style="text-align:center;color:#8b949e;font-size:11px;">${rowNum}</td>
                    <td>
                        <div style="display:flex;align-items:center;gap:8px;">
                            <div style="width:32px;height:32px;border-radius:6px;background:#21262d;display:flex;align-items:center;justify-content:center;overflow:hidden;flex-shrink:0;">
                                <img src="${logoUrl}" alt="${s.symbol}"
                                     style="width:28px;height:28px;object-fit:contain;"
                                     onerror="this.style.display='none';this.nextElementSibling.style.display='flex';">
                                <div style="display:none;width:32px;height:32px;border-radius:6px;background:${logoColor};align-items:center;justify-content:center;font-weight:700;font-size:14px;color:white;position:absolute;">${logoLetter}</div>
                            </div>
                            <div style="display:flex;flex-direction:column;">
                                <span class="symbol">${s.symbol}</span>
                                <span style="font-size:10px;color:#8b949e;">${companyName}</span>
                            </div>
                        </div>
                    </td>
                    <td class="category-cell">${catName}</td>
                    <td>${formatEventDays(s.upcoming_events)}</td>
                    <td class="price ${priceClass}">$${s.price?.toFixed(2) || '--'}${changeStr}</td>
                    <td>${createSparkline(s.price_history || [], s.price)}</td>
                    <td class="${hasPos ? 'position' : 'no-position'}">${s.position || 0}</td>
                    <td>${s.position_size}</td>
                    <td>${createSparkline(s.tick_prices || [], s.price, 80)}</td>
                    <td>${s.prices_collected >= (window.dataRequirement || 60) ? '<span style="color:#3fb950;">READY</span>' : s.prices_collected + '/' + (window.dataRequirement || 60)}</td>
                    <td style="text-align:center;"><span style="color:${s.atr_ok !== false ? '#3fb950' : '#f85149'};">${((s.atr_pct || 0) * 100).toFixed(2)}%</span></td>
                    <td style="text-align:center;">${s.stop_out === 'TRAIL' ? '<span style="color:#f85149;font-weight:600;">Trail</span>' : s.stop_out === 'LOSS' ? '<span style="color:#f85149;font-weight:600;">Loss</span>' : '<span style="color:#8b949e;">--</span>'}</td>
                    <td>
                        <span class="signal-label ${sigClass}">${s.signal || 'WAIT'}</span>
                        <div class="signal-bar"><div class="signal-indicator" style="left:${sigPos}%"></div></div>
                    </td>
                    <td>${formatAlphaScore(s.alpha_score)}</td>
                    <td class="ma-val ma-short">$${s.short_ma?.toFixed(2) || '--'}</td>
                    <td class="ma-val ma-long">$${s.long_ma?.toFixed(2) || '--'}</td>
                    <td class="ma-val" style="color:${(s.rsi || 50) > 70 ? '#f85149' : (s.rsi || 50) < 30 ? '#3fb950' : '#8b949e'};">${s.rsi?.toFixed(1) || '50.0'}</td>
                    <td>
                        <div class="news-bar"><div class="news-indicator" style="left:${newsPos}%"></div></div>
                    </td>
                </tr>
            `;
        }

        function formatAlphaScore(score) {
            if (score === undefined || score === null) {
                return '<span style="color:#8b949e;">--</span>';
            }

            // Color based on thresholds: red (<-0.3), yellow (-0.3 to 0.3), green (>0.3)
            let color;
            if (score >= 0.30) {
                color = '#3fb950';  // Green - bullish
            } else if (score <= -0.30) {
                color = '#f85149';  // Red - bearish
            } else {
                color = '#f0883e';  // Yellow/Orange - neutral
            }

            // Format as signed percentage with one decimal
            const sign = score >= 0 ? '+' : '';
            return `<span style="color:${color};font-weight:600;">${sign}${(score * 100).toFixed(0)}%</span>`;
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

        function createSparkline(prices, currentPrice, customWidth) {
            if (!prices || prices.length < 2) {
                return '<span style="color:#8b949e;font-size:10px;">--</span>';
            }

            const width = customWidth || 60;
            const height = 20;
            const data = prices.slice(-60);  // Last 60 data points

            const min = Math.min(...data);
            const max = Math.max(...data);
            const range = max - min || 1;

            // Build SVG path
            const points = data.map((p, i) => {
                const x = (i / (data.length - 1)) * width;
                const y = height - ((p - min) / range) * height;
                return x + ',' + y;
            }).join(' ');

            // Determine color: green if up, red if down
            const isUp = data[data.length - 1] >= data[0];
            const color = isUp ? '#3fb950' : '#f85149';

            return '<svg width="' + width + '" height="' + height + '" style="vertical-align:middle;"><polyline points="' + points + '" fill="none" stroke="' + color + '" stroke-width="1.5"/></svg>';
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
            // Look up stock data from cached data if not provided
            modalStockData = stockData || latestStocksData.find(s => s.symbol === symbol) || {};
            modalOpen = true;

            document.getElementById('stock-modal').classList.add('active');
            document.getElementById('modal-title').textContent = symbol + ' - Loading...';

            // Set logo
            const modalLogoDiv = document.getElementById('modal-logo');
            const logoUrl = `https://assets.parqet.com/logos/symbol/${symbol}`;
            const logoColor = getLogoColor(symbol);
            const logoLetter = symbol.charAt(0);
            const imgEl = modalLogoDiv.querySelector('img');
            const fallbackEl = modalLogoDiv.querySelector('div');

            // Reset visibility - show img, hide fallback
            imgEl.style.display = '';
            fallbackEl.style.display = 'none';

            // Set logo properties
            imgEl.src = logoUrl;
            imgEl.alt = symbol;
            fallbackEl.textContent = logoLetter;
            fallbackEl.style.background = logoColor;

            // Update with initial data (use resolved modalStockData, not the parameter)
            if (modalStockData && modalStockData.price) {
                updateModalRealtime(modalStockData);
            }

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

                // Clear previous content
                newsEl.innerHTML = '';

                // Display overall sentiment if available
                if (data.overall_sentiment !== undefined) {
                    const overallScore = data.overall_sentiment;
                    let overallColor = '#8b949e';
                    let overallBg = 'rgba(139,148,158,0.15)';
                    let overallLabel = 'Neutral';

                    if (overallScore >= 0.15) {
                        overallColor = '#3fb950';
                        overallBg = 'rgba(63,185,80,0.15)';
                        overallLabel = 'Positive';
                    } else if (overallScore <= -0.15) {
                        overallColor = '#f85149';
                        overallBg = 'rgba(248,81,73,0.15)';
                        overallLabel = 'Negative';
                    }

                    const overallDiv = document.createElement('div');
                    overallDiv.style.cssText = `background:${overallBg};border-left:4px solid ${overallColor};padding:12px;margin-bottom:16px;border-radius:4px;`;
                    overallDiv.innerHTML = `
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <div>
                                <div style="font-size:11px;color:#8b949e;margin-bottom:4px;">Overall News Sentiment (${data.article_count} articles)</div>
                                <div style="font-size:18px;font-weight:600;color:${overallColor};">${overallLabel}</div>
                            </div>
                            <div style="font-size:24px;font-weight:700;color:${overallColor};">${(overallScore * 100).toFixed(0)}</div>
                        </div>
                    `;
                    newsEl.appendChild(overallDiv);
                }

                // Display source info
                const sourceInfo = document.createElement('div');
                sourceInfo.style.cssText = 'color:#8b949e;font-size:11px;margin-bottom:12px;';
                sourceInfo.textContent = data.source || 'News Feed';
                newsEl.appendChild(sourceInfo);

                // Display news articles
                const newsHtml = data.news.map(n => {
                    // Sentiment color based on score
                    let sentimentColor = '#8b949e';  // neutral gray
                    let sentimentBg = 'rgba(139,148,158,0.1)';
                    if (n.sentiment_score !== undefined) {
                        if (n.sentiment_score >= 0.15) {
                            sentimentColor = '#3fb950';  // positive green
                            sentimentBg = 'rgba(63,185,80,0.15)';
                        } else if (n.sentiment_score <= -0.15) {
                            sentimentColor = '#f85149';  // negative red
                            sentimentBg = 'rgba(248,81,73,0.15)';
                        }
                    }

                    // Format sentiment score
                    const scoreDisplay = n.sentiment_score !== undefined
                        ? `<span style="font-weight:600;color:${sentimentColor};">${(n.sentiment_score * 100).toFixed(0)}</span>`
                        : '';

                    // Relevance indicator
                    const relevanceDisplay = n.relevance !== undefined
                        ? `<span style="color:#8b949e;font-size:10px;">• Relevance: ${(n.relevance * 100).toFixed(0)}%</span>`
                        : '';

                    return `
                        <div class="news-item" style="border-left:3px solid ${sentimentColor};padding-left:8px;margin-bottom:10px;">
                            <div class="news-title">${n.link ? '<a href="' + n.link + '" target="_blank" style="color:inherit;text-decoration:none;">' + n.title + '</a>' : n.title}</div>
                            <div class="news-meta" style="display:flex;align-items:center;gap:8px;margin-top:4px;">
                                <span style="color:#8b949e;">${n.source} ${n.time_ago ? '• ' + n.time_ago : ''}</span>
                                ${scoreDisplay ? `<span style="background:${sentimentBg};padding:2px 6px;border-radius:3px;font-size:11px;">
                                    Sentiment: ${scoreDisplay}
                                </span>` : ''}
                                ${relevanceDisplay}
                            </div>
                            ${n.summary ? '<div style="color:#8b949e;font-size:11px;margin-top:4px;line-height:1.4;">' + n.summary.substring(0, 150) + '...</div>' : ''}
                        </div>
                    `;
                }).join('');

                newsEl.innerHTML += newsHtml;
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
                                label: 'Range Hi',
                                data: ma8,
                                borderColor: '#f0883e',
                                borderWidth: 1.5,
                                borderDash: [5, 5],
                                fill: false,
                                tension: 0.1,
                                pointRadius: 0
                            },
                            {
                                label: 'Range Lo',
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
        <div style="display: flex; gap: 8px;">
            <a href="/" class="nav-btn">← Dashboard</a>
            <a href="/market-hours" class="nav-btn">MKT Hours</a>
        </div>
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

MARKET_HOURS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Market Hours - Trading Clock</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
            background: #0d1117; color: #c9d1d9; padding: 20px;
            font-size: 13px;
        }
        .header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 24px; padding-bottom: 12px; border-bottom: 1px solid #30363d;
        }
        .header h1 { font-size: 18px; font-weight: 600; }
        .nav-btn {
            padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 600;
            background: #21262d; border: 1px solid #30363d; color: #c9d1d9;
            text-decoration: none; transition: all 0.2s;
        }
        .nav-btn:hover { background: #30363d; border-color: #58a6ff; color: #58a6ff; }

        .clock-container {
            background: #161b22; border-radius: 8px; padding: 24px;
            border: 1px solid #30363d; margin-bottom: 24px;
        }
        .clock-title {
            font-size: 16px; font-weight: 600; margin-bottom: 20px;
            display: flex; align-items: center; gap: 12px;
        }
        .current-time {
            font-size: 24px; font-weight: 700; color: #58a6ff;
        }
        .timezone-label {
            font-size: 12px; color: #8b949e; font-weight: normal;
        }

        .timeline-container {
            overflow-x: auto; padding-bottom: 10px;
        }
        .timeline-wrapper {
            min-width: 1200px;
        }
        .timeline-header {
            display: flex; margin-bottom: 8px; padding-left: 120px;
        }
        .hour-label {
            flex: 1; text-align: center; font-size: 11px; color: #8b949e;
            min-width: 50px;
        }
        .hour-label.current { color: #58a6ff; font-weight: 700; }

        .market-row {
            display: flex; align-items: center; margin-bottom: 16px;
        }
        .market-name {
            width: 120px; font-weight: 600; font-size: 13px;
            flex-shrink: 0;
        }
        .market-name .flag { font-size: 16px; margin-right: 6px; }
        .market-name .subtitle { font-size: 10px; color: #8b949e; display: block; }

        .timeline-bar {
            flex: 1; height: 32px; position: relative;
            background: #21262d; border-radius: 4px;
            display: flex;
        }
        .hour-segment {
            flex: 1; height: 100%; position: relative;
            border-right: 1px solid #30363d;
        }
        .hour-segment:last-child { border-right: none; }

        .session {
            position: absolute; height: 100%; border-radius: 3px;
            display: flex; align-items: center; justify-content: center;
            font-size: 10px; font-weight: 600; color: white;
            text-shadow: 0 1px 2px rgba(0,0,0,0.5);
            overflow: hidden; white-space: nowrap;
        }
        .session-premarket { background: linear-gradient(135deg, #f0883e, #d68a00); }
        .session-regular { background: linear-gradient(135deg, #238636, #2ea043); }
        .session-afterhours { background: linear-gradient(135deg, #8957e5, #6e40c9); }
        .session-closed { background: #30363d; color: #8b949e; }

        .current-time-line {
            position: absolute; top: 0; bottom: 0; width: 2px;
            background: #f85149; z-index: 10;
            box-shadow: 0 0 8px rgba(248, 81, 73, 0.8);
        }
        .current-time-dot {
            position: absolute; top: -6px; left: -4px;
            width: 10px; height: 10px; background: #f85149;
            border-radius: 50%; border: 2px solid #0d1117;
        }

        .legend {
            display: flex; gap: 24px; margin-top: 20px; flex-wrap: wrap;
        }
        .legend-item {
            display: flex; align-items: center; gap: 8px; font-size: 12px;
        }
        .legend-color {
            width: 16px; height: 16px; border-radius: 3px;
        }
        .legend-premarket { background: linear-gradient(135deg, #f0883e, #d68a00); }
        .legend-regular { background: linear-gradient(135deg, #238636, #2ea043); }
        .legend-afterhours { background: linear-gradient(135deg, #8957e5, #6e40c9); }

        .info-cards {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px;
        }
        .info-card {
            background: #161b22; border-radius: 8px; padding: 20px;
            border: 1px solid #30363d;
        }
        .info-card h3 {
            font-size: 14px; margin-bottom: 12px; display: flex;
            align-items: center; gap: 8px;
        }
        .info-card .flag { font-size: 20px; }
        .info-row {
            display: flex; justify-content: space-between; padding: 8px 0;
            border-bottom: 1px solid #21262d; font-size: 12px;
        }
        .info-row:last-child { border-bottom: none; }
        .info-label { color: #8b949e; }
        .info-value { font-weight: 600; }
        .info-value.open { color: #3fb950; }
        .info-value.closed { color: #f85149; }

        .status-dot {
            display: inline-block; width: 8px; height: 8px;
            border-radius: 50%; margin-right: 6px;
        }
        .status-dot.open { background: #3fb950; box-shadow: 0 0 6px rgba(63, 185, 80, 0.6); }
        .status-dot.closed { background: #f85149; }
        .status-dot.premarket { background: #f0883e; box-shadow: 0 0 6px rgba(240, 136, 62, 0.6); }
        .status-dot.afterhours { background: #8957e5; box-shadow: 0 0 6px rgba(137, 87, 229, 0.6); }
    </style>
</head>
<body>
    <div class="header">
        <h1>Market Hours - Trading Clock</h1>
        <div style="display: flex; gap: 8px;">
            <a href="/" class="nav-btn">← Dashboard</a>
            <a href="/sectors" class="nav-btn">Sectors</a>
        </div>
    </div>

    <div class="clock-container">
        <div class="clock-title">
            <span>Copenhagen Time (CET/CEST):</span>
            <span class="current-time" id="current-time">--:--:--</span>
            <span class="timezone-label" id="timezone-info"></span>
        </div>

        <div class="timeline-container">
            <div class="timeline-wrapper">
                <div class="timeline-header" id="timeline-header">
                    <!-- Hours 0-24 generated by JS -->
                </div>

                <div class="market-row">
                    <div class="market-name">
                        <span class="flag">🇺🇸</span>NYSE
                        <span class="subtitle">New York Stock Exchange</span>
                    </div>
                    <div class="timeline-bar" id="nyse-timeline">
                        <!-- Sessions generated by JS -->
                    </div>
                </div>

                <div class="market-row">
                    <div class="market-name">
                        <span class="flag">🇺🇸</span>NASDAQ
                        <span class="subtitle">Same hours as NYSE</span>
                    </div>
                    <div class="timeline-bar" id="nasdaq-timeline">
                        <!-- Sessions generated by JS -->
                    </div>
                </div>

                <div class="market-row">
                    <div class="market-name">
                        <span class="flag">🇪🇺</span>Euronext
                        <span class="subtitle">Paris, Amsterdam, Brussels</span>
                    </div>
                    <div class="timeline-bar" id="euronext-timeline">
                        <!-- Sessions generated by JS -->
                    </div>
                </div>

                <div class="market-row">
                    <div class="market-name">
                        <span class="flag">🇩🇰</span>Copenhagen
                        <span class="subtitle">Nasdaq Copenhagen</span>
                    </div>
                    <div class="timeline-bar" id="copenhagen-timeline">
                        <!-- Sessions generated by JS -->
                    </div>
                </div>

                <div class="market-row">
                    <div class="market-name">
                        <span class="flag">🇬🇧</span>London
                        <span class="subtitle">London Stock Exchange</span>
                    </div>
                    <div class="timeline-bar" id="london-timeline">
                        <!-- Sessions generated by JS -->
                    </div>
                </div>

                <div class="market-row">
                    <div class="market-name">
                        <span class="flag">🇩🇪</span>Frankfurt
                        <span class="subtitle">Deutsche Börse (Xetra)</span>
                    </div>
                    <div class="timeline-bar" id="frankfurt-timeline">
                        <!-- Sessions generated by JS -->
                    </div>
                </div>
            </div>
        </div>

        <div class="legend">
            <div class="legend-item">
                <div class="legend-color legend-premarket"></div>
                <span>Pre-Market</span>
            </div>
            <div class="legend-item">
                <div class="legend-color legend-regular"></div>
                <span>Regular Trading</span>
            </div>
            <div class="legend-item">
                <div class="legend-color legend-afterhours"></div>
                <span>After-Hours</span>
            </div>
        </div>
    </div>

    <div class="info-cards">
        <div class="info-card">
            <h3><span class="flag">🇺🇸</span>NYSE / NASDAQ</h3>
            <div class="info-row">
                <span class="info-label">Status</span>
                <span class="info-value" id="nyse-status"><span class="status-dot closed"></span>Closed</span>
            </div>
            <div class="info-row">
                <span class="info-label">Pre-Market</span>
                <span class="info-value">10:00 - 15:30 CET</span>
            </div>
            <div class="info-row">
                <span class="info-label">Regular Hours</span>
                <span class="info-value">15:30 - 22:00 CET</span>
            </div>
            <div class="info-row">
                <span class="info-label">After-Hours</span>
                <span class="info-value">22:00 - 02:00 CET</span>
            </div>
            <div class="info-row">
                <span class="info-label">Local Time (ET)</span>
                <span class="info-value" id="et-time">--:--</span>
            </div>
        </div>

        <div class="info-card">
            <h3><span class="flag">🇪🇺</span>Euronext / Copenhagen</h3>
            <div class="info-row">
                <span class="info-label">Status</span>
                <span class="info-value" id="euronext-status"><span class="status-dot closed"></span>Closed</span>
            </div>
            <div class="info-row">
                <span class="info-label">Pre-Market</span>
                <span class="info-value">07:15 - 09:00 CET</span>
            </div>
            <div class="info-row">
                <span class="info-label">Regular Hours</span>
                <span class="info-value">09:00 - 17:30 CET</span>
            </div>
            <div class="info-row">
                <span class="info-label">Post-Market</span>
                <span class="info-value">17:30 - 17:40 CET</span>
            </div>
            <div class="info-row">
                <span class="info-label">Next Open/Close</span>
                <span class="info-value" id="euronext-next">--</span>
            </div>
        </div>

        <div class="info-card">
            <h3><span class="flag">🇬🇧</span>London Stock Exchange</h3>
            <div class="info-row">
                <span class="info-label">Status</span>
                <span class="info-value" id="london-status"><span class="status-dot closed"></span>Closed</span>
            </div>
            <div class="info-row">
                <span class="info-label">Pre-Market</span>
                <span class="info-value">08:00 - 09:00 CET</span>
            </div>
            <div class="info-row">
                <span class="info-label">Regular Hours</span>
                <span class="info-value">09:00 - 17:30 CET</span>
            </div>
            <div class="info-row">
                <span class="info-label">Post-Market</span>
                <span class="info-value">17:30 - 17:35 CET</span>
            </div>
        </div>

        <div class="info-card">
            <h3><span class="flag">🇩🇪</span>Frankfurt (Xetra)</h3>
            <div class="info-row">
                <span class="info-label">Status</span>
                <span class="info-value" id="frankfurt-status"><span class="status-dot closed"></span>Closed</span>
            </div>
            <div class="info-row">
                <span class="info-label">Pre-Market</span>
                <span class="info-value">08:00 - 09:00 CET</span>
            </div>
            <div class="info-row">
                <span class="info-label">Regular Hours</span>
                <span class="info-value">09:00 - 17:30 CET</span>
            </div>
            <div class="info-row">
                <span class="info-label">Post-Market</span>
                <span class="info-value">17:30 - 20:00 CET</span>
            </div>
        </div>
    </div>

    <script>
        // Market hours in CET (Copenhagen time) - hours as decimals (e.g., 9.5 = 9:30)
        const markets = {
            nyse: {
                premarket: { start: 10, end: 15.5 },      // 4:00-9:30 ET = 10:00-15:30 CET
                regular: { start: 15.5, end: 22 },         // 9:30-16:00 ET = 15:30-22:00 CET
                afterhours: { start: 22, end: 26 }         // 16:00-20:00 ET = 22:00-02:00 CET (next day)
            },
            nasdaq: {
                premarket: { start: 10, end: 15.5 },
                regular: { start: 15.5, end: 22 },
                afterhours: { start: 22, end: 26 }
            },
            euronext: {
                premarket: { start: 7.25, end: 9 },        // 07:15 - 09:00 CET
                regular: { start: 9, end: 17.5 },          // 09:00 - 17:30 CET
                afterhours: { start: 17.5, end: 17.67 }    // 17:30 - 17:40 CET
            },
            copenhagen: {
                premarket: { start: 7.25, end: 9 },
                regular: { start: 9, end: 17.5 },
                afterhours: { start: 17.5, end: 17.67 }
            },
            london: {
                premarket: { start: 8, end: 9 },           // 07:00-08:00 GMT = 08:00-09:00 CET
                regular: { start: 9, end: 17.5 },          // 08:00-16:30 GMT = 09:00-17:30 CET
                afterhours: { start: 17.5, end: 17.58 }    // 16:30-16:35 GMT = 17:30-17:35 CET
            },
            frankfurt: {
                premarket: { start: 8, end: 9 },
                regular: { start: 9, end: 17.5 },
                afterhours: { start: 17.5, end: 20 }
            }
        };

        function buildTimeline() {
            // Build hour labels
            const header = document.getElementById('timeline-header');
            header.innerHTML = '';
            for (let h = 0; h <= 24; h++) {
                const label = document.createElement('div');
                label.className = 'hour-label';
                label.textContent = h + 'H';
                label.dataset.hour = h;
                header.appendChild(label);
            }

            // Build each market timeline
            Object.keys(markets).forEach(marketId => {
                const market = markets[marketId];
                const timeline = document.getElementById(marketId + '-timeline');
                if (!timeline) return;

                timeline.innerHTML = '';
                timeline.style.position = 'relative';

                // Create hour segments
                for (let h = 0; h < 24; h++) {
                    const segment = document.createElement('div');
                    segment.className = 'hour-segment';
                    timeline.appendChild(segment);
                }

                // Add session overlays
                addSession(timeline, market.premarket, 'premarket', 'Pre-Market');
                addSession(timeline, market.regular, 'regular', 'Regular');
                addSession(timeline, market.afterhours, 'afterhours', 'After-Hours');
            });
        }

        function addSession(timeline, session, type, label) {
            if (!session) return;

            const startPercent = (session.start / 24) * 100;
            let endHour = session.end > 24 ? 24 : session.end;
            const widthPercent = ((endHour - session.start) / 24) * 100;

            if (widthPercent <= 0) return;

            const sessionEl = document.createElement('div');
            sessionEl.className = 'session session-' + type;
            sessionEl.style.left = startPercent + '%';
            sessionEl.style.width = widthPercent + '%';
            sessionEl.textContent = label;
            timeline.appendChild(sessionEl);

            // Handle sessions that wrap past midnight
            if (session.end > 24) {
                const wrapSession = document.createElement('div');
                wrapSession.className = 'session session-' + type;
                wrapSession.style.left = '0%';
                wrapSession.style.width = ((session.end - 24) / 24 * 100) + '%';
                wrapSession.textContent = label;
                timeline.appendChild(wrapSession);
            }
        }

        function updateCurrentTime() {
            const now = new Date();

            // Get Copenhagen time
            const cetOptions = { timeZone: 'Europe/Copenhagen', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };
            const cetTime = now.toLocaleTimeString('en-GB', cetOptions);
            document.getElementById('current-time').textContent = cetTime;

            // Get timezone info
            const tzName = now.toLocaleTimeString('en-GB', { timeZone: 'Europe/Copenhagen', timeZoneName: 'short' }).split(' ').pop();
            document.getElementById('timezone-info').textContent = tzName;

            // Get ET time
            const etOptions = { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false };
            const etTime = now.toLocaleTimeString('en-GB', etOptions);
            document.getElementById('et-time').textContent = etTime + ' ET';

            // Calculate current hour in CET as decimal
            const cetParts = cetTime.split(':');
            const currentHour = parseInt(cetParts[0]) + parseInt(cetParts[1]) / 60;

            // Update hour label highlighting
            document.querySelectorAll('.hour-label').forEach(label => {
                const hour = parseInt(label.dataset.hour);
                label.classList.toggle('current', hour === Math.floor(currentHour));
            });

            // Update current time line on timelines
            document.querySelectorAll('.timeline-bar').forEach(timeline => {
                let timeLine = timeline.querySelector('.current-time-line');
                if (!timeLine) {
                    timeLine = document.createElement('div');
                    timeLine.className = 'current-time-line';
                    timeLine.innerHTML = '<div class="current-time-dot"></div>';
                    timeline.appendChild(timeLine);
                }
                timeLine.style.left = (currentHour / 24 * 100) + '%';
            });

            // Update market statuses
            updateMarketStatus('nyse', currentHour, markets.nyse);
            updateMarketStatus('euronext', currentHour, markets.euronext);
            updateMarketStatus('london', currentHour, markets.london);
            updateMarketStatus('frankfurt', currentHour, markets.frankfurt);
        }

        function updateMarketStatus(marketId, currentHour, market) {
            const statusEl = document.getElementById(marketId + '-status');
            if (!statusEl) return;

            let status = 'Closed';
            let dotClass = 'closed';

            // Check if weekend
            const now = new Date();
            const day = now.getDay();
            const isWeekend = (day === 0 || day === 6);

            if (!isWeekend) {
                if (currentHour >= market.regular.start && currentHour < market.regular.end) {
                    status = 'Open';
                    dotClass = 'open';
                } else if (currentHour >= market.premarket.start && currentHour < market.premarket.end) {
                    status = 'Pre-Market';
                    dotClass = 'premarket';
                } else if (market.afterhours && currentHour >= market.afterhours.start && currentHour < market.afterhours.end) {
                    status = 'After-Hours';
                    dotClass = 'afterhours';
                } else if (market.afterhours && market.afterhours.end > 24) {
                    // Check wrapped after-hours (past midnight)
                    if (currentHour < (market.afterhours.end - 24)) {
                        status = 'After-Hours';
                        dotClass = 'afterhours';
                    }
                }
            }

            statusEl.innerHTML = '<span class="status-dot ' + dotClass + '"></span>' + status;
        }

        // Initialize
        buildTimeline();
        updateCurrentTime();
        setInterval(updateCurrentTime, 1000);
    </script>
</body>
</html>
"""


def sanitize_floats(obj):
    """Replace NaN and Infinity with None to make JSON-serializable"""
    import math
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_floats(item) for item in obj]
    return obj


def read_state_file():
    """Read state from JSON file (written by bot process)"""
    import os
    state_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'bot_state.json')
    try:
        with open(state_file, 'r', encoding='utf-8') as f:
            content = f.read()
        data = json.loads(content)
        return sanitize_floats(data)  # Clean NaN/Inf values
    except (FileNotFoundError, json.JSONDecodeError, IOError) as e:
        # Fall back to in-memory state if file not available
        return bot_state.get_state()


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    import os
    from dotenv import dotenv_values

    # Read current settings from .env
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    config = dotenv_values(env_path)

    strategy = config.get('STRATEGY_TYPE', 'BREAKOUT')
    lookback = config.get('BREAKOUT_LOOKBACK', '60')
    threshold = float(config.get('BREAKOUT_THRESHOLD', '0.002')) * 100
    atr_filter = config.get('ATR_FILTER', 'true').lower() == 'true'
    atr_min = float(config.get('ATR_MIN_THRESHOLD', '0.001')) * 100

    atr_text = f"ATR >= {atr_min:.2f}%" if atr_filter else "ATR OFF"
    subheader = f"{strategy} Strategy | {lookback}-tick Range | {threshold:.1f}% Threshold | {atr_text} | 24/7"

    # Replace the static subheader with dynamic values
    html = DASHBOARD_HTML.replace(
        'Breakout Strategy | 60-tick Range | 0.2% Threshold | ATR >= 0.05% | 24/7',
        subheader
    )
    return html


@app.get("/sectors", response_class=HTMLResponse)
async def get_sectors():
    return SECTORS_HTML


@app.get("/market-hours", response_class=HTMLResponse)
async def get_market_hours():
    return MARKET_HOURS_HTML


@app.get("/alpha-cake", response_class=HTMLResponse)
async def get_alpha_cake():
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Alpha Cake - Signal Layers</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Righteous&display=swap');
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            min-height: 100vh;
            background: #0d1117;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
            color: #c9d1d9;
            padding: 20px;
        }
        .nav-btn {
            display: inline-block;
            padding: 6px 14px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            background: #21262d;
            border: 1px solid #30363d;
            color: #c9d1d9;
            text-decoration: none;
            transition: all 0.2s;
            margin-bottom: 20px;
        }
        .nav-btn:hover { background: #30363d; border-color: #58a6ff; color: #58a6ff; }

        .header {
            text-align: center;
            margin-bottom: 40px;
        }
        .title {
            font-family: 'Orbitron', sans-serif;
            font-size: 48px;
            font-weight: 900;
            background: linear-gradient(180deg, #ffd700 0%, #ff8c00 50%, #ff6b6b 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            filter: drop-shadow(0 0 20px rgba(255, 215, 0, 0.5));
            letter-spacing: 4px;
        }
        .subtitle {
            font-family: 'Righteous', sans-serif;
            font-size: 24px;
            background: linear-gradient(180deg, #ff69b4 0%, #ff1493 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-top: -5px;
            letter-spacing: 8px;
        }
        .tagline {
            color: #8b949e;
            font-size: 14px;
            margin-top: 10px;
        }

        .container {
            display: flex;
            gap: 40px;
            max-width: 1400px;
            margin: 0 auto;
            align-items: flex-start;
        }

        .cake-visual {
            flex: 0 0 500px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        .cake {
            position: relative;
            width: 100%;
        }

        .cherry {
            width: 30px;
            height: 30px;
            background: radial-gradient(circle at 30% 30%, #ff6b6b, #dc143c);
            border-radius: 50%;
            margin: 0 auto 5px;
            box-shadow: 0 4px 15px rgba(220, 20, 60, 0.5);
            position: relative;
        }
        .cherry::before {
            content: '';
            position: absolute;
            top: -15px;
            left: 50%;
            width: 3px;
            height: 15px;
            background: #228b22;
            border-radius: 2px;
        }

        .layer {
            position: relative;
            margin: 0 auto;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: white;
            text-shadow: 0 2px 4px rgba(0,0,0,0.5);
            transition: all 0.3s ease;
            cursor: pointer;
            overflow: hidden;
        }
        .layer:hover {
            transform: scale(1.02);
            z-index: 10;
        }
        .layer::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
            transition: left 0.5s;
        }
        .layer:hover::before {
            left: 100%;
        }

        .layer-7 { width: 120px; height: 35px; background: linear-gradient(135deg, #ffd700, #ffaa00); }
        .layer-6 { width: 160px; height: 38px; background: linear-gradient(135deg, #ff8c00, #ff6600); margin-top: -2px; }
        .layer-5 { width: 200px; height: 40px; background: linear-gradient(135deg, #ff6b6b, #e74c3c); margin-top: -2px; }
        .layer-4 { width: 250px; height: 42px; background: linear-gradient(135deg, #e91e63, #c2185b); margin-top: -2px; }
        .layer-3 { width: 300px; height: 45px; background: linear-gradient(135deg, #9c27b0, #7b1fa2); margin-top: -2px; }
        .layer-2 { width: 370px; height: 50px; background: linear-gradient(135deg, #3f51b5, #303f9f); margin-top: -2px; }
        .layer-1 { width: 450px; height: 60px; background: linear-gradient(135deg, #1a1a2e, #16213e); margin-top: -2px; border: 2px solid #da3633; }

        .plate {
            width: 480px;
            height: 20px;
            background: linear-gradient(180deg, #8b949e, #6e7681);
            border-radius: 0 0 50% 50% / 0 0 100% 100%;
            margin-top: 5px;
        }

        .layer-info {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .info-card {
            background: #161b22;
            border: 2px solid #30363d;
            border-radius: 8px;
            padding: 16px;
            transition: all 0.3s ease;
        }
        .info-card:hover {
            border-color: #58a6ff;
            transform: translateX(5px);
        }
        .info-card.active {
            border-color: #ffd700;
            box-shadow: 0 0 20px rgba(255, 215, 0, 0.2);
        }

        .info-header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 8px;
        }
        .info-icon {
            font-size: 24px;
        }
        .info-title {
            font-weight: 700;
            font-size: 16px;
        }
        .info-desc {
            color: #8b949e;
            font-size: 13px;
            line-height: 1.5;
        }
        .info-signals {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 10px;
        }
        .signal-tag {
            background: #21262d;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 11px;
            color: #58a6ff;
            border: 1px solid #30363d;
        }

        .layer-1-card { border-color: #da3633; }
        .layer-1-card .info-title { color: #da3633; }
        .layer-2-card { border-color: #3f51b5; }
        .layer-2-card .info-title { color: #3f51b5; }
        .layer-3-card { border-color: #9c27b0; }
        .layer-3-card .info-title { color: #9c27b0; }
        .layer-4-card { border-color: #e91e63; }
        .layer-4-card .info-title { color: #e91e63; }
        .layer-5-card { border-color: #ff6b6b; }
        .layer-5-card .info-title { color: #ff6b6b; }
        .layer-6-card { border-color: #ff8c00; }
        .layer-6-card .info-title { color: #ff8c00; }
        .layer-7-card { border-color: #ffd700; }
        .layer-7-card .info-title { color: #ffd700; }

        .arrow {
            position: absolute;
            right: -30px;
            top: 50%;
            transform: translateY(-50%);
            color: #30363d;
            font-size: 20px;
            opacity: 0;
            transition: all 0.3s;
        }
        .layer:hover .arrow {
            opacity: 1;
            right: -40px;
            color: #58a6ff;
        }

        .flow-indicator {
            text-align: center;
            margin: 30px 0;
            color: #8b949e;
            font-size: 12px;
        }
        .flow-indicator .arrow-up {
            font-size: 24px;
            color: #3fb950;
            animation: bounce 1s infinite;
        }
        @keyframes bounce {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-5px); }
        }
    </style>
</head>
<body>
    <a href="/" class="nav-btn">← Dashboard</a>

    <div class="header">
        <div class="title">ALPHA</div>
        <div class="subtitle">CAKE</div>
        <div class="tagline">Layered Signal Analysis Framework</div>
    </div>

    <div class="container">
        <div class="cake-visual">
            <div class="cake">
                <div class="layer layer-7" data-layer="7">Earnings<span class="arrow">→</span></div>
                <div class="layer layer-6" data-layer="6">Events<span class="arrow">→</span></div>
                <div class="layer layer-5" data-layer="5">Management<span class="arrow">→</span></div>
                <div class="layer layer-4" data-layer="4">Competition<span class="arrow">→</span></div>
                <div class="layer layer-3" data-layer="3">Sector<span class="arrow">→</span></div>
                <div class="layer layer-2" data-layer="2">Macro Economics<span class="arrow">→</span></div>
                <div class="layer layer-1" data-layer="1">Geopolitical<span class="arrow">→</span></div>
                <div class="plate"></div>
            </div>
            <div class="flow-indicator">
                <div class="arrow-up">↑</div>
                <div>Signals flow up through layers</div>
                <div>Base events trigger rotations above</div>
            </div>
        </div>

        <div class="layer-info">
            <div class="info-card layer-7-card" data-layer="7">
                <div class="info-header">
                    <span class="info-icon">💰</span>
                    <span class="info-title">Layer 7: Earnings</span>
                </div>
                <div class="info-desc">
                    The top layer - quarterly earnings reports. Revenue, EPS, guidance, and surprises.
                    This is where all lower layers manifest into actual numbers. Beat or miss.
                </div>
                <div class="info-signals">
                    <span class="signal-tag">Revenue</span>
                    <span class="signal-tag">EPS</span>
                    <span class="signal-tag">Guidance</span>
                    <span class="signal-tag">Margins</span>
                    <span class="signal-tag">Surprise %</span>
                    <span class="signal-tag">Whisper Numbers</span>
                </div>
            </div>

            <div class="info-card layer-6-card" data-layer="6">
                <div class="info-header">
                    <span class="info-icon">📅</span>
                    <span class="info-title">Layer 6: Upcoming Events</span>
                </div>
                <div class="info-desc">
                    Scheduled catalysts that move stocks. Product launches, FDA approvals, conferences,
                    and investor days. Known events with unknown outcomes.
                </div>
                <div class="info-signals">
                    <span class="signal-tag">Product Launch</span>
                    <span class="signal-tag">FDA Decisions</span>
                    <span class="signal-tag">Conferences</span>
                    <span class="signal-tag">Investor Day</span>
                    <span class="signal-tag">Splits/Dividends</span>
                </div>
            </div>

            <div class="info-card layer-5-card" data-layer="5">
                <div class="info-header">
                    <span class="info-icon">👔</span>
                    <span class="info-title">Layer 5: Management & Leadership</span>
                </div>
                <div class="info-desc">
                    Executive changes, insider activity, and corporate governance.
                    CEO transitions, board changes, and leadership track records signal future direction.
                </div>
                <div class="info-signals">
                    <span class="signal-tag">CEO Changes</span>
                    <span class="signal-tag">Insider Buying</span>
                    <span class="signal-tag">Insider Selling</span>
                    <span class="signal-tag">Board Changes</span>
                    <span class="signal-tag">Guidance Style</span>
                </div>
            </div>

            <div class="info-card layer-4-card" data-layer="4">
                <div class="info-header">
                    <span class="info-icon">⚔️</span>
                    <span class="info-title">Layer 4: Competitive Landscape</span>
                </div>
                <div class="info-desc">
                    Direct competitors and market share battles. A competitor's weakness is your opportunity.
                    M&A activity, market disruption, and competitive moats.
                </div>
                <div class="info-signals">
                    <span class="signal-tag">Market Share</span>
                    <span class="signal-tag">M&A Activity</span>
                    <span class="signal-tag">New Entrants</span>
                    <span class="signal-tag">Price Wars</span>
                    <span class="signal-tag">Disruption</span>
                </div>
            </div>

            <div class="info-card layer-3-card" data-layer="3">
                <div class="info-header">
                    <span class="info-icon">🏭</span>
                    <span class="info-title">Layer 3: Sector Dynamics</span>
                </div>
                <div class="info-desc">
                    Industry-wide trends and rotations. Tech vs Value, Growth vs Defensive.
                    Sector ETF flows and industry-specific regulations impact all companies within.
                </div>
                <div class="info-signals">
                    <span class="signal-tag">Sector Rotation</span>
                    <span class="signal-tag">Industry Trends</span>
                    <span class="signal-tag">Regulations</span>
                    <span class="signal-tag">Supply Chain</span>
                    <span class="signal-tag">Commodity Prices</span>
                </div>
            </div>

            <div class="info-card layer-2-card" data-layer="2">
                <div class="info-header">
                    <span class="info-icon">📊</span>
                    <span class="info-title">Layer 2: Macro Economics</span>
                </div>
                <div class="info-desc">
                    Global economic factors that affect all markets. Interest rates, inflation, and monetary policy
                    determine the overall market direction and risk appetite.
                </div>
                <div class="info-signals">
                    <span class="signal-tag">Interest Rates</span>
                    <span class="signal-tag">Inflation (CPI/PPI)</span>
                    <span class="signal-tag">GDP Growth</span>
                    <span class="signal-tag">Unemployment</span>
                    <span class="signal-tag">Fed Policy</span>
                    <span class="signal-tag">Bond Yields</span>
                </div>
            </div>

            <div class="info-card layer-1-card" data-layer="1">
                <div class="info-header">
                    <span class="info-icon">🌍</span>
                    <span class="info-title">Layer 1: Geopolitical Events</span>
                </div>
                <div class="info-desc">
                    The foundation layer. War, conflicts, sanctions, and political shifts create massive market rotations.
                    These events ripple through ALL layers above, triggering sector rotations and flight-to-safety moves.
                </div>
                <div class="info-signals">
                    <span class="signal-tag">War / Conflicts</span>
                    <span class="signal-tag">Sanctions</span>
                    <span class="signal-tag">Elections</span>
                    <span class="signal-tag">Trade Wars</span>
                    <span class="signal-tag">Regime Change</span>
                </div>
            </div>
        </div>
    </div>

    <script>
        document.querySelectorAll('.layer').forEach(layer => {
            layer.addEventListener('mouseenter', () => {
                const layerNum = layer.dataset.layer;
                document.querySelectorAll('.info-card').forEach(card => {
                    card.classList.remove('active');
                    if (card.dataset.layer === layerNum) {
                        card.classList.add('active');
                        card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                    }
                });
            });
        });

        document.querySelectorAll('.info-card').forEach(card => {
            card.addEventListener('mouseenter', () => {
                const layerNum = card.dataset.layer;
                document.querySelectorAll('.layer').forEach(layer => {
                    if (layer.dataset.layer === layerNum) {
                        layer.style.transform = 'scale(1.05)';
                        layer.style.zIndex = '10';
                    }
                });
            });
            card.addEventListener('mouseleave', () => {
                document.querySelectorAll('.layer').forEach(layer => {
                    layer.style.transform = '';
                    layer.style.zIndex = '';
                });
            });
        });
    </script>
</body>
</html>
"""


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Use thread pool to avoid blocking event loop with file I/O
            state = await asyncio.to_thread(read_state_file)
            await websocket.send_json(state)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@app.get("/models", response_class=HTMLResponse)
async def get_models():
    import json
    import os
    models_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'models.json')
    try:
        with open(models_path, 'r') as f:
            models_data = json.load(f)
    except:
        models_data = {"models": {}, "active_model": "BREAKOUT"}

    models = models_data.get("models", {})
    active = models_data.get("active_model", "BREAKOUT")

    # Build model cards HTML
    model_cards = ""
    for key, model in models.items():
        is_active = key == active
        status_class = "active" if is_active else "saved"
        status_text = "ACTIVE" if is_active else "SAVED"

        params_html = ""
        for pkey, pval in model.get("parameters", {}).items():
            params_html += f'<div class="param-row"><span class="param-key">{pkey}</span><span class="param-val">{pval}</span></div>'

        backtest = model.get("backtest_results", {})
        backtest_html = ""
        if "net_return" in backtest:
            net_class = "positive" if backtest["net_return"] > 0 else "negative"
            backtest_html = f'''
                <div class="backtest-results">
                    <div class="result-row"><span>NET Return:</span><span class="{net_class}">{backtest["net_return"]:+.2f}%</span></div>
                    <div class="result-row"><span>Win Rate:</span><span>{backtest.get("win_rate", 0):.1f}%</span></div>
                    <div class="result-row"><span>Trades:</span><span>{backtest.get("trades", 0)}</span></div>
                    <div class="result-row"><span>Commission:</span><span>${backtest.get("commission", 0):.0f}</span></div>
                </div>
            '''
        elif "note" in backtest:
            backtest_html = f'<div class="backtest-note">{backtest["note"]}</div>'

        model_cards += f'''
            <div class="model-card {status_class}">
                <div class="model-header">
                    <div class="model-name">{model.get("name", key)}</div>
                    <span class="model-status {status_class}">{status_text}</span>
                </div>
                <div class="model-desc">{model.get("description", "")}</div>
                <div class="model-params">
                    <div class="params-title">Parameters</div>
                    {params_html}
                </div>
                {backtest_html}
                <div class="model-actions">
                    {"<span class='current-badge'>Currently Running</span>" if is_active else "<button class='activate-btn' onclick='activateModel(" + '"' + key + '"' + ")'>Activate Model</button>"}
                </div>
            </div>
        '''

    return f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Trading Models - Strategy Manager</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            min-height: 100vh;
            background: #0d1117;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
            color: #c9d1d9;
            padding: 20px;
        }}
        .nav-btn {{
            display: inline-block;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            background: #21262d;
            border: 1px solid #30363d;
            color: #c9d1d9;
            text-decoration: none;
            transition: all 0.2s;
            margin-bottom: 20px;
        }}
        .nav-btn:hover {{ background: #30363d; border-color: #58a6ff; color: #58a6ff; }}

        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #30363d;
        }}
        .title {{
            font-size: 28px;
            font-weight: 700;
            background: linear-gradient(135deg, #58a6ff, #a371f7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        .subtitle {{ color: #8b949e; font-size: 14px; margin-top: 4px; }}

        .models-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
            max-width: 1400px;
        }}
        .model-card {{
            background: #161b22;
            border: 2px solid #30363d;
            border-radius: 12px;
            padding: 20px;
            transition: all 0.3s;
        }}
        .model-card:hover {{ border-color: #58a6ff; }}
        .model-card.active {{ border-color: #238636; box-shadow: 0 0 20px rgba(35, 134, 54, 0.3); }}

        .model-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }}
        .model-name {{ font-size: 18px; font-weight: 700; color: #58a6ff; }}
        .model-status {{
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
        }}
        .model-status.active {{ background: #238636; color: white; }}
        .model-status.saved {{ background: #30363d; color: #8b949e; }}

        .model-desc {{
            color: #8b949e;
            font-size: 13px;
            line-height: 1.5;
            margin-bottom: 16px;
        }}
        .model-params {{
            background: #0d1117;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 16px;
        }}
        .params-title {{
            font-size: 10px;
            color: #8b949e;
            text-transform: uppercase;
            margin-bottom: 8px;
            font-weight: 600;
        }}
        .param-row {{
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            padding: 4px 0;
            border-bottom: 1px solid #21262d;
        }}
        .param-row:last-child {{ border-bottom: none; }}
        .param-key {{ color: #8b949e; }}
        .param-val {{ color: #c9d1d9; font-weight: 600; font-family: monospace; }}

        .backtest-results {{
            background: #0d1117;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 16px;
        }}
        .result-row {{
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            padding: 4px 0;
        }}
        .result-row .positive {{ color: #3fb950; font-weight: 700; }}
        .result-row .negative {{ color: #f85149; font-weight: 700; }}

        .backtest-note {{
            background: #0d1117;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 16px;
            font-size: 12px;
            color: #8b949e;
            font-style: italic;
        }}

        .model-actions {{ text-align: center; }}
        .activate-btn {{
            background: linear-gradient(135deg, #238636, #2ea043);
            border: none;
            color: white;
            padding: 10px 24px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .activate-btn:hover {{ transform: scale(1.05); box-shadow: 0 0 15px rgba(35, 134, 54, 0.5); }}
        .current-badge {{
            display: inline-block;
            background: #238636;
            color: white;
            padding: 10px 24px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 700;
        }}

        .info-box {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 16px;
            margin-top: 30px;
            max-width: 600px;
        }}
        .info-box h3 {{ font-size: 14px; margin-bottom: 8px; color: #58a6ff; }}
        .info-box p {{ font-size: 12px; color: #8b949e; line-height: 1.6; }}
    </style>
</head>
<body>
    <a href="/" class="nav-btn">Back to Dashboard</a>

    <div class="header">
        <div>
            <div class="title">Trading Models</div>
            <div class="subtitle">Strategy Manager - Compare and Activate Trading Strategies</div>
        </div>
    </div>

    <div class="models-grid">
        {model_cards}
    </div>

    <div class="info-box">
        <h3>How to Switch Models</h3>
        <p>
            Click "Activate Model" to switch strategies. This will update your .env file with the new parameters.
            The bot will need to be restarted for changes to take effect. Commission costs are based on $1.00/order ($2.00 round-trip).
        </p>
    </div>

    <script>
        function activateModel(modelKey) {{
            if (confirm('Switch to ' + modelKey + ' strategy? Bot restart required for changes.')) {{
                fetch('/api/models/activate/' + modelKey, {{ method: 'POST' }})
                    .then(r => r.json())
                    .then(data => {{
                        if (data.success) {{
                            alert('Model activated! Restart the bot to apply changes.');
                            location.reload();
                        }} else {{
                            alert('Error: ' + data.error);
                        }}
                    }});
            }}
        }}
    </script>
</body>
</html>
'''


@app.post("/api/models/activate/{model_key}")
async def activate_model(model_key: str):
    import json
    import os

    models_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'models.json')
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')

    try:
        with open(models_path, 'r') as f:
            models_data = json.load(f)

        if model_key not in models_data.get("models", {}):
            return {"success": False, "error": "Model not found"}

        # Update active model
        models_data["active_model"] = model_key

        # Update status flags
        for key in models_data["models"]:
            models_data["models"][key]["status"] = "active" if key == model_key else "saved"

        with open(models_path, 'w') as f:
            json.dump(models_data, f, indent=2)

        # Update .env with new strategy type
        model = models_data["models"][model_key]
        params = model.get("parameters", {})

        # Read current .env
        with open(env_path, 'r') as f:
            env_content = f.read()

        # Update STRATEGY_TYPE
        import re
        env_content = re.sub(r'STRATEGY_TYPE=.*', f'STRATEGY_TYPE={model_key}', env_content)

        with open(env_path, 'w') as f:
            f.write(env_content)

        return {"success": True, "model": model_key}

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/stocks")
async def get_stocks():
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, read_state_file)


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

        # Calculate algo trading signals (MA crossover with 0.3% threshold)
        if i >= 20 and i > 0:  # Need MA21 and previous bar
            prev_bar = history[i-1]
            if prev_bar.get('ma8') and prev_bar.get('ma21') and bar['ma8'] and bar['ma21']:
                threshold = 0.008  # 0.8% threshold matching strategy

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
    """Get extended news list with professional sentiment analysis"""
    # Try Alpha Vantage first (professional news with AI sentiment)
    if av_news_available and av_client:
        try:
            av_result = av_client.get_news_sentiment(symbol.upper(), limit=limit)
            if av_result and av_result.get('articles'):
                # Format for dashboard compatibility
                formatted_news = []
                for article in av_result['articles']:
                    formatted_news.append({
                        'title': article['title'],
                        'link': article['url'],
                        'source': article['source'],
                        'time_ago': article['time_ago'],
                        'sentiment': article['sentiment_label'],
                        'sentiment_score': article['sentiment_score'],  # -1 to +1
                        'relevance': article['relevance_score'],
                        'summary': article.get('summary', '')
                    })
                return {
                    "symbol": symbol.upper(),
                    "news": formatted_news,
                    "overall_sentiment": av_result['overall_sentiment'],
                    "article_count": av_result['article_count'],
                    "source": "Alpha Vantage (Professional AI Sentiment)"
                }
        except Exception as e:
            print(f"Alpha Vantage news error: {e}")

    # Fallback to YFinance if Alpha Vantage fails
    news = yf_client.get_news(symbol.upper(), limit=limit)
    return {
        "symbol": symbol.upper(),
        "news": news,
        "source": "Yahoo Finance (VADER Sentiment)"
    }


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
