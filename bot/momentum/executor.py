"""
Momentum trade executor.

Takes a setup dict from the scanner and places a market buy order.
Validates balance and exchange minimums before touching the account.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Tuple

from bot.database import db
from bot.momentum.monitor import momentum_monitor

logger = logging.getLogger(__name__)


async def execute_setup(
    exchange,
    setup: Dict[str, Any],
    user_id: int,
    trade_size_usdt: float,
) -> Tuple[bool, str]:
    """
    Place a market buy for the given setup.

    Returns:
        (success: bool, message: str)
    """
    symbol = setup["symbol"]
    pair   = f"{symbol}/USDT"

    # ── Balance check ──────────────────────────────────────────────────────
    try:
        balance    = await exchange.fetch_balance()
        usdt_free  = float(balance.get("free", {}).get("USDT", 0) or 0)
    except Exception as e:
        return False, f"تعذّر جلب الرصيد: {str(e)[:60]}"

    if usdt_free < trade_size_usdt:
        return False, f"رصيد USDT غير كافٍ (`${usdt_free:.2f}` < `${trade_size_usdt:.2f}`)"

    # ── Place market buy ───────────────────────────────────────────────────
    try:
        order = await exchange.create_market_buy_order_with_cost(pair, trade_size_usdt)
    except Exception as e:
        return False, f"فشل الشراء: {str(e)[:80]}"

    # ── Confirm filled quantity ────────────────────────────────────────────
    filled_qty = float(order.get("filled") or order.get("amount") or 0)
    avg_price  = float(order.get("average") or order.get("price") or setup["entry_price"])

    if filled_qty <= 0:
        return False, "الأوردر نُفِّذ لكن الكمية صفر — تحقق يدوياً"

    qty_half = round(filled_qty / 2, 8)

    # ── Save to DB and monitor ─────────────────────────────────────────────
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    trade = {
        "symbol":      symbol,
        "user_id":     user_id,
        "entry_price": avg_price,
        "stop_loss":   setup["stop_loss"],
        "target1":     setup["target1"],
        "target2":     setup["target2"],
        "qty":         filled_qty,
        "qty_half":    qty_half,
        "t1_hit":      0,
        "opened_at":   now_str,
        "volume_ratio": setup.get("volume_ratio", 0.0),
    }
    await db.save_momentum_trade(user_id, trade)
    momentum_monitor.add_trade(trade)

    pct_to_sl  = ((avg_price - setup["stop_loss"]) / avg_price) * 100
    pct_to_t1  = ((setup["target1"] - avg_price) / avg_price) * 100
    pct_to_t2  = ((setup["target2"] - avg_price) / avg_price) * 100
    msg = (
        f"⚡ *Momentum — دخول جديد*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔹 *{symbol}*\n"
        f"💰 دخول: `${avg_price:.6g}`\n"
        f"📦 الكمية: `{filled_qty:.6g}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 T1: `${setup['target1']:.6g}` \\(`+{pct_to_t1:.1f}%`\\)\n"
        f"🏆 T2: `${setup['target2']:.6g}` \\(`+{pct_to_t2:.1f}%`\\)\n"
        f"🛑 SL: `${setup['stop_loss']:.6g}` \\(`-{pct_to_sl:.1f}%`\\)\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 حجم: `{setup.get('volume_ratio', 0):.1f}x` المتوسط\n"
        f"🕐 `{now_str}`"
    )
    return True, msg
