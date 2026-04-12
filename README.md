# MEXC Smart Portfolio Bot

Auto-rebalancing spot portfolio on MEXC — Bitget-style interface, Python backend, React dashboard.

---

## Features

- **3 rebalance modes**: Proportional (deviation-based), Timed (daily/weekly/monthly at a set hour), Unbalanced (manual only)
- **2–10 assets** with custom % allocations; equal-distribution button
- **Recommended portfolios**: Top 3 Coins, DeFi, Layer 1 Mix, Balanced 5
- **Paper Trading mode**: full simulation without real orders
- **Web dashboard** (Next.js): Pie chart, P&L, asset table, history log, bot controls
- **Telegram bot**: `/status`, `/rebalance`, `/settings`, `/history`, `/stats`, `/export`, `/stop`
- **Auto-notifications**: Telegram message on every rebalance with details and P&L
- **Sell at termination** and **Asset Transfer** options
- SQLite history + CSV export

---

## Repository Layout

```
main.py              – CLI entry point
mexc_client.py       – MEXC Spot REST API client (HMAC-SHA256)
smart_portfolio.py   – Rebalance engine (all 3 modes)
telegram_bot.py      – Telegram bot (python-telegram-bot >= 20)
database.py          – SQLite layer (history + snapshots)
api/main.py          – FastAPI REST API for the web dashboard
web/                 – Next.js 14 dashboard (React + Tailwind + Recharts)
config.json          – Runtime config (single source of truth)
Procfile             – Railway process definitions
requirements.txt     – Python dependencies
```

---

## Environment Variables

| Variable              | Required | Purpose                                    |
|-----------------------|----------|--------------------------------------------|
| MEXC_API_KEY          | Yes      | MEXC API key (Spot trading permissions)    |
| MEXC_SECRET_KEY       | Yes      | MEXC API secret                            |
| TELEGRAM_BOT_TOKEN    | Yes*     | BotFather token; triggers Telegram mode    |
| TELEGRAM_CHAT_ID      | No       | Restrict bot to a single Telegram user ID  |

*Required for Telegram mode (default Railway deployment).

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
export MEXC_API_KEY=your_api_key
export MEXC_SECRET_KEY=your_secret_key
export TELEGRAM_BOT_TOKEN=your_bot_token
export TELEGRAM_CHAT_ID=your_telegram_user_id
```

### 3. Run

```bash
# Telegram bot (default)
python main.py --telegram

# FastAPI web dashboard backend
uvicorn api.main:app --host 0.0.0.0 --port 8000

# Web frontend (development)
cd web && npm install && npm run dev

# One-off manual rebalance
python main.py --rebalance-now

# Portfolio snapshot (no trading)
python main.py --status
```

---

## Web Dashboard

Set the API URL in `web/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Pages

| Tab | Description |
|-----|-------------|
| Dashboard | Pie chart, P&L cards, asset table, history log, manual rebalance |
| Create Bot | Recommended or manual setup, paper trading toggle |
| Settings | Edit assets, allocations, rebalance mode, amount at any time |

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| /start | Main menu with inline keyboard |
| /status | Live portfolio: actual% vs target%, deviation |
| /rebalance | Trigger immediate rebalance |
| /settings | Guided wizard to reconfigure portfolio |
| /history [N] | Last N rebalance operations (default 10, max 50) |
| /stats | P&L, initial vs current value, total operations |
| /export | Download CSV report |
| /stop | Stop the rebalancer loop |
| /help | Command reference |

---

## Rebalance Modes

### Proportional
- Checks every 5 minutes
- Triggers only when any asset deviates >= min_deviation_to_execute_pct (default 3%)
- Configurable threshold: 1%, 3%, or 5%

### Timed
- Runs on a fixed schedule: daily / weekly / monthly
- Configurable UTC hour (e.g. 10:00 UTC)

### Unbalanced
- No automatic rebalancing
- Use the dashboard button or /rebalance to trigger manually

---

## config.json Schema

```json
{
  "bot": { "name": "My MEXC Portfolio" },
  "portfolio": {
    "assets": [
      { "symbol": "BTC", "allocation_pct": 50.0 },
      { "symbol": "ETH", "allocation_pct": 30.0 },
      { "symbol": "SOL", "allocation_pct": 20.0 }
    ],
    "total_usdt": 1000,
    "initial_value_usdt": 1000
  },
  "rebalance": {
    "mode": "proportional",
    "proportional": {
      "threshold_pct": 5,
      "check_interval_minutes": 5,
      "min_deviation_to_execute_pct": 3
    },
    "timed": { "frequency": "daily", "hour": 10 },
    "unbalanced": {}
  },
  "termination": { "sell_at_termination": false },
  "asset_transfer": { "enable_asset_transfer": false },
  "paper_trading": false,
  "last_rebalance": null
}
```

---

## Deployment (Railway)

1. Connect your GitHub repo to Railway
2. Set all environment variables in Railway Variables
3. Procfile runs: worker (Telegram bot) + web (FastAPI API)
4. Deploy Next.js frontend on Vercel with NEXT_PUBLIC_API_URL pointing to Railway API URL

---

## Notes

- All trading pairs are {BASE}USDT (e.g. BTCUSDT)
- Trading fees are standard MEXC Spot fees — no additional bot fees
- Bot name cannot be changed after creation
- All settings can be edited at any time via Settings page or /settings
