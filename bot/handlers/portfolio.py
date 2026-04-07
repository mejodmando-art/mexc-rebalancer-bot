import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from bot.database import db
from bot.keyboards import main_menu_kb, back_to_main_kb
from bot.mexc_client import MexcClient
from bot.rebalancer import calculate_trades


async def portfolio_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    await query.edit_message_text("⏳ جاري جلب بيانات المحفظة...")

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.edit_message_text(
            "❌ يجب ربط مفاتيح MEXC API أولاً.\n\nاذهب إلى 🛠 الإعدادات.",
            reply_markup=main_menu_kb()
        )
        return

    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    try:
        portfolio, total_usdt = await asyncio.wait_for(client.get_portfolio(), timeout=20)
    except asyncio.TimeoutError:
        await query.edit_message_text("❌ انتهت المهلة — MEXC لم يستجب. حاول مجدداً.", reply_markup=main_menu_kb())
        return
    except Exception as e:
        await query.edit_message_text(f"❌ خطأ: {str(e)[:100]}", reply_markup=main_menu_kb())
        return
    finally:
        await client.close()

    if not portfolio:
        await query.edit_message_text("📊 المحفظة فارغة.", reply_markup=main_menu_kb())
        return

    portfolio_id = await db.ensure_active_portfolio(user_id)
    portfolio_info = await db.get_portfolio(portfolio_id)
    allocations = await db.get_portfolio_allocations(portfolio_id)
    threshold = settings.get("threshold", 5.0)

    capital = portfolio_info.get("capital_usdt", 0.0) if portfolio_info else 0.0
    # Use min(capital, actual_balance) so displayed percentages match rebalance logic.
    # If no capital budget is set, use the full account balance.
    effective_total = min(capital, total_usdt) if capital > 0 else total_usdt

    portfolio_name = portfolio_info.get("name", "") if portfolio_info else ""

    rows = sorted(portfolio.items(), key=lambda x: x[1]["value_usdt"], reverse=True)

    # Build allocation map for drift display
    alloc_map = {a["symbol"]: a["target_percentage"] for a in allocations}

    text = (
        f"💼 *{portfolio_name or 'محفظتي'}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 الإجمالي: *${total_usdt:,.2f} USDT*\n"
    )
    if capital > 0:
        text += f"🎯 رأس المال: *${capital:,.2f} USDT*\n"
    text += "━━━━━━━━━━━━━━━━━━━━━\n\n"

    for sym, data in rows:
        val  = data["value_usdt"]
        pct  = (val / effective_total * 100) if effective_total > 0 else 0
        tgt  = alloc_map.get(sym)

        if sym == "USDT":
            bar = _pct_bar(pct)
            text += f"💵 *USDT*\n"
            text += f"   `${val:>10,.2f}`  {bar}  `{pct:.1f}%`\n\n"
        else:
            bar = _pct_bar(pct)
            drift_str = ""
            if tgt is not None:
                drift = pct - tgt
                drift_str = f"  `{drift:+.1f}%`" if abs(drift) >= 0.5 else ""
            text += f"🔹 *{sym}*\n"
            text += f"   `${val:>10,.2f}`  {bar}  `{pct:.1f}%`{drift_str}\n\n"

    text += "━━━━━━━━━━━━━━━━━━━━━"

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_kb())


def _pct_bar(pct: float, width: int = 8) -> str:
    """Return a compact visual bar for a percentage (0–100)."""
    filled = round(pct / 100 * width)
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)
