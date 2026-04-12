"""
Smart Portfolio Telegram handler — Bitget-compatible.

Conversation states
-------------------
SP_MENU          Main Smart Portfolio menu
SP_SET_CAPITAL   Waiting for investment amount
SP_ADD_COIN      Waiting for coin symbol + percentage
SP_EDIT_COIN     Waiting for updated percentage for a coin
"""

import asyncio
import logging
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    CallbackQueryHandler, MessageHandler, filters,
)
from bot.database import db
from bot.mexc_client import MexcClient

log = logging.getLogger(__name__)

# ── Conversation states ────────────────────────────────────────────────────────
SP_MENU, SP_SET_CAPITAL, SP_ADD_COIN, SP_EDIT_COIN = range(40, 44)

# ── Constants ──────────────────────────────────────────────────────────────────
MIN_COINS = 2
MAX_COINS = 10
ALLOWED_THRESHOLDS = [1, 3, 5]
ALLOWED_INTERVALS  = ["daily", "weekly", "monthly"]
INTERVAL_LABELS    = {"daily": "يومياً", "weekly": "أسبوعياً", "monthly": "شهرياً"}
MODE_LABELS = {
    "proportional": "📊 النسبة المئوية",
    "timed":        "⏰ الفاصل الزمني",
    "unbalanced":   "✋ يدوي",
}

# ── Keyboard builders ──────────────────────────────────────────────────────────

def _sp_main_kb(sp: dict) -> InlineKeyboardMarkup:
    mode    = sp.get("rebalance_mode", "unbalanced")
    running = sp.get("is_running", 0)
    capital = sp.get("capital_usdt", 0.0)
    coins   = sp.get("coin_count", 0)
    toggle  = "🔴 إيقاف البوت" if running else "🟢 تشغيل البوت"
    cap_lbl = f"💰 رأس المال: ${capital:,.0f}" if capital > 0 else "💰 تحديد رأس المال"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle,                              callback_data="sp:toggle")],
        [InlineKeyboardButton(f"🪙 العملات ({coins})",            callback_data="sp:coins")],
        [InlineKeyboardButton(cap_lbl,                            callback_data="sp:set_capital")],
        [InlineKeyboardButton(f"⚙️ الوضع: {MODE_LABELS.get(mode, mode)}", callback_data="sp:mode_menu")],
        [InlineKeyboardButton("🔄 توازن يدوي",                   callback_data="sp:manual_rebalance")],
        [InlineKeyboardButton("📊 تقرير الانحراف",               callback_data="sp:drift_report")],
        [InlineKeyboardButton("🛑 إنهاء + بيع الكل",            callback_data="sp:terminate")],
        [InlineKeyboardButton("◀️ رجوع",                         callback_data="home")],
    ])


def _sp_mode_kb(current_mode: str) -> InlineKeyboardMarkup:
    rows = []
    for mode, label in MODE_LABELS.items():
        tick = "✅ " if mode == current_mode else ""
        rows.append([InlineKeyboardButton(f"{tick}{label}", callback_data=f"sp:set_mode:{mode}")])
    rows.append([InlineKeyboardButton("◀️ رجوع", callback_data="sp:menu")])
    return InlineKeyboardMarkup(rows)


def _sp_threshold_kb(current: int) -> InlineKeyboardMarkup:
    rows = []
    for t in ALLOWED_THRESHOLDS:
        tick = "✅ " if t == current else ""
        rows.append([InlineKeyboardButton(f"{tick}{t}%", callback_data=f"sp:set_threshold:{t}")])
    rows.append([InlineKeyboardButton("◀️ رجوع", callback_data="sp:mode_menu")])
    return InlineKeyboardMarkup(rows)


def _sp_interval_kb(current: str) -> InlineKeyboardMarkup:
    rows = []
    for iv in ALLOWED_INTERVALS:
        tick = "✅ " if iv == current else ""
        rows.append([InlineKeyboardButton(f"{tick}{INTERVAL_LABELS[iv]}", callback_data=f"sp:set_interval:{iv}")])
    rows.append([InlineKeyboardButton("◀️ رجوع", callback_data="sp:mode_menu")])
    return InlineKeyboardMarkup(rows)


def _sp_coins_kb(coins: list) -> InlineKeyboardMarkup:
    rows = []
    for c in coins:
        rows.append([InlineKeyboardButton(
            f"🗑 {c['symbol']}  ·  {c['target_percentage']:.1f}%",
            callback_data=f"sp:del_coin:{c['symbol']}"
        )])
    rows.append([InlineKeyboardButton("➕ إضافة عملة",   callback_data="sp:add_coin")])
    rows.append([InlineKeyboardButton("⚖️ توزيع متساوٍ", callback_data="sp:equal_dist")])
    rows.append([InlineKeyboardButton("◀️ رجوع",         callback_data="sp:menu")])
    return InlineKeyboardMarkup(rows)


# ── Helper: load or create SP record ──────────────────────────────────────────

async def _get_or_create_sp(user_id: int) -> dict:
    sp = await db.get_smart_portfolio(user_id)
    if not sp:
        await db.create_smart_portfolio(user_id)
        sp = await db.get_smart_portfolio(user_id)
    return sp


def _sp_summary_text(sp: dict, coins: list) -> str:
    mode    = sp.get("rebalance_mode", "unbalanced")
    capital = sp.get("capital_usdt", 0.0)
    running = sp.get("is_running", 0)
    sell_at = sp.get("sell_at_termination", 0)
    transfer= sp.get("enable_asset_transfer", 0)
    threshold = sp.get("deviation_threshold_pct", 5)
    interval  = sp.get("timed_interval", "weekly")
    total_pct = sum(c["target_percentage"] for c in coins)

    status_icon = "🟢 يعمل" if running else "🔴 متوقف"
    lines = [
        "💼 *Smart Portfolio*",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"الحالة:  {status_icon}",
        f"رأس المال:  `${capital:,.2f} USDT`",
        f"الوضع:  {MODE_LABELS.get(mode, mode)}",
    ]
    if mode == "proportional":
        lines.append(f"عتبة الانحراف:  `{threshold}%`")
    elif mode == "timed":
        lines.append(f"الفاصل الزمني:  {INTERVAL_LABELS.get(interval, interval)}")
    lines += [
        f"بيع عند الإنهاء:  {'✅' if sell_at else '❌'}",
        f"تحويل الأصول:  {'✅' if transfer else '❌'}",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"🪙 *{len(coins)} عملة*" + (f"  ⚠️ مجموع النسب `{total_pct:.1f}%`" if abs(total_pct - 100) > 1 else ""),
    ]
    for c in coins:
        lines.append(f"  • `{c['symbol']:<6}` `{c['target_percentage']:.1f}%`")
    return "\n".join(lines)


# ── Main menu ──────────────────────────────────────────────────────────────────

async def sp_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    sp    = await _get_or_create_sp(user_id)
    coins = await db.get_sp_coins(user_id)
    sp["coin_count"] = len(coins)
    text  = _sp_summary_text(sp, coins)
    kb    = _sp_main_kb(sp)
    if query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


# ── Toggle run/stop ────────────────────────────────────────────────────────────

async def sp_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    sp = await _get_or_create_sp(user_id)
    coins = await db.get_sp_coins(user_id)

    if not sp.get("is_running"):
        # Validate before starting
        if len(coins) < MIN_COINS:
            await query.answer(f"أضف {MIN_COINS} عملات على الأقل", show_alert=True)
            return
        total_pct = sum(c["target_percentage"] for c in coins)
        if abs(total_pct - 100) > 0.5:
            await query.answer(f"مجموع النسب {total_pct:.1f}% — يجب أن يكون 100%", show_alert=True)
            return
        if not sp.get("capital_usdt"):
            await query.answer("حدد رأس المال أولاً", show_alert=True)
            return
        await db.update_smart_portfolio(user_id, is_running=1)
    else:
        await db.update_smart_portfolio(user_id, is_running=0)

    await sp_menu(update, context)


# ── Mode menu ──────────────────────────────────────────────────────────────────

async def sp_mode_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    sp = await _get_or_create_sp(user_id)
    mode = sp.get("rebalance_mode", "unbalanced")
    threshold = sp.get("deviation_threshold_pct", 5)
    interval  = sp.get("timed_interval", "weekly")

    text = (
        "⚙️ *وضع إعادة التوازن*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "اختر الوضع المناسب:\n\n"
        "📊 *النسبة المئوية* — يعيد التوازن عند انحراف أي عملة\n"
        "⏰ *الفاصل الزمني* — يعيد التوازن في وقت محدد\n"
        "✋ *يدوي* — لا توازن تلقائي\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"الوضع الحالي: *{MODE_LABELS.get(mode, mode)}*"
    )
    if mode == "proportional":
        text += f"\nعتبة الانحراف: `{threshold}%`"
    elif mode == "timed":
        text += f"\nالفاصل: {INTERVAL_LABELS.get(interval, interval)}"

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=_sp_mode_kb(mode))


async def sp_set_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    mode = query.data.split(":")[-1]
    await db.update_smart_portfolio(user_id, rebalance_mode=mode)
    sp = await _get_or_create_sp(user_id)

    # After selecting proportional → show threshold picker
    if mode == "proportional":
        threshold = sp.get("deviation_threshold_pct", 5)
        await query.edit_message_text(
            "📊 *وضع النسبة المئوية*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "اختر عتبة الانحراف:\n\n"
            "عندما تنحرف أي عملة بهذه النسبة عن هدفها\n"
            "يقوم البوت بإعادة التوازن تلقائياً.",
            parse_mode="Markdown",
            reply_markup=_sp_threshold_kb(threshold),
        )
    elif mode == "timed":
        interval = sp.get("timed_interval", "weekly")
        await query.edit_message_text(
            "⏰ *وضع الفاصل الزمني*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "اختر الفاصل الزمني:\n\n"
            "يعيد البوت التوازن في الوقت المحدد\n"
            "بغض النظر عن حركة الأسعار.",
            parse_mode="Markdown",
            reply_markup=_sp_interval_kb(interval),
        )
    else:
        await sp_menu(update, context)


async def sp_set_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    threshold = int(query.data.split(":")[-1])
    await db.update_smart_portfolio(user_id, deviation_threshold_pct=threshold)
    await query.answer(f"✅ عتبة الانحراف: {threshold}%", show_alert=False)
    await sp_menu(update, context)


async def sp_set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    interval = query.data.split(":")[-1]
    await db.update_smart_portfolio(user_id, timed_interval=interval)
    await query.answer(f"✅ الفاصل: {INTERVAL_LABELS.get(interval, interval)}", show_alert=False)
    await sp_menu(update, context)


# ── Capital ────────────────────────────────────────────────────────────────────

async def sp_set_capital_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💰 *رأس المال*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "أرسل مبلغ الاستثمار بـ USDT:\n\n"
        "مثال: `1000`\n\n"
        "⚠️ يجب أن يكون المبلغ أكبر من صفر.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="sp:menu")]]),
    )
    return SP_SET_CAPITAL


async def sp_set_capital_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().replace(",", "")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ مبلغ غير صحيح. أرسل رقماً موجباً مثل `1000`.", parse_mode="Markdown")
        return SP_SET_CAPITAL

    await db.update_smart_portfolio(user_id, capital_usdt=amount)
    sp    = await _get_or_create_sp(user_id)
    coins = await db.get_sp_coins(user_id)
    sp["coin_count"] = len(coins)
    await update.message.reply_text(
        f"✅ رأس المال: `${amount:,.2f} USDT`",
        parse_mode="Markdown",
        reply_markup=_sp_main_kb(sp),
    )
    return ConversationHandler.END


# ── Coins list ─────────────────────────────────────────────────────────────────

async def sp_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    coins = await db.get_sp_coins(user_id)
    total_pct = sum(c["target_percentage"] for c in coins)
    warn = f"\n⚠️ مجموع النسب `{total_pct:.1f}%` — يجب 100%" if abs(total_pct - 100) > 1 and coins else ""
    text = (
        f"🪙 *العملات ({len(coins)}/{MAX_COINS})*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "اضغط على عملة لحذفها، أو أضف عملة جديدة.\n"
        f"الحد: {MIN_COINS}–{MAX_COINS} عملات، المجموع 100%."
        f"{warn}"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=_sp_coins_kb(coins))


async def sp_del_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    symbol = query.data.split(":")[-1]
    await db.delete_sp_coin(user_id, symbol)
    await sp_coins(update, context)


async def sp_equal_dist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    coins = await db.get_sp_coins(user_id)
    if len(coins) < MIN_COINS:
        await query.answer(f"أضف {MIN_COINS} عملات على الأقل أولاً", show_alert=True)
        return
    n = len(coins)
    pct = round(100.0 / n, 2)
    for i, c in enumerate(coins):
        adj = round(100.0 - pct * (n - 1), 2) if i == n - 1 else pct
        await db.update_sp_coin(user_id, c["symbol"], adj)
    await sp_coins(update, context)


# ── Add coin conversation ──────────────────────────────────────────────────────

async def sp_add_coin_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    coins = await db.get_sp_coins(user_id)
    if len(coins) >= MAX_COINS:
        await query.answer(f"الحد الأقصى {MAX_COINS} عملات", show_alert=True)
        return ConversationHandler.END
    await query.edit_message_text(
        "➕ *إضافة عملة*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "أرسل رمز العملة والنسبة:\n\n"
        "مثال: `BTC 40` أو `BTC=40`\n\n"
        "النسبة بالمئة من إجمالي المحفظة.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="sp:coins")]]),
    )
    return SP_ADD_COIN


async def sp_add_coin_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().upper().replace("=", " ")
    parts = text.split()
    try:
        if len(parts) != 2:
            raise ValueError
        symbol = parts[0]
        pct = float(parts[1])
        if pct <= 0 or pct > 100:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ صيغة خاطئة. مثال: `BTC 40`", parse_mode="Markdown"
        )
        return SP_ADD_COIN

    coins = await db.get_sp_coins(user_id)
    if len(coins) >= MAX_COINS:
        await update.message.reply_text(f"❌ الحد الأقصى {MAX_COINS} عملات.")
        return ConversationHandler.END

    existing = {c["symbol"] for c in coins}
    if symbol in existing:
        await db.update_sp_coin(user_id, symbol, pct)
        msg = f"✅ تم تحديث `{symbol}` إلى `{pct}%`"
    else:
        await db.add_sp_coin(user_id, symbol, pct)
        msg = f"✅ تمت إضافة `{symbol}` بنسبة `{pct}%`"

    coins = await db.get_sp_coins(user_id)
    total = sum(c["target_percentage"] for c in coins)
    warn = f"\n⚠️ مجموع النسب `{total:.1f}%` — يجب 100%" if abs(total - 100) > 1 else ""
    await update.message.reply_text(
        f"{msg}{warn}",
        parse_mode="Markdown",
        reply_markup=_sp_coins_kb(coins),
    )
    return ConversationHandler.END



# ── Manual rebalance ───────────────────────────────────────────────────────────

async def sp_manual_rebalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    await query.edit_message_text("⏳ جاري تحليل المحفظة...")
    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.edit_message_text(
            "❌ يجب ربط مفاتيح MEXC API أولاً.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="sp:menu")]]),
        )
        return
    sp    = await _get_or_create_sp(user_id)
    coins = await db.get_sp_coins(user_id)
    if len(coins) < MIN_COINS:
        await query.edit_message_text(
            f"❌ أضف {MIN_COINS} عملات على الأقل.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="sp:menu")]]),
        )
        return
    total_pct = sum(c["target_percentage"] for c in coins)
    if abs(total_pct - 100) > 0.5:
        await query.edit_message_text(
            f"⚠️ مجموع النسب `{total_pct:.1f}%` — يجب 100%.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="sp:menu")]]),
        )
        return
    from smart_portfolio import SmartPortfolioExchange, calculate_trades
    client = SmartPortfolioExchange(settings["mexc_api_key"], settings["mexc_secret_key"])
    try:
        portfolio, _ = await asyncio.wait_for(client.get_portfolio(), timeout=20)
    except Exception as e:
        await query.edit_message_text(
            f"❌ خطأ: {str(e)[:100]}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="sp:menu")]]),
        )
        await client.close()
        return
    capital = float(sp.get("capital_usdt") or 0)
    alloc_symbols = {c["symbol"] for c in coins}
    portfolio_slice = {s: d for s, d in portfolio.items() if s in alloc_symbols}
    usdt_val = portfolio.get("USDT", {}).get("value_usdt", 0.0)
    effective = sum(d["value_usdt"] for d in portfolio_slice.values()) + usdt_val
    if capital > 0:
        effective = min(capital, effective)
    threshold = float(sp.get("deviation_threshold_pct") or 5)
    trades, drift_report = calculate_trades(portfolio_slice, effective, coins, threshold)
    await client.close()
    if not trades:
        lines = ["✅ *المحفظة متوازنة*\n━━━━━━━━━━━━━━━━━━━━━"]
        for d in drift_report:
            lines.append(f"  `{d['symbol']:<6}` `{d['current_pct']:.1f}%`→`{d['target_pct']:.1f}%` `{d['drift_pct']:+.1f}%`")
        await query.edit_message_text(
            "\n".join(lines), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="sp:menu")]]),
        )
        return
    context.user_data["_sp_pending_trades"] = trades
    context.user_data["_sp_pending_keys"]   = (settings["mexc_api_key"], settings["mexc_secret_key"])
    text = "⚖️ *إعادة التوازن اليدوية*\n━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"💰 `${effective:,.2f}`  🎯 عتبة `{threshold}%`\n━━━━━━━━━━━━━━━━━━━━━\n"
    for d in drift_report:
        icon = "🔴" if d["drift_pct"] > 0 else ("🟢" if d["drift_pct"] < 0 else "✅")
        text += f"{icon} `{d['symbol']:<6}` `{d['current_pct']:.1f}%`→`{d['target_pct']:.1f}%` `{d['drift_pct']:+.1f}%`\n"
    text += "━━━━━━━━━━━━━━━━━━━━━\n"
    for t in trades:
        act = "🔴 بيع" if t["action"] == "sell" else "🟢 شراء"
        text += f"{act}  `{t['symbol']}`  `${t['usdt_amount']:.2f}`\n"
    await query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تنفيذ", callback_data="sp:exec_rebalance"),
             InlineKeyboardButton("❌ إلغاء", callback_data="sp:menu")],
        ]),
    )


async def sp_exec_rebalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    trades = context.user_data.pop("_sp_pending_trades", [])
    keys   = context.user_data.pop("_sp_pending_keys", None)
    if not trades or not keys:
        await query.edit_message_text(
            "❌ انتهت الجلسة. أعد التحليل.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="sp:menu")]]),
        )
        return
    await query.edit_message_text("⏳ جاري تنفيذ الصفقات...")
    from smart_portfolio import SmartPortfolioExchange
    client = SmartPortfolioExchange(keys[0], keys[1])
    try:
        results = await client.execute_trades(trades)
    except Exception as e:
        await query.edit_message_text(
            f"❌ خطأ: {str(e)[:100]}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="sp:menu")]]),
        )
        await client.close()
        return
    finally:
        await client.close()
    ok  = [r for r in results if r["status"] == "ok"]
    err = [r for r in results if r["status"] == "error"]
    traded = sum(t["usdt_amount"] for t in trades if any(r["symbol"] == t["symbol"] and r["status"] == "ok" for r in results))
    text = "✅ *اكتملت إعادة التوازن*\n━━━━━━━━━━━━━━━━━━━━━\n"
    for r in ok:
        act = "🔴 بيع" if r["action"] == "sell" else "🟢 شراء"
        text += f"{act}  `{r['symbol']}`  `${r.get('usdt', 0):.2f}`  ✅\n"
    for r in err:
        text += f"❌  `{r['symbol']}`: {r.get('reason', 'خطأ')[:50]}\n"
    text += f"━━━━━━━━━━━━━━━━━━━━━\n✅ ناجح: *{len(ok)}*"
    if err:
        text += f"  ❌ خطأ: *{len(err)}*"
    text += f"\n💵 الإجمالي: `${traded:.2f}`"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    await db.add_sp_history(user_id, now, f"يدوي: {len(ok)} ناجح، {len(err)} خطأ", traded, 1 if not err else 0)
    await query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="sp:menu")]]),
    )


# ── Drift report ───────────────────────────────────────────────────────────────

async def sp_drift_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    await query.edit_message_text("⏳ جاري جلب الأسعار...")
    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.edit_message_text(
            "❌ يجب ربط مفاتيح MEXC API أولاً.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="sp:menu")]]),
        )
        return
    sp    = await _get_or_create_sp(user_id)
    coins = await db.get_sp_coins(user_id)
    if not coins:
        await query.edit_message_text(
            "❌ لا توجد عملات في المحفظة.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="sp:menu")]]),
        )
        return
    from smart_portfolio import SmartPortfolioExchange, calculate_trades
    client = SmartPortfolioExchange(settings["mexc_api_key"], settings["mexc_secret_key"])
    try:
        portfolio, _ = await asyncio.wait_for(client.get_portfolio(), timeout=20)
    except Exception as e:
        await query.edit_message_text(
            f"❌ خطأ: {str(e)[:100]}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="sp:menu")]]),
        )
        await client.close()
        return
    finally:
        await client.close()
    capital = float(sp.get("capital_usdt") or 0)
    alloc_symbols = {c["symbol"] for c in coins}
    portfolio_slice = {s: d for s, d in portfolio.items() if s in alloc_symbols}
    usdt_val = portfolio.get("USDT", {}).get("value_usdt", 0.0)
    effective = sum(d["value_usdt"] for d in portfolio_slice.values()) + usdt_val
    if capital > 0:
        effective = min(capital, effective)
    threshold = float(sp.get("deviation_threshold_pct") or 5)
    _, drift_report = calculate_trades(portfolio_slice, effective, coins, threshold)
    text = f"📊 *تقرير الانحراف*\n━━━━━━━━━━━━━━━━━━━━━\n💰 `${effective:,.2f}`  🎯 عتبة `{threshold}%`\n━━━━━━━━━━━━━━━━━━━━━\n"
    for d in drift_report:
        if d["needs_action"]:
            icon = "🔴" if d["drift_pct"] > 0 else "🟢"
            act  = "بيع" if d["drift_pct"] > 0 else "شراء"
            text += f"{icon} `{d['symbol']:<6}` `{d['current_pct']:.1f}%`→`{d['target_pct']:.1f}%` `{d['drift_pct']:+.1f}%` ← {act}\n"
        else:
            text += f"✅ `{d['symbol']:<6}` `{d['current_pct']:.1f}%`→`{d['target_pct']:.1f}%` `{d['drift_pct']:+.1f}%`\n"
    await query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="sp:menu")]]),
    )


# ── Terminate ──────────────────────────────────────────────────────────────────

async def sp_terminate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sp = await _get_or_create_sp(update.effective_user.id)
    sell = sp.get("sell_at_termination", 0)
    await query.edit_message_text(
        "🛑 *إنهاء Smart Portfolio*\n━━━━━━━━━━━━━━━━━━━━━\n"
        + ("سيتم بيع جميع العملات وتحويلها إلى USDT.\n" if sell else "")
        + "هل أنت متأكد؟",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ نعم، أوقف", callback_data="sp:terminate_confirm"),
             InlineKeyboardButton("❌ إلغاء",     callback_data="sp:menu")],
        ]),
    )


async def sp_terminate_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    sp = await _get_or_create_sp(user_id)
    await db.update_smart_portfolio(user_id, is_running=0)
    if sp.get("sell_at_termination"):
        await query.edit_message_text("⏳ جاري بيع جميع العملات...")
        settings = await db.get_settings(user_id)
        if settings and settings.get("mexc_api_key"):
            from smart_portfolio import SmartPortfolioExchange
            coins  = await db.get_sp_coins(user_id)
            client = SmartPortfolioExchange(settings["mexc_api_key"], settings["mexc_secret_key"])
            try:
                results = await client.sell_all_to_usdt(coins)
                ok = sum(1 for r in results if r["status"] == "ok")
                await query.edit_message_text(
                    f"✅ تم إيقاف البوت وبيع {ok} عملة إلى USDT.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="sp:menu")]]),
                )
            except Exception as e:
                await query.edit_message_text(
                    f"⚠️ تم الإيقاف لكن حدث خطأ أثناء البيع: {str(e)[:80]}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="sp:menu")]]),
                )
            finally:
                await client.close()
            return
    await query.edit_message_text(
        "✅ تم إيقاف Smart Portfolio.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="sp:menu")]]),
    )


# ── ConversationHandler + callback dispatcher ──────────────────────────────────

def build_sp_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(sp_set_capital_prompt, pattern="^sp:set_capital$"),
            CallbackQueryHandler(sp_add_coin_prompt,    pattern="^sp:add_coin$"),
        ],
        states={
            SP_SET_CAPITAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, sp_set_capital_receive)],
            SP_ADD_COIN:    [MessageHandler(filters.TEXT & ~filters.COMMAND, sp_add_coin_receive)],
        },
        fallbacks=[
            CallbackQueryHandler(sp_callback, pattern="^sp:"),
            CommandHandler("cancel", lambda u, c: ConversationHandler.END),
        ],
        per_message=False,
    )


async def sp_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route all sp:* callbacks."""
    query = update.callback_query
    data  = query.data

    dispatch = {
        "sp:menu":              sp_menu,
        "sp:toggle":            sp_toggle,
        "sp:mode_menu":         sp_mode_menu,
        "sp:coins":             sp_coins,
        "sp:equal_dist":        sp_equal_dist,
        "sp:manual_rebalance":  sp_manual_rebalance,
        "sp:exec_rebalance":    sp_exec_rebalance,
        "sp:drift_report":      sp_drift_report,
        "sp:terminate":         sp_terminate,
        "sp:terminate_confirm": sp_terminate_confirm,
    }

    if data in dispatch:
        await dispatch[data](update, context)
    elif data.startswith("sp:set_mode:"):
        await sp_set_mode(update, context)
    elif data.startswith("sp:set_threshold:"):
        await sp_set_threshold(update, context)
    elif data.startswith("sp:set_interval:"):
        await sp_set_interval(update, context)
    elif data.startswith("sp:del_coin:"):
        await sp_del_coin(update, context)
