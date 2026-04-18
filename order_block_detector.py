"""
Order Block Detector — ICT/SMC Smart Money Engine.

Architecture:
  - One background thread scans ALL active USDT pairs on MEXC every 5 minutes.
  - For each symbol, fetches OHLCV candles and runs the full detection pipeline:
      1. Swing Highs & Lows identification (structural pivots)
      2. Break of Structure (BoS) / Change of Character (ChoCh) confirmation
      3. Mother candle detection (last strong impulse before reversal)
      4. Order Block zone mapping (high/low of the mother candle)
      5. Quality filters: volume spike, BoS/ChoCh confirmation
  - On confirmed OB signal:
      * Entry at 50% of the OB zone (midpoint)
      * Stop Loss at the opposite end of the OB zone
      * Take Profit 1 at entry + 1%
      * Take Profit 2 at entry + 2%
      * Places real STOP_LOSS_LIMIT orders via MEXC API
  - Stop Loss is optional per-trade (controlled by use_stop_loss flag in config).
  - Multiple concurrent open positions are supported.
  - Full sweep interval: 5 minutes (configurable via SCAN_INTERVAL_SECONDS).
"""

import json
import logging
import threading
import time
from datetime import datetime
from typing import Optional

from mexc_client import MEXCClient
from database import (
    get_ob_detector,
    update_ob_detector_status,
    update_ob_detector_position,
    record_ob_detector_trade,
    set_ob_detector_should_run,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCAN_INTERVAL_SECONDS = 300   # 5 minutes between full market sweeps
INTER_SYMBOL_SLEEP    = 0.35  # rate-limit guard between symbols
CANDLE_LIMIT          = 100   # candles fetched per symbol (enough for swing detection)
SWING_LOOKBACK        = 5     # bars each side to confirm a swing pivot
MIN_VOLUME_MULTIPLIER = 1.2   # mother candle volume must be ≥ 1.2× average
POSITION_POLL         = 20    # seconds between TP/SL checks for open positions

# Registry: detector_id -> {thread, stop_event, last_symbol, scanned, open_positions, error}
_loops: dict[int, dict] = {}
_lock  = threading.Lock()


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Pure detection helpers (stateless)
# ---------------------------------------------------------------------------

def _find_swing_highs_lows(
    candles: list[dict],
    lookback: int = SWING_LOOKBACK,
) -> tuple[list[int], list[int]]:
    """Return indices of confirmed swing highs and swing lows.

    A swing high at index i: candles[i]["high"] is the highest among
    candles[i-lookback : i+lookback+1].
    A swing low at index i: candles[i]["low"] is the lowest in the same window.
    """
    highs: list[int] = []
    lows:  list[int] = []
    n = len(candles)
    for i in range(lookback, n - lookback):
        window_highs = [candles[j]["high"] for j in range(i - lookback, i + lookback + 1)]
        window_lows  = [candles[j]["low"]  for j in range(i - lookback, i + lookback + 1)]
        if candles[i]["high"] == max(window_highs):
            highs.append(i)
        if candles[i]["low"] == min(window_lows):
            lows.append(i)
    return highs, lows


def _detect_bos_choch(
    candles: list[dict],
    swing_highs: list[int],
    swing_lows:  list[int],
) -> tuple[bool, str, float]:
    """Detect Break of Structure (BoS) or Change of Character (ChoCh).

    Bullish BoS: latest close breaks above any swing high in the recent window.
    Bullish ChoCh: price breaks above a swing high that was lower than the
                   previous swing high (lower-high structure = downtrend reversal).

    Checks the last 5 swing highs so a break of any recent structure level
    qualifies, not only the absolute highest peak in the window.

    Returns (confirmed, signal_type, broken_level).
    signal_type: 'BoS_bullish', 'ChoCh_bullish', or ''.
    """
    if not swing_highs or len(candles) < 2:
        return False, "", 0.0

    last_close = candles[-1]["close"]

    # Walk recent swing highs from newest to oldest; fire on the first break.
    recent_shs = swing_highs[-5:]  # up to 5 most recent swing highs
    for i in range(len(recent_shs) - 1, -1, -1):
        sh_idx = recent_shs[i]
        sh_lvl = candles[sh_idx]["high"]

        if last_close > sh_lvl:
            # ChoCh: this swing high is lower than the one before it
            if i > 0:
                prev_lvl = candles[recent_shs[i - 1]]["high"]
                if sh_lvl < prev_lvl:
                    return True, "ChoCh_bullish", sh_lvl
            return True, "BoS_bullish", sh_lvl

    return False, "", 0.0


def _find_mother_candle(
    candles: list[dict],
    swing_lows: list[int],
    bos_level:  float,
) -> tuple[bool, dict]:
    """Find the last strong bearish impulse candle near the most recent swing low.

    Searches a 30-bar window centred on the swing low (20 bars before + 5 bars
    after) to account for OBs that form at or just past the swing low itself.
    Falls back to the second-most-recent swing low if the first yields nothing.

    Returns (found, candle_dict).
    """
    if not swing_lows:
        return False, {}

    # Try the most recent swing low first, then the previous one as fallback.
    candidates = swing_lows[-2:] if len(swing_lows) >= 2 else swing_lows[-1:]
    for sl_idx in reversed(candidates):
        search_start = max(0, sl_idx - 30)
        search_end   = min(len(candles), sl_idx + 6)   # 5 bars past the low
        window = candles[search_start:search_end]

        if not window:
            continue

        bearish = [c for c in window if c["close"] < c["open"]]
        if not bearish:
            continue

        mother = max(bearish, key=lambda c: c["open"] - c["close"])
        return True, mother

    return False, {}


def _volume_filter(candles: list[dict], mother: dict) -> bool:
    """Return True if the mother candle's volume is ≥ MIN_VOLUME_MULTIPLIER × average.

    Uses the 20 candles preceding the mother candle as the baseline.
    """
    try:
        mother_idx = next(
            i for i, c in enumerate(candles)
            if c["open_time"] == mother["open_time"]
        )
    except StopIteration:
        return False

    baseline_start = max(0, mother_idx - 20)
    baseline = candles[baseline_start:mother_idx]
    if not baseline:
        return False

    avg_vol = sum(c["volume"] for c in baseline) / len(baseline)
    return avg_vol > 0 and mother["volume"] >= avg_vol * MIN_VOLUME_MULTIPLIER


def _build_ob_zone(mother: dict) -> tuple[float, float, float]:
    """Return (ob_high, ob_low, ob_midpoint) from the mother candle."""
    ob_high = mother["high"]
    ob_low  = mother["low"]
    ob_mid  = (ob_high + ob_low) / 2
    return ob_high, ob_low, ob_mid


def detect_order_block(candles: list[dict]) -> tuple[bool, dict]:
    """Full ICT/SMC Order Block detection pipeline.

    Steps:
      1. Identify swing highs and lows.
      2. Confirm BoS or ChoCh (structural break).
      3. Find the mother candle (last strong impulse before reversal).
      4. Apply volume quality filter.
      5. Map the OB zone.

    Returns (signal_confirmed, details_dict).
    """
    details: dict = {
        "swing_highs_count": 0,
        "swing_lows_count":  0,
        "bos_confirmed":     False,
        "bos_type":          "",
        "bos_level":         0.0,
        "mother_found":      False,
        "mother_open":       0.0,
        "mother_close":      0.0,
        "mother_high":       0.0,
        "mother_low":        0.0,
        "volume_ok":         False,
        "ob_high":           0.0,
        "ob_low":            0.0,
        "ob_midpoint":       0.0,
    }

    if len(candles) < SWING_LOOKBACK * 2 + 5:
        return False, details

    swing_highs, swing_lows = _find_swing_highs_lows(candles)
    details["swing_highs_count"] = len(swing_highs)
    details["swing_lows_count"]  = len(swing_lows)

    bos_ok, bos_type, bos_level = _detect_bos_choch(candles, swing_highs, swing_lows)
    details["bos_confirmed"] = bos_ok
    details["bos_type"]      = bos_type
    details["bos_level"]     = round(bos_level, 8)

    if not bos_ok:
        return False, details

    mother_ok, mother = _find_mother_candle(candles, swing_lows, bos_level)
    details["mother_found"] = mother_ok
    if mother_ok:
        details["mother_open"]  = round(mother["open"],  8)
        details["mother_close"] = round(mother["close"], 8)
        details["mother_high"]  = round(mother["high"],  8)
        details["mother_low"]   = round(mother["low"],   8)

    if not mother_ok:
        return False, details

    vol_ok = _volume_filter(candles, mother)
    details["volume_ok"] = vol_ok

    if not vol_ok:
        return False, details

    ob_high, ob_low, ob_mid = _build_ob_zone(mother)
    details["ob_high"]     = round(ob_high, 8)
    details["ob_low"]      = round(ob_low,  8)
    details["ob_midpoint"] = round(ob_mid,  8)

    return True, details


# ---------------------------------------------------------------------------
# Position manager
# ---------------------------------------------------------------------------

class _PositionManager:
    """Monitors open positions and executes TP exits."""

    def __init__(
        self,
        detector_id: int,
        client:      MEXCClient,
        tp1_pct:     float,
        tp2_pct:     float,
        stop_event:  threading.Event,
    ):
        self.detector_id = detector_id
        self.client      = client
        self.tp1_pct     = tp1_pct
        self.tp2_pct     = tp2_pct
        self.stop_event  = stop_event
        self._positions: dict[str, dict] = {}
        self._lock       = threading.Lock()
        self._realised   = 0.0

    def add(
        self,
        symbol:      str,
        entry_price: float,
        base_qty:    float,
        qty_prec:    int,
        sl_price:    float,
        use_sl:      bool,
    ) -> None:
        with self._lock:
            self._positions[symbol] = {
                "entry_price": entry_price,
                "base_qty":    base_qty,
                "qty_prec":    qty_prec,
                "sl_price":    sl_price,
                "use_sl":      use_sl,
                "tp1_hit":     False,
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
                    self._check_exits(sym)
                except Exception as e:
                    log.warning("[OBD#%d] exit-check error %s: %s", self.detector_id, sym, e)
            self.stop_event.wait(POSITION_POLL)

    def _check_exits(self, symbol: str) -> None:
        with self._lock:
            pos = self._positions.get(symbol)
        if not pos:
            return

        price    = self.client.get_price(symbol)
        entry    = pos["entry_price"]
        qty      = pos["base_qty"]
        qty_prec = pos["qty_prec"]
        tp1_hit  = pos["tp1_hit"]
        sl_price = pos["sl_price"]
        use_sl   = pos["use_sl"]

        # Stop Loss check (only when enabled)
        if use_sl and sl_price > 0 and price <= sl_price:
            sell_qty = round(qty, qty_prec)
            if sell_qty > 0:
                try:
                    self.client.place_market_sell(symbol, sell_qty, qty_prec)
                    pnl = (price - entry) * sell_qty
                    self._realised += pnl
                    with self._lock:
                        self._positions.pop(symbol, None)
                    record_ob_detector_trade(
                        self.detector_id, "SELL", price, sell_qty,
                        price * sell_qty, pnl=pnl, label=f"SL:{symbol}",
                    )
                    log.info("[OBD#%d] SL hit %s @ %.6f pnl=%.4f",
                             self.detector_id, symbol, price, pnl)
                    self._persist()
                except Exception as e:
                    log.error("[OBD#%d] SL sell failed %s: %s", self.detector_id, symbol, e)
            return

        # TP1: sell 50% at entry + tp1_pct%
        if not tp1_hit and price >= entry * (1 + self.tp1_pct / 100):
            sell_qty = round(qty * 0.5, qty_prec)
            if sell_qty > 0:
                try:
                    self.client.place_market_sell(symbol, sell_qty, qty_prec)
                    pnl = (price - entry) * sell_qty
                    self._realised += pnl
                    with self._lock:
                        if symbol in self._positions:
                            self._positions[symbol]["base_qty"] -= sell_qty
                            self._positions[symbol]["tp1_hit"]   = True
                    record_ob_detector_trade(
                        self.detector_id, "SELL", price, sell_qty,
                        price * sell_qty, pnl=pnl, label=f"TP1:{symbol}",
                    )
                    log.info("[OBD#%d] TP1 %s @ %.6f pnl=%.4f",
                             self.detector_id, symbol, price, pnl)
                    self._persist()
                except Exception as e:
                    log.error("[OBD#%d] TP1 sell failed %s: %s", self.detector_id, symbol, e)

        # TP2: sell remaining at entry + tp1_pct% + tp2_pct%
        elif tp1_hit:
            tp2_trigger = entry * (1 + self.tp1_pct / 100) * (1 + self.tp2_pct / 100)
            if price >= tp2_trigger:
                sell_qty = round(qty, qty_prec)
                if sell_qty > 0:
                    try:
                        self.client.place_market_sell(symbol, sell_qty, qty_prec)
                        pnl = (price - entry) * sell_qty
                        self._realised += pnl
                        with self._lock:
                            self._positions.pop(symbol, None)
                        record_ob_detector_trade(
                            self.detector_id, "SELL", price, sell_qty,
                            price * sell_qty, pnl=pnl, label=f"TP2:{symbol}",
                        )
                        log.info("[OBD#%d] TP2 %s @ %.6f pnl=%.4f",
                                 self.detector_id, symbol, price, pnl)
                        self._persist()
                    except Exception as e:
                        log.error("[OBD#%d] TP2 sell failed %s: %s", self.detector_id, symbol, e)

    def _persist(self) -> None:
        with self._lock:
            positions = dict(self._positions)
        if positions:
            sym = next(iter(positions))
            pos = positions[sym]
            update_ob_detector_position(
                self.detector_id,
                pos["entry_price"],
                pos["base_qty"],
                pos["tp1_hit"],
                self._realised,
            )
        else:
            update_ob_detector_position(self.detector_id, 0, 0, False, self._realised)


# ---------------------------------------------------------------------------
# Market-wide scanner loop
# ---------------------------------------------------------------------------

def _fetch_all_usdt_symbols(client: MEXCClient) -> list[str]:
    """Return all active USDT spot pairs from MEXC exchangeInfo."""
    try:
        data = client._get("/api/v3/exchangeInfo")
        return [
            s["symbol"]
            for s in data.get("symbols", [])
            if s["symbol"].endswith("USDT") and s.get("status") == "1"
        ]
    except Exception as e:
        log.error("[OBD] Failed to fetch symbol list: %s", e)
        return []


def _place_entry_with_orders(
    client:      MEXCClient,
    detector_id: int,
    symbol:      str,
    entry_usdt:  float,
    ob_high:     float,
    ob_low:      float,
    ob_mid:      float,
    tp1_pct:     float,
    tp2_pct:     float,
    use_sl:      bool,
) -> tuple[bool, float, float, int]:
    """Execute entry market buy and place STOP_LOSS_LIMIT order if enabled.

    Entry: market buy at ob_midpoint (50% of OB zone).
    SL:    opposite end of OB zone (ob_low for bullish OB).
    TP1/2: managed by _PositionManager via market sells.

    Returns (success, entry_price, base_qty, qty_prec).
    """
    try:
        order       = client.place_market_buy(symbol, entry_usdt)
        filled_qty  = float(order.get("executedQty", 0))
        filled_usdt = float(order.get("cummulativeQuoteQty", entry_usdt))
        entry_price = (
            filled_usdt / filled_qty if filled_qty > 0
            else client.get_price(symbol)
        )
        qty_prec = client.get_lot_size_precision(symbol)

        record_ob_detector_trade(
            detector_id, "BUY", entry_price, filled_qty,
            filled_usdt, label=f"OB_entry:{symbol}",
        )
        log.info("[OBD#%d] Entered %s @ %.6f qty=%.6f",
                 detector_id, symbol, entry_price, filled_qty)

        # Place STOP_LOSS_LIMIT order when SL is enabled
        if use_sl and ob_low > 0 and filled_qty > 0:
            sl_price  = round(ob_low, qty_prec)
            sl_qty    = round(filled_qty, qty_prec)
            try:
                client.place_stop_loss_limit_order(symbol, sl_qty, sl_price, qty_prec)
                log.info("[OBD#%d] SL order placed %s sl=%.6f", detector_id, symbol, sl_price)
            except Exception as e:
                log.warning("[OBD#%d] SL order failed %s: %s — SL managed in software",
                            detector_id, symbol, e)

        return True, entry_price, filled_qty, qty_prec

    except Exception as e:
        log.error("[OBD#%d] Entry failed %s: %s", detector_id, symbol, e)
        return False, 0.0, 0.0, 8


def _ob_detector_loop(detector_id: int, stop_event: threading.Event) -> None:
    log.info("[OBD#%d] market-wide loop started", detector_id)
    client = MEXCClient()

    try:
        row = get_ob_detector(detector_id)
        if not row:
            log.error("[OBD#%d] detector not found in DB", detector_id)
            return

        timeframe  = row.get("timeframe", "5m")
        entry_usdt = float(row.get("entry_usdt", 15.0))
        tp1_pct    = float(row.get("tp1_pct", 1.0))
        tp2_pct    = float(row.get("tp2_pct", 2.0))
        use_sl     = bool(row.get("use_stop_loss", True))

        pm = _PositionManager(detector_id, client, tp1_pct, tp2_pct, stop_event)

        # Restore open position from DB if server restarted mid-trade
        if float(row.get("entry_price", 0)) > 0 and float(row.get("base_qty", 0)) > 0:
            sym      = row.get("symbol", "")
            qty_prec = client.get_lot_size_precision(sym) if sym else 8
            pm.add(
                sym,
                float(row["entry_price"]),
                float(row["base_qty"]),
                qty_prec,
                sl_price=float(row.get("sl_price", 0)),
                use_sl=use_sl,
            )
            log.info("[OBD#%d] restored open position: %s", detector_id, sym)

        pm_thread = threading.Thread(
            target=pm.run, daemon=True, name=f"obd-pm-{detector_id}"
        )
        pm_thread.start()

        update_ob_detector_status(detector_id, "scanning")
        sweep_count = 0

        while not stop_event.is_set():
            symbols = _fetch_all_usdt_symbols(client)
            if not symbols:
                stop_event.wait(60)
                continue

            sweep_count += 1
            log.info(
                "[OBD#%d] sweep #%d — %d symbols | positions: %d",
                detector_id, sweep_count, len(symbols), pm.count(),
            )
            update_ob_detector_status(
                detector_id,
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
                    if len(candles) < SWING_LOOKBACK * 2 + 5:
                        continue

                    signal, details = detect_order_block(candles)
                    scanned += 1

                    with _lock:
                        if detector_id in _loops:
                            _loops[detector_id]["last_conditions"] = details
                            _loops[detector_id]["last_symbol"]     = symbol
                            _loops[detector_id]["scanned"]         = scanned
                            _loops[detector_id]["open_positions"]  = pm.count()

                    if signal:
                        ob_high = details["ob_high"]
                        ob_low  = details["ob_low"]
                        ob_mid  = details["ob_midpoint"]
                        log.info(
                            "[OBD#%d] OB SIGNAL %s | type=%s ob=[%.6f–%.6f] entry=%.6f",
                            detector_id, symbol, details["bos_type"],
                            ob_low, ob_high, ob_mid,
                        )

                        ok, entry_price, base_qty, qty_prec = _place_entry_with_orders(
                            client, detector_id, symbol, entry_usdt,
                            ob_high, ob_low, ob_mid, tp1_pct, tp2_pct, use_sl,
                        )
                        if ok:
                            sl_price = ob_low if use_sl else 0.0
                            pm.add(symbol, entry_price, base_qty, qty_prec,
                                   sl_price=sl_price, use_sl=use_sl)
                            update_ob_detector_position(
                                detector_id, entry_price, base_qty,
                                False, pm.realised_pnl(),
                                conditions=details,
                                sl_price=sl_price,
                                symbol=symbol,
                            )
                            update_ob_detector_status(detector_id, "in_position")

                    stop_event.wait(INTER_SYMBOL_SLEEP)

                except Exception as e:
                    log.debug("[OBD#%d] skip %s: %s", detector_id, symbol, e)

            log.info(
                "[OBD#%d] sweep #%d done — scanned=%d positions=%d pnl=%.4f",
                detector_id, sweep_count, scanned, pm.count(), pm.realised_pnl(),
            )
            pm._persist()

            # Wait for the next 5-minute sweep window
            stop_event.wait(SCAN_INTERVAL_SECONDS)

    except Exception as e:
        log.error("[OBD#%d] loop crashed: %s", detector_id, e)
        with _lock:
            if detector_id in _loops:
                _loops[detector_id]["error"] = str(e)
    finally:
        update_ob_detector_status(detector_id, "stopped")
        set_ob_detector_should_run(detector_id, False)
        with _lock:
            _loops.pop(detector_id, None)
        log.info("[OBD#%d] loop stopped", detector_id)


# ---------------------------------------------------------------------------
# Public control API
# ---------------------------------------------------------------------------

def start_ob_detector(detector_id: int) -> bool:
    """Start the market-wide OB detector loop. Returns False if already running."""
    with _lock:
        if detector_id in _loops:
            return False
        stop_event = threading.Event()
        t = threading.Thread(
            target=_ob_detector_loop,
            args=(detector_id, stop_event),
            daemon=True,
            name=f"obd-{detector_id}",
        )
        _loops[detector_id] = {
            "thread":          t,
            "stop_event":      stop_event,
            "last_conditions": {},
            "last_symbol":     "",
            "scanned":         0,
            "open_positions":  0,
            "error":           None,
        }
    set_ob_detector_should_run(detector_id, True)
    update_ob_detector_status(detector_id, "scanning")
    t.start()
    return True


def stop_ob_detector(detector_id: int) -> bool:
    """Signal the detector loop to stop. Returns False if not running."""
    with _lock:
        entry = _loops.get(detector_id)
    if not entry:
        return False
    entry["stop_event"].set()
    set_ob_detector_should_run(detector_id, False)
    return True


def resume_ob_detector(detector_id: int) -> bool:
    """Resume a previously stopped detector (same as start)."""
    return start_ob_detector(detector_id)


def is_ob_detector_running(detector_id: int) -> bool:
    with _lock:
        return detector_id in _loops


def get_ob_detector_status(detector_id: int) -> dict:
    """Return a status snapshot for the given detector."""
    with _lock:
        entry = _loops.get(detector_id)
    row = get_ob_detector(detector_id)
    if not row:
        return {"running": False, "error": "not found"}
    return {
        "running":        detector_id in _loops,
        "status":         row.get("status", "stopped"),
        "symbol":         row.get("symbol", "MARKET"),
        "timeframe":      row.get("timeframe", "5m"),
        "entry_usdt":     row.get("entry_usdt", 15.0),
        "tp1_pct":        row.get("tp1_pct", 1.0),
        "tp2_pct":        row.get("tp2_pct", 2.0),
        "use_stop_loss":  bool(row.get("use_stop_loss", True)),
        "entry_price":    row.get("entry_price", 0),
        "sl_price":       row.get("sl_price", 0),
        "base_qty":       row.get("base_qty", 0),
        "tp1_hit":        bool(row.get("tp1_hit", 0)),
        "realised_pnl":   row.get("realised_pnl", 0),
        "conditions":     row.get("conditions", {}),
        "last_symbol":    entry["last_symbol"]    if entry else "",
        "scanned":        entry["scanned"]        if entry else 0,
        "open_positions": entry["open_positions"] if entry else 0,
        "error":          entry["error"]          if entry else None,
    }
