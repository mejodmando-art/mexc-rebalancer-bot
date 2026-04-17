"""
Order Block Scanner — Smart Money Entry/Exit Engine.

Strategy:
- Scans candles on a configurable timeframe (default 15m).
- Waits for all four conditions to align:
    1. Liquidity sweep  — price wicks below a recent swing low (or above swing high)
    2. BOS / CHoCH      — the next candle closes above the swept level (structure break)
    3. Fresh OB         — the last bearish candle before the impulse (unmitigated)
    4. FFG / Imbalance  — a Fair Value Gap exists between the OB and the BOS candle

- Entry: market buy $15 USDT when all conditions are met.
- TP1  : market sell 50% of position when price rises +tp1_pct% above entry.
- TP2  : market sell remaining 50% when price rises +tp2_pct% above TP1 fill price.
- No hard stop loss — position sizing (fixed $15) limits max loss.

The loop runs in a daemon thread, one per scanner instance.
"""

import logging
import threading
import time
from datetime import datetime
from typing import Optional

from mexc_client import MEXCClient
from database import (
    get_ob_scanner, update_ob_scanner_status, update_ob_position,
    record_ob_trade, set_ob_should_run,
)

log = logging.getLogger(__name__)

POLL_INTERVAL = 30   # seconds between candle fetches while scanning
TRADE_POLL    = 10   # seconds between price checks while in a position

# Registry: scanner_id → {thread, stop_event, last_conditions, error}
_loops: dict[int, dict] = {}
_lock  = threading.Lock()


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Technical detection helpers
# ---------------------------------------------------------------------------

def _detect_liquidity_sweep(candles: list[dict]) -> tuple[bool, float]:
    """
    Detect a liquidity sweep: price wicks below the lowest low of the
    preceding N candles, then closes back above it (wick rejection).

    Returns (swept, swept_level).
    """
    if len(candles) < 10:
        return False, 0.0

    lookback = candles[-11:-1]   # 10 candles before the last
    last     = candles[-1]

    swing_low = min(c["low"] for c in lookback)

    # Wick pierced below swing low but candle closed above it
    swept = last["low"] < swing_low and last["close"] > swing_low
    return swept, swing_low


def _detect_bos(candles: list[dict], swept_level: float) -> bool:
    """
    BOS / CHoCH: the most recent closed candle closes above the swept level,
    confirming a structure break after the sweep.
    """
    if len(candles) < 2:
        return False
    last = candles[-1]
    return last["close"] > swept_level


def _detect_fresh_ob(candles: list[dict]) -> tuple[bool, float, float]:
    """
    Fresh Order Block: the last bearish candle (close < open) before the
    impulse move (last 3 candles). Returns (found, ob_high, ob_low).

    The OB is 'fresh' because we only look at recent candles — if price
    had already revisited it, the impulse would not have formed.
    """
    # Search the 5 candles before the last two (impulse window)
    window = candles[-7:-2]
    for c in reversed(window):
        if c["close"] < c["open"]:   # bearish candle
            return True, c["high"], c["low"]
    return False, 0.0, 0.0


def _detect_ffg(candles: list[dict]) -> bool:
    """
    Fair Value Gap (FVG / Imbalance): a 3-candle pattern where
    candle[i-2].high < candle[i].low  (bullish FVG — gap between wicks).

    Checks the last 5 candles for any such gap.
    """
    if len(candles) < 3:
        return False
    for i in range(2, min(6, len(candles))):
        c0 = candles[-i - 1]
        c2 = candles[-i + 1] if i > 1 else candles[-1]
        if c0["high"] < c2["low"]:
            return True
    return False


def _check_conditions(candles: list[dict]) -> tuple[bool, dict]:
    """
    Run all four filters. Returns (all_pass, conditions_dict).
    conditions_dict maps each condition name to True/False.
    """
    swept, swept_level = _detect_liquidity_sweep(candles)
    bos                = _detect_bos(candles, swept_level) if swept else False
    ob_found, ob_h, ob_l = _detect_fresh_ob(candles)
    ffg                = _detect_ffg(candles)

    conditions = {
        "liquidity_sweep": swept,
        "swept_level":     round(swept_level, 8),
        "bos_choch":       bos,
        "fresh_ob":        ob_found,
        "ob_high":         round(ob_h, 8),
        "ob_low":          round(ob_l, 8),
        "ffg":             ffg,
    }
    all_pass = swept and bos and ob_found and ffg
    return all_pass, conditions


# ---------------------------------------------------------------------------
# Main scanner loop
# ---------------------------------------------------------------------------

def _ob_loop(scanner_id: int, stop_event: threading.Event) -> None:
    log.info("[OB#%d] loop started", scanner_id)
    client = MEXCClient()

    try:
        row = get_ob_scanner(scanner_id)
        if not row:
            log.error("[OB#%d] scanner not found in DB", scanner_id)
            return

        symbol     = row["symbol"]
        timeframe  = row.get("timeframe", "15m")
        entry_usdt = float(row.get("entry_usdt", 15.0))
        tp1_pct    = float(row.get("tp1_pct", 5.0))
        tp2_pct    = float(row.get("tp2_pct", 5.0))

        # Restore in-progress position from DB
        entry_price: float = float(row.get("entry_price", 0))
        base_qty:    float = float(row.get("base_qty", 0))
        tp1_hit:     bool  = bool(row.get("tp1_hit", 0))
        realised_pnl: float = float(row.get("realised_pnl", 0))
        in_position: bool  = entry_price > 0 and base_qty > 0

        qty_prec = client.get_lot_size_precision(symbol)
        update_ob_scanner_status(scanner_id, "in_position" if in_position else "scanning")

        while not stop_event.is_set():
            try:
                # ── Phase 1: scanning for entry ──────────────────────────
                if not in_position:
                    candles = client.get_klines(symbol, timeframe, limit=50)
                    all_pass, conditions = _check_conditions(candles)

                    # Store latest condition snapshot regardless of pass/fail
                    update_ob_position(scanner_id, 0, 0, False, realised_pnl, conditions)

                    with _lock:
                        if scanner_id in _loops:
                            _loops[scanner_id]["last_conditions"] = conditions

                    if all_pass:
                        log.info("[OB#%d] All conditions met — entering %s with $%.2f",
                                 scanner_id, symbol, entry_usdt)
                        try:
                            order = client.place_market_buy(symbol, entry_usdt)
                            filled_qty  = float(order.get("executedQty", 0))
                            filled_usdt = float(order.get("cummulativeQuoteQty", entry_usdt))
                            entry_price = filled_usdt / filled_qty if filled_qty > 0 else client.get_price(symbol)
                            base_qty    = filled_qty
                            tp1_hit     = False
                            in_position = True

                            update_ob_position(scanner_id, entry_price, base_qty, False, realised_pnl, conditions)
                            update_ob_scanner_status(scanner_id, "in_position")
                            record_ob_trade(scanner_id, "BUY", entry_price, base_qty,
                                            filled_usdt, label="entry")
                            log.info("[OB#%d] Entered at %.6f, qty=%.6f", scanner_id, entry_price, base_qty)
                        except Exception as e:
                            log.error("[OB#%d] Entry order failed: %s", scanner_id, e)

                    stop_event.wait(POLL_INTERVAL)

                # ── Phase 2: managing open position ─────────────────────
                else:
                    current_price = client.get_price(symbol)

                    # TP1: sell 50% at +tp1_pct% above entry
                    if not tp1_hit:
                        tp1_trigger = entry_price * (1 + tp1_pct / 100)
                        if current_price >= tp1_trigger:
                            sell_qty = round(base_qty * 0.5, qty_prec)
                            if sell_qty > 0:
                                try:
                                    order = client.place_market_sell(symbol, sell_qty, qty_prec)
                                    fill_price = current_price
                                    pnl = (fill_price - entry_price) * sell_qty
                                    realised_pnl += pnl
                                    base_qty -= sell_qty
                                    tp1_hit = True

                                    update_ob_position(scanner_id, entry_price, base_qty, True, realised_pnl)
                                    record_ob_trade(scanner_id, "SELL", fill_price, sell_qty,
                                                    fill_price * sell_qty, pnl=pnl, label="TP1")
                                    log.info("[OB#%d] TP1 hit at %.6f — sold %.6f, PnL=%.4f USDT",
                                             scanner_id, fill_price, sell_qty, pnl)
                                except Exception as e:
                                    log.error("[OB#%d] TP1 sell failed: %s", scanner_id, e)

                    # TP2: sell remaining 50% at +tp2_pct% above TP1 fill price
                    else:
                        tp2_trigger = entry_price * (1 + tp1_pct / 100) * (1 + tp2_pct / 100)
                        if current_price >= tp2_trigger:
                            sell_qty = round(base_qty, qty_prec)
                            if sell_qty > 0:
                                try:
                                    order = client.place_market_sell(symbol, sell_qty, qty_prec)
                                    fill_price = current_price
                                    pnl = (fill_price - entry_price) * sell_qty
                                    realised_pnl += pnl
                                    base_qty = 0
                                    in_position = False
                                    entry_price = 0

                                    update_ob_position(scanner_id, 0, 0, False, realised_pnl)
                                    update_ob_scanner_status(scanner_id, "scanning")
                                    record_ob_trade(scanner_id, "SELL", fill_price, sell_qty,
                                                    fill_price * sell_qty, pnl=pnl, label="TP2")
                                    log.info("[OB#%d] TP2 hit at %.6f — sold %.6f, total PnL=%.4f USDT",
                                             scanner_id, fill_price, sell_qty, realised_pnl)
                                except Exception as e:
                                    log.error("[OB#%d] TP2 sell failed: %s", scanner_id, e)

                    stop_event.wait(TRADE_POLL)

            except Exception as e:
                log.error("[OB#%d] loop error: %s", scanner_id, e)
                with _lock:
                    if scanner_id in _loops:
                        _loops[scanner_id]["error"] = str(e)
                stop_event.wait(POLL_INTERVAL)

    finally:
        update_ob_scanner_status(scanner_id, "stopped")
        set_ob_should_run(scanner_id, False)
        with _lock:
            _loops.pop(scanner_id, None)
        log.info("[OB#%d] loop stopped", scanner_id)


# ---------------------------------------------------------------------------
# Public control API
# ---------------------------------------------------------------------------

def start_ob_scanner(scanner_id: int) -> bool:
    """Start the scanner loop for scanner_id. Returns False if already running."""
    with _lock:
        if scanner_id in _loops:
            return False
        stop_event = threading.Event()
        t = threading.Thread(
            target=_ob_loop,
            args=(scanner_id, stop_event),
            daemon=True,
            name=f"ob-scanner-{scanner_id}",
        )
        _loops[scanner_id] = {
            "thread":           t,
            "stop_event":       stop_event,
            "last_conditions":  {},
            "error":            None,
        }
    set_ob_should_run(scanner_id, True)
    update_ob_scanner_status(scanner_id, "scanning")
    t.start()
    return True


def stop_ob_scanner(scanner_id: int) -> bool:
    """Signal the scanner loop to stop. Returns False if not running."""
    with _lock:
        entry = _loops.get(scanner_id)
    if not entry:
        return False
    entry["stop_event"].set()
    set_ob_should_run(scanner_id, False)
    return True


def resume_ob_scanner(scanner_id: int) -> bool:
    """Resume a stopped scanner (same as start)."""
    return start_ob_scanner(scanner_id)


def is_running(scanner_id: int) -> bool:
    with _lock:
        return scanner_id in _loops


def get_ob_scanner_status(scanner_id: int) -> dict:
    with _lock:
        entry = _loops.get(scanner_id)
    row = get_ob_scanner(scanner_id)
    if not row:
        return {"running": False, "error": "not found"}
    return {
        "running":          scanner_id in _loops,
        "status":           row.get("status", "stopped"),
        "symbol":           row.get("symbol"),
        "timeframe":        row.get("timeframe"),
        "entry_usdt":       row.get("entry_usdt"),
        "tp1_pct":          row.get("tp1_pct"),
        "tp2_pct":          row.get("tp2_pct"),
        "entry_price":      row.get("entry_price", 0),
        "base_qty":         row.get("base_qty", 0),
        "tp1_hit":          bool(row.get("tp1_hit", 0)),
        "realised_pnl":     row.get("realised_pnl", 0),
        "conditions":       row.get("conditions", {}),
        "error":            entry["error"] if entry else None,
    }
