"""
Whale trade monitor — runs every 20 seconds.

After entry, real orders are placed on MEXC:
  - Limit sell at T1 for 60% of qty
  - Stop-market sell at SL for full qty

When T1 fills:
  - Cancel old SL, place new SL for remaining 40%
  - Place limit sell at T2 for remaining 40%

Having real orders on MEXC means the position is protected even if
the bot goes offline.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from bot.database import db

logger = logging.getLogger(__name__)


async def _place_stop_loss(exchange, symbol: str, qty: float, stop_price: float) -> Dict[str, Any]:
    """
    Place a limit sell at the stop price on MEXC Spot.

    MEXC Spot does not support conditional orders. A plain limit sell at the
    SL price sits on the exchange and executes automatically even if the bot
    is offline.
    """
    order = await exchange.create_limit_sell_order(symbol, qty, stop_price)
    logger.info(f"WhaleMonitor: SL limit sell {symbol} qty={qty} @ {stop_price} → id={order.get('id')}")
    return order


class WhaleTradeMonitor:
    def __init__(self):
        self.open_trades: Dict[str, Dict[str, Any]] = {}

    async def add_trade(self, setup: Dict, result: Dict, user_id: int) -> None:
        symbol     = setup["symbol"]
        filled_qty = float(result.get("filled_qty") or setup["qty"])
        qty_60     = round(filled_qty * 0.6, 8)
        qty_40     = round(filled_qty * 0.4, 8)

        trade = {
            "symbol":      symbol,
            "user_id":     user_id,
            "entry_price": setup["entry_price"],
            "stop_loss":   setup["stop_loss"],
            "target1":     setup["target1"],
            "target2":     setup["target2"],
            "qty":         filled_qty,
            "qty_60pct":   qty_60,
            "qty_40pct":   qty_40,
            "risk_reward": setup["risk_reward"],
            "t1_hit":      False,
            "t2_hit":      False,
            "t1_order_id": result.get("target1_order", {}).get("id"),
            "t2_order_id": None,
            "sl_order_id": result.get("sl_order", {}).get("id"),
            "opened_at":   datetime.now(timezone.utc).isoformat(),
            "strategy":    "whale",
        }
        self.open_trades[symbol] = trade
        try:
            await db.save_scalping_trade(user_id, trade)
        except Exception as e:
            logger.error(f"WhaleMonitor: failed to persist {symbol}: {e}")
        logger.info(f"WhaleMonitor: tracking {symbol}")

    async def remove_trade(self, symbol: str) -> None:
        self.open_trades.pop(symbol, None)
        try:
            await db.delete_scalping_trade(symbol)
        except Exception as e:
            logger.error(f"WhaleMonitor: failed to delete {symbol}: {e}")

    async def load_from_db(self) -> None:
        """Restore open whale trades from DB after a restart."""
        try:
            rows = await db.load_scalping_trades()
            for row in rows:
                # Only restore trades that belong to the whale strategy
                if row.get("strategy") != "whale":
                    continue
                filled_qty = float(row.get("qty") or 0)
                self.open_trades[row["symbol"]] = {
                    "symbol":      row["symbol"],
                    "user_id":     row.get("user_id"),
                    "entry_price": row["entry_price"],
                    "stop_loss":   row["stop_loss"],
                    "target1":     row["target1"],
                    "target2":     row["target2"],
                    "qty":         filled_qty,
                    "qty_60pct":   round(filled_qty * 0.6, 8),
                    "qty_40pct":   round(filled_qty * 0.4, 8),
                    "risk_reward": row["risk_reward"],
                    "t1_hit":      bool(row["t1_hit"]),
                    "t2_hit":      bool(row.get("t2_hit", 0)),
                    "t1_order_id": row.get("t1_order_id"),
                    "t2_order_id": row.get("t2_order_id"),
                    "sl_order_id": row.get("sl_order_id"),
                    "opened_at":   row["opened_at"],
                    "strategy":    "whale",
                }
            if self.open_trades:
                logger.info(f"WhaleMonitor: restored {len(self.open_trades)} open trade(s) from DB")
        except Exception as e:
            logger.error(f"WhaleMonitor: failed to load trades from DB: {e}")

    @property
    def open_symbols(self) -> set:
        return set(self.open_trades.keys())

    def open_symbols_for(self, user_id: int) -> set:
        """Return only the symbols with open trades belonging to user_id."""
        return {sym for sym, t in self.open_trades.items() if t.get("user_id") == user_id}

    async def check_all(self, exchange, bot, user_id: int) -> None:
        # Only process trades that belong to this user
        user_trades = {
            sym: t for sym, t in self.open_trades.items()
            if t.get("user_id") == user_id
        }
        if not user_trades:
            return

        symbols = list(user_trades.keys())
        try:
            tickers = await exchange.fetch_tickers(symbols)
        except Exception as e:
            logger.error(f"WhaleMonitor: fetch_tickers failed: {e}")
            return

        for symbol, trade in list(user_trades.items()):
            ticker = tickers.get(symbol, {})
            price  = float(ticker.get("last") or 0)
            if price <= 0:
                continue
            await self._check_trade(trade, price, exchange, bot, user_id)

    async def _check_trade(self, trade, price, exchange, bot, user_id) -> None:
        symbol  = trade["symbol"]
        target1 = trade["target1"]
        target2 = trade["target2"]

        # ── Check if SL limit order was filled on MEXC ────────────────────
        if trade.get("sl_order_id"):
            try:
                sl_order = await exchange.fetch_order(trade["sl_order_id"], symbol)
                if sl_order.get("status") == "closed":
                    await self._on_sl_hit(trade, price, exchange, bot, user_id)
                    return
            except Exception as e:
                logger.warning(f"WhaleMonitor: could not fetch SL order for {symbol}: {e}")

        # ── Fallback: price-based SL detection ───────────────────────────
        if price <= trade["stop_loss"]:
            await self._on_sl_hit(trade, price, exchange, bot, user_id)
            return

        # ── Check if T1 limit order was filled on MEXC ────────────────────
        if not trade["t1_hit"] and trade.get("t1_order_id"):
            try:
                t1_order = await exchange.fetch_order(trade["t1_order_id"], symbol)
                if t1_order.get("status") == "closed":
                    await self._on_t1_filled(trade, price, exchange, bot, user_id)
                    return
            except Exception as e:
                logger.warning(f"WhaleMonitor: could not fetch T1 order for {symbol}: {e}")

        # ── Fallback: price-based T1 detection ────────────────────────────
        if not trade["t1_hit"] and price >= target1:
            await self._on_t1_filled(trade, price, exchange, bot, user_id)
            return

        # ── T2 hit ─────────────────────────────────────────────────────────
        if trade["t1_hit"] and not trade["t2_hit"] and price >= target2:
            await self._on_t2_hit(trade, price, exchange, bot, user_id)
            return

    async def _on_sl_hit(self, trade, price, exchange, bot, user_id) -> None:
        """SL limit order filled on MEXC (or price-based fallback triggered)."""
        symbol = trade["symbol"]
        qty    = trade["qty_40pct"] if trade["t1_hit"] else trade["qty"]

        # Cancel open T1/T2 orders
        for order_id in [trade.get("t1_order_id"), trade.get("t2_order_id")]:
            if order_id:
                try:
                    await exchange.cancel_order(order_id, symbol)
                except Exception:
                    pass

        # Fallback: if SL order wasn't on exchange, fire market sell now
        if not trade.get("sl_order_id"):
            try:
                await exchange.create_market_sell_order(symbol, qty)
                logger.info(f"WhaleMonitor: SL fallback market sell {symbol} qty={qty} @ {price:.6g}")
            except Exception as e:
                logger.error(f"WhaleMonitor: SL fallback market sell failed for {symbol}: {e}")

        await self.remove_trade(symbol)

        entry = trade["entry_price"]
        pnl   = ((price - entry) / entry) * 100
        await self._notify(
            bot, user_id,
            f"🛑 *{symbol}* — Stop Loss اتنفذ\n\n"
            f"📉 بيع عند `${price:.6g}`  (`{pnl:.2f}%`)\n"
            f"🔒 SL كان عند `${trade['stop_loss']:.6g}`"
        )

    async def _on_t1_filled(self, trade, price, exchange, bot, user_id) -> None:
        symbol  = trade["symbol"]
        target2 = trade["target2"]
        trade["t1_hit"] = True

        # Cancel old SL (full qty) and place new one for remaining 40%
        if trade.get("sl_order_id"):
            try:
                await exchange.cancel_order(trade["sl_order_id"], symbol)
            except Exception:
                pass

        new_sl = round(trade["entry_price"] * 0.999, 8)
        if new_sl > trade["stop_loss"]:
            trade["stop_loss"] = new_sl

        # Fetch actual free balance before placing T2/SL to avoid oversell
        base_sym = symbol.split("/")[0]
        try:
            bal = await exchange.fetch_balance()
            actual_free = float(bal.get("free", {}).get(base_sym, 0) or 0)
            safe_40 = round(min(trade["qty_40pct"], actual_free) * 0.999, 8) if actual_free > 0 else round(trade["qty_40pct"] * 0.999, 8)
        except Exception:
            safe_40 = round(trade["qty_40pct"] * 0.999, 8)

        try:
            sl_order = await _place_stop_loss(exchange, symbol, safe_40, trade["stop_loss"])
            trade["sl_order_id"] = sl_order.get("id")
            logger.info(f"WhaleMonitor: {symbol} T1 filled — new SL @ {trade['stop_loss']:.6g}")
        except Exception as e:
            logger.warning(f"WhaleMonitor: failed to place new SL after T1 for {symbol}: {e}")
            trade["sl_order_id"] = None

        # Place T2 limit order for remaining 40%
        try:
            t2_order = await exchange.create_limit_sell_order(symbol, safe_40, target2)
            trade["t2_order_id"] = t2_order.get("id")
            logger.info(f"WhaleMonitor: {symbol} T2 limit placed @ {target2:.6g}")
        except Exception as e:
            logger.warning(f"WhaleMonitor: failed to place T2 order for {symbol}: {e}")

        try:
            await db.save_scalping_trade(user_id, trade)
        except Exception:
            pass

        entry = trade["entry_price"]
        pnl   = ((price - entry) / entry) * 100
        await self._notify(
            bot, user_id,
            f"🎯 *{symbol}* — هدف 1 اتحقق!\n\n"
            f"✅ بيع 60% عند `${price:.6g}`  (`+{pnl:.2f}%`)\n"
            f"🎯 هدف 2: `${target2:.6g}` — أوردر على MEXC ✅\n"
            f"🛑 Stop Loss محدث على MEXC ✅"
        )

    async def _on_t2_hit(self, trade, price, exchange, bot, user_id) -> None:
        symbol = trade["symbol"]
        trade["t2_hit"] = True

        # Cancel T2 limit order if still open
        for order_id in [trade.get("t2_order_id")]:
            if order_id:
                try:
                    await exchange.cancel_order(order_id, symbol)
                except Exception:
                    pass

        await self.remove_trade(symbol)

        entry = trade["entry_price"]
        pnl   = ((price - entry) / entry) * 100
        await self._notify(
            bot, user_id,
            f"✅ *{symbol}* — هدف 2 اتحقق!\n\n"
            f"🎯 بيع 40% عند `${price:.6g}`  (`+{pnl:.2f}%`)\n"
            f"📊 الصفقة اتغلقت كاملاً"
        )

    async def cancel_all_orders(self, trade: Dict, exchange) -> None:
        """Cancel all open orders for a trade (called on manual sell or cleanup)."""
        symbol = trade["symbol"]
        for order_id in [
            trade.get("t1_order_id"),
            trade.get("t2_order_id"),
            trade.get("sl_order_id"),
        ]:
            if order_id:
                try:
                    await exchange.cancel_order(order_id, symbol)
                except Exception:
                    pass

    async def _notify(self, bot, user_id: int, text: str) -> None:
        try:
            await bot.send_message(user_id, text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"WhaleMonitor: notify failed: {e}")


whale_monitor = WhaleTradeMonitor()
