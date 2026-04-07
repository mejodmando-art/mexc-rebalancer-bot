"""
Momentum Breakout Scanner.

Scans USDT spot markets every 10 minutes looking for coins with:
  1. Volume spike — current candle volume > VOLUME_SPIKE_X * 20-candle average
  2. Price breakout — current close > highest close of last BREAKOUT_LOOKBACK candles
  3. Recent move — breakout happened within the last 2 candles (not stale)

Only 2 API calls per symbol: fetch_tickers (shared) + fetch_ohlcv.
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# ── Filters ────────────────────────────────────────────────────────────────────
MIN_VOLUME_24H    = 300_000   # $300K minimum 24h volume — filters illiquid coins
MAX_SPREAD_PCT    = 0.8       # max bid/ask spread %
VOLUME_SPIKE_X    = 3.0       # current volume must be 3x the 20-candle average
BREAKOUT_LOOKBACK = 20        # candles to look back for the breakout level
TIMEFRAME         = "5m"      # 5-minute candles — fast enough for momentum
CANDLES_NEEDED    = 25        # fetch slightly more than lookback for the average


async def get_setups(
    exchange,
    open_symbols: set,
    trade_size_usdt: float = 20.0,
    max_setups: int = 3,
) -> List[Dict[str, Any]]:
    """
    Return up to max_setups momentum breakout opportunities.

    Args:
        exchange:        authenticated ccxt async exchange
        open_symbols:    symbols already in an open trade (skip these)
        trade_size_usdt: USDT per trade (used for min-notional pre-check)
        max_setups:      cap per scan — caller passes user's remaining slots

    Returns:
        List of setup dicts with keys:
          symbol, entry_price, stop_loss, target1, target2, volume_ratio
    """
    # ── Step 1: fetch all USDT tickers in one call ─────────────────────────
    try:
        await exchange.load_markets()
        usdt_symbols = [
            s for s, m in exchange.markets.items()
            if s.endswith("/USDT") and m.get("spot") and m.get("active")
        ]
        tickers = await exchange.fetch_tickers(usdt_symbols)
    except Exception as e:
        logger.error(f"MomentumScanner: fetch_tickers failed: {e}")
        return []

    # ── Step 2: pre-filter by volume and spread ────────────────────────────
    candidates = []
    for sym, t in tickers.items():
        if sym in open_symbols:
            continue
        vol24 = float(t.get("quoteVolume") or 0)
        if vol24 < MIN_VOLUME_24H:
            continue
        bid = float(t.get("bid") or 0)
        ask = float(t.get("ask") or 0)
        if bid <= 0 or ask <= 0:
            continue
        if ((ask - bid) / bid) * 100 > MAX_SPREAD_PCT:
            continue
        last = float(t.get("last") or t.get("close") or 0)
        if last <= 0:
            continue
        # Pre-check: trade size must be viable (avoid micro-cap dust)
        if trade_size_usdt / last < 1e-6:
            continue
        candidates.append((sym, last, vol24))

    # Sort by 24h volume descending — highest liquidity first
    candidates.sort(key=lambda x: x[2], reverse=True)
    # Limit candidates to avoid scanning thousands of symbols
    candidates = candidates[:150]

    logger.info(f"MomentumScanner: {len(candidates)} candidates after pre-filter")

    # ── Step 3: OHLCV check per candidate ─────────────────────────────────
    setups = []
    for sym, last_price, _ in candidates:
        if len(setups) >= max_setups:
            break
        try:
            setup = await _check_symbol(exchange, sym, last_price, trade_size_usdt)
            if setup:
                setups.append(setup)
                logger.info(
                    f"MomentumScanner: setup → {sym} "
                    f"entry={setup['entry_price']:.6g} "
                    f"vol_ratio={setup['volume_ratio']:.1f}x"
                )
        except Exception as e:
            logger.debug(f"MomentumScanner: {sym} error: {e}")
            continue

    logger.info(f"MomentumScanner: done — {len(setups)} setups found")
    return setups


async def _check_symbol(
    exchange, symbol: str, last_price: float, trade_size_usdt: float
) -> Dict[str, Any] | None:
    """
    Fetch OHLCV and check volume spike + price breakout conditions.
    Returns a setup dict or None.
    """
    ohlcv = await exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=CANDLES_NEEDED)
    if not ohlcv or len(ohlcv) < BREAKOUT_LOOKBACK + 2:
        return None

    # ohlcv rows: [timestamp, open, high, low, close, volume]
    closes  = [float(c[4]) for c in ohlcv]
    volumes = [float(c[5]) * float(c[4]) for c in ohlcv]  # volume in USDT

    current_close  = closes[-1]
    current_volume = volumes[-1]

    # Volume spike: current candle vs average of previous 20
    avg_volume = sum(volumes[-CANDLES_NEEDED:-1]) / (CANDLES_NEEDED - 1)
    if avg_volume <= 0:
        return None
    volume_ratio = current_volume / avg_volume
    if volume_ratio < VOLUME_SPIKE_X:
        return None

    # Breakout: current close must exceed the highest close of last N candles
    lookback_closes = closes[-(BREAKOUT_LOOKBACK + 1):-1]
    breakout_level  = max(lookback_closes)
    if current_close <= breakout_level:
        return None

    # Recency: breakout must have happened in the last 2 candles
    prev_close = closes[-2]
    if prev_close > breakout_level:
        return None  # breakout is older than 2 candles — stale

    # ── Risk levels ────────────────────────────────────────────────────────
    # Stop loss: below the lowest low of the last 3 candles, with a small buffer
    recent_lows = [float(c[3]) for c in ohlcv[-3:]]
    swing_low   = min(recent_lows)
    stop_loss   = round(swing_low * 0.995, 8)  # 0.5% below swing low

    risk_pct = (current_close - stop_loss) / current_close
    if risk_pct <= 0 or risk_pct > 0.05:
        # Stop too tight or too wide — skip
        return None

    target1 = round(current_close * 1.02, 8)   # +2%
    target2 = round(current_close * 1.04, 8)   # +4%

    # Minimum R/R of 1.5 — target1 must be at least 1.5x the risk
    reward1 = (target1 - current_close) / current_close
    if reward1 / risk_pct < 1.5:
        return None

    return {
        "symbol":       symbol,
        "entry_price":  round(current_close, 8),
        "stop_loss":    stop_loss,
        "target1":      target1,
        "target2":      target2,
        "volume_ratio": round(volume_ratio, 1),
        "breakout_lvl": round(breakout_level, 8),
    }
