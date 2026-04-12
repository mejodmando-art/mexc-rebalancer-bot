"""
Entry point for the Smart Portfolio bot.

Modes
-----
Default (no args): starts the Telegram bot. API keys are entered via /setup.

CLI flags (for direct use without Telegram):
    --run            Run the portfolio bot directly (requires MEXC_API_KEY + MEXC_SECRET_KEY)
    --status         Print portfolio snapshot
    --rebalance-now  Trigger a manual rebalance
    --setup          Interactive CLI setup
    --terminate      Stop and optionally sell all assets

Required env vars
-----------------
    TELEGRAM_BOT_TOKEN   – always required
    TELEGRAM_CHAT_ID     – your Telegram user ID (whitelist, recommended)
    MEXC_API_KEY         – can be set via /setup in Telegram instead
    MEXC_SECRET_KEY      – can be set via /setup in Telegram instead
"""

import argparse
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def check_mexc_env() -> bool:
    return bool(os.environ.get("MEXC_API_KEY")) and bool(os.environ.get("MEXC_SECRET_KEY"))


def require_mexc_env() -> None:
    missing = [k for k in ("MEXC_API_KEY", "MEXC_SECRET_KEY") if not os.environ.get(k)]
    if missing:
        print(f"[ERROR] Missing environment variables: {', '.join(missing)}")
        print("Set them before running:")
        for k in missing:
            print(f"  export {k}=your_value")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="MEXC Smart Portfolio Bot")
    parser.add_argument("--run", action="store_true", help="Run portfolio bot directly (no Telegram)")
    parser.add_argument("--setup", action="store_true", help="Interactive CLI setup")
    parser.add_argument("--rebalance-now", action="store_true", help="Trigger manual rebalance")
    parser.add_argument("--status", action="store_true", help="Print portfolio snapshot")
    parser.add_argument("--terminate", action="store_true", help="Stop bot and optionally sell assets")
    args = parser.parse_args()

    # ------------------------------------------------------------------ CLI modes
    if args.setup:
        require_mexc_env()
        from smart_portfolio import interactive_setup, load_config
        cfg = load_config()
        interactive_setup(cfg)
        print("\nSetup complete. Run 'python main.py' to start the Telegram bot.")
        return

    if args.status:
        require_mexc_env()
        from mexc_client import MEXCClient
        from smart_portfolio import get_portfolio_value, load_config
        cfg = load_config()
        client = MEXCClient()
        portfolio = get_portfolio_value(client, cfg["portfolio"]["assets"])
        print(f"\nPortfolio: {cfg['bot']['name']}")
        print(f"Total: {portfolio['total_usdt']:.2f} USDT\n")
        targets = {a["symbol"]: a["allocation_pct"] for a in cfg["portfolio"]["assets"]}
        print(f"{'Asset':<8} {'Balance':>16} {'Price':>12} {'Value':>12} {'Actual%':>9} {'Target%':>9}")
        print("-" * 70)
        for r in portfolio["assets"]:
            print(f"{r['symbol']:<8} {r['balance']:>16.8f} {r['price']:>12.4f} "
                  f"{r['value_usdt']:>12.2f} {r['actual_pct']:>8.2f}% {targets[r['symbol']]:>8.2f}%")
        return

    if args.rebalance_now:
        require_mexc_env()
        from mexc_client import MEXCClient
        from smart_portfolio import execute_rebalance, load_config
        cfg = load_config()
        execute_rebalance(MEXCClient(), cfg)
        return

    if args.terminate:
        require_mexc_env()
        from mexc_client import MEXCClient
        from smart_portfolio import load_config, terminate
        terminate(MEXCClient(), load_config())
        return

    if args.run:
        require_mexc_env()
        from smart_portfolio import load_config, run, validate_allocations
        cfg = load_config()
        validate_allocations(cfg["portfolio"]["assets"])
        run(cfg)
        return

    # ------------------------------------------------------------------ Telegram mode (default)
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        print("[ERROR] TELEGRAM_BOT_TOKEN غير موجود.")
        print("أضفه كـ Secret في Ona أو:")
        print("  export TELEGRAM_BOT_TOKEN=your_token")
        sys.exit(1)

    log.info("Starting Telegram bot...")
    if check_mexc_env():
        log.info("MEXC API keys found in environment.")
    else:
        log.info("MEXC API keys not set — use /setup in Telegram to enter them.")

    from telegram_bot import start_telegram_bot
    start_telegram_bot()


if __name__ == "__main__":
    main()
