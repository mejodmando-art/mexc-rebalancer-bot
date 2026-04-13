"""
Smart Portfolio – MEXC Spot Auto-Rebalancing Bot.

Rebalance modes
---------------
proportional : rebalance when any asset drifts beyond threshold_pct.
               Checks every check_interval_minutes (default 5 min).
               Only executes if deviation >= min_deviation_to_execute_pct (default 3%).
               Supported thresholds: 1%, 3%, 5%.
timed        : rebalance on a fixed schedule (daily / weekly / monthly).
unbalanced   : no automatic rebalancing; user triggers manually via CLI.

Setup modes
-----------
recommended  : load a pre-built allocation from config.json.
manual       : user defines assets and percentages interactively.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

from mexc_client import MEXCClient
from database import init_db, record_rebalance, record_snapshot, get_rebalance_history, get_snapshots

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

# Initialise DB on import
init_db()

VALID_THRESHOLDS = {1, 3, 5}
VALID_TIMED_FREQUENCIES = {"daily", "weekly", "monthly"}
MIN_ASSETS = 2
MAX_ASSETS = 10


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(path: str = CONFIG_PATH) -> dict:
    """Load config from the active portfolio in DB if one exists, else fall back to config.json."""
    try:
        from database import list_portfolios, get_portfolio as db_get_portfolio
        portfolios = list_portfolios()
        active = next((p for p in portfolios if p.get("active")), None)
        if active:
            cfg = db_get_portfolio(active["id"])
            if cfg:
                return cfg
    except Exception as e:
        log.warning("Could not load active portfolio from DB (%s) — falling back to config.json", e)
    with open(path, "r") as f:
        return json.load(f)


def save_config(cfg: dict, path: str = CONFIG_PATH) -> None:
    """Persist config to the active portfolio in DB (if one exists) and to config.json."""
    try:
        from database import list_portfolios, update_portfolio_config
        portfolios = list_portfolios()
        active = next((p for p in portfolios if p.get("active")), None)
        if active:
            update_portfolio_config(active["id"], cfg)
            log.info("Config saved to DB (portfolio id=%s)", active["id"])
    except Exception as e:
        log.warning("Could not save config to DB (%s) — saving to config.json only", e)
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
    log.info("Config saved to %s", path)


def validate_allocations(assets: list) -> None:
    if not (MIN_ASSETS <= len(assets) <= MAX_ASSETS):
        raise ValueError(f"Number of assets must be between {MIN_ASSETS} and {MAX_ASSETS}.")
    symbols = [a["symbol"].strip().upper() for a in assets]
    # Check for empty symbols
    if any(not s for s in symbols):
        raise ValueError("All assets must have a symbol.")
    # Check for duplicates
    if len(symbols) != len(set(symbols)):
        dupes = [s for s in symbols if symbols.count(s) > 1]
        raise ValueError(f"Duplicate symbols: {', '.join(set(dupes))}")
    total = sum(a["allocation_pct"] for a in assets)
    if abs(total - 100.0) > 0.01:
        raise ValueError(f"Allocations must sum to 100% (got {total:.2f}%).")


# ---------------------------------------------------------------------------
# Interactive setup (manual mode)
# ---------------------------------------------------------------------------

def interactive_setup(cfg: dict) -> dict:
    """Walk the user through manual portfolio configuration."""
    print("\n=== Smart Portfolio Setup (Manual) ===")

    # Bot name (set once, never changed)
    name = input("Bot name (press Enter to keep current): ").strip()
    if name:
        cfg["bot"]["name"] = name

    # Assets
    print(f"\nEnter between {MIN_ASSETS} and {MAX_ASSETS} assets.")
    assets = []
    while True:
        sym = input("  Asset symbol (e.g. BTC) or 'done': ").strip().upper()
        if sym == "DONE":
            if len(assets) < MIN_ASSETS:
                print(f"  Need at least {MIN_ASSETS} assets.")
                continue
            break
        if len(assets) >= MAX_ASSETS:
            print(f"  Maximum {MAX_ASSETS} assets reached.")
            break
        assets.append({"symbol": sym, "allocation_pct": 0.0})

    # Allocation
    equal = input("Allocate equally? (y/n): ").strip().lower()
    if equal == "y":
        pct = round(100.0 / len(assets), 4)
        for a in assets:
            a["allocation_pct"] = pct
        # Fix rounding so total == 100
        diff = 100.0 - sum(a["allocation_pct"] for a in assets)
        assets[-1]["allocation_pct"] = round(assets[-1]["allocation_pct"] + diff, 4)
    else:
        remaining = 100.0
        for i, a in enumerate(assets):
            if i == len(assets) - 1:
                a["allocation_pct"] = round(remaining, 4)
                print(f"  {a['symbol']}: {a['allocation_pct']}% (auto-assigned)")
            else:
                while True:
                    try:
                        pct = float(input(f"  {a['symbol']} allocation %: "))
                        if pct <= 0 or pct >= remaining:
                            print(f"  Must be > 0 and < {remaining:.2f}")
                            continue
                        a["allocation_pct"] = round(pct, 4)
                        remaining = round(remaining - pct, 4)
                        break
                    except ValueError:
                        print("  Enter a number.")

    cfg["portfolio"]["assets"] = assets

    # USDT amount
    while True:
        try:
            amount = float(input("\nTotal USDT to invest: "))
            if amount <= 0:
                print("  Must be positive.")
                continue
            cfg["portfolio"]["total_usdt"] = amount
            break
        except ValueError:
            print("  Enter a number.")

    # Rebalance mode
    print("\nRebalance mode:")
    print("  1. proportional")
    print("  2. timed")
    print("  3. unbalanced")
    while True:
        choice = input("Choose (1/2/3): ").strip()
        if choice == "1":
            cfg["rebalance"]["mode"] = "proportional"
            print("  Threshold options: 1%, 3%, 5%")
            while True:
                try:
                    t = int(input("  Threshold %: "))
                    if t not in VALID_THRESHOLDS:
                        print(f"  Must be one of {VALID_THRESHOLDS}")
                        continue
                    cfg["rebalance"]["proportional"]["threshold_pct"] = t
                    break
                except ValueError:
                    print("  Enter a number.")
            break
        elif choice == "2":
            cfg["rebalance"]["mode"] = "timed"
            print("  Frequency options: daily / weekly / monthly")
            while True:
                freq = input("  Frequency: ").strip().lower()
                if freq not in VALID_TIMED_FREQUENCIES:
                    print(f"  Must be one of {VALID_TIMED_FREQUENCIES}")
                    continue
                cfg["rebalance"]["timed"]["frequency"] = freq
                break
            break
        elif choice == "3":
            cfg["rebalance"]["mode"] = "unbalanced"
            break
        else:
            print("  Enter 1, 2, or 3.")

    # Termination
    sell = input("\nSell all assets to USDT at termination? (y/n): ").strip().lower()
    cfg["termination"]["sell_at_termination"] = sell == "y"

    # Asset transfer
    transfer = input("Enable asset transfer (use wallet balance first)? (y/n): ").strip().lower()
    cfg["asset_transfer"]["enable_asset_transfer"] = transfer == "y"

    validate_allocations(cfg["portfolio"]["assets"])
    save_config(cfg)
    return cfg


# ---------------------------------------------------------------------------
# Portfolio valuation
# ---------------------------------------------------------------------------

def get_portfolio_value(
    client: MEXCClient,
    assets: list,
    budget_usdt: float | None = None,
) -> dict:
    """
    Returns the current value of the configured portfolio assets only.

    budget_usdt: when provided, this value is used as the authoritative
    portfolio total instead of summing live asset values.  Percentages
    (actual_pct) are calculated against budget_usdt, so the rebalancer
    always works within the user-defined allocation and never touches
    funds outside it.  Pass None for informational/status calls where
    you want the true live value.

    Returns:
        {
          "total_usdt": float,
          "assets": [
            {"symbol": str, "balance": float, "price": float,
             "value_usdt": float, "actual_pct": float},
            ...
          ]
        }
    """
    result = []
    invalid_symbols = []

    for a in assets:
        sym = a["symbol"]
        try:
            if sym == "USDT":
                balance = client.get_asset_balance("USDT")
                price = 1.0
            else:
                balance = client.get_asset_balance(sym)
                price = client.get_price(f"{sym}USDT")
        except Exception as e:
            log.warning("Cannot fetch price for %s: %s – skipping", sym, e)
            invalid_symbols.append(sym)
            result.append({
                "symbol": sym,
                "balance": 0.0,
                "price": 0.0,
                "value_usdt": 0.0,
                "actual_pct": 0.0,
                "error": str(e),
            })
            continue
        value = balance * price
        result.append({
            "symbol": sym,
            "balance": balance,
            "price": price,
            "value_usdt": value,
            "actual_pct": 0.0,
        })

    if invalid_symbols:
        log.warning("Invalid symbols (not found on MEXC): %s", invalid_symbols)

    # When a budget is set, use it as the fixed total so that actual_pct
    # reflects how each asset sits relative to the intended allocation.
    # This prevents assets held outside the portfolio from inflating the
    # total and causing the bot to over-trade.
    if budget_usdt is not None:
        total = budget_usdt
        log.info("Portfolio total (fixed budget): %.2f USDT", total)
    else:
        # Informational mode: sum live values + free USDT not in portfolio.
        total = sum(r["value_usdt"] for r in result)
        asset_symbols = {a["symbol"].upper() for a in assets}
        if "USDT" not in asset_symbols:
            try:
                usdt_free = client.get_asset_balance("USDT")
                total += usdt_free
            except Exception as e:
                log.warning("Could not fetch free USDT balance: %s", e)
        log.info("Portfolio total (live): %.2f USDT", total)

    for r in result:
        r["actual_pct"] = (r["value_usdt"] / total * 100) if total > 0 else 0.0

    return {"total_usdt": total, "assets": result, "invalid_symbols": invalid_symbols}


# ---------------------------------------------------------------------------
# Rebalance execution
# ---------------------------------------------------------------------------

def execute_rebalance(client: MEXCClient, cfg: dict) -> list:
    """
    Calculate deviations and place market orders to restore target allocations.
    Sells overweight assets first, then buys underweight ones.

    Returns a list of order detail dicts for notification/history.
    When cfg['paper_trading'] is True, logs orders but does not place them.
    """
    # PAPER_TRADING env var overrides config (set to "false" on Railway for live trading)
    env_paper = os.environ.get("PAPER_TRADING", "").lower()
    if env_paper in ("true", "1", "yes"):
        paper = True
    elif env_paper in ("false", "0", "no"):
        paper = False
    else:
        paper = cfg.get("paper_trading", False)
    assets_cfg = cfg["portfolio"]["assets"]
    # Pass the configured budget so get_portfolio_value never counts more USDT
    # than the user allocated, even if the account holds a larger balance.
    budget_usdt = cfg["portfolio"].get("total_usdt")
    portfolio = get_portfolio_value(client, assets_cfg, budget_usdt=budget_usdt)
    total_usdt = portfolio["total_usdt"]

    log.info("Portfolio total: %.2f USDT%s", total_usdt, " [PAPER]" if paper else "")

    targets = {a["symbol"]: a["allocation_pct"] for a in assets_cfg}
    actuals = {r["symbol"]: r for r in portfolio["assets"]}

    sells = []
    buys = []
    details = []

    for sym, target_pct in targets.items():
        actual = actuals[sym]
        deviation = actual["actual_pct"] - target_pct
        target_value = total_usdt * target_pct / 100
        diff_usdt = actual["value_usdt"] - target_value

        log.info(
            "%s | target=%.2f%% actual=%.2f%% deviation=%.2f%% diff=%.2f USDT",
            sym, target_pct, actual["actual_pct"], deviation, diff_usdt,
        )

        entry = {
            "symbol": sym,
            "target_pct": target_pct,
            "actual_pct": round(actual["actual_pct"], 2),
            "deviation": round(deviation, 2),
            "diff_usdt": round(diff_usdt, 2),
            "action": "SKIP",
        }

        MIN_ORDER_USDT = 1.0  # MEXC minimum order size
        if diff_usdt > MIN_ORDER_USDT:
            sells.append({"symbol": sym, "diff_usdt": diff_usdt, "price": actual["price"], "entry": entry})
        elif diff_usdt < -MIN_ORDER_USDT:
            buys.append({"symbol": sym, "diff_usdt": abs(diff_usdt), "entry": entry})
        else:
            entry["action"] = "SKIP"
            details.append(entry)

    # Execute sells first to free up USDT
    for s in sells:
        sym = s["symbol"]
        entry = s["entry"]
        if sym == "USDT":
            entry["action"] = "SKIP"
            details.append(entry)
            continue
        base_qty = s["diff_usdt"] / s["price"]
        log.info("%sSELL %.8f %s (~%.2f USDT)", "[PAPER] " if paper else "", base_qty, sym, s["diff_usdt"])
        entry["action"] = "SELL"
        if not paper:
            try:
                resp = client.place_market_sell(f"{sym}USDT", base_qty)
                log.info("Sell order response: %s", resp)
            except Exception as e:
                log.error("Sell failed for %s: %s", sym, e)
                entry["action"] = f"SELL_ERROR: {e}"
        details.append(entry)

    if not paper:
        time.sleep(2)

    # Execute buys — re-check available USDT before each order to avoid
    # spending more than the account actually holds after the sell phase.
    for b in buys:
        sym = b["symbol"]
        entry = b["entry"]
        if sym == "USDT":
            entry["action"] = "SKIP"
            details.append(entry)
            continue

        spend_usdt = b["diff_usdt"]

        if not paper:
            # Guard: never spend more USDT than is actually available,
            # and never exceed the configured budget.
            try:
                available_usdt = client.get_asset_balance("USDT")
                capped_budget = min(available_usdt, budget_usdt) if budget_usdt else available_usdt
                if spend_usdt > capped_budget:
                    log.warning(
                        "BUY %s: wanted %.2f USDT but only %.2f available (budget cap %.2f) — adjusting",
                        sym, spend_usdt, available_usdt, capped_budget,
                    )
                    spend_usdt = capped_budget
                if spend_usdt <= 0:
                    log.warning("BUY %s: no USDT available — skipping", sym)
                    entry["action"] = "SKIP_NO_FUNDS"
                    details.append(entry)
                    continue
            except Exception as e:
                log.warning("Could not verify USDT balance before buying %s: %s", sym, e)

        log.info("%sBUY %.2f USDT of %s", "[PAPER] " if paper else "", spend_usdt, sym)
        entry["action"] = "BUY"
        if not paper:
            try:
                resp = client.place_market_buy(f"{sym}USDT", spend_usdt)
                log.info("Buy order response: %s", resp)
            except Exception as e:
                log.error("Buy failed for %s: %s", sym, e)
                entry["action"] = f"BUY_ERROR: {e}"
        details.append(entry)

    # Persist to DB and config
    mode = cfg["rebalance"]["mode"]
    record_rebalance(mode, total_usdt, details, paper=paper)
    record_snapshot(total_usdt, [
        {"symbol": r["symbol"], "value_usdt": r["value_usdt"], "actual_pct": r["actual_pct"]}
        for r in portfolio["assets"]
    ])

    cfg["last_rebalance"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    save_config(cfg)

    return details


def execute_rebalance_equal(client: MEXCClient, cfg: dict) -> list:
    """
    Rebalance by redistributing equally across all assets regardless of
    their configured allocation_pct.  Temporarily overrides targets to
    equal shares, then delegates to execute_rebalance.
    """
    import copy
    cfg_eq = copy.deepcopy(cfg)
    assets = cfg_eq["portfolio"]["assets"]
    n = len(assets)
    base = round(100.0 / n, 4)
    remainder = round(100.0 - base * (n - 1), 4)
    for i, a in enumerate(assets):
        a["allocation_pct"] = remainder if i == n - 1 else base
    return execute_rebalance(client, cfg_eq)


def get_pnl(cfg: dict, current_usdt: float | None = None) -> dict:
    """Return simple P&L vs initial invested value.

    current_usdt: live portfolio value from MEXC. If not provided, falls back
    to the last recorded snapshot (or initial value if no snapshots exist).
    """
    initial = cfg["portfolio"].get("initial_value_usdt", cfg["portfolio"].get("total_usdt", 0))
    if current_usdt is None:
        snapshots = get_snapshots(1)
        current_usdt = snapshots[0]["total_usdt"] if snapshots else initial
    # Don't show P&L if we have no real data yet
    if current_usdt == 0:
        return {"initial_usdt": initial, "current_usdt": 0, "pnl_usdt": 0, "pnl_pct": 0}
    pnl_usdt = current_usdt - initial
    pnl_pct = (pnl_usdt / initial * 100) if initial else 0.0
    return {
        "initial_usdt": initial,
        "current_usdt": current_usdt,
        "pnl_usdt": round(pnl_usdt, 2),
        "pnl_pct": round(pnl_pct, 2),
    }


# ---------------------------------------------------------------------------
# Deviation check (proportional mode)
# ---------------------------------------------------------------------------

def needs_rebalance_proportional(client: MEXCClient, cfg: dict) -> bool:
    """Return True if any asset deviates >= min_deviation_to_execute_pct."""
    assets_cfg = cfg["portfolio"]["assets"]
    min_dev = cfg["rebalance"]["proportional"]["min_deviation_to_execute_pct"]
    budget_usdt = cfg["portfolio"].get("total_usdt")
    portfolio = get_portfolio_value(client, assets_cfg, budget_usdt=budget_usdt)
    targets = {a["symbol"]: a["allocation_pct"] for a in assets_cfg}

    for r in portfolio["assets"]:
        deviation = abs(r["actual_pct"] - targets[r["symbol"]])
        if deviation >= min_dev:
            log.info(
                "%s deviation=%.2f%% >= threshold %.2f%% → rebalance triggered",
                r["symbol"], deviation, min_dev,
            )
            return True
    return False


# ---------------------------------------------------------------------------
# Timed schedule helper
# ---------------------------------------------------------------------------

def next_run_time(
    frequency: str,
    from_dt: Optional[datetime] = None,
    target_hour: int = 0,
) -> datetime:
    """Return the next scheduled run datetime.

    target_hour: UTC hour (0-23) at which the rebalance should fire.
    """
    now = from_dt or datetime.utcnow()
    if frequency == "daily":
        candidate = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate
    elif frequency == "weekly":
        candidate = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(weeks=1)
        return candidate
    elif frequency == "monthly":
        candidate = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=30)
        return candidate
    raise ValueError(f"Unknown frequency: {frequency}")


# ---------------------------------------------------------------------------
# Termination
# ---------------------------------------------------------------------------

def terminate(client: MEXCClient, cfg: dict) -> None:
    """Stop the bot. If sell_at_termination is True, liquidate all assets to USDT."""
    log.info("Terminating bot '%s'", cfg["bot"]["name"])
    if cfg["termination"]["sell_at_termination"]:
        log.info("sell_at_termination=True – selling all assets to USDT")
        for a in cfg["portfolio"]["assets"]:
            sym = a["symbol"]
            if sym == "USDT":
                continue
            balance = client.get_asset_balance(sym)
            if balance > 0:
                log.info("Selling %.8f %s", balance, sym)
                try:
                    resp = client.place_market_sell(f"{sym}USDT", balance)
                    log.info("Sell response: %s", resp)
                except Exception as e:
                    log.error("Failed to sell %s: %s", sym, e)
    else:
        log.info("sell_at_termination=False – assets left as-is")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(cfg: dict) -> None:
    client = MEXCClient()
    mode = cfg["rebalance"]["mode"]
    bot_name = cfg["bot"]["name"]

    log.info("Starting Smart Portfolio bot: %s | mode: %s", bot_name, mode)

    if mode == "proportional":
        interval_sec = cfg["rebalance"]["proportional"]["check_interval_minutes"] * 60
        log.info("Check interval: %d seconds", interval_sec)
        try:
            while True:
                log.info("--- Proportional check ---")
                if needs_rebalance_proportional(client, cfg):
                    execute_rebalance(client, cfg)
                else:
                    log.info("No rebalance needed.")
                time.sleep(interval_sec)
        except KeyboardInterrupt:
            terminate(client, cfg)

    elif mode == "timed":
        timed_cfg = cfg["rebalance"]["timed"]
        frequency = timed_cfg["frequency"]
        target_hour = timed_cfg.get("hour", 0)
        next_run = next_run_time(frequency, target_hour=target_hour)
        log.info("First rebalance scheduled at %s UTC", next_run.isoformat())
        try:
            while True:
                now = datetime.utcnow()
                if now >= next_run:
                    log.info("--- Timed rebalance (%s) ---", frequency)
                    execute_rebalance(client, cfg)
                    cfg = load_config()
                    frequency = cfg["rebalance"]["timed"]["frequency"]
                    target_hour = cfg["rebalance"]["timed"].get("hour", 0)
                    next_run = next_run_time(frequency, target_hour=target_hour)
                    log.info("Next rebalance at %s UTC", next_run.isoformat())
                time.sleep(60)
        except KeyboardInterrupt:
            terminate(client, cfg)

    elif mode == "unbalanced":
        log.info("Mode: unbalanced – no automatic rebalancing.")
        log.info("Run with --rebalance-now to trigger a manual rebalance.")
        portfolio = get_portfolio_value(client, cfg["portfolio"]["assets"])
        log.info("Current portfolio value: %.2f USDT", portfolio["total_usdt"])
        for r in portfolio["assets"]:
            log.info(
                "  %s: %.8f @ %.4f = %.2f USDT (%.2f%%)",
                r["symbol"], r["balance"], r["price"], r["value_usdt"], r["actual_pct"],
            )

    else:
        raise ValueError(f"Unknown rebalance mode: {mode}")
