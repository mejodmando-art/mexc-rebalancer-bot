"""
Market limits cache for MEXC Spot.

Fetches and caches per-symbol minimums so executor and scanner can validate
orders before placement. Avoids repeated fetch_markets() calls (expensive —
returns thousands of records).

Cached fields per symbol:
  min_qty      — minimum base asset quantity per order
  min_notional — minimum order value in USDT (min cost)
  qty_step     — quantity precision step (lot size)
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Cache TTL: 30 minutes. Market limits rarely change.
_CACHE_TTL = 1800.0

_cache: Dict[str, Dict[str, float]] = {}
_cache_ts: float = 0.0
_refresh_lock = asyncio.Lock()  # prevents concurrent fetch_markets() calls


def _parse_limits(market: dict) -> Dict[str, float]:
    limits  = market.get("limits") or {}
    amount  = limits.get("amount") or {}
    cost    = limits.get("cost") or {}
    price   = limits.get("price") or {}

    precision = market.get("precision") or {}
    # amount precision can be a step value or decimal places
    raw_step = precision.get("amount")
    if raw_step and raw_step < 1:
        qty_step = float(raw_step)
    elif raw_step and raw_step >= 1:
        # decimal places → convert to step
        qty_step = 10 ** (-int(raw_step))
    else:
        qty_step = 0.0

    return {
        "min_qty":      float(amount.get("min") or 0),
        "min_notional": float(cost.get("min") or 0),
        "qty_step":     qty_step,
    }


async def get_limits(symbol: str, exchange) -> Dict[str, float]:
    """
    Return cached limits for symbol. Refreshes the full cache if stale.

    Returns dict with keys: min_qty, min_notional, qty_step.
    All values default to 0 if unknown (caller should treat 0 as "no limit").
    """
    global _cache, _cache_ts

    now = time.monotonic()
    if now - _cache_ts > _CACHE_TTL or symbol not in _cache:
        async with _refresh_lock:
            # Re-check inside lock — another coroutine may have refreshed already
            if time.monotonic() - _cache_ts > _CACHE_TTL or symbol not in _cache:
                await _refresh(exchange)

    return _cache.get(symbol, {"min_qty": 0.0, "min_notional": 0.0, "qty_step": 0.0})


async def _refresh(exchange) -> None:
    global _cache, _cache_ts
    try:
        markets = await exchange.fetch_markets()
        new_cache: Dict[str, Dict[str, float]] = {}
        for m in markets:
            sym = m.get("symbol", "")
            if sym.endswith("/USDT") and m.get("spot"):
                new_cache[sym] = _parse_limits(m)
        _cache = new_cache
        _cache_ts = time.monotonic()
        logger.debug(f"MarketLimits: refreshed {len(_cache)} USDT spot markets")
    except Exception as e:
        logger.warning(f"MarketLimits: fetch_markets failed: {e}")
        # Keep stale cache rather than clearing it


def check_order_viable(
    symbol: str,
    qty: float,
    price: float,
    limits: Dict[str, float],
    label: str = "order",
) -> Optional[str]:
    """
    Returns an error string if the order violates exchange minimums, else None.

    Args:
        symbol: trading pair
        qty:    base asset quantity
        price:  limit/market price
        limits: dict from get_limits()
        label:  human-readable label for logging
    """
    min_qty      = limits.get("min_qty", 0)
    min_notional = limits.get("min_notional", 0)
    notional     = qty * price

    if min_qty > 0 and qty < min_qty:
        return f"{label}: qty {qty:.8f} < min_qty {min_qty}"

    if min_notional > 0 and notional < min_notional:
        return f"{label}: notional ${notional:.4f} < min_notional ${min_notional}"

    return None
