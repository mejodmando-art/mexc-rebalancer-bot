import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.config import config
from bot.database import db
from bot.keyboards import main_menu_kb


def _build_home_text(p: dict, allocs: list, capital: float, total_account=None) -> str:
    """بناء نص الشاشة الرئيسية — يُستخدم مرتين (فوري + بعد MEXC)."""
    total_pct = sum(a["target_percentage"] for a in allocs)
    lines = [f"📁 *{p['name']}*", "━━━━━━━━━━━━━━━━━━━━━"]
    if total_account is not None:
        lines.append(f"🏦  الحساب:    `${total_account:,.2f} USDT`")
    if capital > 0:
        lines.append(f"💼  المحفظة:   `${capital:,.2f} USDT`")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    if allocs:
        pct_warn = f"⚠️ مجموع النسب `{total_pct:.1f}%`" if abs(total_pct - 100) > 1 else ""
        lines.append(f"🪙  *{len(allocs)} عملة*" + (f"  {pct_warn}" if pct_warn else ""))
    else:
        lines.append("🪙  لا توجد عملات — اضغط *تعديل العملات*")
    return "\n".join(lines)


async def _show_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    الواجهة الرئيسية — تُرسل فوراً بدون انتظار MEXC،
    ثم تُحدَّث بالرصيد الحي في الخلفية.
    """
    from bot.handlers.portfolio_manager import _portfolio_kb

    user_id      = update.effective_user.id
    portfolio_id = await db.ensure_active_portfolio(user_id)
    p            = await db.get_portfolio(portfolio_id) if portfolio_id else None

    if not p:
        text = (
            "👋 *أهلاً بك في MEXC Rebalancer*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
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

    allocs  = await db.get_portfolio_allocations(portfolio_id)
    capital = float(p.get("capital_usdt") or 0.0)
    kb      = await _portfolio_kb(portfolio_id, user_id)

    # ── إرسال فوري بدون رصيد MEXC ────────────────────────────────────────────
    text_initial = _build_home_text(p, allocs, capital, total_account=None)
    if update.message:
        sent = await update.message.reply_text(
            text_initial, parse_mode="Markdown", reply_markup=kb
        )
    else:
        await update.callback_query.edit_message_text(
            text_initial, parse_mode="Markdown", reply_markup=kb
        )
        sent = update.callback_query.message

    # ── جلب رصيد MEXC في الخلفية وتحديث الرسالة ─────────────────────────────
    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        return

    try:
        from bot.mexc_client import MexcClient
        client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
        try:
            _, total_account = await asyncio.wait_for(
                client.get_portfolio(), timeout=8
            )
        finally:
            await client.close()

        text_updated = _build_home_text(p, allocs, capital, total_account)
        if text_updated != text_initial:
            await sent.edit_text(text_updated, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        pass  # فشل جلب MEXC — الشاشة الأولية كافية


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Auth is enforced globally via TypeHandler in main.py — no check needed here
    await _show_home(update, context)


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *دليل الاستخدام*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣  🔑 *إعدادات API* ← ربط مفاتيح MEXC\n"
        "2️⃣  💰 *رأس المال* ← تحديد المبلغ\n"
        "3️⃣  ✏️ *تعديل العملات* ← أضف العملات بنسبها\n"
        "4️⃣  🔄 *إعادة التوازن* ← يدوي أو تلقائي\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🪙 *إضافة العملات*\n"
        "أرسل الرموز: `BTC ETH SOL`\n"
        "أو بالنسب:   `BTC=40 ETH=30 SOL=30`\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ *Momentum* — اختراقات تلقائية كل 10 دقائق\n"
        "🔲 *Grid Bot* — شبكة أوامر تلقائية\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
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
