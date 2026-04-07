"""
Momentum trade monitor — runs every 60 seconds.

For each open momentum trade:
  - Fetch current price
  - Check T1 (+2%): sell 50%, move SL to breakeven
  - Check T2 (+4%): sell remaining 50%
  - Check SL: sell all immediately
  - Check max age (2 hours): sell all if trade is too old
  - Notify user after every action
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from bot.database import db

logger = logging.getLogger(__name__)

MAX_TRADE_AGE_HOURS = 2


class MomentumMonitor:
    """Holds open trades in memory and checks them on each tick."""

    def __init__(self):
        # symbol → trade dict
        self._trades: Dict[str, Dict[str, Any]] = {}

    # ── State management ───────────────────────────────────────────────────

    def add_trade(self, trade: dict) -> None:
        self._trades[trade["symbol"]] = trade

    def remove_trade(self, symbol: str) -> None:
        self._trades.pop(symbol, None)

    def open_symbols(self) -> set:
        return set(self._trades.keys())

    def open_symbols_for(self, user_id: int) -> set:
        return {s for s, t in self._trades.items() if t["user_id"] == user_id}

    def open_trades_for(self, user_id: int) -> list:
        return [t for t in self._trades.values() if t["user_id"] == user_id]

    async def restore_from_db(self) -> None:
        """Reload open trades from DB on bot startup."""
        rows = await db.load_momentum_trades()
        for row in rows:
            self._trades[row["symbol"]] = dict(row)
        if self._trades:
            logger.info(f"MomentumMonitor: restored {len(self._trades)} open trades")

    # ── Main tick ──────────────────────────────────────────────────────────

    async def tick(self, app) -> None:
        """Called every 60 seconds. Checks all open trades."""
        if not self._trades:
            return

        # Group trades by user to reuse one exchange client per user
        by_user: Dict[int, list] = {}
        for trade in list(self._trades.values()):
            by_user.setdefault(trade["user_id"], []).append(trade)

        for user_id, trades in by_user.items():
            settings = await db.get_settings(user_id)
            if not settings or not settings.get("mexc_api_key"):
                continue
            try:
                import ccxt.async_support as ccxt
                exchange = ccxt.mexc({
                    "apiKey":          settings["mexc_api_key"],
                    "secret":          settings["mexc_secret_key"],
                    "enableRateLimit": True,
                    "timeout":         10000,
                    "options":         {"defaultType": "spot"},
                })
                # Fetch all prices for this user's open symbols in one call
                pairs = [f"{t['symbol']}/USDT" for t in trades]
                try:
                    tickers = await exchange.fetch_tickers(pairs)
                except Exception:
                    tickers = {}

                for trade in trades:
                    try:
                        await self._check_trade(app, exchange, trade, tickers, user_id)
                    except Exception as e:
                        logger.error(f"MomentumMonitor: error on {trade['symbol']}: {e}")
            except Exception as e:
                logger.error(f"MomentumMonitor: exchange init failed user={user_id}: {e}")
            finally:
                try:
                    await exchange.close()
                except Exception:
                    pass

    async def _check_trade(self, app, exchange, trade: dict, tickers: dict, user_id: int) -> None:
        symbol     = trade["symbol"]
        pair       = f"{symbol}/USDT"
        entry      = float(trade["entry_price"])
        stop_loss  = float(trade["stop_loss"])
        target1    = float(trade["target1"])
        target2    = float(trade["target2"])
        t1_hit     = bool(trade.get("t1_hit"))
        qty        = float(trade["qty"])
        qty_half   = float(trade["qty_half"])
        opened_at  = trade.get("opened_at", "")

        # Current price
        ticker     = tickers.get(pair, {})
        price      = float(ticker.get("last") or ticker.get("close") or 0)
        if price <= 0:
            return

        now     = datetime.now(timezone.utc)
        now_str = now.strftime("%Y-%m-%d %H:%M UTC")

        # ── Max age check ──────────────────────────────────────────────────
        if opened_at:
            try:
                opened_dt = datetime.fromisoformat(opened_at.replace(" UTC", "+00:00"))
                if now - opened_dt > timedelta(hours=MAX_TRADE_AGE_HOURS):
                    await self._close_trade(
                        app, exchange, trade, price, qty, user_id, now_str,
                        reason=f"⏰ انتهى وقت الصفقة ({MAX_TRADE_AGE_HOURS} ساعة)"
                    )
                    return
            except Exception:
                pass

        # ── Stop loss ──────────────────────────────────────────────────────
        if price <= stop_loss:
            remaining_qty = qty_half if t1_hit else qty
            await self._close_trade(
                app, exchange, trade, price, remaining_qty, user_id, now_str,
                reason="🛑 وقف الخسارة"
            )
            return

        # ── Target 2 (only after T1) ───────────────────────────────────────
        if t1_hit and price >= target2:
            await self._close_trade(
                app, exchange, trade, price, qty_half, user_id, now_str,
                reason="🏆 الهدف 2"
            )
            return

        # ── Target 1 ──────────────────────────────────────────────────────
        if not t1_hit and price >= target1:
            await self._hit_target1(app, exchange, trade, price, user_id, now_str)
            return

    async def _hit_target1(self, app, exchange, trade: dict, price: float,
                           user_id: int, now_str: str) -> None:
        symbol   = trade["symbol"]
        pair     = f"{symbol}/USDT"
        qty_half = float(trade["qty_half"])
        entry    = float(trade["entry_price"])
        pnl_pct  = ((price - entry) / entry) * 100

        try:
            await exchange.create_market_sell_order(pair, qty_half)
        except Exception as e:
            logger.error(f"MomentumMonitor: T1 sell failed {symbol}: {e}")
            return

        # Move SL to breakeven
        new_sl = round(entry * 1.001, 8)  # entry + 0.1% buffer
        trade["stop_loss"] = new_sl
        trade["t1_hit"]    = 1
        await db.update_momentum_trade(symbol, stop_loss=new_sl, t1_hit=1)

        pnl_usdt = qty_half * (price - entry)
        await _notify(
            app, user_id,
            f"🎯 *Momentum — الهدف 1*\n\n"
            f"📈 `{symbol}`\n"
            f"💰 بيع 50% بسعر `${price:.6g}`\n"
            f"📊 ربح: `+{pnl_pct:.2f}%`  (`+${pnl_usdt:.2f}`)\n"
            f"🔒 SL تحرّك لـ Breakeven\n"
            f"🕐 {now_str}"
        )

    async def _close_trade(self, app, exchange, trade: dict, price: float,
                           qty: float, user_id: int, now_str: str, reason: str) -> None:
        symbol = trade["symbol"]
        pair   = f"{symbol}/USDT"
        entry  = float(trade["entry_price"])
        pnl_pct = ((price - entry) / entry) * 100
        pnl_usdt = qty * (price - entry)

        try:
            await exchange.create_market_sell_order(pair, qty)
        except Exception as e:
            logger.error(f"MomentumMonitor: close sell failed {symbol}: {e}")
            return

        self.remove_trade(symbol)
        await db.delete_momentum_trade(symbol)

        sign = "+" if pnl_usdt >= 0 else ""
        await _notify(
            app, user_id,
            f"{'✅' if pnl_usdt >= 0 else '❌'} *Momentum — {reason}*\n\n"
            f"📈 `{symbol}`\n"
            f"💰 بيع بسعر `${price:.6g}`\n"
            f"📊 نتيجة: `{sign}{pnl_pct:.2f}%`  (`{sign}${pnl_usdt:.2f}`)\n"
            f"🕐 {now_str}"
        )


async def _notify(app, user_id: int, text: str) -> None:
    try:
        await app.bot.send_message(user_id, text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"MomentumMonitor: notify failed user={user_id}: {e}")


# Singleton used by handler and main
momentum_monitor = MomentumMonitor()
