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
        await query.edit_message_text(
            "🏠 *القائمة الرئيسية*\n\nاختر ما تريد:",
            parse_mode="Markdown",
            reply_markup=main_menu_kb(),
        )

    elif action == "settings":
        settings = await db.get_settings(user_id)
        auto_on   = bool(settings.get("auto_enabled"))   if settings else False
        has_api   = bool(settings.get("mexc_api_key"))   if settings else False
        threshold = settings.get("threshold", 5.0)       if settings else 5.0
        interval  = settings.get("auto_interval_hours", 24) if settings else 24
        allocs    = await db.get_allocations(user_id)

        portfolio_id   = await db.get_active_portfolio_id(user_id)
        portfolio_line = ""
        if portfolio_id:
            p = await db.get_portfolio(portfolio_id)
            if p:
                portfolio_line = f"\n🗂 المحفظة النشطة: *{p['name']}*"

        api_icon   = "✅" if has_api  else "❌"
        auto_icon  = "🟢" if auto_on  else "🔴"
        alloc_line = f"📊 {len(allocs)} عملة" if allocs else "📊 لا يوجد توزيع"
        auto_line  = f"{auto_icon} تلقائي كل {interval} ساعة" if auto_on else f"{auto_icon} التوازن التلقائي معطل"

        text = (
            f"⚙️ *الإعدادات*{portfolio_line}\n\n"
            f"{api_icon} API{'  ·  ' + alloc_line}\n"
            f"🎯 حد الانحراف: *{threshold}%*\n"
            f"{auto_line}"
        )
        await query.edit_message_text(
            text, parse_mode="Markdown", reply_markup=settings_kb(auto_on)
        )

    elif action == "info":
        await query.edit_message_text(
            "💡 *كيف تبدأ*\n\n"
            "1️⃣ ⚙️ الإعدادات ← ربط مفاتيح MEXC API\n"
            "2️⃣ 🗂 محافظي ← إنشاء محفظة وتحديد رأس المال\n"
            "3️⃣ الإعدادات ← إضافة العملات بنسبها المستهدفة\n"
            "4️⃣ ⚖️ إعادة التوازن ← تنفيذ يدوي أو تلقائي\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "كل محفظة لها رأس مال وعملات ونسب مستقلة تماماً\n"
            "يمكن تفعيل التوازن التلقائي لكل محفظة على حدة",
            parse_mode="Markdown",
            reply_markup=main_menu_kb(),
        )
