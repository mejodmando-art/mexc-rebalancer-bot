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
    increment_grid_shift_count, get_grid_shift_info, set_grid_initial_range_pct,
    set_grid_range_pcts, get_grid_range_pcts,
    set_grid_expand_direction, get_grid_expand_direction,
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
                          volatility_pct: float = 5.0,
                          lower_pct: Optional[float] = None,
                          upper_pct: Optional[float] = None) -> tuple[float, float]:
    """
    Calculate price range from current price.

    If lower_pct/upper_pct are provided they are used asymmetrically:
      price_low  = price * (1 - lower_pct/100)
      price_high = price * (1 + upper_pct/100)
    Otherwise falls back to symmetric ±volatility_pct%.
    """
    price = client.get_price(symbol)
    if lower_pct is not None and upper_pct is not None:
        return (
            round(price * (1 - lower_pct / 100), 8),
            round(price * (1 + upper_pct / 100), 8),
        )
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
                            stop_event: Optional[threading.Event] = None,
                            initial_buy_qty: float = 0.0) -> None:
    """
    Place BUY orders below current price and SELL orders above it.

    Grid allocation is split equally between levels below and above the current
    price so each side gets the same number of orders and the same USDT per grid.

    initial_buy_qty: base-asset quantity already purchased at market price before
    grid placement (half-investment buy). SELL orders above are sized from this
    held quantity divided equally across upper levels, so the bot can sell what
    it actually owns. BUY orders below use usdt_per_grid as usual.

    Orders are placed gradually (PLACE_INTERVAL between each) to avoid market
    impact. In 'infinity' mode there is no upper bound for SELLs.
    Respects stop_event so the bot can be stopped mid-placement.
    """
    buy_levels  = [l for l in levels[:-1] if l < current_price]
    sell_levels = [l for l in levels[1:]  if l > current_price]

    # Equalise: use the smaller count so both sides have the same number of orders
    n = min(len(buy_levels), len(sell_levels))
    buy_levels  = buy_levels[-n:]   # closest n levels below price
    sell_levels = sell_levels[:n]   # closest n levels above price

    # SELL qty per level: distribute held base qty equally across upper levels
    sell_qty_per_level = (
        round(initial_buy_qty / n * (1 - FEE_RATE), qty_prec) if n > 0 and initial_buy_qty > 0
        else 0.0
    )

    for level in buy_levels:
        if stop_event and stop_event.is_set():
            return
        qty = usdt_per_grid / level
        _place_limit_order(client, bot_id, symbol, "BUY", level, qty, qty_prec)
        if stop_event:
            stop_event.wait(PLACE_INTERVAL)
        else:
            time.sleep(PLACE_INTERVAL)

    for level in sell_levels:
        if stop_event and stop_event.is_set():
            return
        if mode == "infinity" or level <= levels[-1]:
            qty = sell_qty_per_level if sell_qty_per_level > 0 else round(
                (usdt_per_grid / level) * (1 - FEE_RATE), qty_prec
            )
            _place_limit_order(client, bot_id, symbol, "SELL", level, qty, qty_prec)
            if stop_event:
                stop_event.wait(PLACE_INTERVAL)
            else:
                time.sleep(PLACE_INTERVAL)


def _rebuild_grid(client: MEXCClient, bot_id: int, symbol: str,
                   investment: float, mode: str, qty_prec: int,
                   stop_event: Optional[threading.Event] = None) -> tuple[float, float, float, int, list[float]]:
    """
    Cancel all open orders, shift grid to current price, and expand the range.

    Expansion rule (doubles each shift):
      shift N → range_pct = initial_range_pct * 2^N  (capped at 50%)

    expand_direction controls which side grows:
      'both'  — lower_pct and upper_pct both double
      'lower' — only lower_pct doubles; upper_pct stays at initial
      'upper' — only upper_pct doubles; lower_pct stays at initial
    """
    log.info("[Grid %d] rebuilding grid (price out of range)", bot_id)
    _cancel_all_open_orders(client, bot_id, symbol)

    new_shift_count = increment_grid_shift_count(bot_id)
    _, initial_range_pct = get_grid_shift_info(bot_id)
    lower_pct_init, upper_pct_init = get_grid_range_pcts(bot_id)
    direction = get_grid_expand_direction(bot_id)

    multiplier = 2 ** new_shift_count

    if direction == "lower":
        new_lower = min(lower_pct_init * multiplier, 50.0)
        new_upper = upper_pct_init
    elif direction == "upper":
        new_lower = lower_pct_init
        new_upper = min(upper_pct_init * multiplier, 50.0)
    else:  # both
        new_lower = min(lower_pct_init * multiplier, 50.0)
        new_upper = min(upper_pct_init * multiplier, 50.0)

    log.info(
        "[Grid %d] shift #%d dir=%s — lower=%.1f%% upper=%.1f%%",
        bot_id, new_shift_count, direction, new_lower, new_upper,
    )

    price_low, price_high = calculate_grid_range(
        client, symbol, lower_pct=new_lower, upper_pct=new_upper
    )
    grid_count = calculate_grid_count(investment, price_low, price_high)
    update_grid_bot_range(bot_id, price_low, price_high, grid_count)

    levels        = build_grid_levels(price_low, price_high, grid_count)
    usdt_per_grid = investment / grid_count
    current_price = client.get_price(symbol)

    # On grid rebuild (price out of range) we already hold base asset from the
    # initial market buy — no new market buy needed; SELL orders use usdt_per_grid sizing.
    _place_initial_orders(client, bot_id, symbol, levels, current_price,
                           usdt_per_grid, qty_prec, mode, stop_event,
                           initial_buy_qty=0.0)
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

        # Place initial orders only if no open orders exist (avoids duplicates on resume)
        existing_open = [o for o in get_grid_orders(bot_id) if o["status"] == "open"]
        if not existing_open:
            current_price = client.get_price(symbol)

            # Buy 50% of investment at market price immediately so the bot holds
            # base asset to back the SELL orders placed above current price.
            # On resume after restart we skip this — base_qty is already tracked.
            initial_buy_qty = 0.0
            if base_qty == 0.0:
                half_usdt = investment / 2.0
                market_qty = round(half_usdt / current_price, qty_prec)
                if market_qty > 0:
                    try:
                        resp = client.place_market_buy(symbol, half_usdt)
                        filled_qty   = float(resp.get("executedQty", market_qty))
                        filled_price = (
                            float(resp.get("cummulativeQuoteQty", half_usdt)) / filled_qty
                            if filled_qty > 0 else current_price
                        )
                        initial_buy_qty = filled_qty
                        base_qty        = filled_qty
                        avg_buy_price   = filled_price
                        log.info(
                            "[Grid %d] initial market BUY %.6f %s @ ~%.4f (%.2f USDT)",
                            bot_id, filled_qty, symbol, filled_price, half_usdt,
                        )
                        update_grid_bot_position(bot_id, avg_buy_price, base_qty, 0.0, realised_profit)
                    except Exception as e:
                        log.warning("[Grid %d] initial market buy failed: %s — placing grid without pre-buy", bot_id, e)

            _place_initial_orders(client, bot_id, symbol, levels, current_price,
                                   usdt_per_grid, qty_prec, mode, stop_event,
                                   initial_buy_qty=initial_buy_qty)

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
                   lower_pct: Optional[float] = None,
                   upper_pct: Optional[float] = None,
                   expand_direction: str = "both",
                   mode: str = "normal",
                   use_base_balance: bool = False) -> int:
    """
    Create and start a grid bot.

    Range input (choose one):
      - lower_pct / upper_pct : percentage below/above current price (preferred)
      - price_low / price_high : explicit prices (legacy / manual override)
      If none provided, defaults to ±5%.

    expand_direction: when price exits the range, which side expands:
      'both'  — lower and upper both double each shift
      'lower' — only lower side doubles
      'upper' — only upper side doubles

    mode:
      'normal'   - standard grid with upper and lower bounds.
      'infinity' - no upper price cap; only price_low acts as a floor.

    use_base_balance:
      When True, adds existing base-asset USDT value to investment.

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

    # Resolve price range: % input takes priority over explicit prices
    if lower_pct is not None or upper_pct is not None:
        _lower = lower_pct if lower_pct is not None else 5.0
        _upper = upper_pct if upper_pct is not None else 5.0
        price_low, price_high = calculate_grid_range(
            client, symbol, lower_pct=_lower, upper_pct=_upper
        )
    elif price_low is None or price_high is None:
        _lower, _upper = 5.0, 5.0
        price_low, price_high = calculate_grid_range(client, symbol)
    else:
        # Derive % from explicit prices for consistent expand behaviour
        try:
            _cur = client.get_price(symbol)
            _lower = round((_cur - price_low) / _cur * 100, 4) if _cur > 0 else 5.0
            _upper = round((price_high - _cur) / _cur * 100, 4) if _cur > 0 else 5.0
        except Exception:
            _lower, _upper = 5.0, 5.0

    if grid_count is None:
        grid_count = calculate_grid_count(investment, price_low, price_high)

    config = {
        "symbol":           symbol,
        "investment":       investment,
        "grid_count":       grid_count,
        "price_low":        price_low,
        "price_high":       price_high,
        "lower_pct":        _lower,
        "upper_pct":        _upper,
        "expand_direction": expand_direction,
        "mode":             mode,
        "created_at":       _now(),
    }

    bot_id = create_grid_bot(symbol, investment, grid_count,
                              price_low, price_high, config, mode=mode)
    log.info("[Grid %d] created: %s mode=%s inv=%.2f grids=%d range=[%.4f, %.4f] (↓%.1f%% ↑%.1f%%)",
             bot_id, symbol, mode, investment, grid_count, price_low, price_high, _lower, _upper)

    # Persist range % and expand direction for use in _rebuild_grid
    set_grid_range_pcts(bot_id, _lower, _upper)
    set_grid_expand_direction(bot_id, expand_direction)
    set_grid_initial_range_pct(bot_id, round((_lower + _upper) / 2, 4))

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
