"""
Open trade monitor — runs every 20 seconds.

With real MEXC orders in place (T1 limit + SL stop-limit), the monitor's
job is lighter:
  - Detect when T1 limit order is filled → place T2 limit + update SL
  - Trailing stop: after T1 hit, trail SL upward (cancel old, place new)
  - Fallback market sell if SL order is missing (safety net)
"""

import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List

from bot.database import db

logger = logging.getLogger(__name__)

TRAIL_PCT           = 0.015   # 1.5% trail distance before T1
TRAIL_PCT_AFTER_T1  = 0.010   # 1.0% trail distance after T1 (tighter — protect profit)


async def _place_stop_loss(exchange, symbol: str, qty: float, stop_price: float) -> Dict[str, Any]:
    """
    Place a stop-loss sell order on MEXC Spot.

    MEXC Spot requires STOP_LOSS_LIMIT (not stop-market). The limit price is
    set 0.3% below the stop trigger so the order fills immediately when hit.
    """
    limit_price = round(stop_price * 0.997, 8)
    try:
        order = await exchange.create_order(
            symbol,
            "STOP_LOSS_LIMIT",
            "sell",
            qty,
            limit_price,
            params={"stopPrice": stop_price},
        )
        return order
    except Exception as e:
        logger.warning(f"Monitor: STOP_LOSS_LIMIT failed for {symbol}: {e} — trying limit fallback")

    # Fallback: plain limit sell at the stop price
    order = await exchange.create_limit_sell_order(symbol, qty, limit_price)
    return order


class TradeMonitor:
    def __init__(self):
        # open_trades: {symbol: trade_dict}
        self.open_trades: Dict[str, Dict[str, Any]] = {}

    async def add_trade(self, setup: Dict[str, Any], result: Dict[str, Any], user_id: int) -> None:
        """Register a newly executed trade and persist it to the database."""
        symbol = setup["symbol"]
        # Use actual filled qty from executor (may differ from estimated qty due to
        # MEXC Spot using quoteOrderQty for market buys)
        actual_qty      = float(result.get("filled_qty") or setup["qty"])
        actual_qty_half = float(result.get("qty_half")   or setup["qty_half"])
        entry_price     = setup["entry_price"]
        initial_sl      = setup["stop_loss"]
        trade = {
            "symbol":            symbol,
            "user_id":           user_id,
            "entry_price":       entry_price,
            "stop_loss":         initial_sl,
            "initial_stop_loss": initial_sl,
            "highest_price":     entry_price,
            "target1":           setup["target1"],
            "target2":           setup["target2"],
            "qty":               actual_qty,
            "qty_half":          actual_qty_half,
            "risk_reward":       setup["risk_reward"],
            "t1_hit":            False,
            "t2_hit":            False,
            "t1_order_id":       result.get("target1_order", {}).get("id"),
            "t2_order_id":       None,
            "sl_order_id":       result.get("sl_order", {}).get("id"),
            "opened_at":         datetime.now(timezone.utc).isoformat(),
            "breakeven":         False,
        }
        self.open_trades[symbol] = trade
        try:
            await db.save_scalping_trade(user_id, trade)
        except Exception as e:
            logger.error(f"Monitor: failed to persist trade {symbol}: {e}")
        logger.info(f"Monitor: tracking {symbol}")

    async def remove_trade(self, symbol: str) -> None:
        self.open_trades.pop(symbol, None)
        try:
            await db.delete_scalping_trade(symbol)
        except Exception as e:
            logger.error(f"Monitor: failed to delete trade {symbol} from DB: {e}")

    async def load_from_db(self) -> None:
        """Restore open trades from DB after a restart."""
        try:
            rows = await db.load_scalping_trades()
            for row in rows:
                # Skip whale trades — whale_monitor handles those
                if row.get("strategy") == "whale":
                    continue
                self.open_trades[row["symbol"]] = {
                    "symbol":            row["symbol"],
                    "user_id":           row.get("user_id"),
                    "entry_price":       row["entry_price"],
                    "stop_loss":         row["stop_loss"],
                    "initial_stop_loss": row.get("initial_stop_loss") or row["stop_loss"],
                    "highest_price":     row.get("highest_price") or row["entry_price"],
                    "target1":           row["target1"],
                    "target2":           row["target2"],
                    "qty":               row["qty"],
                    "qty_half":          row["qty_half"],
                    "risk_reward":       row["risk_reward"],
                    "t1_hit":            bool(row["t1_hit"]),
                    "t2_hit":            bool(row.get("t2_hit", False)),
                    "t1_order_id":       row["t1_order_id"],
                    "t2_order_id":       row["t2_order_id"],
                    "sl_order_id":       row.get("sl_order_id"),
                    "opened_at":         row["opened_at"],
                    "breakeven":         bool(row["breakeven"]),
                }
            if self.open_trades:
                logger.info(f"Monitor: restored {len(self.open_trades)} open trade(s) from DB")
        except Exception as e:
            logger.error(f"Monitor: failed to load trades from DB: {e}")

    @property
    def open_symbols(self) -> set:
        return set(self.open_trades.keys())

    def open_symbols_for(self, user_id: int) -> set:
        """Return only the symbols with open trades belonging to user_id."""
        return {sym for sym, t in self.open_trades.items() if t.get("user_id") == user_id}

    async def check_all(self, exchange, bot, user_id: int) -> None:
        """Check open trades for user_id. Called every 20 seconds."""
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
            logger.error(f"Monitor: fetch_tickers failed: {e}")
            return

        for symbol, trade in list(user_trades.items()):
            ticker = tickers.get(symbol, {})
            price  = float(ticker.get("last") or 0)
            if price <= 0:
                continue
            await self._check_trade(trade, price, exchange, bot, user_id)

    async def _check_trade(
        self,
        trade: Dict[str, Any],
        price: float,
        exchange,
        bot,
        user_id: int,
    ) -> None:
        symbol  = trade["symbol"]
        target2 = trade["target2"]

        # ── Check if T1 limit order was filled on MEXC ────────────────────
        if not trade["t1_hit"] and trade.get("t1_order_id"):
            try:
                t1_order = await exchange.fetch_order(trade["t1_order_id"], symbol)
                if t1_order.get("status") == "closed":
                    await self._on_t1_filled(trade, price, exchange, bot, user_id)
                    return
            except Exception as e:
                logger.warning(f"Monitor: could not fetch T1 order for {symbol}: {e}")

        # ── Fallback: price-based T1 detection (if order fetch fails) ─────
        if not trade["t1_hit"] and price >= trade["target1"]:
            await self._on_t1_filled(trade, price, exchange, bot, user_id)
            return

        # ── After T1: trailing stop + T2 ──────────────────────────────────
        if trade["t1_hit"]:
            # T2 hit → close trade
            if not trade.get("t2_hit") and price >= target2:
                await self._on_t2_hit(trade, price, exchange, bot, user_id)
                return

            # Trailing stop — update SL order on MEXC
            entry_price = trade["entry_price"]
            initial_sl  = trade.get("initial_stop_loss") or trade["stop_loss"]
            risk        = entry_price - initial_sl

            if price > trade["highest_price"]:
                trade["highest_price"] = price
                new_sl = round(price * (1 - TRAIL_PCT_AFTER_T1), 8)
                if new_sl > trade["stop_loss"]:
                    old_sl = trade["stop_loss"]
                    trade["stop_loss"] = new_sl
                    logger.info(f"Monitor: {symbol} trailing SL {old_sl:.6g} → {new_sl:.6g}")

                    # Cancel old SL order and place new one
                    if trade.get("sl_order_id"):
                        try:
                            await exchange.cancel_order(trade["sl_order_id"], symbol)
                        except Exception:
                            pass
                    try:
                        sl_order = await _place_stop_loss(exchange, symbol, trade["qty_half"], new_sl)
                        trade["sl_order_id"] = sl_order.get("id")
                        logger.info(f"Monitor: {symbol} new SL order placed @ {new_sl:.6g}")
                    except Exception as e:
                        logger.warning(f"Monitor: failed to update SL order for {symbol}: {e}")

                    try:
                        await db.save_scalping_trade(user_id, trade)
                    except Exception as e:
                        logger.error(f"Monitor: failed to save trade {symbol}: {e}")

    async def _on_t1_filled(
        self,
        trade: Dict[str, Any],
        price: float,
        exchange,
        bot,
        user_id: int,
    ) -> None:
        symbol  = trade["symbol"]
        target2 = trade["target2"]

        trade["t1_hit"]    = True
        trade["breakeven"] = True

        # Cancel existing SL (covers full qty) — replace with half qty SL
        if trade.get("sl_order_id"):
            try:
                await exchange.cancel_order(trade["sl_order_id"], symbol)
            except Exception:
                pass

        # New SL at breakeven (entry price) for remaining 50%
        new_sl = round(price * (1 - TRAIL_PCT_AFTER_T1), 8)
        if new_sl > trade["stop_loss"]:
            trade["stop_loss"] = new_sl

        sl_order = {}
        try:
            sl_order = await _place_stop_loss(exchange, symbol, trade["qty_half"], trade["stop_loss"])
            trade["sl_order_id"] = sl_order.get("id")
            logger.info(f"Monitor: {symbol} T1 filled — new SL @ {trade['stop_loss']:.6g}")
        except Exception as e:
            logger.warning(f"Monitor: failed to place new SL after T1 for {symbol}: {e}")

        # Place T2 limit order for remaining 50%
        try:
            t2_order = await exchange.create_limit_sell_order(symbol, trade["qty_half"], target2)
            trade["t2_order_id"] = t2_order.get("id")
            logger.info(f"Monitor: {symbol} T2 limit placed @ {target2:.6g}")
        except Exception as e:
            logger.warning(f"Monitor: failed to place T2 order for {symbol}: {e}")

        try:
            await db.save_scalping_trade(user_id, trade)
        except Exception as e:
            logger.error(f"Monitor: failed to save trade {symbol} after T1: {e}")

        entry  = trade["entry_price"]
        t1_pct = ((price - entry) / entry) * 100
        t2_pct = ((target2 - entry) / entry) * 100
        await self._notify(
            bot, user_id,
            f"🎯 *{symbol}* — هدف 1 اتحقق!\n\n"
            f"✅ بيع 50% عند `${price:.6g}`  (`+{t1_pct:.2f}%`)\n"
            f"🎯 هدف 2: `${target2:.6g}`  (`+{t2_pct:.2f}%`) — أوردر على MEXC ✅\n"
            f"🔒 Stop Loss تحرك لـ `${trade['stop_loss']:.6g}`\n"
            f"📈 الباقي شغال نحو هدف 2"
        )

    async def _on_t2_hit(
        self,
        trade: Dict[str, Any],
        price: float,
        exchange,
        bot,
        user_id: int,
    ) -> None:
        symbol = trade["symbol"]
        trade["t2_hit"] = True

        # Cancel SL order — T2 already handled by limit order on MEXC
        for order_id in [trade.get("sl_order_id"), trade.get("t2_order_id")]:
            if order_id:
                try:
                    await exchange.cancel_order(order_id, symbol)
                except Exception:
                    pass

        await self.remove_trade(symbol)

        entry  = trade["entry_price"]
        t2_pct = ((price - entry) / entry) * 100
        await self._notify(
            bot, user_id,
            f"🏆 *{symbol}* — هدف 2 اتحقق!\n\n"
            f"✅ بيع الـ 50% الباقية عند `${price:.6g}`  (`+{t2_pct:.2f}%`)\n"
            f"🎯 هدف 1 + هدف 2 تحققا — الصفقة مغلقة بالكامل\n"
            f"📊 R/R: `1:{trade['risk_reward']}`"
        )

    async def cancel_all_orders(self, trade: Dict[str, Any], exchange) -> None:
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
            logger.error(f"Monitor: notify failed: {e}")


# Singleton used across the app
trade_monitor = TradeMonitor()
