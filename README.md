# MEXC Smart Portfolio Rebalancer v2

Auto-rebalancing bot for MEXC spot portfolios with a Telegram interface and a web dashboard.

## Features

- **3 rebalance modes**: Proportional (1/3/5% thresholds), Timed (daily/weekly/monthly), Unbalanced (manual)
- **Telegram bot**: full setup wizard, status, history, P&L stats, CSV export, notifications on every rebalance
- **Web dashboard**: dark-mode, pie chart, performance line chart, assets table with deviation indicators, settings panel
- **Paper trading**: simulate rebalances without placing real orders
- **SQLite history**: stores every rebalance operation and portfolio snapshot for P&L tracking

---

## Quick Start

### 1. Clone & install Python deps

```bash
git clone https://github.com/mejodmando-art/mexc-rebalancer-bot.git
cd mexc-rebalancer-bot
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
export MEXC_API_KEY=your_api_key
export MEXC_SECRET_KEY=your_secret_key
export TELEGRAM_BOT_TOKEN=your_bot_token
export TELEGRAM_CHAT_ID=your_telegram_user_id   # optional whitelist
```

Or copy `.env.example` to `.env` and fill in the values.

### 3. Run the Telegram bot

```bash
python main.py --telegram
```

### 4. Run the API + dashboard (optional)

```bash
# Terminal 1 – FastAPI backend
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 – Next.js dashboard
cd web && npm install && npm run dev
```

Dashboard: http://localhost:3000

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Main menu with inline buttons |
| `/status` | Live portfolio snapshot (actual vs target %) |
| `/rebalance` | Trigger manual rebalance immediately |
| `/settings` | Full setup wizard (assets, mode, thresholds) |
| `/history` | Last 10 rebalance operations |
| `/stats` | P&L and total rebalance count |
| `/export` | Download CSV report |
| `/stop` | Stop the rebalancer loop |
| `/help` | Command list |

---

## Rebalance Modes

### Proportional
Checks every 5 minutes. Executes only when any asset deviates ≥ `min_deviation_to_execute_pct` (default 3%).
Supported thresholds: **1% / 3% / 5%**.

### Timed
Rebalances on a fixed schedule regardless of prices: **daily / weekly / monthly**.

### Unbalanced
No automatic rebalancing. Use `/rebalance` or the dashboard button to trigger manually.

---

## Paper Trading

Set `"paper_trading": true` in `config.json` or toggle it in the Telegram settings wizard / web dashboard.
Orders are logged but never sent to the exchange.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MEXC_API_KEY` | Yes | MEXC API key (Spot trading permissions) |
| `MEXC_SECRET_KEY` | Yes | MEXC API secret |
| `TELEGRAM_BOT_TOKEN` | Yes* | From @BotFather |
| `TELEGRAM_CHAT_ID` | No | Whitelist a single Telegram user ID |
| `API_URL` | No | Backend URL for Next.js rewrites (default: http://localhost:8000) |

*Required for Telegram mode (default deployment).

---

## Deployment on Railway

1. Create a new Railway project and connect this repo.
2. Add the environment variables above in Railway → Variables.
3. Railway will use the `Procfile` to start the Telegram bot automatically.
4. For the web dashboard, add a second service pointing to `web/` with build command `npm run build` and start command `npm start`.

---

## Project Structure

```
main.py              – CLI entry point
mexc_client.py       – MEXC REST API client (HMAC-SHA256)
smart_portfolio.py   – Rebalance logic, portfolio valuation, P&L
telegram_bot.py      – Telegram bot with full wizard and notifications
database.py          – SQLite layer (history + snapshots)
api/
  main.py            – FastAPI REST API for the dashboard
web/
  src/app/page.tsx   – Next.js dashboard (dark mode, charts, settings)
config.json          – Runtime configuration
requirements.txt     – Python dependencies
Procfile             – Railway process definition
```
