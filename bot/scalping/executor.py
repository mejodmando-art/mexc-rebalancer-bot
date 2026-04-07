"""
Trade executor — places entry + take profit + stop loss on MEXC Spot.

Flow:
  1. Pre-flight: fetch market limits and validate that the full trade AND
     the half-qty T1/SL orders all meet exchange minimums. Abort before
     touching the account if any order would be rejected.
  2. Market buy (quoteOrderQty)
  3. Limit sell at T1 for 50% of qty  (take profit partial exit)
  4. Limit sell at SL for full qty    (stop loss protection)

MEXC Spot does not support stop-market orders via ccxt. A plain limit sell
at the SL price is the closest equivalent — it sits on the exchange and
executes automatically when price reaches it, even if the bot is offline.
Edge case: if price gaps below SL without touching it, the order won't fill.

T2 and trailing stop are handled by monitor.py after T1 is hit, since MEXC
Spot does not support chained conditional orders.
"""

import logging
from typing import Dict, Any

from bot.scalping.market_limits import get_limits, check_order_viable

logger = logging.getLogger(__name__)

# Safety margin applied to filled qty before placing sell orders (avoids
# oversell due to fee deductions or rounding on the exchange side).
_SELL_MARGIN = 0.999


async def _place_stop_loss(exchange, symbol: str, qty: float, stop_price: float) -> Dict[str, Any]:
    order = await exchange.create_limit_sell_order(symbol, qty, stop_price)
    logger.info(f"Executor: SL limit sell {symbol} qty={qty} @ {stop_price} -> id={order.get('id')}")
    return order


async def execute_trade(setup: Dict[str, Any], exchange) -> Dict[str, Any]:
    symbol          = setup["symbol"]
    entry_price     = setup["entry_price"]
    trade_size_usdt = setup["qty"] * entry_price
    stop_loss       = setup["stop_loss"]
    target1         = setup["target1"]

    # ── Pre-flight: validate all three orders against exchange minimums ───
    try:
        limits = await get_limits(symbol, exchange)

        # Estimate qty from trade size (actual filled qty may differ slightly)
        est_qty      = trade_size_usdt / entry_price if entry_price > 0 else 0
        est_safe_qty = est_qty * _SELL_MARGIN
        est_half_qty = est_safe_qty / 2

        # Entry order (market buy by cost — MEXC accepts quoteOrderQty so
        # the notional is exactly trade_size_usdt; only min_qty matters here)
        err = check_order_viable(symbol, est_qty, entry_price, limits, "entry")
        if err:
            logger.warning(f"Executor: pre-flight failed for {symbol}: {err}")
            return _preflight_error(symbol, err)

        # T1 order — half qty at target1
        err = check_order_viable(symbol, est_half_qty, target1, limits, "T1")
        if err:
            logger.warning(f"Executor: pre-flight failed for {symbol}: {err}")
            return _preflight_error(symbol, err)

        # SL order — full safe qty at stop_loss
        err = check_order_viable(symbol, est_safe_qty, stop_loss, limits, "SL")
        if err:
            logger.warning(f"Executor: pre-flight failed for {symbol}: {err}")
            return _preflight_error(symbol, err)

    except Exception as e:
        # Non-fatal: if limits fetch fails entirely, proceed with a warning.
        # Better to attempt the trade than to silently skip it.
        logger.warning(f"Executor: pre-flight limits check failed for {symbol}: {e} — proceeding anyway")

    try:
        # ── 1. Market buy ─────────────────────────────────────────────────
        logger.info(f"Executor: market buy {symbol} cost={trade_size_usdt:.2f} USDT")
        entry_order = await exchange.create_market_buy_order_with_cost(symbol, trade_size_usdt)
        logger.info(
            f"Executor: filled {symbol} -> id={entry_order.get('id')} "
            f"filled={entry_order.get('filled')} status={entry_order.get('status')}"
        )

        filled_qty = float(entry_order.get("filled") or entry_order.get("amount") or 0)
        if filled_qty <= 0:
            avg = float(entry_order.get("average") or entry_order.get("price") or entry_price)
            filled_qty = trade_size_usdt / avg if avg > 0 else setup["qty"]

        # Verify against actual free balance — MEXC sometimes returns filled=0
        # for market orders even when executed, causing oversell errors on T1/SL.
        base_sym = symbol.split("/")[0]
        try:
            balance    = await exchange.fetch_balance()
            actual_qty = float(balance.get("free", {}).get(base_sym, 0) or 0)
            if actual_qty > 0:
                filled_qty = min(filled_qty, actual_qty) if filled_qty > 0 else actual_qty
                logger.info(f"Executor: balance check {base_sym} free={actual_qty:.8f} -> using {filled_qty:.8f}")
        except Exception as e:
            logger.warning(f"Executor: balance check failed for {base_sym}: {e}")

        safe_qty = round(filled_qty * _SELL_MARGIN, 8)
        qty_half = round(safe_qty / 2, 8)

        # ── 2. Take profit — limit sell at T1 for 50% ────────────────────
        t1_order  = {}
        t1_placed = False
        t1_error  = ""
        try:
            t1_order  = await exchange.create_limit_sell_order(symbol, qty_half, target1)
            t1_placed = True
            logger.info(f"Executor: T1 limit sell {symbol} qty={qty_half} @ {target1} -> id={t1_order.get('id')}")
        except Exception as e:
            t1_error = _friendly_error(str(e))
            logger.warning(f"Executor: T1 order failed for {symbol}: {e}")

        # ── 3. Stop loss — limit sell at SL price ────────────────────────
        sl_order  = {}
        sl_placed = False
        sl_error  = ""
        try:
            sl_order  = await _place_stop_loss(exchange, symbol, safe_qty, stop_loss)
            sl_placed = True
        except Exception as e:
            sl_error = _friendly_error(str(e))
            logger.warning(f"Executor: SL order failed for {symbol}: {e}")

        return {
            "status":        "ok",
            "symbol":        symbol,
            "entry_order":   entry_order,
            "target1_order": t1_order,
            "target2_order": {},
            "sl_order":      sl_order,
            "filled_qty":    filled_qty,
            "qty_half":      qty_half,
            "t1_placed":     t1_placed,
            "sl_placed":     sl_placed,
            "t1_error":      t1_error,
            "sl_error":      sl_error,
            "reason":        "",
        }

    except Exception as e:
        logger.error(f"Executor: failed on {symbol}: {type(e).__name__}: {e}")
        return {
            "status":        "error",
            "symbol":        symbol,
            "entry_order":   {},
            "target1_order": {},
            "target2_order": {},
            "sl_order":      {},
            "filled_qty":    0.0,
            "qty_half":      0.0,
            "t1_placed":     False,
            "sl_placed":     False,
            "t1_error":      "",
            "sl_error":      "",
            "reason":        str(e)[:120],
        }


def _preflight_error(symbol: str, reason: str) -> Dict[str, Any]:
    """Return an error result without touching the exchange account."""
    return {
        "status":        "preflight_error",
        "symbol":        symbol,
        "entry_order":   {},
        "target1_order": {},
        "target2_order": {},
        "sl_order":      {},
        "filled_qty":    0.0,
        "qty_half":      0.0,
        "t1_placed":     False,
        "sl_placed":     False,
        "t1_error":      "",
        "sl_error":      "",
        "reason":        reason,
    }


def _friendly_error(raw: str) -> str:
    """Map common ccxt error messages to short Arabic-friendly descriptions."""
    low = raw.lower()
    if "minimum" in low or "min" in low or "too small" in low or "below" in low:
        return "المبلغ أقل من الحد الأدنى المسموح"
    if "insufficient" in low or "balance" in low:
        return "رصيد غير كافٍ"
    if "precision" in low or "lot size" in low:
        return "خطأ في دقة الكمية"
    return raw[:80]
