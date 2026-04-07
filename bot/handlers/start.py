from telegram import Update
from telegram.ext import ContextTypes
from bot.config import config
from bot.keyboards import main_menu_kb


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if config.allowed_user_ids and user.id not in config.allowed_user_ids:
        await update.message.reply_text("⛔ غير مصرح لك باستخدام هذا البوت.")
        return

    await update.message.reply_text(
        f"👋 أهلاً *{user.first_name}*\n\n"
        "🤖 *MEXC Rebalancer Bot*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🗂️ *محافظي* — إدارة المحافظ وإعادة التوازن\n"
        "⚡ *Momentum* — استراتيجية الاختراق التلقائي\n"
        "🔲 *Grid Bot* — شبكة أوامر تلقائية\n"
        "⚙️ *الإعدادات* — ربط MEXC API\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "ابدأ من ⚙️ *الإعدادات* لربط مفاتيح MEXC",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *دليل الاستخدام*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚙️ *الإعداد الأولي*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ الإعدادات ← ربط مفاتيح MEXC API\n"
        "2️⃣ محافظي ← إنشاء محفظة وتحديد رأس المال\n"
        "3️⃣ إضافة العملات بنسبها المستهدفة\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🪙 *إضافة العملات*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "أرسل الرموز: `BTC ETH SOL USDT`\n"
        "أو بالنسب مباشرة:\n"
        "`BTC=40 ETH=30 SOL=20 USDT=10`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 *طرق التوزيع*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚖️ متساوٍ  ·  📈 حسب السوق  ·  ✏️ يدوي\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ *Momentum Breakout*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "يبحث كل 10 دقائق عن اختراقات حجم قوية\n"
        "T1: +2% يبيع 50% ويحرك SL للـ Breakeven\n"
        "T2: +4% يبيع الباقي\n\n"
        "`/cancel` — إلغاء أي عملية جارية",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏠 *القائمة الرئيسية*",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🏠 *القائمة الرئيسية*",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )
