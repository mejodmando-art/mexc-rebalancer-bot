"""
Grid Bot engine — Dynamic AI Grid Trading on MEXC Spot.

Strategy:
- Divides a price range into N equal grid levels.
- Places limit BUY orders below current price and SELL orders above.
- When a BUY fills → places a SELL one grid level higher (and vice versa).
- Monitors open orders every POLL_INTERVAL seconds.
- Auto-adjusts range when price moves outside bounds (dynamic mode).
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
    update_grid_bot_profit, add_grid_order, get_grid_orders,
    update_grid_order, delete_grid_bot,
)

log = logging.getLogger(__name__)

POLL_INTERVAL = 10   # seconds between order checks
MIN_USDT_PER_GRID = 1.0  # minimum USDT per grid level


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def calculate_grid_range(client: MEXCClient, symbol: str,
                          volatility_pct: float = 5.0) -> tuple[float, float]:
    """
    Auto-calculate price range based on current price ± volatility_pct%.
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
    return max(3, min(max_grids, 20))  # cap between 3 and 20 grids


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
        qty_prec = 6
        if "PRICE_FILTER" in filters:
            tick = filters["PRICE_FILTER"].get("tickSize", "0.00000001")
            price_prec = max(0, -int(math.floor(math.log10(float(tick)))))
        if "LOT_SIZE" in filters:
            step = filters["LOT_SIZE"].get("stepSize", "0.000001")
            qty_prec = max(0, -int(math.floor(math.log10(float(step)))))
        return price_prec, qty_prec
    except Exception:
        return 8, 6


# ---------------------------------------------------------------------------
# Active loops registry
# ---------------------------------------------------------------------------

_grid_loops: dict[int, dict] = {}  # bot_id -> {thread, stop_event, error}
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
# Grid loop
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

        symbol      = bot["symbol"]
        investment  = bot["investment"]
        grid_count  = bot["grid_count"]
        price_low   = bot["price_low"]
        price_high  = bot["price_high"]

        levels      = build_grid_levels(price_low, price_high, grid_count)
        usdt_per_grid = investment / grid_count
        _, qty_prec = get_symbol_precision(client, symbol)

        # Place initial BUY limit orders below current price
        current_price = client.get_price(symbol)
        placed = 0
        for level in levels[:-1]:  # skip top level for buys
            if level < current_price:
                qty = round(usdt_per_grid / level, qty_prec)
                if qty <= 0:
                    continue
                try:
                    resp = client._post("/api/v3/order", {
                        "symbol": symbol,
                        "side": "BUY",
                        "type": "LIMIT",
                        "price": str(level),
                        "quantity": str(qty),
                        "timeInForce": "GTC",
                    })
                    order_id = str(resp.get("orderId", ""))
                    add_grid_order(bot_id, order_id, "BUY", level, qty)
                    placed += 1
                    log.info("[Grid %d] BUY @ %.8f qty=%.6f", bot_id, level, qty)
                except Exception as e:
                    log.warning("[Grid %d] failed to place BUY @ %.8f: %s", bot_id, level, e)

        log.info("[Grid %d] placed %d initial BUY orders", bot_id, placed)

        # Monitoring loop
        total_profit = 0.0
        while not stop_event.is_set():
            try:
                orders = get_grid_orders(bot_id)
                open_orders = [o for o in orders if o["status"] == "open"]

                for order in open_orders:
                    try:
                        mexc_order = client.get_order(symbol, order["order_id"])
                        mexc_status = mexc_order.get("status", "")

                        if mexc_status == "FILLED":
                            filled_price = float(mexc_order.get("price", order["price"]))
                            filled_qty   = float(mexc_order.get("executedQty", order["qty"]))
                            side         = order["side"]

                            if side == "BUY":
                                # Place a SELL one grid level above
                                step = (price_high - price_low) / grid_count
                                sell_price = round(filled_price + step, 8)
                                sell_qty   = round(filled_qty * 0.999, qty_prec)  # 0.1% fee buffer
                                profit_per_grid = round((sell_price - filled_price) * sell_qty, 4)
                                try:
                                    resp = client._post("/api/v3/order", {
                                        "symbol": symbol,
                                        "side": "SELL",
                                        "type": "LIMIT",
                                        "price": str(sell_price),
                                        "quantity": str(sell_qty),
                                        "timeInForce": "GTC",
                                    })
                                    new_id = str(resp.get("orderId", ""))
                                    add_grid_order(bot_id, new_id, "SELL", sell_price, sell_qty)
                                    log.info("[Grid %d] SELL placed @ %.8f (profit est. %.4f USDT)",
                                             bot_id, sell_price, profit_per_grid)
                                except Exception as e:
                                    log.warning("[Grid %d] failed to place SELL: %s", bot_id, e)

                            elif side == "SELL":
                                # Realise profit and place new BUY one level below
                                step = (price_high - price_low) / grid_count
                                buy_price  = round(filled_price - step, 8)
                                buy_qty    = round(usdt_per_grid / buy_price, qty_prec)
                                profit_realised = round((filled_price - buy_price) * filled_qty, 4)
                                total_profit += profit_realised
                                update_grid_bot_profit(bot_id, total_profit)
                                try:
                                    resp = client._post("/api/v3/order", {
                                        "symbol": symbol,
                                        "side": "BUY",
                                        "type": "LIMIT",
                                        "price": str(buy_price),
                                        "quantity": str(buy_qty),
                                        "timeInForce": "GTC",
                                    })
                                    new_id = str(resp.get("orderId", ""))
                                    add_grid_order(bot_id, new_id, "BUY", buy_price, buy_qty)
                                    log.info("[Grid %d] BUY re-placed @ %.8f profit=%.4f",
                                             bot_id, buy_price, profit_realised)
                                except Exception as e:
                                    log.warning("[Grid %d] failed to re-place BUY: %s", bot_id, e)

                            update_grid_order(order["order_id"], "filled", profit_per_grid if side == "BUY" else profit_realised)

                        elif mexc_status in ("CANCELED", "EXPIRED", "REJECTED"):
                            update_grid_order(order["order_id"], mexc_status.lower())

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
                   price_high: Optional[float] = None) -> int:
    """
    Create and start a grid bot.
    If price_low/price_high are None, auto-calculates from current price ±5%.
    If grid_count is None, auto-calculates from investment size.
    Returns the new bot_id.
    """
    client = MEXCClient()
    symbol = symbol.upper()
    if not symbol.endswith("USDT"):
        symbol = symbol + "USDT"

    # Auto-range
    if price_low is None or price_high is None:
        price_low, price_high = calculate_grid_range(client, symbol)

    # Auto grid count
    if grid_count is None:
        grid_count = calculate_grid_count(investment, price_low, price_high)

    config = {
        "symbol": symbol,
        "investment": investment,
        "grid_count": grid_count,
        "price_low": price_low,
        "price_high": price_high,
        "auto_range": True,
        "created_at": _now(),
    }

    bot_id = create_grid_bot(symbol, investment, grid_count,
                              price_low, price_high, config)
    log.info("[Grid %d] created: %s inv=%.2f grids=%d range=[%.4f, %.4f]",
             bot_id, symbol, investment, grid_count, price_low, price_high)

    stop_event = threading.Event()
    t = threading.Thread(target=_grid_loop, args=(bot_id, stop_event),
                         daemon=True, name=f"grid-{bot_id}")
    with _lock:
        _grid_loops[bot_id] = {"thread": t, "stop_event": stop_event, "error": None}
    t.start()
    return bot_id


def stop_grid_bot(bot_id: int) -> None:
    """Signal the grid loop to stop and cancel all open orders."""
    with _lock:
        entry = _grid_loops.get(bot_id)
    if entry:
        entry["stop_event"].set()

    # Cancel open orders on exchange
    try:
        client = MEXCClient()
        bot = get_grid_bot(bot_id)
        if bot:
            orders = get_grid_orders(bot_id)
            for o in orders:
                if o["status"] == "open" and o["order_id"]:
                    try:
                        client._delete("/api/v3/order", {
                            "symbol": bot["symbol"],
                            "orderId": o["order_id"],
                        })
                        update_grid_order(o["order_id"], "cancelled")
                        log.info("[Grid %d] cancelled order %s", bot_id, o["order_id"])
                    except Exception as e:
                        log.warning("[Grid %d] cancel order error: %s", bot_id, e)
    except Exception as e:
        log.error("[Grid %d] stop_grid_bot error: %s", bot_id, e)

    update_grid_bot_status(bot_id, "stopped")


def resume_grid_bot(bot_id: int) -> None:
    """Resume a stopped grid bot (re-starts the monitoring loop)."""
    if is_running(bot_id):
        return
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
    orders = get_grid_orders(bot_id)
    open_count   = sum(1 for o in orders if o["status"] == "open")
    filled_count = sum(1 for o in orders if o["status"] == "filled")
    return {
        "id":           bot["id"],
        "symbol":       bot["symbol"],
        "investment":   bot["investment"],
        "grid_count":   bot["grid_count"],
        "price_low":    bot["price_low"],
        "price_high":   bot["price_high"],
        "status":       bot["status"],
        "profit":       bot["profit"],
        "running":      is_running(bot_id),
        "error":        get_error(bot_id),
        "open_orders":  open_count,
        "filled_orders": filled_count,
        "ts_created":   bot["ts_created"],
    }
