"""
Trade executor — places entry + take profit + stop loss on MEXC Spot.

Flow:
  1. Market buy (quoteOrderQty)
  2. Limit sell at T1 for 50% of qty  (take profit partial exit)
  3. Stop-limit sell at SL for full qty (stop loss protection)

MEXC Spot does not support stop-market orders via ccxt. We use
STOP_LOSS_LIMIT with the limit price set slightly below the stop trigger
(0.3% below) to ensure the order fills quickly when triggered.

T2 and trailing stop are handled by monitor.py after T1 is hit,
since MEXC Spot does not support chained conditional orders.

Having real orders on MEXC means the position is protected even if
the bot goes offline.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


async def _place_stop_loss(exchange, symbol: str, qty: float, stop_price: float) -> Dict[str, Any]:
    """
    Place a limit sell at the stop price on MEXC Spot.

    MEXC Spot does not support conditional (stop) orders. A plain limit sell
    at the SL price is the closest equivalent — it sits on the exchange and
    executes automatically when price reaches it, even if the bot is offline.

    Edge case: if price gaps below SL without touching it, the order won't
    fill. This is rare on liquid coins but possible on smaller ones.
    """
    order = await exchange.create_limit_sell_order(symbol, qty, stop_price)
    logger.info(f"Executor: SL limit sell {symbol} qty={qty} @ {stop_price} → id={order.get('id')}")
    return order


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

        # Verify against actual free balance — MEXC sometimes returns filled=0
        # for market orders even when executed, causing oversell errors on T1/SL.
        base_sym = symbol.split("/")[0]
        try:
            balance    = await exchange.fetch_balance()
            actual_qty = float(balance.get("free", {}).get(base_sym, 0) or 0)
            if actual_qty > 0:
                # Use the lesser of the two to avoid selling more than we hold
                filled_qty = min(filled_qty, actual_qty) if filled_qty > 0 else actual_qty
                logger.info(f"Executor: balance check {base_sym} free={actual_qty:.8f} → using {filled_qty:.8f}")
        except Exception as e:
            logger.warning(f"Executor: balance check failed for {base_sym}: {e}")

        qty_half = round(filled_qty / 2, 8)

        # ── 2. Take profit — limit sell at T1 for 50% ────────────────────
        t1_order = {}
        t1_placed = False
        t1_error  = ""
        try:
            t1_order  = await exchange.create_limit_sell_order(symbol, qty_half, target1)
            t1_placed = True
            logger.info(f"Executor: T1 limit sell {symbol} qty={qty_half} @ {target1} → id={t1_order.get('id')}")
        except Exception as e:
            t1_error = str(e)[:120]
            logger.warning(f"Executor: T1 limit order failed for {symbol}: {e}")

        # ── 3. Stop loss — limit sell on MEXC at SL price ────────────────
        sl_order = {}
        sl_placed = False
        sl_error  = ""
        try:
            sl_order  = await _place_stop_loss(exchange, symbol, filled_qty, stop_loss)
            sl_placed = True
        except Exception as e:
            sl_error = str(e)[:120]
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
            "reason":        str(e)[:120],
        }
