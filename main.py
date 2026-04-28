"""
Entry point — starts the Telegram bot with the portfolio rebalancer engine.

    python main.py
"""
import logging
import os
import sys

# Load .env if present (local dev)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("main")

from database import (
    init_db, get_running_portfolios, get_portfolio,
    set_bot_running, list_portfolios, get_rebalance_history,
)
from engine import start_portfolio_loop, stop_portfolio_loop, is_portfolio_running
from smart_portfolio import execute_rebalance, get_portfolio_value, get_pnl, load_config
from mexc_client import MEXCClient


def _rebalance_fn(portfolio_id: int) -> list:
    cfg = get_portfolio(portfolio_id)
    if cfg is None:
        return []
    client = MEXCClient()
    return execute_rebalance(client, cfg, portfolio_id=portfolio_id)


def _get_status_fn() -> dict:
    cfg = load_config()
    client = MEXCClient()
    portfolio = get_portfolio_value(client, cfg["portfolio"]["assets"], budget_usdt=None)
    targets = {a["symbol"]: a["allocation_pct"] for a in cfg["portfolio"]["assets"]}
    pnl = get_pnl(cfg, current_usdt=portfolio["total_usdt"])
    assets_out = []
    for r in portfolio["assets"]:
        diff = round(r["actual_pct"] - targets[r["symbol"]], 2)
        assets_out.append({
            "symbol": r["symbol"],
            "balance": r["balance"],
            "price": r["price"],
            "value_usdt": r["value_usdt"],
            "actual_pct": round(r["actual_pct"], 2),
            "target_pct": targets[r["symbol"]],
            "deviation": diff,
        })
    return {
        "bot_name": cfg["bot"]["name"],
        "total_usdt": portfolio["total_usdt"],
        "mode": cfg["rebalance"]["mode"],
        "assets": assets_out,
        "pnl": pnl,
        "paper_trading": cfg.get("paper_trading", False),
    }


def main():
    log.info("Initialising database...")
    init_db()

    # Resume any portfolio loops that were running before last shutdown
    running_ids = get_running_portfolios()
    for pid in running_ids:
        cfg = get_portfolio(pid)
        if cfg is None:
            set_bot_running(pid, False)
            continue
        log.info("Resuming portfolio loop %d", pid)
        start_portfolio_loop(pid)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        log.error("TELEGRAM_BOT_TOKEN is not set — cannot start bot")
        sys.exit(1)

    log.info("Starting Telegram bot...")
    from bot.telegram_bot import run_bot
    run_bot(
        get_status_fn=_get_status_fn,
        start_fn=start_portfolio_loop,
        stop_fn=stop_portfolio_loop,
        rebalance_fn=_rebalance_fn,
        list_portfolios_fn=list_portfolios,
        is_running_fn=is_portfolio_running,
        get_history_fn=get_rebalance_history,
        get_portfolio_fn=get_portfolio,
    )


if __name__ == "__main__":
    main()
