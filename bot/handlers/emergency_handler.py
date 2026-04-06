"""
Emergency sell handler.

Single-coin flow:
  emergency:pick_coin        → show all coins as toggle buttons (multi-select)
  emergency:toggle:{sym}     → toggle coin selection on/off
  emergency:sell_selected    → confirm then sell all selected coins at market

Sell-all flow:
  emergency:confirm_all      → confirm screen
  emergency:exec_all         → sell every coin at market
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.database import db
from bot.mexc_client import MexcClient
from bot.keyboards import back_to_main_kb

logger = logging.getLogger(__name__)

_MIN_VALUE_USD = 1.0


# ── Menu ───────────────────────────────────────────────────────────────────────

async def emergency_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Clear any previous selection
    context.user_data.pop("_emg_selected", None)
    context.user_data.pop("_emg_portfolio", None)
    await query.edit_message_text(
        "🚨 *بيع طوارئ*\n\n"
        "⚠️ سيتم تنفيذ البيع *فوراً* بسعر السوق الحالي.\n\n"
        "اختر نوع البيع:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔴 اختار عملات للبيع", callback_data="emergency:pick_coin")],
            [InlineKeyboardButton("💥 بيع الكل (كل العملات)", callback_data="emergency:confirm_all")],
            [InlineKeyboardButton("◀️ القائمة الرئيسية", callback_data="menu:main")],
        ]),
    )


# ── Build the multi-select keyboard ───────────────────────────────────────────

def _build_select_kb(coins: list, selected: set, portfolio: dict) -> InlineKeyboardMarkup:
    """
    coins: list of symbol strings sorted by value desc
    selected: set of currently selected symbols
    """
    buttons = []
    row = []
    for sym in coins:
        val  = portfolio[sym]["value_usdt"]
        tick = "✅ " if sym in selected else ""
        row.append(InlineKeyboardButton(
            f"{tick}{sym}  ${val:.1f}",
            callback_data=f"emergency:toggle:{sym}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Action row
    if selected:
        count = len(selected)
        buttons.append([InlineKeyboardButton(
            f"🔴 بيع المحدد ({count} عملة)",
            callback_data="emergency:confirm_selected",
        )])
    buttons.append([InlineKeyboardButton("◀️ رجوع", callback_data="emergency:menu")])
    return InlineKeyboardMarkup(buttons)


def _select_text(selected: set, portfolio: dict) -> str:
    if not selected:
        return (
            "🔴 *اختار العملات للبيع*\n\n"
            "اضغط على أي عملة لتحديدها ✅\n"
            "تقدر تحدد أكتر من عملة في نفس الوقت\n\n"
            "_(مرتبة حسب القيمة)_"
        )
    total = sum(portfolio[s]["value_usdt"] for s in selected if s in portfolio)
    syms  = "، ".join(sorted(selected))
    return (
        f"🔴 *اختار العملات للبيع*\n\n"
        f"✅ المحدد: `{syms}`\n"
        f"💰 إجمالي: `${total:.2f} USDT`\n\n"
        "اضغط على عملة مرة ثانية لإلغاء تحديدها"
    )


# ── Pick coins (initial load) ──────────────────────────────────────────────────

async def emergency_pick_coin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.answer("❌ يجب ربط MEXC API أولاً", show_alert=True)
        return

    await query.edit_message_text("⏳ جاري جلب رصيدك من MEXC...")

    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    try:
        portfolio, _ = await client.get_portfolio()
    except Exception as e:
        await query.edit_message_text(
            f"❌ تعذّر جلب الرصيد: {str(e)[:80]}",
            reply_markup=back_to_main_kb(),
        )
        return
    finally:
        await client.close()

    coins = [
        sym for sym, data in portfolio.items()
        if sym != "USDT" and data.get("value_usdt", 0) >= _MIN_VALUE_USD
    ]

    if not coins:
        await query.edit_message_text(
            "⚠️ لا يوجد عملات بقيمة كافية للبيع.",
            reply_markup=back_to_main_kb(),
        )
        return

    # Sort by value descending
    coins.sort(key=lambda s: portfolio[s]["value_usdt"], reverse=True)

    context.user_data["_emg_portfolio"] = portfolio
    context.user_data["_emg_coins"]     = coins
    context.user_data["_emg_selected"]  = set()

    await query.edit_message_text(
        _select_text(set(), portfolio),
        parse_mode="Markdown",
        reply_markup=_build_select_kb(coins, set(), portfolio),
    )


# ── Toggle a coin ──────────────────────────────────────────────────────────────

async def emergency_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    symbol = query.data.split(":")[2]

    portfolio = context.user_data.get("_emg_portfolio")
    coins     = context.user_data.get("_emg_coins")
    selected  = context.user_data.get("_emg_selected", set())

    if not portfolio or not coins:
        await query.answer("⚠️ انتهت الجلسة، ابدأ من جديد", show_alert=True)
        return

    # Toggle
    if symbol in selected:
        selected.discard(symbol)
        await query.answer(f"❌ تم إلغاء تحديد {symbol}")
    else:
        selected.add(symbol)
        val = portfolio[symbol]["value_usdt"]
        await query.answer(f"✅ تم تحديد {symbol}  ${val:.1f}")

    context.user_data["_emg_selected"] = selected

    await query.edit_message_text(
        _select_text(selected, portfolio),
        parse_mode="Markdown",
        reply_markup=_build_select_kb(coins, selected, portfolio),
    )


# ── Confirm selected ───────────────────────────────────────────────────────────

async def emergency_confirm_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    portfolio = context.user_data.get("_emg_portfolio", {})
    selected  = context.user_data.get("_emg_selected", set())

    if not selected:
        await query.answer("⚠️ لم تحدد أي عملة", show_alert=True)
        return

    total = sum(portfolio[s]["value_usdt"] for s in selected if s in portfolio)
    lines = []
    for sym in sorted(selected):
        data = portfolio.get(sym, {})
        lines.append(f"• `{sym}` — `${data.get('value_usdt', 0):.2f}`")

    await query.edit_message_text(
        f"⚠️ *تأكيد البيع*\n\n"
        + "\n".join(lines) +
        f"\n\n💰 الإجمالي: `${total:.2f} USDT`\n\n"
        "سيتم بيع *كامل الرصيد* من كل عملة محددة بسعر السوق فوراً.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"✅ تأكيد بيع {len(selected)} عملة", callback_data="emergency:exec_selected"),
                InlineKeyboardButton("❌ إلغاء", callback_data="emergency:pick_coin"),
            ]
        ]),
    )


# ── Execute selected ───────────────────────────────────────────────────────────

async def emergency_exec_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    selected = context.user_data.get("_emg_selected", set())
    if not selected:
        await query.answer("⚠️ لم تحدد أي عملة", show_alert=True)
        return

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.answer("❌ يجب ربط MEXC API أولاً", show_alert=True)
        return

    await query.edit_message_text(f"⏳ جاري بيع {len(selected)} عملة...")

    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    results = []
    try:
        balance = await client.exchange.fetch_balance()
        for sym in sorted(selected):
            qty = float(balance.get("free", {}).get(sym, 0) or 0)
            if qty < 1e-8:
                results.append(f"⏭ `{sym}`: رصيد صفر")
                continue
            pair = f"{sym}/USDT"
            try:
                order = await client.exchange.create_market_sell_order(pair, qty)
                cost  = float(order.get("cost") or 0)
                results.append(f"🔴 `{sym}` — `${cost:.2f}` ✅")
            except Exception as e:
                results.append(f"❌ `{sym}`: {str(e)[:60]}")
    except Exception as e:
        logger.error(f"Emergency exec selected: {e}")
        await query.edit_message_text(
            f"❌ خطأ: {str(e)[:100]}", reply_markup=back_to_main_kb()
        )
        return
    finally:
        await client.close()

    # Clear selection
    context.user_data.pop("_emg_selected", None)
    context.user_data.pop("_emg_portfolio", None)

    result_text = "\n".join(results)
    await query.edit_message_text(
        f"✅ *اكتملت عملية البيع*\n\n{result_text}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔴 بيع عملات أخرى", callback_data="emergency:pick_coin")],
            [InlineKeyboardButton("◀️ القائمة الرئيسية", callback_data="menu:main")],
        ]),
    )


# ── Sell All ───────────────────────────────────────────────────────────────────

async def emergency_confirm_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💥 *تأكيد بيع الكل*\n\n"
        "⚠️ سيتم بيع *جميع العملات* في حسابك بسعر السوق فوراً.\n\n"
        "هذا الإجراء لا يمكن التراجع عنه.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💥 نعم، بيع الكل", callback_data="emergency:exec_all"),
                InlineKeyboardButton("❌ إلغاء", callback_data="emergency:menu"),
            ]
        ]),
    )


async def emergency_exec_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.answer("❌ يجب ربط MEXC API أولاً", show_alert=True)
        return

    await query.edit_message_text("⏳ جاري بيع جميع العملات...")

    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    results = []
    try:
        portfolio, _ = await client.get_portfolio()
        for sym, data in portfolio.items():
            if sym == "USDT":
                continue
            if data.get("value_usdt", 0) < _MIN_VALUE_USD:
                continue
            pair = f"{sym}/USDT"
            try:
                balance = await client.exchange.fetch_balance()
                qty     = float(balance.get("free", {}).get(sym, 0) or 0)
                if qty < 1e-8:
                    results.append(f"⏭ `{sym}`: رصيد صفر")
                    continue
                order = await client.exchange.create_market_sell_order(pair, qty)
                cost  = float(order.get("cost") or 0)
                results.append(f"🔴 `{sym}` — `${cost:.2f}` ✅")
            except Exception as e:
                results.append(f"❌ `{sym}`: {str(e)[:60]}")
    except Exception as e:
        logger.error(f"Emergency sell all: {e}")
        await query.edit_message_text(
            f"❌ خطأ: {str(e)[:100]}", reply_markup=back_to_main_kb()
        )
        return
    finally:
        await client.close()

    result_text = "\n".join(results) if results else "لم تُنفَّذ أي صفقة"
    await query.edit_message_text(
        f"✅ *اكتملت عملية البيع الشامل*\n\n{result_text}",
        parse_mode="Markdown",
        reply_markup=back_to_main_kb(),
    )
