# AGENTS.md — MEXC Rebalancer Bot

## Project Overview

A Python bot that auto-rebalances a spot portfolio on MEXC exchange.
Supports three rebalance modes (proportional, timed, unbalanced), a Grid
Trading bot, and a bilingual (Arabic/English) web dashboard. Deployed on
Railway via Nixpacks (`nixpacks.toml`).

## Repository Layout

```
main.py              – Entry point; starts uvicorn serving api/main.py
api/main.py          – FastAPI application (REST API + static file serving)
mexc_client.py       – MEXC Spot REST API client (HMAC-SHA256 auth)
smart_portfolio.py   – Rebalance logic, portfolio valuation, config helpers
telegram_bot.py      – Telegram bot (started by api/main.py on startup)
grid_bot.py          – Grid trading engine (dynamic AI grid strategy)
database.py          – SQLite / PostgreSQL persistence layer
config.json          – Legacy runtime config (superseded by DB for multi-portfolio)
requirements.txt     – Python dependencies
nixpacks.toml        – Railway Nixpacks build config (Python + Node.js)
railway.json         – Railway service config (start command, restart policy)
web/                 – Next.js 14 frontend (TypeScript + Tailwind CSS)
static/              – Next.js build output; served by FastAPI as static files
```

## Web Stack

```
web/
  src/app/           – App Router pages (layout.tsx, page.tsx, globals.css)
  src/components/    – React components (Dashboard, Sidebar, Navbar, StatCard, …)
  src/lib/           – API client (api.ts) + i18n translations (i18n.ts)
```

Build: `cd web && npm install && npm run build && cp -r out/* ../static/`

## Environment Variables

| Variable              | Required | Purpose                                         |
|-----------------------|----------|-------------------------------------------------|
| `MEXC_API_KEY`        | Yes      | MEXC API key (Spot trading permissions)         |
| `MEXC_SECRET_KEY`     | Yes      | MEXC API secret                                 |
| `TELEGRAM_BOT_TOKEN`  | No       | BotFather token; enables Telegram notifications |
| `TELEGRAM_CHAT_ID`    | No       | Restrict Telegram access to one user ID         |
| `DISCORD_WEBHOOK_URL` | No       | Discord webhook for trade notifications         |
| `PAPER_TRADING`       | No       | Set `true` to skip real orders (dry-run mode)   |
| `DATABASE_URL`        | No       | PostgreSQL URL; falls back to SQLite if unset   |
| `PORT`                | No       | HTTP port for uvicorn (default: 8000)           |

## Running the Bot

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Build the web UI (required for production; skip for API-only dev)
cd web && npm install && npm run build && cp -r out/* ../static/ && cd ..

# 3. Start the server (API + web UI + Telegram bot)
python main.py
# or directly:
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Open the dashboard at `http://localhost:8000`.

## Key Modules

### `api/main.py` — FastAPI Application
- Mounts the Next.js static build at `/`.
- REST endpoints: `GET /api/status`, `POST /api/rebalance`, `GET /api/history`,
  `GET /api/snapshots`, `GET /api/config`, `POST /api/config`,
  `GET /api/portfolios`, `POST /api/bot/start`, `POST /api/bot/stop`,
  `GET /api/export/csv`, `GET /api/export/excel`, and notification config endpoints.
- On startup: initialises the DB, starts the Telegram bot (if token is set),
  and resumes any previously running portfolio loops.
- Per-portfolio rebalancer loops run in background threads; each has its own
  stop event so they can be started/stopped independently.

### `mexc_client.py` — `MEXCClient`
- Auth: HMAC-SHA256 over URL-encoded params; key sent as `X-MEXC-APIKEY` header.
- Signed requests append `timestamp` + `signature` to query string.
- Core methods: `get_account`, `get_price`, `get_symbol_info`, `place_market_buy`,
  `place_market_sell`.

### `smart_portfolio.py`
- `load_config` / `save_config`: read/write `config.json`.
- `validate_allocations`: asserts 2–10 assets summing to 100%.
- `get_portfolio_value`: fetches live balances and prices; computes actual %.
- `execute_rebalance`: sells overweight assets first, then buys underweight ones.
- `execute_rebalance_equal`: equal-weight rebalance variant.
- `needs_rebalance_proportional`: triggers if any asset deviates ≥ `min_deviation_to_execute_pct`.
- `get_pnl`: computes realised + unrealised P&L from DB snapshots.

### `grid_bot.py` — Grid Trading Engine
- Implements a dynamic AI grid strategy: divides a price range into N equal
  levels; places limit BUY orders below and SELL orders above current price.
- When a BUY fills → places a SELL one grid step higher; vice versa.
- Dynamic re-ranging: when price exits the range, cancels all orders and
  rebuilds the grid around the new price.
- Infinity mode: no upper price cap; SELL orders placed one step above each
  filled BUY with `price_low` as the only bound.
- Key functions: `start_grid_bot`, `stop_grid_bot`, `resume_grid_bot`,
  `get_grid_bot_status`, `calculate_grid_range`, `calculate_grid_count`.

### `database.py` — Persistence Layer
- Uses PostgreSQL when `DATABASE_URL` is set; falls back to SQLite (`portfolio.db`).
- PostgreSQL uses a `ThreadedConnectionPool` (min=1, max=5) with automatic
  retry on transient errors.
- Key tables: `portfolios`, `rebalance_history`, `portfolio_snapshots`,
  `grid_bots`, `grid_orders`.
- Key functions: `init_db`, `save_portfolio`, `list_portfolios`,
  `get_portfolio`, `set_active_portfolio`, `record_snapshot`, `get_snapshots`,
  `get_rebalance_history`, `create_grid_bot`, `update_grid_bot_status`.

### `telegram_bot.py`
- Reads credentials from env vars (no key collection via chat).
- Commands: `/start`, `/status`, `/rebalance`, `/history`, `/stats`,
  `/export`, `/settings`, `/stop`, `/help`.
- Inline keyboard for common actions.
- Started as a background thread from `api/main.py` on server startup.

## `config.json` Schema

```json
{
  "bot": { "name": "string" },
  "portfolio": {
    "assets": [{ "symbol": "BTC", "allocation_pct": 50.0 }],
    "total_usdt": 1000
  },
  "rebalance": {
    "mode": "proportional | timed | unbalanced",
    "proportional": {
      "threshold_pct": 5,
      "check_interval_minutes": 5,
      "min_deviation_to_execute_pct": 3
    },
    "timed": { "frequency": "daily | weekly | monthly" },
    "unbalanced": {}
  },
  "termination": { "sell_at_termination": false },
  "asset_transfer": { "enable_asset_transfer": false }
}
```

> `config.json` is used by the legacy single-portfolio path. Multi-portfolio
> state is stored in the database; `config.json` is no longer the primary
> source of truth for new deployments.

## Coding Conventions

- Python 3.10+; type hints on all public functions.
- `logging` via module-level `log = logging.getLogger(__name__)`.
- Exceptions from exchange calls are caught per-order and logged; the loop continues.
- All MEXC symbol pairs are `{BASE}USDT` (e.g. `BTCUSDT`).
- Frontend: TypeScript strict mode; components in `web/src/components/`;
  translations via `web/src/lib/i18n.ts`; API calls via `web/src/lib/api.ts`.

## Testing

No automated test suite exists. Manual verification steps:
1. `GET /api/status` — confirms API connectivity and live balance reads.
2. `POST /api/rebalance` — triggers a live rebalance (use small amounts).
3. Telegram `/status` — confirms bot responds and portfolio data is correct.
4. Open `http://localhost:8000` — confirms web dashboard loads and charts render.

## Deployment (Railway)

- `nixpacks.toml` installs Python 3.11 + Node.js 20, builds the Next.js UI,
  copies the output to `static/`, then starts `python main.py`.
- `railway.json` sets `startCommand: "python main.py"` with `ON_FAILURE` restart.
- Required Railway Variables: `MEXC_API_KEY`, `MEXC_SECRET_KEY`.
- Recommended: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DATABASE_URL` (PostgreSQL).
