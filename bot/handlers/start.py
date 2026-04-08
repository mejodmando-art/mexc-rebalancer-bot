import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.config import config
from bot.database import db
from bot.keyboards import main_menu_kb, settings_kb


async def _show_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    الواجهة الرئيسية = شاشة المحفظة النشطة.
    تعرض: الرصيد العام للحساب + رصيد المحفظة + العملات.
    """
    from bot.handlers.portfolio_manager import _portfolio_kb

    user_id = update.effective_user.id
    portfolio_id = await db.ensure_active_portfolio(user_id)
    p = await db.get_portfolio(portfolio_id) if portfolio_id else None

    if not p:
        text = (
            "👋 *أهلاً بك في MEXC Rebalancer*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "لا توجد محفظة بعد.\n"
            "ابدأ بإنشاء محفظتك الأولى 👇"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕  إنشاء محفظة", callback_data="portfolio_new")],
            [InlineKeyboardButton("🔑  إعدادات API",  callback_data="menu:settings")],
        ])
        if update.message:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
        return

    allocs    = await db.get_portfolio_allocations(portfolio_id)
    capital   = float(p.get("capital_usdt") or 0.0)
    total_pct = sum(a["target_percentage"] for a in allocs)

    # جلب الرصيد الحقيقي من MEXC (بدون انتظار طويل)
    total_account = None
    settings = await db.get_settings(user_id)
    if settings and settings.get("mexc_api_key"):
        try:
            from bot.mexc_client import MexcClient
            client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
            try:
                _, total_account = await asyncio.wait_for(
                    client.get_portfolio(), timeout=8
                )
            finally:
                await client.close()
        except Exception:
            total_account = None

    # بناء سطر الأرصدة
    if total_account is not None:
        account_str  = f"${total_account:,.2f}"
        portfolio_str = f"${capital:,.2f}" if capital > 0 else "—"
        balance_line = (
            f"🏦 *الرصيد العام:* `{account_str} USD`\n"
            f"💼 *رصيد المحفظة:* `{portfolio_str} USD`"
        )
    else:
        portfolio_str = f"${capital:,.2f}" if capital > 0 else "بدون رأس مال"
        balance_line = f"💼 *رصيد المحفظة:* `{portfolio_str} USD`"

    pct_warn = ""
    if allocs and abs(total_pct - 100) > 1:
        pct_warn = f"\n⚠️ مجموع النسب `{total_pct:.1f}%` — يجب أن يكون 100%"

    text = (
        f"📁 *{p['name']}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{balance_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 *العملات \\({len(allocs)}\\)*"
        f"{pct_warn}"
    )

    kb = await _portfolio_kb(portfolio_id, user_id)

    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if config.allowed_user_ids and user.id not in config.allowed_user_ids:
        await update.message.reply_text("⛔ غير مصرح لك باستخدام هذا البوت.")
        return
    await _show_home(update, context)


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *دليل الاستخدام*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚙️ *الإعداد الأولي*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ اضغط 🔑 إعدادات API ← ربط مفاتيح MEXC\n"
        "2️⃣ اضغط 💰 رأس المال ← تحديد المبلغ\n"
        "3️⃣ اضغط 🎯 تعديل العملات ← إضافة العملات بنسبها\n"
        "4️⃣ اضغط 🔄 إعادة التوازن الآن\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🪙 *إضافة العملات*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "أرسل الرموز: `BTC ETH SOL`\n"
        "أو بالنسب: `BTC=40 ETH=30 SOL=30`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ *Momentum* — اختراقات تلقائية كل 10 دقائق\n"
        "🔲 *Grid Bot* — شبكة أوامر تلقائية\n\n"
        "`/cancel` — إلغاء أي عملية جارية",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_home(update, context)


async def home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """callback_data='home'"""
    query = update.callback_query
    await query.answer()
    await _show_home(update, context)


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """callback_data='menu:main'"""
    query = update.callback_query
    await query.answer()
    await _show_home(update, context)
