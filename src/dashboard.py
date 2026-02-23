import asyncio
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from typing import List
import uvicorn

from src.dashboard_state import bot_state

app = FastAPI(title="Trading Bot Dashboard")


class ConnectionManager:
    """Manage WebSocket connections"""
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)


manager = ConnectionManager()

# Load HTML template
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Bot Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e; color: #eee; padding: 20px;
        }
        .header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #333;
        }
        .status-indicator {
            display: flex; align-items: center; gap: 8px; margin-top: 8px;
        }
        .status-dot {
            width: 12px; height: 12px; border-radius: 50%;
            animation: pulse 2s infinite;
        }
        .status-dot.connected { background: #4ade80; }
        .status-dot.disconnected { background: #f87171; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px; margin-bottom: 20px;
        }
        .card {
            background: #16213e; border-radius: 12px; padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .card h3 {
            font-size: 0.85rem; text-transform: uppercase;
            color: #888; margin-bottom: 12px; letter-spacing: 1px;
        }
        .card .value { font-size: 2rem; font-weight: 700; }
        .card .sub { font-size: 0.9rem; color: #888; margin-top: 8px; }

        .signal { padding: 6px 16px; border-radius: 20px; font-weight: 600; }
        .signal.BUY { background: #166534; color: #4ade80; }
        .signal.SELL { background: #7f1d1d; color: #f87171; }
        .signal.HOLD { background: #374151; color: #9ca3af; }

        .mode-badge {
            padding: 4px 12px; border-radius: 12px; font-size: 0.75rem;
            font-weight: 600; text-transform: uppercase;
        }
        .mode-badge.dry { background: #fbbf24; color: #000; }
        .mode-badge.live { background: #ef4444; color: #fff; }

        .data-badge {
            padding: 4px 12px; border-radius: 12px; font-size: 0.75rem;
            font-weight: 600; margin-left: 8px;
        }
        .data-badge.live { background: #22c55e; color: #fff; }
        .data-badge.delayed { background: #f59e0b; color: #000; }

        .chart-container {
            background: #16213e; border-radius: 12px; padding: 20px;
            height: 350px;
        }

        .ma-values { display: flex; gap: 20px; margin-top: 10px; }
        .ma-item { display: flex; align-items: center; gap: 8px; }
        .ma-dot { width: 10px; height: 10px; border-radius: 50%; }
        .ma-dot.short { background: #f97316; }
        .ma-dot.long { background: #3b82f6; }

        .hero-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 12px; margin-bottom: 16px;
        }
        .hero-card {
            background: #16213e; border-radius: 10px; padding: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            text-align: center;
        }
        .hero-card h3 {
            font-size: 0.7rem; text-transform: uppercase;
            color: #888; margin-bottom: 4px; letter-spacing: 1px;
        }
        .hero-card .ticker {
            font-size: 1.8rem; font-weight: 800; color: #4ade80;
        }
        .hero-card .live-price {
            font-size: 1.8rem; font-weight: 800; color: #fff;
        }
        .hero-card .probability {
            font-size: 1.5rem; font-weight: 700;
        }
        .hero-card .probability.high { color: #4ade80; }
        .hero-card .probability.medium { color: #fbbf24; }
        .hero-card .probability.low { color: #9ca3af; }
        .hero-card .sub { font-size: 0.75rem; color: #888; margin-top: 4px; }
        .hero-card .model-name { font-size: 1.1rem; font-weight: 700; color: #a855f7; }
        .hero-card .agent-status { font-size: 1.2rem; font-weight: 700; }
        .hero-card .agent-status.active { color: #4ade80; }
        .hero-card .agent-status.inactive { color: #f87171; }

        .heartbeat {
            display: inline-flex; align-items: center; gap: 6px;
            padding: 4px 10px; border-radius: 12px; font-size: 0.7rem;
            font-weight: 600; margin-left: 12px;
        }
        .heartbeat .dot {
            width: 8px; height: 8px; border-radius: 50%;
        }
        .heartbeat.live { background: rgba(74, 222, 128, 0.2); color: #4ade80; }
        .heartbeat.live .dot { background: #4ade80; animation: pulse 1s infinite; }
        .heartbeat.stale { background: rgba(251, 191, 36, 0.2); color: #fbbf24; }
        .heartbeat.stale .dot { background: #fbbf24; }
        .heartbeat.old { background: rgba(248, 113, 113, 0.2); color: #f87171; }
        .heartbeat.old .dot { background: #f87171; }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>Trading Bot Dashboard</h1>
            <div class="status-indicator">
                <div class="status-dot" id="connStatus"></div>
                <span id="connText">Connecting...</span>
                <span class="mode-badge" id="modeBadge">-</span>
                <span class="data-badge" id="dataBadge">-</span>
                <span class="heartbeat" id="heartbeat"><span class="dot"></span><span id="heartbeatText">-</span></span>
            </div>
        </div>
    </div>

    <div class="hero-grid">
        <div class="hero-card">
            <h3>Stock</h3>
            <div class="ticker" id="symbolDisplay">-</div>
            <div class="sub">NYSE</div>
        </div>
        <div class="hero-card">
            <h3>Price</h3>
            <div class="live-price" id="livePrice">-</div>
            <div class="sub">Bid: <span id="bid">-</span> | Ask: <span id="ask">-</span></div>
        </div>
        <div class="hero-card">
            <h3>Trade Prob</h3>
            <div class="probability" id="tradeProbability">-</div>
            <div class="sub" id="probDirection">-</div>
        </div>
        <div class="hero-card">
            <h3>Model</h3>
            <div class="model-name">MA Crossover</div>
            <div class="sub">10/30 + RSI</div>
        </div>
        <div class="hero-card">
            <h3>Agent</h3>
            <div class="agent-status" id="agentStatus">-</div>
            <div class="sub" id="agentSub">-</div>
        </div>
    </div>

    <div class="grid">
        <div class="card">
            <h3>Current Price</h3>
            <div class="value" id="price">-</div>
            <div class="sub">Spread: <span id="spread">-</span></div>
        </div>
        <div class="card">
            <h3>Position</h3>
            <div class="value" id="position">-</div>
            <div class="sub">Target size: <span id="posSize">-</span> shares</div>
        </div>
        <div class="card">
            <h3>Signal</h3>
            <div class="value"><span class="signal" id="signal">-</span></div>
            <div class="sub">Prices collected: <span id="pricesCount">-</span></div>
        </div>
        <div class="card">
            <h3>Moving Averages</h3>
            <div class="ma-values">
                <div class="ma-item"><div class="ma-dot short"></div>Short MA: <span id="shortMa">-</span></div>
            </div>
            <div class="ma-values" style="margin-top: 8px;">
                <div class="ma-item"><div class="ma-dot long"></div>Long MA: <span id="longMa">-</span></div>
            </div>
            <div class="sub" style="margin-top: 10px;">Windows: <span id="windows">-</span></div>
        </div>
    </div>

    <div class="chart-container">
        <canvas id="priceChart"></canvas>
    </div>

    <div class="chart-container" style="height: 200px; margin-top: 20px;">
        <canvas id="rsiChart"></canvas>
    </div>

    <script>
        const ctx = document.getElementById('priceChart').getContext('2d');
        const chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    { label: 'Price', data: [], borderColor: '#4ade80', borderWidth: 2, fill: false, tension: 0.1, pointRadius: 0 },
                    { label: 'Short MA', data: [], borderColor: '#f97316', borderWidth: 2, fill: false, tension: 0.1, borderDash: [5,5], pointRadius: 0 },
                    { label: 'Long MA', data: [], borderColor: '#3b82f6', borderWidth: 2, fill: false, tension: 0.1, borderDash: [5,5], pointRadius: 0 }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { grid: { color: '#333' }, ticks: { color: '#888' } },
                    x: { grid: { color: '#333' }, ticks: { color: '#888', maxTicksLimit: 10 } }
                },
                plugins: { legend: { labels: { color: '#888' } } },
                animation: { duration: 0 }
            }
        });

        const rsiCtx = document.getElementById('rsiChart').getContext('2d');
        const rsiChart = new Chart(rsiCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'RSI (14)',
                    data: [],
                    borderColor: '#a855f7',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1,
                    pointRadius: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        min: 0, max: 100,
                        grid: { color: '#333' },
                        ticks: { color: '#888' }
                    },
                    x: { grid: { color: '#333' }, ticks: { color: '#888', maxTicksLimit: 10 } }
                },
                plugins: {
                    legend: { labels: { color: '#888' } },
                    annotation: {
                        annotations: {
                            overbought: { type: 'line', yMin: 70, yMax: 70, borderColor: '#ef4444', borderWidth: 1, borderDash: [5,5] },
                            oversold: { type: 'line', yMin: 30, yMax: 30, borderColor: '#22c55e', borderWidth: 1, borderDash: [5,5] }
                        }
                    }
                },
                animation: { duration: 0 }
            }
        });

        function calcMA(prices, window) {
            if (prices.length < window) return [];
            const result = [];
            for (let i = 0; i < prices.length; i++) {
                if (i < window - 1) { result.push(null); continue; }
                const slice = prices.slice(i - window + 1, i + 1);
                result.push(slice.reduce((a,b) => a+b, 0) / window);
            }
            return result;
        }

        function updateUI(data) {
            const dot = document.getElementById('connStatus');
            const text = document.getElementById('connText');
            dot.className = 'status-dot ' + (data.status.connected ? 'connected' : 'disconnected');
            text.textContent = data.status.connected ? 'Connected to IB' : 'Disconnected';

            const badge = document.getElementById('modeBadge');
            badge.className = 'mode-badge ' + (data.status.dry_run ? 'dry' : 'live');
            badge.textContent = data.status.dry_run ? 'PAPER' : 'REAL $';

            const dataBadge = document.getElementById('dataBadge');
            const isStreaming = data.status.is_live_streaming;
            dataBadge.className = 'data-badge ' + (isStreaming ? 'live' : 'delayed');
            dataBadge.textContent = isStreaming ? 'STREAMING' : 'HISTORICAL';

            // Heartbeat - data freshness
            const heartbeat = document.getElementById('heartbeat');
            const heartbeatText = document.getElementById('heartbeatText');
            const priceAge = data.status.price_age_seconds;
            const isLive = data.status.is_live_streaming;

            if (isLive && priceAge < 10) {
                heartbeat.className = 'heartbeat live';
                heartbeatText.textContent = 'LIVE';
            } else if (priceAge < 300) {
                heartbeat.className = 'heartbeat stale';
                const mins = Math.floor(priceAge / 60);
                heartbeatText.textContent = mins > 0 ? mins + 'm ago' : Math.floor(priceAge) + 's ago';
            } else {
                heartbeat.className = 'heartbeat old';
                const hours = Math.floor(priceAge / 3600);
                const mins = Math.floor((priceAge % 3600) / 60);
                heartbeatText.textContent = hours > 0 ? hours + 'h ' + mins + 'm old' : mins + 'm old';
            }

            // Agent status
            const agentStatus = document.getElementById('agentStatus');
            const agentSub = document.getElementById('agentSub');
            const isActive = data.status.connected && data.price.current > 0;
            agentStatus.textContent = isActive ? 'ACTIVE' : 'INACTIVE';
            agentStatus.className = 'agent-status ' + (isActive ? 'active' : 'inactive');
            agentSub.textContent = data.status.connected ? (isActive ? 'Trading' : 'No data') : 'Disconnected';

            // Hero section - Stock, Live Price, Trade Probability
            document.getElementById('symbolDisplay').textContent = data.position.symbol || '-';
            document.getElementById('livePrice').textContent = data.price.current > 0 ? '$' + data.price.current.toFixed(2) : '-';
            document.getElementById('price').textContent = data.price.current > 0 ? '$' + data.price.current.toFixed(2) : '-';
            document.getElementById('bid').textContent = data.price.bid > 0 ? '$' + data.price.bid.toFixed(2) : '-';
            document.getElementById('ask').textContent = data.price.ask > 0 ? '$' + data.price.ask.toFixed(2) : '-';
            document.getElementById('spread').textContent = data.price.spread > 0 ? '$' + data.price.spread.toFixed(4) : '-';

            // Calculate trade probability based on MA crossover proximity
            const shortMa = data.strategy.short_ma;
            const longMa = data.strategy.long_ma;
            const probEl = document.getElementById('tradeProbability');
            const probDir = document.getElementById('probDirection');

            if (shortMa > 0 && longMa > 0) {
                const ratio = shortMa / longMa;
                const buyThreshold = 1.01;  // 1% above
                const sellThreshold = 0.99; // 1% below

                let probability = 0;
                let direction = '';

                if (ratio >= buyThreshold) {
                    probability = 100;
                    direction = 'BUY Signal Active';
                } else if (ratio <= sellThreshold) {
                    probability = 100;
                    direction = 'SELL Signal Active';
                } else if (ratio > 1) {
                    // Approaching buy threshold
                    probability = Math.round(((ratio - 1) / 0.01) * 100);
                    direction = 'Approaching BUY';
                } else {
                    // Approaching sell threshold
                    probability = Math.round(((1 - ratio) / 0.01) * 100);
                    direction = 'Approaching SELL';
                }

                probEl.textContent = probability + '%';
                probEl.className = 'probability ' + (probability >= 70 ? 'high' : probability >= 40 ? 'medium' : 'low');
                probDir.textContent = direction;
            } else {
                probEl.textContent = '-';
                probEl.className = 'probability low';
                probDir.textContent = 'Waiting for data...';
            }

            document.getElementById('position').textContent = data.position.current + ' shares';
            document.getElementById('posSize').textContent = data.position.size;

            const sig = document.getElementById('signal');
            sig.textContent = data.strategy.signal;
            sig.className = 'signal ' + data.strategy.signal;
            document.getElementById('pricesCount').textContent = data.strategy.prices_collected;

            document.getElementById('shortMa').textContent = data.strategy.short_ma > 0 ? '$' + data.strategy.short_ma.toFixed(4) : '-';
            document.getElementById('longMa').textContent = data.strategy.long_ma > 0 ? '$' + data.strategy.long_ma.toFixed(4) : '-';
            document.getElementById('windows').textContent = data.strategy.short_window + '/' + data.strategy.long_window;

            // Use historical data if available, otherwise use session prices
            const histPrices = data.chart_data.historical_prices;
            const histTimes = data.chart_data.historical_times;
            const rsiData = data.chart_data.rsi;

            if (histPrices && histPrices.length > 0) {
                chart.data.labels = histTimes;
                chart.data.datasets[0].data = histPrices;
                chart.data.datasets[1].data = calcMA(histPrices, data.strategy.short_window);
                chart.data.datasets[2].data = calcMA(histPrices, data.strategy.long_window);
                chart.update('none');

                // Update RSI chart
                rsiChart.data.labels = histTimes;
                rsiChart.data.datasets[0].data = rsiData;
                rsiChart.update('none');
            } else {
                const prices = data.chart_data.prices;
                if (prices.length > 0) {
                    chart.data.labels = prices.map((_, i) => i + 1);
                    chart.data.datasets[0].data = prices;
                    chart.data.datasets[1].data = calcMA(prices, data.strategy.short_window);
                    chart.data.datasets[2].data = calcMA(prices, data.strategy.long_window);
                    chart.update('none');
                }
            }
        }

        function connect() {
            const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
            const ws = new WebSocket(protocol + '//' + location.host + '/ws');

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                updateUI(data);
            };

            ws.onclose = () => {
                document.getElementById('connStatus').className = 'status-dot disconnected';
                document.getElementById('connText').textContent = 'Dashboard reconnecting...';
                setTimeout(connect, 3000);
            };

            ws.onerror = () => ws.close();
        }

        connect();
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Serve the dashboard HTML"""
    return DASHBOARD_HTML


@app.get("/api/state")
async def get_state():
    """REST endpoint for current state"""
    return bot_state.to_dict()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.send_json(bot_state.to_dict())
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


def run_dashboard(host: str = "0.0.0.0", port: int = 8080):
    """Start the dashboard server"""
    uvicorn.run(app, host=host, port=port, log_level="warning")
