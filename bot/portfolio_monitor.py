"""
Portfolio take-profit / stop-loss monitor — runs every 5 minutes.

For each portfolio with tp_enabled=1:
  1. Fetch current value of all portfolio coins from MEXC.
  2. Compare against tp_entry_value (value at the time targets were activated).
  3. If TP1 hit → sell tp1_sell_pct% of every coin at market, mark tp1_hit=1.
  4. If TP2 hit (and TP1 already hit) → sell tp2_sell_pct% of remaining, mark tp2_hit=1.
  5. If SL hit → sell all remaining coins, disable monitoring.
  6. Notify user via Telegram after each action.

Target types:
  pct  — percentage gain/loss from entry value (e.g. +10% or -5%)
  usdt — absolute portfolio value in USDT (e.g. $55 means sell when portfolio reaches $55)
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

from bot.config import config
from bot.database import db
from bot.mexc_client import MexcClient

logger = logging.getLogger(__name__)


def _target_reached(current_value: float, entry_value: float, tp_type: str, tp_value: float, is_sl: bool = False) -> bool:
    """Return True if the target/stop condition is met."""
    if tp_value <= 0 or entry_value <= 0:
        return False
    if tp_type == "pct":
        change_pct = ((current_value - entry_value) / entry_value) * 100
        return change_pct <= -tp_value if is_sl else change_pct >= tp_value
    else:  # usdt
        return current_value <= tp_value if is_sl else current_value >= tp_value


async def _sell_portfolio_pct(
    exchange,
    allocations: List[Dict],
    sell_pct: float,
    quote: str = None,
) -> List[str]:
    """
    Sell sell_pct% of each coin in the portfolio at market price.
    Fetches balance once for all coins instead of once per coin.
    Returns a list of result lines for the notification message.
    """
    quote = quote or config.quote_currency or "USDT"
    results = []

    # Single balance fetch for all coins
    try:
        balance = await exchange.fetch_balance()
        free_balances = balance.get("free", {})
    except Exception as e:
        return [f"❌ تعذّر جلب الرصيد: {str(e)[:80]}"]

    for a in allocations:
        sym  = a["symbol"]
        if sym == quote:
            continue
        pair = f"{sym}/{quote}"
        try:
            qty_total   = float(free_balances.get(sym, 0) or 0)
            qty_to_sell = round(qty_total * (sell_pct / 100.0), 8)
            if qty_to_sell <= 0:
                results.append(f"⏭ `{sym}`: رصيد صفر")
                continue
            await exchange.create_market_sell_order(pair, qty_to_sell)
            results.append(f"✅ بيع `{sym}` — {sell_pct:.0f}%")
        except Exception as e:
            results.append(f"❌ `{sym}`: {str(e)[:60]}")
    return results


async def run_portfolio_monitor(app) -> None:
    """Check all portfolios with tp_enabled=1 against current market prices."""
    try:
        portfolios = await db.get_all_portfolios_with_tp()
    except Exception as e:
        logger.error(f"PortfolioMonitor: failed to fetch portfolios: {e}")
        return

    for p in portfolios:
        portfolio_id = p["id"]
        user_id      = p["user_id"]
        try:
            await _check_portfolio(app, p)
        except Exception as e:
            logger.error(f"PortfolioMonitor: error portfolio={portfolio_id} user={user_id}: {e}")


async def _check_portfolio(app, p: Dict[str, Any]) -> None:
    portfolio_id = p["id"]
    user_id      = p["user_id"]

    tp1_hit  = bool(p.get("tp1_hit"))
    tp2_hit  = bool(p.get("tp2_hit"))

    # Both targets already hit — nothing left to do, disable monitoring
    if tp1_hit and tp2_hit:
        await db.update_portfolio(portfolio_id, tp_enabled=0)
        return

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        return

    allocations = await db.get_portfolio_allocations(portfolio_id)
    if not allocations:
        return

    quote = settings.get("quote_currency") or config.quote_currency or "USDT"

    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    try:
        portfolio_balances, _ = await client.get_portfolio()
    except Exception as e:
        logger.warning(f"PortfolioMonitor: get_portfolio failed for {portfolio_id}: {e}")
        await client.close()
        return

    # Current value = sum of portfolio coins only
    alloc_symbols   = {a["symbol"] for a in allocations}
    current_value   = sum(
        portfolio_balances.get(sym, {}).get("value_usdt", 0.0)
        for sym in alloc_symbols
    )
    entry_value = float(p.get("tp_entry_value") or 0)

    if entry_value <= 0 or current_value <= 0:
        await client.close()
        return

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ── Stop Loss ──────────────────────────────────────────────────────────────
    sl_value = float(p.get("sl_value") or 0)
    sl_type  = p.get("sl_type") or "pct"
    if sl_value > 0 and _target_reached(current_value, entry_value, sl_type, sl_value, is_sl=True):
        results = await _sell_portfolio_pct(client.exchange, allocations, 100.0, quote=quote)
        await db.update_portfolio(portfolio_id, tp_enabled=0, tp1_hit=1, tp2_hit=1)
        result_text = "\n".join(results)
        sl_desc = f"-{sl_value}%" if sl_type == "pct" else f"${sl_value:.2f}"
        await _notify(
            app, user_id,
            f"🛑 *{p['name']}* — وقف الخسارة اتحقق!\n\n"
            f"📉 القيمة الحالية: `${current_value:.2f}`\n"
            f"🔒 وقف الخسارة: `{sl_desc}`\n\n"
            f"*الصفقات:*\n{result_text}\n\n"
            f"🕐 {now_str}"
        )
        await client.close()
        return

    # ── Take Profit 1 ──────────────────────────────────────────────────────────
    if not tp1_hit:
        tp1_value    = float(p.get("tp1_value") or 0)
        tp1_type     = p.get("tp1_type") or "pct"
        tp1_sell_pct = float(p.get("tp1_sell_pct") or 50.0)
        if tp1_value > 0 and _target_reached(current_value, entry_value, tp1_type, tp1_value):
            results = await _sell_portfolio_pct(client.exchange, allocations, tp1_sell_pct, quote=quote)
            await db.update_portfolio(portfolio_id, tp1_hit=1)
            result_text = "\n".join(results)
            tp1_desc = f"+{tp1_value}%" if tp1_type == "pct" else f"${tp1_value:.2f}"
            pnl_pct  = ((current_value - entry_value) / entry_value) * 100
            await _notify(
                app, user_id,
                f"🎯 *{p['name']}* — هدف 1 اتحقق!\n\n"
                f"📈 القيمة الحالية: `${current_value:.2f}`  (`+{pnl_pct:.2f}%`)\n"
                f"🎯 الهدف: `{tp1_desc}`\n"
                f"💰 تم بيع `{tp1_sell_pct:.0f}%` من كل عملة\n\n"
                f"*الصفقات:*\n{result_text}\n\n"
                f"🕐 {now_str}"
            )
            await client.close()
            return

    # ── Take Profit 2 (only after TP1 hit) ────────────────────────────────────
    if tp1_hit and not tp2_hit:
        tp2_value    = float(p.get("tp2_value") or 0)
        tp2_type     = p.get("tp2_type") or "pct"
        tp2_sell_pct = float(p.get("tp2_sell_pct") or 100.0)
        if tp2_value > 0 and _target_reached(current_value, entry_value, tp2_type, tp2_value):
            results = await _sell_portfolio_pct(client.exchange, allocations, tp2_sell_pct, quote=quote)
            await db.update_portfolio(portfolio_id, tp2_hit=1, tp_enabled=0)
            result_text = "\n".join(results)
            tp2_desc = f"+{tp2_value}%" if tp2_type == "pct" else f"${tp2_value:.2f}"
            pnl_pct  = ((current_value - entry_value) / entry_value) * 100
            await _notify(
                app, user_id,
                f"🏆 *{p['name']}* — هدف 2 اتحقق!\n\n"
                f"📈 القيمة الحالية: `${current_value:.2f}`  (`+{pnl_pct:.2f}%`)\n"
                f"🏆 الهدف: `{tp2_desc}`\n"
                f"💰 تم بيع `{tp2_sell_pct:.0f}%` من الباقي\n\n"
                f"*الصفقات:*\n{result_text}\n\n"
                f"🕐 {now_str}"
            )
            await client.close()
            return

    await client.close()


async def _notify(app, user_id: int, text: str) -> None:
    try:
        await app.bot.send_message(user_id, text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"PortfolioMonitor: notify failed user={user_id}: {e}")
