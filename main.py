"""
Entry point for the Smart Portfolio bot.

Usage
-----
# Run via Telegram bot (recommended):
    python main.py --telegram

# First-time setup (manual mode):
    python main.py --setup

# Run the bot loop directly (uses config.json):
    python main.py

# Trigger a one-off manual rebalance:
    python main.py --rebalance-now

# Show current portfolio snapshot without trading:
    python main.py --status

Environment variables required
-------------------------------
    MEXC_API_KEY         – not needed in --telegram mode (bot collects them)
    MEXC_SECRET_KEY      – not needed in --telegram mode (bot collects them)
    TELEGRAM_BOT_TOKEN   – required for --telegram mode
    TELEGRAM_CHAT_ID     – optional whitelist for --telegram mode
"""

import argparse
import os
import sys

from mexc_client import MEXCClient
from smart_portfolio import (
    execute_rebalance,
    get_portfolio_value,
    interactive_setup,
    load_config,
    run,
    terminate,
    validate_allocations,
)


def check_env() -> None:
    missing = [k for k in ("MEXC_API_KEY", "MEXC_SECRET_KEY") if not os.environ.get(k)]
    if missing:
        print(f"[ERROR] Missing environment variables: {', '.join(missing)}")
        print("Set them before running:")
        for k in missing:
            print(f"  export {k}=your_value")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="MEXC Smart Portfolio Bot")
    parser.add_argument("--telegram", action="store_true", help="Start Telegram bot interface")
    parser.add_argument("--setup", action="store_true", help="Run interactive setup")
    parser.add_argument("--rebalance-now", action="store_true", help="Trigger a manual rebalance immediately")
    parser.add_argument("--status", action="store_true", help="Print current portfolio snapshot")
    parser.add_argument("--terminate", action="store_true", help="Stop bot and optionally sell all assets")
    args = parser.parse_args()

    if args.telegram:
        from telegram_bot import start_telegram_bot
        start_telegram_bot()
        return

    check_env()
    cfg = load_config()

    if args.setup:
        cfg = interactive_setup(cfg)
        print("\nSetup complete. Run 'python main.py' to start the bot.")
        return

    validate_allocations(cfg["portfolio"]["assets"])
    client = MEXCClient()

    if args.status:
        portfolio = get_portfolio_value(client, cfg["portfolio"]["assets"])
        print(f"\nPortfolio: {cfg['bot']['name']}")
        print(f"Total value: {portfolio['total_usdt']:.2f} USDT\n")
        print(f"{'Asset':<8} {'Balance':>16} {'Price':>12} {'Value (USDT)':>14} {'Actual %':>10} {'Target %':>10}")
        print("-" * 74)
        targets = {a["symbol"]: a["allocation_pct"] for a in cfg["portfolio"]["assets"]}
        for r in portfolio["assets"]:
            print(
                f"{r['symbol']:<8} {r['balance']:>16.8f} {r['price']:>12.4f} "
                f"{r['value_usdt']:>14.2f} {r['actual_pct']:>9.2f}% {targets[r['symbol']]:>9.2f}%"
            )
        return

    if args.rebalance_now:
        print("Manual rebalance triggered.")
        execute_rebalance(client, cfg)
        return

    if args.terminate:
        terminate(client, cfg)
        return

    run(cfg)


if __name__ == "__main__":
    main()
