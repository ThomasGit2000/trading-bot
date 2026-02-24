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

        table { width: 100%; border-collapse: collapse; }
        th {
            text-align: left; padding: 6px 8px; font-size: 10px;
            color: #8b949e; text-transform: uppercase; border-bottom: 1px solid #30363d;
        }
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
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <div class="header">
        <h1>Master Board - NO STOPS MA(10/30)</h1>
        <div>
            <span id="connection-status" class="status-badge status-disconnected">...</span>
            <span id="trading-mode" class="status-badge status-dry">DRY</span>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Symbol</th>
                <th>Category</th>
                <th>Price</th>
                <th>Pos</th>
                <th>Target</th>
                <th>Data</th>
                <th>Signal</th>
                <th>MA(10)</th>
                <th>MA(30)</th>
                <th>News</th>
            </tr>
        </thead>
        <tbody id="stocks-body">
            <tr><td colspan="10" style="text-align:center;color:#8b949e;">Loading...</td></tr>
        </tbody>
    </table>

    <div class="footer">
        <span id="last-update">--</span>
        <span id="stock-count">0 stocks</span>
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

        function connect() {
            ws = new WebSocket(`ws://${window.location.host}/ws`);
            ws.onopen = () => {
                document.getElementById('connection-status').textContent = 'LIVE';
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
                document.getElementById('connection-status').textContent = 'OFF';
                document.getElementById('connection-status').className = 'status-badge status-disconnected';
                setTimeout(connect, 2000);
            };
        }

        function updateDashboard(data) {
            const mode = document.getElementById('trading-mode');
            mode.textContent = data.dry_run ? 'DRY' : 'LIVE';
            mode.className = 'status-badge ' + (data.dry_run ? 'status-dry' : 'status-live');

            const body = document.getElementById('stocks-body');
            if (data.stocks && data.stocks.length > 0) {
                body.innerHTML = data.stocks.map(createRow).join('');
            }

            document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
            document.getElementById('stock-count').textContent = (data.stocks?.length || 0) + ' stocks';
        }

        function createRow(s) {
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
                    <td><span class="symbol">${s.symbol}</span></td>
                    <td class="category-cell">${catName}</td>
                    <td class="price ${priceClass}">$${s.price?.toFixed(2) || '--'}${changeStr}</td>
                    <td class="${hasPos ? 'position' : 'no-position'}">${s.position || 0}</td>
                    <td>${s.position_size}</td>
                    <td>${s.prices_collected}/30</td>
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

        function getNewsSentiment(news) {
            if (!news || news.length === 0) return 0;
            let score = 0;
            news.forEach(n => {
                if (n.sentiment === 'positive') score += 33;
                else if (n.sentiment === 'negative') score -= 33;
            });
            return Math.max(-100, Math.min(100, score));
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
                const ma10 = data.data.map(d => d.ma10);
                const ma30 = data.data.map(d => d.ma30);

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
                                label: 'MA(10)',
                                data: ma10,
                                borderColor: '#f0883e',
                                borderWidth: 1.5,
                                borderDash: [5, 5],
                                fill: false,
                                tension: 0.1,
                                pointRadius: 0
                            },
                            {
                                label: 'MA(30)',
                                data: ma30,
                                borderColor: '#58a6ff',
                                borderWidth: 1.5,
                                borderDash: [5, 5],
                                fill: false,
                                tension: 0.1,
                                pointRadius: 0
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


@app.get("/api/stock/{symbol}/history")
async def get_stock_history(symbol: str, period: str = "1mo", interval: str = "1d"):
    """Get historical OHLCV data with pre-calculated MAs for charting"""
    history = yf_client.get_history(symbol.upper(), period=period, interval=interval)

    # Calculate MAs
    closes = [bar['close'] for bar in history]
    for i, bar in enumerate(history):
        bar['date'] = bar['date'].isoformat() if hasattr(bar['date'], 'isoformat') else str(bar['date'])
        # Calculate MA10
        if i >= 9:
            bar['ma10'] = sum(closes[i-9:i+1]) / 10
        else:
            bar['ma10'] = None
        # Calculate MA30
        if i >= 29:
            bar['ma30'] = sum(closes[i-29:i+1]) / 30
        else:
            bar['ma30'] = None

    return {"symbol": symbol.upper(), "period": period, "interval": interval, "data": history}


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
