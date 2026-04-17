"""
Order Block Scanner — Market-Wide Smart Money Engine.

Two modes:
  1. Single-symbol scanner  (legacy, kept for compatibility)
  2. Market-wide scanner    (one thread scans ALL USDT pairs sequentially)

Market-wide flow:
  - Fetches every active USDT pair from MEXC exchangeInfo.
  - Iterates through them one by one, pulling `limit` candles per symbol.
  - When all 4 OB conditions align on a symbol -> places a $entry_usdt market buy.
  - Manages open positions (TP1 at +tp1_pct%, TP2 at +tp2_pct%) while continuing
    to scan for new entries on other symbols.
  - Multiple concurrent open positions are supported.
  - One full market sweep typically takes 2-5 minutes depending on pair count.

No hard stop-loss — fixed entry amount is the only risk control.
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

POSITION_POLL      = 15   # seconds between TP checks for open positions
INTER_SYMBOL_SLEEP = 0.3  # seconds between symbols (rate-limit guard)
CANDLE_LIMIT       = 60   # candles fetched per symbol

# Registry: scanner_id -> {thread, stop_event, last_symbol, scanned, open_positions, error}
_loops: dict[int, dict] = {}
_lock  = threading.Lock()


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Technical detection helpers  (pure, stateless)
# ---------------------------------------------------------------------------

def _detect_liquidity_sweep(candles: list[dict]) -> tuple[bool, float]:
    if len(candles) < 12:
        return False, 0.0
    lookback  = candles[-12:-1]
    last      = candles[-1]
    swing_low = min(c["low"] for c in lookback)
    swept     = last["low"] < swing_low and last["close"] > swing_low
    return swept, swing_low


def _detect_bos(candles: list[dict], swept_level: float) -> bool:
    if len(candles) < 2:
        return False
    return candles[-1]["close"] > swept_level


def _detect_fresh_ob(candles: list[dict]) -> tuple[bool, float, float]:
    window = candles[-8:-2]
    for c in reversed(window):
        if c["close"] < c["open"]:
            return True, c["high"], c["low"]
    return False, 0.0, 0.0


def _detect_ffg(candles: list[dict]) -> bool:
    if len(candles) < 3:
        return False
    for i in range(2, min(7, len(candles))):
        c0 = candles[-(i + 1)]
        c2 = candles[-(i - 1)]
        if c0["high"] < c2["low"]:
            return True
    return False


def _check_conditions(candles: list[dict]) -> tuple[bool, dict]:
    swept, swept_level   = _detect_liquidity_sweep(candles)
    bos                  = _detect_bos(candles, swept_level) if swept else False
    ob_found, ob_h, ob_l = _detect_fresh_ob(candles)
    ffg                  = _detect_ffg(candles)
    conditions = {
        "liquidity_sweep": swept,
        "swept_level":     round(swept_level, 8),
        "bos_choch":       bos,
        "fresh_ob":        ob_found,
        "ob_high":         round(ob_h, 8),
        "ob_low":          round(ob_l, 8),
        "ffg":             ffg,
    }
    return (swept and bos and ob_found and ffg), conditions


# ---------------------------------------------------------------------------
# Position manager  (side-thread, checks TP for all open positions)
# ---------------------------------------------------------------------------

class _PositionManager:
    def __init__(self, scanner_id: int, client: MEXCClient,
                 tp1_pct: float, tp2_pct: float, stop_event: threading.Event):
        self.scanner_id = scanner_id
        self.client     = client
        self.tp1_pct    = tp1_pct
        self.tp2_pct    = tp2_pct
        self.stop_event = stop_event
        self._positions: dict[str, dict] = {}
        self._lock      = threading.Lock()
        self._realised  = 0.0

    def add(self, symbol: str, entry_price: float, base_qty: float, qty_prec: int) -> None:
        with self._lock:
            self._positions[symbol] = {
                "entry_price": entry_price,
                "base_qty":    base_qty,
                "tp1_hit":     False,
                "qty_prec":    qty_prec,
            }

    def has(self, symbol: str) -> bool:
        with self._lock:
            return symbol in self._positions

    def count(self) -> int:
        with self._lock:
            return len(self._positions)

    def realised_pnl(self) -> float:
        return self._realised

    def run(self) -> None:
        while not self.stop_event.is_set():
            with self._lock:
                symbols = list(self._positions.keys())
            for sym in symbols:
                if self.stop_event.is_set():
                    break
                try:
                    self._check_tp(sym)
                except Exception as e:
                    log.warning("[OB#%d] TP check error %s: %s", self.scanner_id, sym, e)
            self.stop_event.wait(POSITION_POLL)

    def _check_tp(self, symbol: str) -> None:
        with self._lock:
            pos = self._positions.get(symbol)
        if not pos:
            return
        price    = self.client.get_price(symbol)
        entry    = pos["entry_price"]
        qty      = pos["base_qty"]
        tp1_hit  = pos["tp1_hit"]
        qty_prec = pos["qty_prec"]

        if not tp1_hit:
            if price >= entry * (1 + self.tp1_pct / 100):
                sell_qty = round(qty * 0.5, qty_prec)
                if sell_qty > 0:
                    self.client.place_market_sell(symbol, sell_qty, qty_prec)
                    pnl = (price - entry) * sell_qty
                    self._realised += pnl
                    with self._lock:
                        if symbol in self._positions:
                            self._positions[symbol]["base_qty"] -= sell_qty
                            self._positions[symbol]["tp1_hit"]   = True
                    record_ob_trade(self.scanner_id, "SELL", price, sell_qty,
                                    price * sell_qty, pnl=pnl, label=f"TP1:{symbol}")
                    log.info("[OB#%d] TP1 %s @ %.6f pnl=%.4f", self.scanner_id, symbol, price, pnl)
                    self._persist()
        else:
            tp2_trigger = entry * (1 + self.tp1_pct / 100) * (1 + self.tp2_pct / 100)
            if price >= tp2_trigger:
                sell_qty = round(qty, qty_prec)
                if sell_qty > 0:
                    self.client.place_market_sell(symbol, sell_qty, qty_prec)
                    pnl = (price - entry) * sell_qty
                    self._realised += pnl
                    with self._lock:
                        self._positions.pop(symbol, None)
                    record_ob_trade(self.scanner_id, "SELL", price, sell_qty,
                                    price * sell_qty, pnl=pnl, label=f"TP2:{symbol}")
                    log.info("[OB#%d] TP2 %s @ %.6f pnl=%.4f", self.scanner_id, symbol, price, pnl)
                    self._persist()

    def _persist(self) -> None:
        with self._lock:
            positions = dict(self._positions)
        if positions:
            sym = next(iter(positions))
            pos = positions[sym]
            update_ob_position(self.scanner_id, pos["entry_price"],
                               pos["base_qty"], pos["tp1_hit"], self._realised)
        else:
            update_ob_position(self.scanner_id, 0, 0, False, self._realised)


# ---------------------------------------------------------------------------
# Market-wide scanner loop
# ---------------------------------------------------------------------------

def _fetch_all_usdt_symbols(client: MEXCClient) -> list[str]:
    try:
        data = client._get("/api/v3/exchangeInfo")
        return [
            s["symbol"]
            for s in data.get("symbols", [])
            if s["symbol"].endswith("USDT") and s.get("status") == "1"
        ]
    except Exception as e:
        log.error("Failed to fetch symbol list: %s", e)
        return []


def _ob_loop(scanner_id: int, stop_event: threading.Event) -> None:
    log.info("[OB#%d] market-wide loop started", scanner_id)
    client = MEXCClient()

    try:
        row = get_ob_scanner(scanner_id)
        if not row:
            log.error("[OB#%d] scanner not found in DB", scanner_id)
            return

        timeframe  = row.get("timeframe", "15m")
        entry_usdt = float(row.get("entry_usdt", 15.0))
        tp1_pct    = float(row.get("tp1_pct", 5.0))
        tp2_pct    = float(row.get("tp2_pct", 5.0))

        pm = _PositionManager(scanner_id, client, tp1_pct, tp2_pct, stop_event)

        # Restore open position from DB if server restarted mid-trade
        if float(row.get("entry_price", 0)) > 0 and float(row.get("base_qty", 0)) > 0:
            sym      = row["symbol"]
            qty_prec = client.get_lot_size_precision(sym)
            pm.add(sym, float(row["entry_price"]), float(row["base_qty"]), qty_prec)
            log.info("[OB#%d] restored open position: %s", scanner_id, sym)

        pm_thread = threading.Thread(target=pm.run, daemon=True,
                                     name=f"ob-pm-{scanner_id}")
        pm_thread.start()

        update_ob_scanner_status(scanner_id, "scanning")
        sweep_count = 0

        while not stop_event.is_set():
            symbols = _fetch_all_usdt_symbols(client)
            if not symbols:
                stop_event.wait(60)
                continue

            sweep_count += 1
            log.info("[OB#%d] sweep #%d — %d symbols | positions: %d",
                     scanner_id, sweep_count, len(symbols), pm.count())

            update_ob_scanner_status(
                scanner_id,
                "in_position" if pm.count() > 0 else "scanning",
            )

            scanned = 0
            for symbol in symbols:
                if stop_event.is_set():
                    break
                if pm.has(symbol):
                    continue
                try:
                    candles = client.get_klines(symbol, timeframe, limit=CANDLE_LIMIT)
                    if len(candles) < 15:
                        continue
                    all_pass, conditions = _check_conditions(candles)
                    scanned += 1

                    with _lock:
                        if scanner_id in _loops:
                            _loops[scanner_id]["last_conditions"] = conditions
                            _loops[scanner_id]["last_symbol"]     = symbol
                            _loops[scanner_id]["scanned"]         = scanned
                            _loops[scanner_id]["open_positions"]  = pm.count()

                    if all_pass:
                        log.info("[OB#%d] SIGNAL %s — entering $%.2f",
                                 scanner_id, symbol, entry_usdt)
                        try:
                            order       = client.place_market_buy(symbol, entry_usdt)
                            filled_qty  = float(order.get("executedQty", 0))
                            filled_usdt = float(order.get("cummulativeQuoteQty", entry_usdt))
                            entry_price = (filled_usdt / filled_qty
                                           if filled_qty > 0
                                           else client.get_price(symbol))
                            qty_prec    = client.get_lot_size_precision(symbol)
                            pm.add(symbol, entry_price, filled_qty, qty_prec)
                            update_ob_position(scanner_id, entry_price, filled_qty,
                                               False, pm.realised_pnl(), conditions)
                            update_ob_scanner_status(scanner_id, "in_position")
                            record_ob_trade(scanner_id, "BUY", entry_price, filled_qty,
                                            filled_usdt, label=f"entry:{symbol}")
                            log.info("[OB#%d] Entered %s @ %.6f qty=%.6f",
                                     scanner_id, symbol, entry_price, filled_qty)
                        except Exception as e:
                            log.error("[OB#%d] Entry failed %s: %s", scanner_id, symbol, e)

                    stop_event.wait(INTER_SYMBOL_SLEEP)

                except Exception as e:
                    log.debug("[OB#%d] skip %s: %s", scanner_id, symbol, e)

            log.info("[OB#%d] sweep #%d done — scanned=%d positions=%d pnl=%.4f",
                     scanner_id, sweep_count, scanned, pm.count(), pm.realised_pnl())
            pm._persist()
            stop_event.wait(5)

    except Exception as e:
        log.error("[OB#%d] loop crashed: %s", scanner_id, e)
        with _lock:
            if scanner_id in _loops:
                _loops[scanner_id]["error"] = str(e)
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
    with _lock:
        if scanner_id in _loops:
            return False
        stop_event = threading.Event()
        t = threading.Thread(target=_ob_loop, args=(scanner_id, stop_event),
                             daemon=True, name=f"ob-scanner-{scanner_id}")
        _loops[scanner_id] = {
            "thread":          t,
            "stop_event":      stop_event,
            "last_conditions": {},
            "last_symbol":     "",
            "scanned":         0,
            "open_positions":  0,
            "error":           None,
        }
    set_ob_should_run(scanner_id, True)
    update_ob_scanner_status(scanner_id, "scanning")
    t.start()
    return True


def stop_ob_scanner(scanner_id: int) -> bool:
    with _lock:
        entry = _loops.get(scanner_id)
    if not entry:
        return False
    entry["stop_event"].set()
    set_ob_should_run(scanner_id, False)
    return True


def resume_ob_scanner(scanner_id: int) -> bool:
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
        "running":        scanner_id in _loops,
        "status":         row.get("status", "stopped"),
        "symbol":         row.get("symbol", "MARKET"),
        "timeframe":      row.get("timeframe"),
        "entry_usdt":     row.get("entry_usdt"),
        "tp1_pct":        row.get("tp1_pct"),
        "tp2_pct":        row.get("tp2_pct"),
        "entry_price":    row.get("entry_price", 0),
        "base_qty":       row.get("base_qty", 0),
        "tp1_hit":        bool(row.get("tp1_hit", 0)),
        "realised_pnl":   row.get("realised_pnl", 0),
        "conditions":     row.get("conditions", {}),
        "last_symbol":    entry["last_symbol"]    if entry else "",
        "scanned":        entry["scanned"]        if entry else 0,
        "open_positions": entry["open_positions"] if entry else 0,
        "error":          entry["error"]          if entry else None,
    }
