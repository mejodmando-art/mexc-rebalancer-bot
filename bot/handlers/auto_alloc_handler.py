"""
التوزيع الذكي التلقائي للعملات.
المستخدم يختار الطريقة → البوت يحسب النسب من MEXC → يعرضها → يؤكد → يحفظ.
"""
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from bot.database import db
from bot.keyboards import (
    auto_alloc_methods_kb,
    auto_alloc_confirm_kb,
)

_METHOD_LABELS = {
    "equal":  "⚖️ توزيع متساوٍ",
    "volume": "📊 حسب حجم التداول",
    "mcap":   "📈 حسب القيمة السوقية",
}


async def auto_alloc_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة طرق التوزيع الذكي."""
    query = update.callback_query
    await query.answer()
    portfolio_id = int(query.data.split(":")[1])
    user_id = update.effective_user.id

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    allocs = await db.get_portfolio_allocations(portfolio_id)
    if not allocs:
        await query.edit_message_text(
            "❌ لا توجد عملات في المحفظة.\nأضف العملات أولاً ثم اختر طريقة التوزيع.",
            reply_markup=auto_alloc_methods_kb(portfolio_id),
        )
        return

    capital = float(p.get("capital_usdt") or 0.0)
    capital_str = f"${capital:,.1f}" if capital > 0 else "غير محدد"

    await query.edit_message_text(
        f"🤖 *التوزيع الذكي التلقائي*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 المحفظة: *{p['name']}*\n"
        f"💰 رأس المال: *{capital_str}*\n"
        f"🪙 العملات: *{len(allocs)} عملة*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"اختر طريقة حساب النسب:",
        parse_mode="Markdown",
        reply_markup=auto_alloc_methods_kb(portfolio_id),
    )


async def auto_alloc_preview_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    احسب النسب بالطريقة المختارة وعرضها للمستخدم قبل التطبيق.
    callback_data = auto_alloc:{method}:{portfolio_id}
    """
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    parts = query.data.split(":")
    method = parts[1]
    portfolio_id = int(parts[2])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    allocs = await db.get_portfolio_allocations(portfolio_id)
    if not allocs:
        await query.answer("❌ لا توجد عملات", show_alert=True)
        return

    await query.edit_message_text("⏳ جاري حساب النسب...")

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.edit_message_text(
            "❌ يجب ربط مفاتيح MEXC API أولاً.",
            reply_markup=auto_alloc_methods_kb(portfolio_id),
        )
        return

    from bot.mexc_client import MexcClient
    symbols = [a["symbol"] for a in allocs]
    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    try:
        new_allocs = await asyncio.wait_for(
            client.compute_allocations(symbols, method), timeout=20
        )
    except asyncio.TimeoutError:
        await query.edit_message_text(
            "❌ انتهت المهلة — MEXC لم يستجب.",
            reply_markup=auto_alloc_methods_kb(portfolio_id),
        )
        return
    except Exception as e:
        await query.edit_message_text(
            f"❌ خطأ: {str(e)[:100]}",
            reply_markup=auto_alloc_methods_kb(portfolio_id),
        )
        return
    finally:
        await client.close()

    # حفظ النسب المحسوبة مؤقتاً في user_data
    context.user_data["_auto_alloc_preview"] = new_allocs
    context.user_data["_auto_alloc_portfolio_id"] = portfolio_id

    capital = float(p.get("capital_usdt") or 0.0)
    method_label = _METHOD_LABELS.get(method, method)

    text = (
        f"🤖 *{method_label}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 *{p['name']}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
    )
    for a in new_allocs:
        val = capital * a["target_percentage"] / 100 if capital > 0 else 0
        val_str = f"  `${val:,.1f}`" if val > 0 else ""
        bar_len = max(1, round(a["target_percentage"] / 5))
        bar = "█" * bar_len + "░" * max(0, 20 - bar_len)
        text += f"`{a['symbol']:6}` {bar} *{a['target_percentage']:.2f}%*{val_str}\n"

    text += f"━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📌 المجموع: *100%*\n\n"
    text += "هل تريد تطبيق هذه النسب؟"

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=auto_alloc_confirm_kb(portfolio_id, method),
    )


async def auto_alloc_apply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    تطبيق النسب المحسوبة وحفظها في قاعدة البيانات.
    callback_data = auto_alloc_apply:{method}:{portfolio_id}
    """
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    parts = query.data.split(":")
    method = parts[1]
    portfolio_id = int(parts[2])

    new_allocs = context.user_data.get("_auto_alloc_preview", [])
    saved_pid  = context.user_data.get("_auto_alloc_portfolio_id")

    if not new_allocs or saved_pid != portfolio_id:
        await query.edit_message_text(
            "❌ انتهت الجلسة. أعد الحساب من 🤖 توزيع ذكي.",
            reply_markup=auto_alloc_methods_kb(portfolio_id),
        )
        return

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    # حفظ النسب الجديدة — نحذف القديمة ونضيف الجديدة
    await db.clear_portfolio_allocations(portfolio_id)
    for a in new_allocs:
        await db.set_portfolio_allocation(
            portfolio_id, user_id, a["symbol"], a["target_percentage"]
        )

    context.user_data.pop("_auto_alloc_preview", None)
    context.user_data.pop("_auto_alloc_portfolio_id", None)

    method_label = _METHOD_LABELS.get(method, method)

    # إعادة بناء شاشة المحفظة
    from bot.handlers.portfolio_manager import _portfolio_kb
    kb = await _portfolio_kb(portfolio_id, user_id)

    capital = float(p.get("capital_usdt") or 0.0)
    capital_str = f"${capital:,.1f} USD" if capital > 0 else "بدون رأس مال"
    updated_allocs = await db.get_portfolio_allocations(portfolio_id)
    total_pct = sum(a["target_percentage"] for a in updated_allocs)

    await query.edit_message_text(
        f"✅ *تم تطبيق {method_label}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 *{p['name']}*\n"
        f"💰 *{capital_str}*          💰 *{capital_str}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 *العملات \\({len(updated_allocs)}\\)*",
        parse_mode="Markdown",
        reply_markup=kb,
    )
