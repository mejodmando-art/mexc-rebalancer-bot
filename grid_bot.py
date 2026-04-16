"""
Grid Bot engine — Dynamic AI Grid Trading on MEXC Spot.

Strategy (matches the Dynamic AI Grid spec):
- Divides a price range into N equal grid levels.
- Places limit BUY orders below current price AND limit SELL orders above it
  at startup (not just BUYs).
- When a BUY fills → places a SELL one grid step higher.
- When a SELL fills → places a BUY one grid step lower.
- Orders are placed gradually (one per PLACE_INTERVAL seconds) to avoid
  moving the market.
- Tracks average buy price and held base quantity to compute unrealized P&L.
- Total profit = realised grid profit + unrealized P&L.
- Dynamic re-ranging: when price moves outside the current range the bot
  cancels all open orders, recalculates the range around the new price, and
  rebuilds the grid.
- Infinity mode: no upper price cap — SELL orders are placed one step above
  each filled BUY with no ceiling, while price_low acts as the lower bound.
"""

import logging
import math
import threading
import time
from datetime import datetime
from typing import Optional

from mexc_client import MEXCClient
from database import (
    create_grid_bot, get_grid_bot, update_grid_bot_status,
    update_grid_bot_position, update_grid_bot_range,
    add_grid_order, get_grid_orders,
    update_grid_order, delete_grid_bot, set_grid_bot_should_run,
)

log = logging.getLogger(__name__)

POLL_INTERVAL      = 10    # seconds between order-status checks
PLACE_INTERVAL     = 0.4   # seconds between placing individual orders (gradual)
MIN_USDT_PER_GRID  = 1.0   # minimum USDT allocated per grid level
FEE_RATE           = 0.001 # 0.1% taker fee buffer on sell qty


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def calculate_grid_range(client: MEXCClient, symbol: str,
                          volatility_pct: float = 5.0) -> tuple[float, float]:
    """
    Auto-calculate price range based on current price +/- volatility_pct%.
    Returns (price_low, price_high).
    """
    price = client.get_price(symbol)
    spread = price * (volatility_pct / 100)
    return round(price - spread, 8), round(price + spread, 8)


def calculate_grid_count(investment: float, price_low: float,
                          price_high: float) -> int:
    """
    Choose grid count so each grid has at least MIN_USDT_PER_GRID.
    Clamps between 3 and 20.
    """
    max_grids = int(investment / MIN_USDT_PER_GRID)
    return max(3, min(max_grids, 20))


def build_grid_levels(price_low: float, price_high: float,
                       grid_count: int) -> list[float]:
    """Return list of grid_count+1 evenly spaced price levels."""
    step = (price_high - price_low) / grid_count
    return [round(price_low + i * step, 8) for i in range(grid_count + 1)]


def get_symbol_precision(client: MEXCClient, symbol: str) -> tuple[int, int]:
    """Return (price_precision, qty_precision) for a symbol."""
    try:
        info = client.get_symbol_info(symbol)
        filters = {f["filterType"]: f for f in info.get("filters", [])}
        price_prec = 8
        qty_prec   = 6
        if "PRICE_FILTER" in filters:
            tick = filters["PRICE_FILTER"].get("tickSize", "0.00000001")
            price_prec = max(0, -int(math.floor(math.log10(float(tick)))))
        if "LOT_SIZE" in filters:
            step = filters["LOT_SIZE"].get("stepSize", "0.000001")
            qty_prec = max(0, -int(math.floor(math.log10(float(step)))))
        return price_prec, qty_prec
    except Exception:
        return 8, 6


def _place_limit_order(client: MEXCClient, bot_id: int, symbol: str,
                        side: str, price: float, qty: float,
                        qty_prec: int) -> Optional[str]:
    """Place a single LIMIT order and record it in DB. Returns order_id or None.

    Order placement and DB recording are kept in strict sequence: if the exchange
    call succeeds but the DB write fails, the order_id is still returned so the
    caller can log it. The order is recorded with status 'open' before returning
    so _cancel_all_open_orders can always find and cancel it.
    """
    qty = round(qty, qty_prec)
    if qty <= 0:
        return None
    order_id: Optional[str] = None
    try:
        resp = client._post("/api/v3/order", {
            "symbol":      symbol,
            "side":        side,
            "type":        "LIMIT",
            "price":       str(price),
            "quantity":    str(qty),
            "timeInForce": "GTC",
        })
        order_id = str(resp.get("orderId", ""))
        # Record in DB immediately after exchange confirms the order.
        # If this write fails the order exists on MEXC but not in DB (orphan).
        # We log a critical warning so the operator can cancel it manually.
        try:
            add_grid_order(bot_id, order_id, side, price, qty)
        except Exception as db_err:
            log.error(
                "[Grid %d] ORPHAN ORDER — placed %s %s @ %.8f qty=%.6f orderId=%s "
                "but DB write failed: %s — cancel this order manually on MEXC",
                bot_id, side, symbol, price, qty, order_id, db_err,
            )
        log.info("[Grid %d] %s @ %.8f qty=%.6f", bot_id, side, price, qty)
        return order_id
    except Exception as e:
        log.warning("[Grid %d] failed to place %s @ %.8f: %s", bot_id, side, price, e)
        return None


def _cancel_all_open_orders(client: MEXCClient, bot_id: int,
                              symbol: str) -> None:
    """Cancel every open order for this bot on the exchange."""
    orders = get_grid_orders(bot_id)
    for o in orders:
        if o["status"] == "open" and o["order_id"]:
            try:
                client._delete("/api/v3/order", {
                    "symbol":  symbol,
                    "orderId": o["order_id"],
                })
                update_grid_order(o["order_id"], "cancelled", 0.0)
                log.info("[Grid %d] cancelled order %s", bot_id, o["order_id"])
            except Exception as e:
                log.warning("[Grid %d] cancel error %s: %s", bot_id, o["order_id"], e)


# ---------------------------------------------------------------------------
# Active loops registry
# ---------------------------------------------------------------------------

_grid_loops: dict[int, dict] = {}   # bot_id -> {thread, stop_event, error}
_lock = threading.Lock()


def is_running(bot_id: int) -> bool:
    with _lock:
        entry = _grid_loops.get(bot_id)
        return bool(entry and entry["thread"].is_alive())


def get_error(bot_id: int) -> Optional[str]:
    with _lock:
        entry = _grid_loops.get(bot_id)
        return entry["error"] if entry else None


# ---------------------------------------------------------------------------
# Grid placement helpers
# ---------------------------------------------------------------------------

def _place_initial_orders(client: MEXCClient, bot_id: int, symbol: str,
                            levels: list[float], current_price: float,
                            usdt_per_grid: float, qty_prec: int,
                            mode: str,
                            stop_event: Optional[threading.Event] = None) -> None:
    """
    Place BUY orders below current price and SELL orders above it.
    Orders are placed gradually (PLACE_INTERVAL between each) to avoid
    market impact.  In 'infinity' mode there is no upper bound for SELLs.
    Respects stop_event so the bot can be stopped mid-placement.
    """
    for level in levels[:-1]:   # N+1 points; skip the very top for BUY
        if stop_event and stop_event.is_set():
            return
        if level < current_price:
            qty = usdt_per_grid / level
            _place_limit_order(client, bot_id, symbol, "BUY", level, qty, qty_prec)
            if stop_event:
                stop_event.wait(PLACE_INTERVAL)
            else:
                time.sleep(PLACE_INTERVAL)

    for level in levels[1:]:    # skip the very bottom for SELL
        if stop_event and stop_event.is_set():
            return
        if level > current_price:
            sell_qty = round((usdt_per_grid / level) * (1 - FEE_RATE), qty_prec)
            _place_limit_order(client, bot_id, symbol, "SELL", level, sell_qty, qty_prec)
            if stop_event:
                stop_event.wait(PLACE_INTERVAL)
            else:
                time.sleep(PLACE_INTERVAL)


def _rebuild_grid(client: MEXCClient, bot_id: int, symbol: str,
                   investment: float, mode: str, qty_prec: int,
                   stop_event: Optional[threading.Event] = None) -> tuple[float, float, float, int, list[float]]:
    """
    Cancel all open orders, recalculate range around current price, place
    new grid. Returns (price_low, price_high, current_price, grid_count, levels).
    """
    log.info("[Grid %d] rebuilding grid (price out of range)", bot_id)
    _cancel_all_open_orders(client, bot_id, symbol)

    price_low, price_high = calculate_grid_range(client, symbol)
    grid_count = calculate_grid_count(investment, price_low, price_high)
    update_grid_bot_range(bot_id, price_low, price_high, grid_count)

    levels        = build_grid_levels(price_low, price_high, grid_count)
    usdt_per_grid = investment / grid_count
    current_price = client.get_price(symbol)

    _place_initial_orders(client, bot_id, symbol, levels, current_price,
                           usdt_per_grid, qty_prec, mode, stop_event)
    return price_low, price_high, current_price, grid_count, levels


# ---------------------------------------------------------------------------
# Grid monitoring loop
# ---------------------------------------------------------------------------

def _grid_loop(bot_id: int, stop_event: threading.Event) -> None:
    """Main monitoring loop for a single grid bot."""
    client = MEXCClient()
    log.info("[Grid %d] loop started", bot_id)

    try:
        bot = get_grid_bot(bot_id)
        if not bot:
            log.error("[Grid %d] bot not found in DB", bot_id)
            return

        symbol        = bot["symbol"]
        investment    = bot["investment"]
        grid_count    = bot["grid_count"]
        price_low     = bot["price_low"]
        price_high    = bot["price_high"]
        mode          = bot.get("mode", "normal")   # 'normal' | 'infinity'

        levels        = build_grid_levels(price_low, price_high, grid_count)
        usdt_per_grid = investment / grid_count
        _, qty_prec   = get_symbol_precision(client, symbol)

        # Position tracking — loaded from DB so they survive restarts.
        # Use realised_profit column (not profit which includes unrealized).
        avg_buy_price   = float(bot.get("avg_buy_price") or 0)
        base_qty        = float(bot.get("base_qty") or 0)
        realised_profit = float(bot.get("realised_profit") or 0)

        # Place initial BUY + SELL orders only if no open orders exist
        # (avoids duplicates on resume after restart)
        existing_open = [o for o in get_grid_orders(bot_id) if o["status"] == "open"]
        if not existing_open:
            current_price = client.get_price(symbol)
            _place_initial_orders(client, bot_id, symbol, levels, current_price,
                                   usdt_per_grid, qty_prec, mode, stop_event)

        # Monitoring loop
        while not stop_event.is_set():
            try:
                current_price = client.get_price(symbol)

                # Dynamic re-ranging: rebuild when price exits the range.
                # In infinity mode only the lower bound matters.
                out_of_range = current_price < price_low or (
                    mode != "infinity" and current_price > price_high
                )
                if out_of_range:
                    price_low, price_high, current_price, grid_count, levels = \
                        _rebuild_grid(client, bot_id, symbol, investment, mode, qty_prec, stop_event)
                    usdt_per_grid = investment / grid_count
                    stop_event.wait(POLL_INTERVAL)
                    continue

                # Update unrealized P&L
                if base_qty > 0 and avg_buy_price > 0:
                    unrealized_pnl = round((current_price - avg_buy_price) * base_qty, 4)
                else:
                    unrealized_pnl = 0.0
                # Write realised_profit separately so it survives restarts correctly
                update_grid_bot_position(bot_id, avg_buy_price, base_qty,
                                         unrealized_pnl, realised_profit)

                # Check each open order
                orders      = get_grid_orders(bot_id)
                open_orders = [o for o in orders if o["status"] == "open"]

                for order in open_orders:
                    try:
                        mexc_order  = client.get_order(symbol, order["order_id"])
                        mexc_status = mexc_order.get("status", "")

                        if mexc_status == "FILLED":
                            filled_price = float(mexc_order.get("price", order["price"]))
                            filled_qty   = float(mexc_order.get("executedQty", order["qty"]))
                            side         = order["side"]
                            step         = (price_high - price_low) / grid_count

                            if side == "BUY":
                                # Weighted average buy price
                                total_cost    = avg_buy_price * base_qty + filled_price * filled_qty
                                base_qty     += filled_qty
                                avg_buy_price = total_cost / base_qty if base_qty > 0 else filled_price

                                # Place SELL one step above (no ceiling in infinity mode)
                                sell_price = round(filled_price + step, 8)
                                sell_qty   = round(filled_qty * (1 - FEE_RATE), qty_prec)
                                _place_limit_order(client, bot_id, symbol,
                                                   "SELL", sell_price, sell_qty, qty_prec)
                                update_grid_order(order["order_id"], "filled", 0.0)

                            elif side == "SELL":
                                # Only count profit when we have a valid avg_buy_price.
                                # A SELL filling before any BUY (avg_buy_price == 0) means
                                # the order was placed at startup above the current price;
                                # there is no cost basis to compute profit against.
                                if avg_buy_price > 0:
                                    profit_per_unit  = filled_price - avg_buy_price
                                    grid_profit      = round(profit_per_unit * filled_qty, 4)
                                    realised_profit += grid_profit
                                else:
                                    grid_profit = 0.0
                                    log.info(
                                        "[Grid %d] SELL filled @ %.8f before any BUY — "
                                        "skipping profit calculation (no cost basis)",
                                        bot_id, filled_price,
                                    )

                                # Reduce held position
                                base_qty = max(0.0, base_qty - filled_qty)
                                if base_qty <= 0:
                                    avg_buy_price = 0.0

                                # Place BUY one step below (only if above price_floor)
                                buy_price = round(filled_price - step, 8)
                                if buy_price >= price_low:
                                    buy_qty = usdt_per_grid / buy_price
                                    _place_limit_order(client, bot_id, symbol,
                                                       "BUY", buy_price, buy_qty, qty_prec)

                                update_grid_order(order["order_id"], "filled", grid_profit)
                                log.info("[Grid %d] SELL filled @ %.8f profit=%.4f USDT",
                                         bot_id, filled_price, grid_profit)

                        elif mexc_status in ("CANCELED", "EXPIRED", "REJECTED"):
                            update_grid_order(order["order_id"], mexc_status.lower(), 0.0)

                    except Exception as e:
                        log.warning("[Grid %d] order check error: %s", bot_id, e)

            except Exception as e:
                log.error("[Grid %d] monitoring error: %s", bot_id, e)
                with _lock:
                    if bot_id in _grid_loops:
                        _grid_loops[bot_id]["error"] = str(e)

            stop_event.wait(POLL_INTERVAL)

    except Exception as e:
        log.error("[Grid %d] fatal error: %s", bot_id, e)
        with _lock:
            if bot_id in _grid_loops:
                _grid_loops[bot_id]["error"] = str(e)
    finally:
        update_grid_bot_status(bot_id, "stopped")
        log.info("[Grid %d] loop stopped", bot_id)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_grid_bot(symbol: str, investment: float,
                   grid_count: Optional[int] = None,
                   price_low: Optional[float] = None,
                   price_high: Optional[float] = None,
                   mode: str = "normal",
                   use_base_balance: bool = False) -> int:
    """
    Create and start a grid bot.

    mode:
      'normal'   - standard grid with upper and lower bounds.
      'infinity' - no upper price cap; only price_low acts as a floor.

    use_base_balance:
      When True, the bot reads the existing base-asset balance from the wallet
      and adds its USDT value to `investment` (USDT+BASE mode from the spec).

    If price_low/price_high are None, auto-calculates from current price +/-5%.
    If grid_count is None, auto-calculates from investment size.
    Returns the new bot_id.
    """
    client = MEXCClient()
    symbol = symbol.upper()
    if not symbol.endswith("USDT"):
        symbol += "USDT"

    # USDT+BASE: add value of existing base-asset holdings to investment
    if use_base_balance:
        base_asset = symbol.replace("USDT", "")
        try:
            base_held  = client.get_asset_balance(base_asset)
            base_price = client.get_price(symbol)
            base_value = base_held * base_price
            if base_value > 0:
                log.info("[Grid new] USDT+BASE: found %.6f %s worth %.2f USDT",
                         base_held, base_asset, base_value)
                investment += base_value
        except Exception as e:
            log.warning("[Grid new] could not read base balance: %s", e)

    if price_low is None or price_high is None:
        price_low, price_high = calculate_grid_range(client, symbol)

    if grid_count is None:
        grid_count = calculate_grid_count(investment, price_low, price_high)

    config = {
        "symbol":     symbol,
        "investment": investment,
        "grid_count": grid_count,
        "price_low":  price_low,
        "price_high": price_high,
        "mode":       mode,
        "auto_range": True,
        "created_at": _now(),
    }

    bot_id = create_grid_bot(symbol, investment, grid_count,
                              price_low, price_high, config, mode=mode)
    log.info("[Grid %d] created: %s mode=%s inv=%.2f grids=%d range=[%.4f, %.4f]",
             bot_id, symbol, mode, investment, grid_count, price_low, price_high)

    set_grid_bot_should_run(bot_id, True)
    stop_event = threading.Event()
    t = threading.Thread(target=_grid_loop, args=(bot_id, stop_event),
                         daemon=True, name=f"grid-{bot_id}")
    with _lock:
        _grid_loops[bot_id] = {"thread": t, "stop_event": stop_event, "error": None}
    t.start()
    return bot_id


def stop_grid_bot(bot_id: int) -> None:
    """Signal the grid loop to stop and cancel all open orders.

    The loop thread is joined before cancelling orders to avoid a race where
    the thread places new orders between stop_event.set() and the cancel call.
    """
    set_grid_bot_should_run(bot_id, False)

    with _lock:
        entry = _grid_loops.get(bot_id)
    if entry:
        entry["stop_event"].set()
        # Wait for the loop thread to finish before cancelling so no new orders
        # are placed after we issue cancels.
        entry["thread"].join(timeout=15)
        if entry["thread"].is_alive():
            log.warning("[Grid %d] loop thread did not stop within 15 s — "
                        "proceeding with order cancellation anyway", bot_id)

    try:
        client = MEXCClient()
        bot    = get_grid_bot(bot_id)
        if bot:
            _cancel_all_open_orders(client, bot_id, bot["symbol"])
    except Exception as e:
        log.error("[Grid %d] stop_grid_bot error: %s", bot_id, e)

    update_grid_bot_status(bot_id, "stopped")


def resume_grid_bot(bot_id: int) -> None:
    """Resume a stopped grid bot (re-starts the monitoring loop)."""
    if is_running(bot_id):
        return
    set_grid_bot_should_run(bot_id, True)
    stop_event = threading.Event()
    t = threading.Thread(target=_grid_loop, args=(bot_id, stop_event),
                         daemon=True, name=f"grid-{bot_id}")
    with _lock:
        _grid_loops[bot_id] = {"thread": t, "stop_event": stop_event, "error": None}
    update_grid_bot_status(bot_id, "running")
    t.start()


def get_grid_bot_status(bot_id: int) -> dict:
    """Return live status dict for a grid bot."""
    bot = get_grid_bot(bot_id)
    if not bot:
        return {"error": "not found"}
    orders       = get_grid_orders(bot_id)
    open_count   = sum(1 for o in orders if o["status"] == "open")
    filled_count = sum(1 for o in orders if o["status"] == "filled")

    avg_buy_price   = float(bot.get("avg_buy_price") or 0)
    base_qty        = float(bot.get("base_qty") or 0)
    unrealized_pnl  = float(bot.get("unrealized_pnl") or 0)
    realised        = float(bot.get("realised_profit") or 0)
    total_profit    = round(realised + unrealized_pnl, 4)

    return {
        "id":              bot["id"],
        "symbol":          bot["symbol"],
        "investment":      bot["investment"],
        "grid_count":      bot["grid_count"],
        "price_low":       bot["price_low"],
        "price_high":      bot["price_high"],
        "mode":            bot.get("mode", "normal"),
        "status":          bot["status"],
        # Profit breakdown matching the spec
        "profit":          total_profit,       # realised + unrealized
        "realised_profit": realised,
        "unrealized_pnl":  unrealized_pnl,
        "avg_buy_price":   avg_buy_price,
        "base_qty":        base_qty,
        "running":         is_running(bot_id),
        "error":           get_error(bot_id),
        "open_orders":     open_count,
        "filled_orders":   filled_count,
        "ts_created":      bot["ts_created"],
    }
