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
    set_bot_running, list_portfolios, save_portfolio,
    update_portfolio_config,
)
from engine import start_portfolio_loop, stop_portfolio_loop, is_portfolio_running
from smart_portfolio import execute_rebalance
from mexc_client import MEXCClient


def _rebalance_fn(portfolio_id: int) -> list:
    cfg = get_portfolio(portfolio_id)
    if cfg is None:
        return []
    return execute_rebalance(MEXCClient(), cfg, portfolio_id=portfolio_id)


def _buy_fn(symbol: str, usdt_amount: float) -> dict:
    return MEXCClient().place_market_buy(symbol, usdt_amount)


def _sell_fn(symbol: str, base_amount: float) -> dict:
    return MEXCClient().place_market_sell(symbol, base_amount)


def _get_balances_fn() -> dict:
    return MEXCClient().get_all_balances()


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
        start_fn=start_portfolio_loop,
        stop_fn=stop_portfolio_loop,
        rebalance_fn=_rebalance_fn,
        list_portfolios_fn=list_portfolios,
        is_running_fn=is_portfolio_running,
        get_portfolio_fn=get_portfolio,
        save_portfolio_fn=save_portfolio,
        update_portfolio_fn=update_portfolio_config,
        buy_fn=_buy_fn,
        sell_fn=_sell_fn,
        get_balances_fn=_get_balances_fn,
    )


if __name__ == "__main__":
    main()
