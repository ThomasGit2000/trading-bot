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
    <title>Trading Dashboard</title>
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
        tr:hover { background: #161b22; }
        tr.has-position { border-left: 3px solid #238636; }

        .symbol { font-weight: 700; color: #58a6ff; font-size: 14px; }
        .price { font-weight: 600; }
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
    </style>
</head>
<body>
    <div class="header">
        <h1>Trading Bot - NO STOPS MA(10/30)</h1>
        <div>
            <span id="connection-status" class="status-badge status-disconnected">...</span>
            <span id="trading-mode" class="status-badge status-dry">DRY</span>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Symbol</th>
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
            <tr><td colspan="9" style="text-align:center;color:#8b949e;">Loading...</td></tr>
        </tbody>
    </table>

    <div class="footer">
        <span id="last-update">--</span>
        <span id="stock-count">0 stocks</span>
    </div>

    <script>
        let ws;
        function connect() {
            ws = new WebSocket(`ws://${window.location.host}/ws`);
            ws.onopen = () => {
                document.getElementById('connection-status').textContent = 'LIVE';
                document.getElementById('connection-status').className = 'status-badge status-live';
            };
            ws.onmessage = (e) => updateDashboard(JSON.parse(e.data));
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

            return `
                <tr class="${hasPos ? 'has-position' : ''}">
                    <td><span class="symbol">${s.symbol}</span></td>
                    <td class="price">$${s.price?.toFixed(2) || '--'}</td>
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
            state = bot_state.get_state()
            await websocket.send_json(state)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@app.get("/api/stocks")
async def get_stocks():
    return bot_state.get_state()


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": bot_state.last_update}


def run_multi_dashboard(host: str = '0.0.0.0', port: int = 8080):
    uvicorn.run(
        app, host=host, port=port, log_level="warning",
        timeout_keep_alive=5, ws_ping_interval=20, ws_ping_timeout=20
    )


if __name__ == '__main__':
    run_multi_dashboard()
