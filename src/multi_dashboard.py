"""
Scalable Multi-Stock Trading Dashboard
Displays multiple stocks with real-time updates via WebSocket.
"""
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from typing import List
import uvicorn
import json

from src.dashboard_state import bot_state

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
    <title>Multi-Stock Trading Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117; color: #c9d1d9; padding: 20px;
            min-height: 100vh;
        }
        .header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #30363d;
        }
        .header h1 { font-size: 24px; font-weight: 600; }
        .status-badge {
            padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;
        }
        .status-live { background: #238636; }
        .status-dry { background: #f0883e; }
        .status-disconnected { background: #da3633; }

        .stocks-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
        }

        .stock-card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 20px;
            transition: border-color 0.2s;
        }
        .stock-card:hover { border-color: #58a6ff; }
        .stock-card.has-position { border-left: 4px solid #238636; }

        .stock-header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 16px;
        }
        .stock-symbol {
            font-size: 28px; font-weight: 700; color: #58a6ff;
        }
        .stock-price {
            font-size: 24px; font-weight: 600;
        }
        .price-up { color: #3fb950; }
        .price-down { color: #f85149; }

        .stock-details {
            display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px;
            margin-bottom: 16px;
        }
        .detail-item {
            background: #21262d; padding: 12px; border-radius: 8px;
        }
        .detail-label { font-size: 11px; color: #8b949e; text-transform: uppercase; }
        .detail-value { font-size: 18px; font-weight: 600; margin-top: 4px; }

        .signal-display {
            text-align: center; padding: 16px; border-radius: 8px;
            font-size: 20px; font-weight: 700;
        }
        .signal-buy { background: #238636; color: white; }
        .signal-sell { background: #da3633; color: white; }
        .signal-hold { background: #30363d; color: #8b949e; }
        .signal-wait { background: #21262d; color: #6e7681; }

        .ma-display {
            display: flex; justify-content: space-around; margin-top: 12px;
            padding: 12px; background: #21262d; border-radius: 8px;
        }
        .ma-item { text-align: center; }
        .ma-label { font-size: 11px; color: #8b949e; }
        .ma-value { font-size: 16px; font-weight: 600; }
        .ma-short { color: #58a6ff; }
        .ma-long { color: #f0883e; }

        .probability-section {
            margin-top: 12px; padding: 12px; background: #21262d; border-radius: 8px;
        }
        .probability-header {
            display: flex; justify-content: space-between; margin-bottom: 8px;
            font-size: 11px; color: #8b949e; text-transform: uppercase;
        }
        .probability-bars {
            display: flex; gap: 8px;
        }
        .prob-bar-container {
            flex: 1;
        }
        .prob-bar-label {
            display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px;
        }
        .prob-bar {
            height: 8px; background: #161b22; border-radius: 4px; overflow: hidden;
        }
        .prob-fill-buy {
            height: 100%; background: linear-gradient(90deg, #238636, #3fb950);
            transition: width 0.5s ease;
        }
        .prob-fill-sell {
            height: 100%; background: linear-gradient(90deg, #da3633, #f85149);
            transition: width 0.5s ease;
        }
        .prob-value { font-weight: 600; }
        .prob-value-buy { color: #3fb950; }
        .prob-value-sell { color: #f85149; }
        .prob-high { animation: glow 1s infinite alternate; }
        @keyframes glow {
            from { filter: brightness(1); }
            to { filter: brightness(1.3); }
        }

        .progress-bar {
            height: 4px; background: #21262d; border-radius: 2px; margin-top: 8px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%; background: #58a6ff; transition: width 0.3s;
        }

        .events-section {
            margin-top: 12px; padding: 12px; background: #21262d; border-radius: 8px;
        }
        .events-header {
            font-size: 11px; color: #8b949e; text-transform: uppercase; margin-bottom: 8px;
        }
        .event-item {
            display: flex; justify-content: space-between; padding: 4px 0;
            font-size: 13px; border-bottom: 1px solid #30363d;
        }
        .event-item:last-child { border-bottom: none; }
        .event-label { color: #8b949e; }
        .event-value { color: #f0883e; font-weight: 600; }

        .news-section {
            margin-top: 12px; padding: 12px; background: #21262d; border-radius: 8px;
        }
        .news-header {
            font-size: 11px; color: #8b949e; text-transform: uppercase; margin-bottom: 8px;
        }
        .news-item {
            padding: 8px 0; border-bottom: 1px solid #30363d;
        }
        .news-item:last-child { border-bottom: none; }
        .news-title {
            font-size: 12px; color: #c9d1d9; line-height: 1.4;
        }
        .news-meta {
            display: flex; justify-content: space-between; margin-top: 4px;
            font-size: 11px; color: #8b949e;
        }
        .sentiment-positive { color: #3fb950; }
        .sentiment-negative { color: #f85149; }
        .sentiment-neutral { color: #8b949e; }

        .footer {
            margin-top: 24px; padding-top: 16px; border-top: 1px solid #30363d;
            display: flex; justify-content: space-between; color: #8b949e; font-size: 12px;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .updating { animation: pulse 1s infinite; }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>Multi-Stock Trading Bot</h1>
            <div style="color: #8b949e; font-size: 14px; margin-top: 4px;">
                Strategy: NO STOPS MA(10/30)
            </div>
        </div>
        <div>
            <span id="connection-status" class="status-badge status-disconnected">Connecting...</span>
            <span id="trading-mode" class="status-badge status-dry">DRY RUN</span>
        </div>
    </div>

    <div id="stocks-container" class="stocks-grid">
        <div class="stock-card">
            <div style="text-align: center; padding: 40px; color: #8b949e;">
                Loading stocks...
            </div>
        </div>
    </div>

    <div class="footer">
        <div id="last-update">Last update: --</div>
        <div id="strategy-info">Waiting for data...</div>
    </div>

    <script>
        let ws;
        let reconnectAttempts = 0;

        function connect() {
            ws = new WebSocket(`ws://${window.location.host}/ws`);

            ws.onopen = () => {
                console.log('WebSocket connected');
                document.getElementById('connection-status').textContent = 'Connected';
                document.getElementById('connection-status').className = 'status-badge status-live';
                reconnectAttempts = 0;
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                updateDashboard(data);
            };

            ws.onclose = () => {
                document.getElementById('connection-status').textContent = 'Disconnected';
                document.getElementById('connection-status').className = 'status-badge status-disconnected';
                setTimeout(connect, Math.min(1000 * Math.pow(2, reconnectAttempts++), 30000));
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        }

        function updateDashboard(data) {
            // Update trading mode
            const modeEl = document.getElementById('trading-mode');
            if (data.dry_run) {
                modeEl.textContent = 'DRY RUN';
                modeEl.className = 'status-badge status-dry';
            } else {
                modeEl.textContent = 'LIVE';
                modeEl.className = 'status-badge status-live';
            }

            // Update stocks
            const container = document.getElementById('stocks-container');
            if (data.stocks && data.stocks.length > 0) {
                container.innerHTML = data.stocks.map(stock => createStockCard(stock)).join('');
            }

            // Update footer
            document.getElementById('last-update').textContent =
                'Last update: ' + new Date().toLocaleTimeString();
            document.getElementById('strategy-info').textContent =
                `Trading ${data.stocks ? data.stocks.length : 0} stocks`;
        }

        function createStockCard(stock) {
            const hasPosition = stock.position > 0;
            const signalClass = getSignalClass(stock.signal);
            const progress = Math.min(100, (stock.prices_collected / 30) * 100);
            const buyProb = stock.buy_probability || 0;
            const sellProb = stock.sell_probability || 0;
            const buyHighClass = buyProb >= 70 ? 'prob-high' : '';
            const sellHighClass = sellProb >= 70 ? 'prob-high' : '';

            return `
                <div class="stock-card ${hasPosition ? 'has-position' : ''}">
                    <div class="stock-header">
                        <span class="stock-symbol">${stock.symbol}</span>
                        <span class="stock-price">$${stock.price?.toFixed(2) || '--'}</span>
                    </div>

                    <div class="stock-details">
                        <div class="detail-item">
                            <div class="detail-label">Position</div>
                            <div class="detail-value">${stock.position || 0} shares</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Target Size</div>
                            <div class="detail-value">${stock.position_size} shares</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Data Source</div>
                            <div class="detail-value">${stock.data_source || 'N/A'}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Data Points</div>
                            <div class="detail-value">${stock.prices_collected}/30</div>
                        </div>
                    </div>

                    <div class="signal-display ${signalClass}">
                        ${stock.signal || 'WAIT'}
                    </div>

                    <div class="probability-section">
                        <div class="probability-header">
                            <span>Signal Probability</span>
                            <span>Based on MA convergence</span>
                        </div>
                        <div class="probability-bars">
                            <div class="prob-bar-container">
                                <div class="prob-bar-label">
                                    <span>BUY</span>
                                    <span class="prob-value prob-value-buy ${buyHighClass}">${buyProb.toFixed(1)}%</span>
                                </div>
                                <div class="prob-bar">
                                    <div class="prob-fill-buy ${buyHighClass}" style="width: ${buyProb}%"></div>
                                </div>
                            </div>
                            <div class="prob-bar-container">
                                <div class="prob-bar-label">
                                    <span>SELL</span>
                                    <span class="prob-value prob-value-sell ${sellHighClass}">${sellProb.toFixed(1)}%</span>
                                </div>
                                <div class="prob-bar">
                                    <div class="prob-fill-sell ${sellHighClass}" style="width: ${sellProb}%"></div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="ma-display">
                        <div class="ma-item">
                            <div class="ma-label">Short MA (10)</div>
                            <div class="ma-value ma-short">$${stock.short_ma?.toFixed(2) || '--'}</div>
                        </div>
                        <div class="ma-item">
                            <div class="ma-label">Long MA (30)</div>
                            <div class="ma-value ma-long">$${stock.long_ma?.toFixed(2) || '--'}</div>
                        </div>
                    </div>

                    ${createEventsSection(stock.upcoming_events)}
                    ${createNewsSection(stock.news)}

                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${progress}%"></div>
                    </div>
                </div>
            `;
        }

        function createEventsSection(events) {
            if (!events || Object.keys(events).length === 0) {
                return '';
            }

            let items = '';
            if (events.earnings_date) {
                items += `<div class="event-item">
                    <span class="event-label">Earnings</span>
                    <span class="event-value">${events.earnings_date}</span>
                </div>`;
            }
            if (events.ex_dividend_date) {
                const divRate = events.dividend_rate ? ` ($${events.dividend_rate.toFixed(2)})` : '';
                items += `<div class="event-item">
                    <span class="event-label">Ex-Dividend${divRate}</span>
                    <span class="event-value">${events.ex_dividend_date}</span>
                </div>`;
            }

            if (!items) return '';

            return `
                <div class="events-section">
                    <div class="events-header">Upcoming Events</div>
                    ${items}
                </div>
            `;
        }

        function createNewsSection(news) {
            if (!news || news.length === 0) {
                return '';
            }

            const items = news.map(article => {
                const sentimentClass = 'sentiment-' + (article.sentiment || 'neutral');
                const sentimentIcon = article.sentiment === 'positive' ? '↑' :
                                     article.sentiment === 'negative' ? '↓' : '•';
                return `
                    <div class="news-item">
                        <div class="news-title">${article.title}</div>
                        <div class="news-meta">
                            <span>${article.source} · ${article.time_ago}</span>
                            <span class="${sentimentClass}">${sentimentIcon} ${article.sentiment}</span>
                        </div>
                    </div>
                `;
            }).join('');

            return `
                <div class="news-section">
                    <div class="news-header">Latest News</div>
                    ${items}
                </div>
            `;
        }

        function getSignalClass(signal) {
            switch(signal) {
                case 'BUY': return 'signal-buy';
                case 'SELL': return 'signal-sell';
                case 'HOLD': return 'signal-hold';
                default: return 'signal-wait';
            }
        }

        // Start connection
        connect();
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    return DASHBOARD_HTML


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Get current state
            state = bot_state.get_state()

            # Send state to client
            await websocket.send_json(state)

            # Wait before next update
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@app.get("/api/stocks")
async def get_stocks():
    """API endpoint to get all stock states"""
    return bot_state.get_state()


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": bot_state.last_update}


def run_multi_dashboard(host: str = '0.0.0.0', port: int = 8080):
    """Run the dashboard server"""
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == '__main__':
    run_multi_dashboard()
