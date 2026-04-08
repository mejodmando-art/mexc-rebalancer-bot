from telegram import Update
from telegram.ext import ContextTypes
from bot.database import db
from bot.keyboards import main_menu_kb, settings_kb


async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1] if ":" in query.data else "main"
    user_id = update.effective_user.id

    if action == "main":
        # الواجهة الرئيسية = شاشة المحفظة النشطة
        from bot.handlers.start import _show_home
        await _show_home(update, context)
        return

    elif action == "settings":
        settings = await db.get_settings(user_id)
        has_api  = bool(settings.get("mexc_api_key")) if settings else False
        api_icon = "✅" if has_api else "❌"

        text = (
            f"⚙️ *الإعدادات العامة*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"{api_icon} MEXC API: *{'مربوط' if has_api else 'غير مربوط'}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 إعدادات إعادة التوازن (حد الانحراف، فترة التوازن، التلقائي)\n"
            f"موجودة داخل شاشة المحفظة مباشرة."
        )
        await query.edit_message_text(
            text, parse_mode="Markdown", reply_markup=settings_kb()
        )

    elif action == "info":
        await query.edit_message_text(
            "💡 *كيف تبدأ*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "1️⃣ ⚙️ *الإعدادات* ← ربط مفاتيح MEXC API\n"
            "2️⃣ 🗂 *محافظي* ← إنشاء محفظة وتحديد رأس المال\n"
            "3️⃣ إضافة العملات بنسبها المستهدفة\n"
            "4️⃣ ⚖️ *إعادة التوازن* ← يدوي أو تلقائي\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 كل محفظة لها رأس مال وعملات ونسب مستقلة\n"
            "📌 التوازن التلقائي يعمل لكل محفظة على حدة\n"
            "📌 ⚡ Momentum يبحث عن اختراقات كل 10 دقائق",
            parse_mode="Markdown",
            reply_markup=main_menu_kb(),
        )
