"""
Trade executor — places entry + take profit + stop loss on MEXC Spot.

Flow:
  1. Market buy (quoteOrderQty)
  2. Limit sell at T1 for 50% of qty  (take profit partial exit)
  3. Stop-market sell at SL for full qty (stop loss protection)

T2 and trailing stop are handled by monitor.py after T1 is hit,
since MEXC Spot does not support chained conditional orders.

Having real orders on MEXC means the position is protected even if
the bot goes offline.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


async def execute_trade(setup: Dict[str, Any], exchange) -> Dict[str, Any]:
    symbol          = setup["symbol"]
    trade_size_usdt = setup["qty"] * setup["entry_price"]
    stop_loss       = setup["stop_loss"]
    target1         = setup["target1"]

    try:
        # ── 1. Market buy ─────────────────────────────────────────────────
        logger.info(f"Executor: market buy {symbol} cost={trade_size_usdt:.2f} USDT")
        entry_order = await exchange.create_market_buy_order_with_cost(symbol, trade_size_usdt)
        logger.info(
            f"Executor: filled {symbol} → id={entry_order.get('id')} "
            f"filled={entry_order.get('filled')} status={entry_order.get('status')}"
        )

        filled_qty = float(entry_order.get("filled") or entry_order.get("amount") or 0)
        if filled_qty <= 0:
            avg = float(entry_order.get("average") or entry_order.get("price") or setup["entry_price"])
            filled_qty = trade_size_usdt / avg if avg > 0 else setup["qty"]

        qty_half = round(filled_qty / 2, 8)

        # ── 2. Take profit — limit sell at T1 for 50% ────────────────────
        t1_order = {}
        try:
            t1_order = await exchange.create_limit_sell_order(symbol, qty_half, target1)
            logger.info(f"Executor: T1 limit sell {symbol} qty={qty_half} @ {target1} → id={t1_order.get('id')}")
        except Exception as e:
            logger.warning(f"Executor: T1 limit order failed for {symbol}: {e}")

        # ── 3. Stop loss — stop-market sell for full qty ──────────────────
        sl_order = {}
        try:
            sl_order = await exchange.createStopMarketOrder(symbol, "sell", filled_qty, stop_loss)
            logger.info(f"Executor: SL stop-market {symbol} qty={filled_qty} trigger={stop_loss} → id={sl_order.get('id')}")
        except Exception as e:
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
            "reason":        str(e)[:120],
        }
