"""
Whale Order Flow scanner — runs every 5 minutes.

Pipeline (5 conditions, all must pass):

  1. Trusted symbol: only well-known coins with real liquidity.

  2. Volume spike: last 5M candle volume >= 2x the 20-candle average.
     Real whale prints leave a volume footprint.

  3. Fresh FVG: a bullish imbalance formed in the last 10 candles and
     price is currently inside or just above it.

  4. Strong CVD shift: order flow flipped bullish AND the delta is
     >= 3x the baseline delta of the first half. Weak flips are noise.

  5. Breakout candle: last closed 5M candle broke above the highest
     high of the previous 10 candles with a bullish body.

Targets: T1=+0.8%, T2=+1.6%, SL=-0.5%
Average hold: 5–20 minutes.
"""

import logging
from typing import List, Dict, Any

from bot.scalping.imbalance  import get_imbalance
from bot.scalping.orderflow  import get_order_flow
from bot.scalping.whale_risk import calculate_whale_risk

logger = logging.getLogger(__name__)

# Only trade coins with real liquidity and a known track record.
# Meme coins and low-cap tokens are excluded intentionally.
TRUSTED_SYMBOLS = {
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "ADA/USDT", "AVAX/USDT", "DOT/USDT", "MATIC/USDT", "LINK/USDT",
    "LTC/USDT", "UNI/USDT", "ATOM/USDT", "FIL/USDT", "NEAR/USDT",
    "APT/USDT", "ARB/USDT", "OP/USDT",  "INJ/USDT", "SUI/USDT",
    "TRX/USDT", "DOGE/USDT", "TON/USDT", "PEPE/USDT", "WIF/USDT",
    "JUP/USDT", "SEI/USDT", "TIA/USDT", "RENDER/USDT", "FET/USDT",
    "GRT/USDT", "AAVE/USDT", "MKR/USDT", "CRV/USDT", "LDO/USDT",
    "RUNE/USDT", "ALGO/USDT", "VET/USDT", "HBAR/USDT", "ICP/USDT",
}

MIN_VOLUME_24H    = 1_000_000   # $1M minimum 24h volume — real liquidity only
MAX_SPREAD_PCT    = 0.3         # 0.3% max spread
VOLUME_SPIKE_MULT = 2.0         # last candle volume must be >= 2x the 20-candle avg
MAX_SETUPS        = 3           # quality over quantity


async def whale_scan(
    exchange,
    open_symbols: set,
    trade_size_usdt: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    Full whale order flow scan across trusted symbols only.

    Returns list of valid setups (capped at MAX_SETUPS).
    """
    symbols = await _get_valid_symbols(exchange)
    logger.info(f"WhaleScanner: checking {len(symbols)} trusted symbols")

    passed_vol = passed_fvg = passed_flow = passed_break = 0
    setups = []

    for symbol in symbols:
        if len(setups) >= MAX_SETUPS:
            break
        if symbol in open_symbols:
            continue

        try:
            # ── Step 1: Volume spike on last 5M candle ─────────────────────
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe="5m", limit=25)
            if not ohlcv or len(ohlcv) < 22:
                continue

            closed      = ohlcv[:-1]   # exclude forming candle
            last_candle = closed[-1]
            last_volume = float(last_candle[5])
            avg_volume  = sum(float(c[5]) for c in closed[-21:-1]) / 20

            if avg_volume <= 0 or last_volume < avg_volume * VOLUME_SPIKE_MULT:
                logger.debug(
                    f"WhaleScanner: {symbol} — no volume spike "
                    f"({last_volume:.0f} vs avg {avg_volume:.0f})"
                )
                continue
            passed_vol += 1

            # ── Step 2: Fresh FVG (formed in last 10 candles) ──────────────
            imb = await get_imbalance(symbol, exchange)
            if not imb["found"] or imb.get("age", 999) > 10:
                logger.debug(f"WhaleScanner: {symbol} — no fresh FVG")
                continue
            passed_fvg += 1

            # ── Step 3: Strong CVD shift ───────────────────────────────────
            flow = await get_order_flow(symbol, exchange)
            if not flow["shifted"] or not flow["strong"]:
                logger.debug(
                    f"WhaleScanner: {symbol} — CVD shift too weak "
                    f"(delta={flow['delta']:.4f})"
                )
                continue
            passed_flow += 1

            # ── Step 4: Breakout above last 10 candles high ────────────────
            prev_10      = closed[-11:-1]
            last_close   = float(last_candle[4])
            last_open    = float(last_candle[1])
            prev_10_high = max(float(c[2]) for c in prev_10)

            if last_close <= last_open or last_close <= prev_10_high:
                logger.debug(f"WhaleScanner: {symbol} — no breakout above 10-candle high")
                continue
            passed_break += 1

            # ── Risk calculation ───────────────────────────────────────────
            entry_price = last_close
            risk = calculate_whale_risk(entry_price, trade_size_usdt)
            if not risk["valid"]:
                continue

            setups.append({
                "symbol":      symbol,
                "side":        "buy",
                "entry_price": entry_price,
                "stop_loss":   risk["stop_loss"],
                "target1":     risk["target1"],
                "target2":     risk["target2"],
                "qty":         risk["qty"],
                "qty_60pct":   risk["qty_60pct"],
                "qty_40pct":   risk["qty_40pct"],
                "risk_reward": risk["risk_reward"],
                "fvg_low":     imb["fvg_low"],
                "fvg_high":    imb["fvg_high"],
                "cvd_delta":   flow["delta"],
                "vol_spike":   round(last_volume / avg_volume, 2),
            })

            logger.info(
                f"WhaleScanner: setup → {symbol} entry={entry_price:.6g} "
                f"vol_spike={last_volume/avg_volume:.1f}x delta={flow['delta']:.4f}"
            )

        except Exception as e:
            logger.debug(f"WhaleScanner: error on {symbol}: {e}")
            continue

    logger.info(
        f"WhaleScanner: done — vol={passed_vol} fvg={passed_fvg} "
        f"flow={passed_flow} break={passed_break} setups={len(setups)}"
    )
    return setups


async def _get_valid_symbols(exchange) -> List[str]:
    """Return trusted symbols that pass volume and spread filters."""
    try:
        tickers = await exchange.fetch_tickers(list(TRUSTED_SYMBOLS))
        valid = []
        for sym in TRUSTED_SYMBOLS:
            t = tickers.get(sym, {})
            if not t:
                continue
            volume = float(t.get("quoteVolume") or 0)
            if volume < MIN_VOLUME_24H:
                continue
            bid = float(t.get("bid") or 0)
            ask = float(t.get("ask") or 0)
            if bid <= 0 or ask <= 0:
                continue
            spread = ((ask - bid) / bid) * 100
            if spread > MAX_SPREAD_PCT:
                continue
            valid.append((sym, volume))

        valid.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in valid]

    except Exception as e:
        logger.error(f"WhaleScanner: failed to fetch tickers: {e}")
        return []
