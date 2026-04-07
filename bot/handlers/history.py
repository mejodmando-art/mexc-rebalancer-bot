from telegram import Update
from telegram.ext import ContextTypes
from bot.database import db
from bot.keyboards import main_menu_kb


async def history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    history = await db.get_history(user_id, limit=10)

    if not history:
        await query.edit_message_text(
            "📋 *سجل العمليات*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "لا توجد عمليات مسجلة بعد.\n\n"
            "_نفّذ أول عملية توازن لتظهر هنا_",
            parse_mode="Markdown",
            reply_markup=main_menu_kb()
        )
        return

    text = "📋 *آخر 10 عمليات*\n━━━━━━━━━━━━━━━━━━━━━\n\n"

    for h in history:
        # Skip internal momentum_loss accounting entries
        if h["summary"].startswith("momentum_loss:"):
            continue
        icon   = "✅" if h["success"] else "❌"
        p_name = h.get("portfolio_name") or ""
        p_label = f"  🗂 `{p_name}`\n" if p_name else ""
        text += (
            f"{icon} `{h['timestamp']}`\n"
            f"{p_label}"
            f"  📝 {h['summary']}\n"
            f"  💵 `${h['total_traded_usdt']:.2f}`\n\n"
        )

    text += "━━━━━━━━━━━━━━━━━━━━━"
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_kb())
