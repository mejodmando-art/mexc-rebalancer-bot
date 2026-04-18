"""
Supertrend + EMA + RSI + Volume Scanner — 5-minute scalping engine.

Entry conditions (all must pass):
  1. Supertrend flips Bullish  (price crosses above the Supertrend line)
  2. EMA 20 is rising          (current EMA20 > EMA20 three bars ago)
  3. RSI(14) between 50–70     (momentum positive, not overbought)
  4. Last candle closes above EMA 20
  5. Last candle volume > 1.5× average of prior 20 candles

Exit (software-managed, no SL orders — MEXC Spot doesn't support them):
  TP1: +1.0%  → sell 50%
  TP2: +1.5%  → sell 30%
  TP3: +2.5%  → sell 20%

No hard stop-loss. Risk is capped by the fixed $entry_usdt per trade.
"""

import logging
import threading
import time
from datetime import datetime
from typing import Optional

from mexc_client import MEXCClient
from database import (
    get_supertrend_scanner,
    update_supertrend_scanner_status,
    update_supertrend_position,
    record_supertrend_trade,
    set_supertrend_should_run,
)

log = logging.getLogger(__name__)

SCAN_INTERVAL   = 300   # seconds between full market sweeps (5 min = one 5m candle)
INTER_SYMBOL    = 0.35  # rate-limit guard between symbols
CANDLE_LIMIT    = 120   # candles per symbol (enough for all indicators)
POSITION_POLL   = 15    # seconds between TP checks
MAX_HOLD_HOURS  = 4     # force-close position after 4 hours (no-SL guard)
MAX_SYMBOLS     = 300   # only scan top-300 USDT pairs by 24h volume

# Supertrend parameters
ST_PERIOD    = 10
ST_MULTIPLIER = 3.0

# Registry: scanner_id -> {thread, stop_event, last_symbol, scanned, open_positions, error}
_loops: dict[int, dict] = {}
_lock  = threading.Lock()


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Indicator calculations (pure, stateless)
# ---------------------------------------------------------------------------

def _ema(values: list[float], period: int) -> list[float]:
    """Exponential Moving Average."""
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    result = [sum(values[:period]) / period]
    for v in values[period:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def _rsi(closes: list[float], period: int = 14) -> float:
    """RSI of the last candle."""
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [d if d > 0 else 0.0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0.0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _atr(candles: list[dict], period: int) -> list[float]:
    """Average True Range."""
    trs = []
    for i in range(1, len(candles)):
        high  = candles[i]["high"]
        low   = candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if len(trs) < period:
        return []
    atrs = [sum(trs[:period]) / period]
    for tr in trs[period:]:
        atrs.append((atrs[-1] * (period - 1) + tr) / period)
    return atrs


def _supertrend(candles: list[dict], period: int = ST_PERIOD,
                multiplier: float = ST_MULTIPLIER) -> tuple[list[float], list[bool]]:
    """
    Compute Supertrend line and direction for each candle.

    Returns (st_values, is_bullish) aligned to candles[period:].
    is_bullish[i] = True means price is above the Supertrend line (bullish).
    """
    atrs = _atr(candles, period)
    if not atrs:
        return [], []

    # Align: atrs[0] corresponds to candles[period]
    offset = period
    n = len(atrs)

    hl2 = [(candles[offset + i]["high"] + candles[offset + i]["low"]) / 2
           for i in range(n)]

    upper_band = [hl2[i] + multiplier * atrs[i] for i in range(n)]
    lower_band = [hl2[i] - multiplier * atrs[i] for i in range(n)]

    st      = [0.0] * n
    bullish = [True] * n

    # Initialise first value
    st[0]      = lower_band[0]
    bullish[0] = candles[offset]["close"] >= st[0]

    for i in range(1, n):
        close = candles[offset + i]["close"]
        prev_close = candles[offset + i - 1]["close"]

        # Final upper/lower bands with carry-forward logic
        final_upper = (upper_band[i]
                       if upper_band[i] < st[i - 1] or prev_close > st[i - 1]
                       else st[i - 1])
        final_lower = (lower_band[i]
                       if lower_band[i] > st[i - 1] or prev_close < st[i - 1]
                       else st[i - 1])

        if not bullish[i - 1]:
            st[i]      = final_upper
            bullish[i] = close > final_upper
        else:
            st[i]      = final_lower
            bullish[i] = close >= final_lower

    return st, bullish


def detect_supertrend_signal(candles: list[dict]) -> tuple[bool, dict]:
    """
    Run the full signal pipeline on a candle list.

    Returns (signal_confirmed, details_dict).
    """
    details: dict = {
        "supertrend_bullish":    False,
        "supertrend_flipped":    False,
        "ema20_rising":          False,
        "rsi":                   0.0,
        "rsi_ok":                False,
        "close_above_ema20":     False,
        "volume_ok":             False,
        "supertrend_value":      0.0,
        "ema20_value":           0.0,
    }

    if len(candles) < CANDLE_LIMIT // 2:
        return False, details

    closes  = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]

    # --- Supertrend ---
    st_vals, st_bull = _supertrend(candles)
    if len(st_bull) < 2:
        return False, details

    details["supertrend_bullish"] = st_bull[-1]
    details["supertrend_flipped"] = st_bull[-1] and not st_bull[-2]  # just flipped
    details["supertrend_value"]   = round(st_vals[-1], 8)

    if not st_bull[-1]:
        return False, details

    # --- EMA 20 ---
    ema20 = _ema(closes, 20)
    if len(ema20) < 4:
        return False, details

    details["ema20_value"]    = round(ema20[-1], 8)
    details["ema20_rising"]   = ema20[-1] > ema20[-4]
    details["close_above_ema20"] = closes[-1] > ema20[-1]

    if not details["ema20_rising"]:
        return False, details
    if not details["close_above_ema20"]:
        return False, details

    # --- RSI ---
    rsi_val = _rsi(closes)
    details["rsi"]    = round(rsi_val, 2)
    details["rsi_ok"] = 50.0 <= rsi_val <= 70.0

    if not details["rsi_ok"]:
        return False, details

    # --- Volume ---
    if len(volumes) < 22:
        return False, details
    avg_vol = sum(volumes[-21:-1]) / 20
    details["volume_ok"] = avg_vol > 0 and volumes[-1] >= avg_vol * 1.5

    if not details["volume_ok"]:
        return False, details

    return True, details


# ---------------------------------------------------------------------------
# Position manager — monitors open positions, fires TP market sells
# ---------------------------------------------------------------------------

class _PositionManager:
    def __init__(self, scanner_id: int, client: MEXCClient,
                 tp1_pct: float, tp2_pct: float, tp3_pct: float,
                 stop_event: threading.Event):
        self.scanner_id = scanner_id
        self.client     = client
        self.tp1_pct    = tp1_pct
        self.tp2_pct    = tp2_pct
        self.tp3_pct    = tp3_pct
        self.stop_event = stop_event
        self._positions: dict[str, dict] = {}
        self._lock      = threading.Lock()
        self._realised  = 0.0

    def add(self, symbol: str, entry_price: float,
            base_qty: float, qty_prec: int,
            entry_usdt: float = 0.0) -> None:
        # Use single-exit mode when the entry is too small to split safely.
        # MEXC minimum order is ~$5; splitting $5 into 50%/30%/20% gives
        # $2.5 / $1.5 / $1.0 — all below the minimum and will be rejected.
        # Threshold: entry < $20 → sell 100% at TP1.
        single_exit = entry_usdt > 0 and entry_usdt < 20.0
        with self._lock:
            self._positions[symbol] = {
                "entry_price": entry_price,
                "base_qty":    base_qty,
                "qty_prec":    qty_prec,
                "tp1_hit":     False,
                "tp2_hit":     False,
                "single_exit": single_exit,
                "entry_time":  datetime.utcnow(),
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
                    log.warning("[ST#%d] TP check error %s: %s", self.scanner_id, sym, e)
            self.stop_event.wait(POSITION_POLL)

    def _check_tp(self, symbol: str) -> None:
        with self._lock:
            pos = self._positions.get(symbol)
        if not pos:
            return

        # ── Max hold time guard (no-SL fallback) ─────────────────────────────
        entry_time = pos.get("entry_time")
        if entry_time and (datetime.utcnow() - entry_time).total_seconds() > MAX_HOLD_HOURS * 3600:
            price    = self.client.get_price(symbol)
            sell_qty = round(pos["base_qty"], pos["qty_prec"])
            if sell_qty > 0:
                try:
                    self.client.place_market_sell(symbol, sell_qty, pos["qty_prec"])
                    pnl = (price - pos["entry_price"]) * sell_qty
                    self._realised += pnl
                    with self._lock:
                        self._positions.pop(symbol, None)
                    record_supertrend_trade(self.scanner_id, "SELL", price, sell_qty,
                                            price * sell_qty, pnl=pnl, label=f"MAX_HOLD:{symbol}")
                    log.info("[ST#%d] MAX_HOLD exit %s @ %.6f pnl=%.4f",
                             self.scanner_id, symbol, price, pnl)
                    self._persist()
                except Exception as e:
                    log.error("[ST#%d] MAX_HOLD sell failed %s: %s", self.scanner_id, symbol, e)
            return

        price       = self.client.get_price(symbol)
        entry       = pos["entry_price"]
        qty         = pos["base_qty"]
        qty_prec    = pos["qty_prec"]
        tp1_hit     = pos["tp1_hit"]
        tp2_hit     = pos["tp2_hit"]
        single_exit = pos.get("single_exit", False)

        # ── Single-exit mode (entry < $20) ──────────────────────────────────
        # Sell 100% at TP1 to avoid MEXC minimum-order rejections on splits.
        if single_exit:
            if not tp1_hit and price >= entry * (1 + self.tp1_pct / 100):
                sell_qty = round(qty, qty_prec)
                if sell_qty > 0:
                    try:
                        self.client.place_market_sell(symbol, sell_qty, qty_prec)
                        pnl = (price - entry) * sell_qty
                        self._realised += pnl
                        with self._lock:
                            self._positions.pop(symbol, None)
                        record_supertrend_trade(self.scanner_id, "SELL", price, sell_qty,
                                                price * sell_qty, pnl=pnl, label=f"TP1_full:{symbol}")
                        log.info("[ST#%d] TP1-full %s @ %.6f pnl=%.4f",
                                 self.scanner_id, symbol, price, pnl)
                        self._persist()
                    except Exception as e:
                        log.error("[ST#%d] TP1-full sell failed %s: %s", self.scanner_id, symbol, e)
            return

        # ── Split-exit mode (entry ≥ $20) ───────────────────────────────────

        # TP1: +1% → sell 50%
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
                    record_supertrend_trade(self.scanner_id, "SELL", price, sell_qty,
                                            price * sell_qty, pnl=pnl, label=f"TP1:{symbol}")
                    log.info("[ST#%d] TP1 %s @ %.6f pnl=%.4f", self.scanner_id, symbol, price, pnl)
                    self._persist()
                except Exception as e:
                    log.error("[ST#%d] TP1 sell failed %s: %s", self.scanner_id, symbol, e)
            return

        # TP2: +1.5% from entry → sell 30%
        if tp1_hit and not tp2_hit and price >= entry * (1 + self.tp2_pct / 100):
            sell_qty = round(qty * (0.3 / 0.5), qty_prec)  # 30% of original
            if sell_qty > 0:
                try:
                    self.client.place_market_sell(symbol, sell_qty, qty_prec)
                    pnl = (price - entry) * sell_qty
                    self._realised += pnl
                    with self._lock:
                        if symbol in self._positions:
                            self._positions[symbol]["base_qty"] -= sell_qty
                            self._positions[symbol]["tp2_hit"]   = True
                    record_supertrend_trade(self.scanner_id, "SELL", price, sell_qty,
                                            price * sell_qty, pnl=pnl, label=f"TP2:{symbol}")
                    log.info("[ST#%d] TP2 %s @ %.6f pnl=%.4f", self.scanner_id, symbol, price, pnl)
                    self._persist()
                except Exception as e:
                    log.error("[ST#%d] TP2 sell failed %s: %s", self.scanner_id, symbol, e)
            return

        # TP3: +2.5% from entry → sell remaining 20%
        if tp1_hit and tp2_hit and price >= entry * (1 + self.tp3_pct / 100):
            sell_qty = round(qty, qty_prec)
            if sell_qty > 0:
                try:
                    self.client.place_market_sell(symbol, sell_qty, qty_prec)
                    pnl = (price - entry) * sell_qty
                    self._realised += pnl
                    with self._lock:
                        self._positions.pop(symbol, None)
                    record_supertrend_trade(self.scanner_id, "SELL", price, sell_qty,
                                            price * sell_qty, pnl=pnl, label=f"TP3:{symbol}")
                    log.info("[ST#%d] TP3 %s @ %.6f pnl=%.4f", self.scanner_id, symbol, price, pnl)
                    self._persist()
                except Exception as e:
                    log.error("[ST#%d] TP3 sell failed %s: %s", self.scanner_id, symbol, e)

    def _persist(self) -> None:
        with self._lock:
            positions = dict(self._positions)
        if positions:
            sym = next(iter(positions))
            pos = positions[sym]
            update_supertrend_position(self.scanner_id, pos["entry_price"],
                                       pos["base_qty"], pos["tp1_hit"],
                                       pos["tp2_hit"], self._realised)
        else:
            update_supertrend_position(self.scanner_id, 0, 0, False, False, self._realised)


# ---------------------------------------------------------------------------
# Market-wide scanner loop
# ---------------------------------------------------------------------------

def _fetch_all_usdt_symbols(client: MEXCClient) -> list[str]:
    """Return top MAX_SYMBOLS USDT pairs sorted by 24h quote volume.

    Fetching only high-volume pairs dramatically reduces sweep time
    (300 × 0.35 s ≈ 105 s vs 1500 × 0.35 s ≈ 525 s) and keeps the
    scanner focused on liquid coins where signals are actionable.
    """
    try:
        tickers = client._get("/api/v3/ticker/24hr")
        usdt_pairs = [
            t for t in tickers
            if isinstance(t, dict)
            and t.get("symbol", "").endswith("USDT")
            and float(t.get("quoteVolume", 0)) > 0
        ]
        usdt_pairs.sort(key=lambda t: float(t.get("quoteVolume", 0)), reverse=True)
        symbols = [t["symbol"] for t in usdt_pairs[:MAX_SYMBOLS]]
        log.info("[ST] Scanning top %d USDT pairs by volume (of %d total)",
                 len(symbols), len(usdt_pairs))
        return symbols
    except Exception as e:
        log.error("[ST] Failed to fetch symbol list: %s", e)
        return []


def _st_loop(scanner_id: int, stop_event: threading.Event) -> None:
    log.info("[ST#%d] market-wide loop started", scanner_id)
    client = MEXCClient()

    try:
        row = get_supertrend_scanner(scanner_id)
        if not row:
            log.error("[ST#%d] scanner not found in DB", scanner_id)
            return

        entry_usdt = float(row.get("entry_usdt", 5.0))
        tp1_pct    = float(row.get("tp1_pct",    1.0))
        tp2_pct    = float(row.get("tp2_pct",    1.5))
        tp3_pct    = float(row.get("tp3_pct",    2.5))

        pm = _PositionManager(scanner_id, client, tp1_pct, tp2_pct, tp3_pct, stop_event)

        # Restore open position if server restarted mid-trade
        if float(row.get("entry_price", 0)) > 0 and float(row.get("base_qty", 0)) > 0:
            sym      = row.get("symbol", "")
            qty_prec = client.get_lot_size_precision(sym) if sym else 8
            pm.add(sym, float(row["entry_price"]), float(row["base_qty"]),
                   qty_prec, entry_usdt=entry_usdt)
            log.info("[ST#%d] restored open position: %s", scanner_id, sym)

        pm_thread = threading.Thread(target=pm.run, daemon=True,
                                     name=f"st-pm-{scanner_id}")
        pm_thread.start()

        update_supertrend_scanner_status(scanner_id, "scanning")
        sweep_count = 0

        while not stop_event.is_set():
            symbols = _fetch_all_usdt_symbols(client)
            if not symbols:
                stop_event.wait(60)
                continue

            sweep_count += 1
            log.info("[ST#%d] sweep #%d — %d symbols | positions: %d",
                     scanner_id, sweep_count, len(symbols), pm.count())

            update_supertrend_scanner_status(
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
                    candles = client.get_klines(symbol, "5m", limit=CANDLE_LIMIT)
                    if len(candles) < CANDLE_LIMIT // 2:
                        continue

                    signal, details = detect_supertrend_signal(candles)
                    scanned += 1

                    with _lock:
                        if scanner_id in _loops:
                            _loops[scanner_id]["last_conditions"] = details
                            _loops[scanner_id]["last_symbol"]     = symbol
                            _loops[scanner_id]["scanned"]         = scanned
                            _loops[scanner_id]["open_positions"]  = pm.count()

                    if signal:
                        log.info("[ST#%d] SIGNAL %s — entering $%.2f | rsi=%.1f",
                                 scanner_id, symbol, entry_usdt, details["rsi"])
                        try:
                            order       = client.place_market_buy(symbol, entry_usdt)
                            filled_qty  = float(order.get("executedQty", 0))
                            filled_usdt = float(order.get("cummulativeQuoteQty", entry_usdt))
                            entry_price = (filled_usdt / filled_qty
                                           if filled_qty > 0
                                           else client.get_price(symbol))
                            qty_prec    = client.get_lot_size_precision(symbol)
                            pm.add(symbol, entry_price, filled_qty, qty_prec,
                                   entry_usdt=entry_usdt)
                            update_supertrend_position(
                                scanner_id, entry_price, filled_qty,
                                False, False, pm.realised_pnl(),
                                conditions=details, symbol=symbol,
                            )
                            update_supertrend_scanner_status(scanner_id, "in_position")
                            record_supertrend_trade(
                                scanner_id, "BUY", entry_price, filled_qty,
                                filled_usdt, label=f"entry:{symbol}",
                            )
                            log.info("[ST#%d] Entered %s @ %.6f qty=%.6f",
                                     scanner_id, symbol, entry_price, filled_qty)
                        except Exception as e:
                            log.error("[ST#%d] Entry failed %s: %s", scanner_id, symbol, e)

                    stop_event.wait(INTER_SYMBOL)

                except Exception as e:
                    log.debug("[ST#%d] skip %s: %s", scanner_id, symbol, e)

            log.info("[ST#%d] sweep #%d done — scanned=%d positions=%d pnl=%.4f",
                     scanner_id, sweep_count, scanned, pm.count(), pm.realised_pnl())
            pm._persist()
            stop_event.wait(SCAN_INTERVAL)

    except Exception as e:
        log.error("[ST#%d] loop crashed: %s", scanner_id, e)
        with _lock:
            if scanner_id in _loops:
                _loops[scanner_id]["error"] = str(e)
    finally:
        update_supertrend_scanner_status(scanner_id, "stopped")
        set_supertrend_should_run(scanner_id, False)
        with _lock:
            _loops.pop(scanner_id, None)
        log.info("[ST#%d] loop stopped", scanner_id)


# ---------------------------------------------------------------------------
# Public control API
# ---------------------------------------------------------------------------

def start_supertrend_scanner(scanner_id: int) -> bool:
    with _lock:
        if scanner_id in _loops:
            return False
        stop_event = threading.Event()
        t = threading.Thread(target=_st_loop, args=(scanner_id, stop_event),
                             daemon=True, name=f"st-scanner-{scanner_id}")
        _loops[scanner_id] = {
            "thread":          t,
            "stop_event":      stop_event,
            "last_conditions": {},
            "last_symbol":     "",
            "scanned":         0,
            "open_positions":  0,
            "error":           None,
        }
    set_supertrend_should_run(scanner_id, True)
    update_supertrend_scanner_status(scanner_id, "scanning")
    t.start()
    return True


def stop_supertrend_scanner(scanner_id: int) -> bool:
    with _lock:
        entry = _loops.get(scanner_id)
    if not entry:
        return False
    entry["stop_event"].set()
    set_supertrend_should_run(scanner_id, False)
    return True


def resume_supertrend_scanner(scanner_id: int) -> bool:
    return start_supertrend_scanner(scanner_id)


def is_supertrend_running(scanner_id: int) -> bool:
    with _lock:
        return scanner_id in _loops


def get_supertrend_scanner_status(scanner_id: int) -> dict:
    with _lock:
        entry = _loops.get(scanner_id)
    row = get_supertrend_scanner(scanner_id)
    if not row:
        return {"running": False, "error": "not found"}
    return {
        "running":        scanner_id in _loops,
        "status":         row.get("status", "stopped"),
        "entry_usdt":     row.get("entry_usdt", 5.0),
        "tp1_pct":        row.get("tp1_pct", 1.0),
        "tp2_pct":        row.get("tp2_pct", 1.5),
        "tp3_pct":        row.get("tp3_pct", 2.5),
        "entry_price":    row.get("entry_price", 0),
        "base_qty":       row.get("base_qty", 0),
        "tp1_hit":        bool(row.get("tp1_hit", 0)),
        "tp2_hit":        bool(row.get("tp2_hit", 0)),
        "realised_pnl":   row.get("realised_pnl", 0),
        "conditions":     row.get("conditions", {}),
        "last_symbol":    entry["last_symbol"]    if entry else "",
        "scanned":        entry["scanned"]        if entry else 0,
        "open_positions": entry["open_positions"] if entry else 0,
        "error":          entry["error"]          if entry else None,
    }
