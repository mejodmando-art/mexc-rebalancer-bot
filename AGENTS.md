# AGENTS.md — MEXC Rebalancer Bot

## Project Overview

A Python bot that auto-rebalances a spot portfolio on MEXC exchange.
Supports three rebalance modes (proportional, timed, unbalanced) and a
Telegram interface for remote control. Deployed on Railway via `Procfile`.

## Repository Layout

```
main.py            – CLI entry point; dispatches to telegram_bot or smart_portfolio
mexc_client.py     – MEXC Spot REST API client (HMAC-SHA256 auth)
smart_portfolio.py – Rebalance logic, portfolio valuation, config helpers
telegram_bot.py    – Telegram bot interface (python-telegram-bot ≥ 20)
config.json        – Runtime config (portfolio assets, rebalance settings)
requirements.txt   – Python dependencies
Procfile           – Railway process definition
```

## Environment Variables

| Variable            | Required | Purpose                                      |
|---------------------|----------|----------------------------------------------|
| `MEXC_API_KEY`      | Yes      | MEXC API key (Spot trading permissions)      |
| `MEXC_SECRET_KEY`   | Yes      | MEXC API secret                              |
| `TELEGRAM_BOT_TOKEN`| Yes*     | BotFather token; triggers Telegram mode      |
| `TELEGRAM_CHAT_ID`  | No       | Whitelist a single Telegram user ID          |

*Required for Telegram mode (the default deployment mode via `Procfile`).

## Running the Bot

```bash
# Install dependencies
pip install -r requirements.txt

# Telegram mode (default, used by Railway)
python main.py --telegram

# Direct loop mode (reads config.json)
python main.py

# One-off manual rebalance
python main.py --rebalance-now

# Print portfolio snapshot without trading
python main.py --status

# Interactive first-time setup
python main.py --setup
```

## Key Modules

### `mexc_client.py` — `MEXCClient`
- Auth: HMAC-SHA256 over URL-encoded params; key sent as `X-MEXC-APIKEY` header.
- Signed requests append `timestamp` + `signature` to query string.
- Core methods: `get_account`, `get_price`, `get_symbol_info`, `place_market_buy`, `place_market_sell`.

### `smart_portfolio.py`
- `load_config` / `save_config`: read/write `config.json`.
- `validate_allocations`: asserts 2–10 assets summing to 100%.
- `get_portfolio_value`: fetches live balances and prices; computes actual %.
- `execute_rebalance`: sells overweight assets first, then buys underweight ones.
- `needs_rebalance_proportional`: triggers if any asset deviates ≥ `min_deviation_to_execute_pct`.
- `run`: main loop; handles `proportional`, `timed`, and `unbalanced` modes.

### `telegram_bot.py`
- Reads credentials from env vars (no key collection via chat).
- Commands: `/start`, `/status`, `/rebalance`, `/stop`, `/help`.
- Inline keyboard for common actions.
- Runs the rebalancer loop in a background thread; stop via `/stop` or `⏹ Stop`.

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

## Coding Conventions

- Python 3.10+; type hints on all public functions.
- `logging` via module-level `log = logging.getLogger(__name__)`.
- Exceptions from exchange calls are caught per-order and logged; the loop continues.
- `config.json` is the single source of truth for runtime settings; never hardcode values.
- All MEXC symbol pairs are `{BASE}USDT` (e.g. `BTCUSDT`).

## Testing

No automated test suite exists yet. Manual verification steps:
1. `python main.py --status` — confirms API connectivity and balance reads.
2. `python main.py --rebalance-now` — triggers a live rebalance (use small amounts).
3. Telegram `/status` — confirms bot responds and portfolio data is correct.

## Deployment (Railway)

- `Procfile` runs `python main.py --telegram`.
- Set `MEXC_API_KEY`, `MEXC_SECRET_KEY`, `TELEGRAM_BOT_TOKEN` in Railway Variables.
- `TELEGRAM_CHAT_ID` is recommended to restrict access to your user ID.
