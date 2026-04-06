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
from bot.grid.monitor import grid_monitor
from bot.scalping.monitor import trade_monitor
from bot.scalping.whale_monitor import whale_monitor

logger = logging.getLogger(__name__)

_MIN_VALUE_USD = 1.0

# عملات الشبكات والمحافظ — لا يجوز بيعها لأنها بتُستخدم كرسوم أو محافظ أساسية
NETWORK_COINS = {
    "BNB",   # رسوم شبكة BSC
    "ETH",   # رسوم شبكة Ethereum
    "TRX",   # رسوم شبكة TRON
    "XRP",   # رسوم شبكة Ripple
    "SOL",   # رسوم شبكة Solana
    "MATIC", # رسوم شبكة Polygon
    "AVAX",  # رسوم شبكة Avalanche
    "DOT",   # شبكة Polkadot
    "ADA",   # شبكة Cardano
    "ATOM",  # شبكة Cosmos
    "TON",   # رسوم شبكة TON
    "MX",    # عملة MEXC الأساسية
}


def _get_grid_locked_symbols(user_id: int) -> set:
    """Return base coin symbols that have an active grid for this user."""
    locked = set()
    for grid in grid_monitor.active_grids.values():
        if grid.get("user_id") == user_id:
            base = grid["symbol"].split("/")[0]
            locked.add(base)
    return locked


def _get_scalping_symbols(user_id: int) -> set:
    """Return symbols with open scalping trades for this user."""
    return {
        sym for sym, t in trade_monitor.open_trades.items()
        if t.get("user_id") == user_id
    }


def _get_whale_symbols(user_id: int) -> set:
    """Return symbols with open whale trades for this user."""
    return {
        sym for sym, t in whale_monitor.open_trades.items()
        if t.get("user_id") == user_id
    }


# ── Menu ───────────────────────────────────────────────────────────────────────

async def emergency_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    # Clear any previous selection
    context.user_data.pop("_emg_selected", None)
    context.user_data.pop("_emg_portfolio", None)

    scalping_count = len(_get_scalping_symbols(user_id))
    whale_count    = len(_get_whale_symbols(user_id))

    scalping_label = f"⚡ بيع صفقات Scalping ({scalping_count})" if scalping_count else "⚡ Scalping — لا توجد صفقات"
    whale_label    = f"🐋 بيع صفقات Whale ({whale_count})"       if whale_count    else "🐋 Whale — لا توجد صفقات"

    buttons = [
        [InlineKeyboardButton(scalping_label, callback_data="emergency:pick_scalping")],
        [InlineKeyboardButton(whale_label,    callback_data="emergency:pick_whale")],
        [InlineKeyboardButton("🔴 اختار عملات أخرى للبيع", callback_data="emergency:pick_coin")],
        [InlineKeyboardButton("💥 بيع الكل", callback_data="emergency:confirm_all")],
        [InlineKeyboardButton("◀️ القائمة الرئيسية", callback_data="menu:main")],
    ]

    await query.edit_message_text(
        "🚨 *بيع طوارئ*\n\n"
        "⚠️ سيتم تنفيذ البيع *فوراً* بسعر السوق الحالي.\n\n"
        "اختر نوع البيع:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
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
    """
    بيع بالتحديد — يجيب كل عملات الحساب الفعلية من MEXC
    (مش بس اللي في المحفظة المضبوطة في البوت).
    """
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.answer("❌ يجب ربط MEXC API أولاً", show_alert=True)
        return

    await query.edit_message_text("⏳ جاري جلب كل عملاتك من MEXC...")

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

    locked  = _get_grid_locked_symbols(user_id)
    network = NETWORK_COINS

    # كل العملات الموجودة في الحساب فعلاً — مش بس المحفظة المضبوطة
    coins = [
        sym for sym, data in portfolio.items()
        if sym != "USDT"
        and data.get("value_usdt", 0) >= _MIN_VALUE_USD
        and sym not in locked
        and sym not in network
    ]

    if not coins:
        await query.edit_message_text(
            "⚠️ لا يوجد عملات متاحة للبيع.",
            parse_mode="Markdown",
            reply_markup=back_to_main_kb(),
        )
        return

    coins.sort(key=lambda s: portfolio[s]["value_usdt"], reverse=True)

    context.user_data["_emg_portfolio"] = portfolio
    context.user_data["_emg_coins"]     = coins
    context.user_data["_emg_selected"]  = set()
    context.user_data["_emg_source"]    = "pick"

    excluded = sorted((locked | network) & set(portfolio.keys()))
    excluded_note = f"\n\n🔒 مستثنى: `{'، '.join(excluded)}`" if excluded else ""

    await query.edit_message_text(
        _select_text(set(), portfolio) + excluded_note,
        parse_mode="Markdown",
        reply_markup=_build_select_kb(coins, set(), portfolio),
    )


# ── Pick scalping trades ───────────────────────────────────────────────────────

async def emergency_pick_scalping_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    symbols = _get_scalping_symbols(user_id)
    if not symbols:
        await query.answer("⚠️ لا توجد صفقات Scalping مفتوحة", show_alert=True)
        return

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.answer("❌ يجب ربط MEXC API أولاً", show_alert=True)
        return

    await query.edit_message_text("⏳ جاري جلب رصيدك من MEXC...")
    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    try:
        portfolio, _ = await client.get_portfolio()
    except Exception as e:
        await query.edit_message_text(f"❌ تعذّر جلب الرصيد: {str(e)[:80]}", reply_markup=back_to_main_kb())
        return
    finally:
        await client.close()

    # فلتر العملات اللي عندها صفقة scalping فعلاً
    coins = [sym.split("/")[0] for sym in symbols if sym.split("/")[0] in portfolio]
    coins.sort(key=lambda s: portfolio.get(s, {}).get("value_usdt", 0), reverse=True)

    context.user_data["_emg_portfolio"] = portfolio
    context.user_data["_emg_coins"]     = coins
    context.user_data["_emg_selected"]  = set(coins)  # محدد كلهم تلقائياً

    await query.edit_message_text(
        f"⚡ *بيع صفقات Scalping*\n\n"
        f"عدد الصفقات: *{len(coins)}*\n"
        "كل الصفقات محددة — اضغط على أي عملة لإلغاء تحديدها:",
        parse_mode="Markdown",
        reply_markup=_build_select_kb(coins, set(coins), portfolio),
    )


# ── Pick whale trades ──────────────────────────────────────────────────────────

async def emergency_pick_whale_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    symbols = _get_whale_symbols(user_id)
    if not symbols:
        await query.answer("⚠️ لا توجد صفقات Whale مفتوحة", show_alert=True)
        return

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.answer("❌ يجب ربط MEXC API أولاً", show_alert=True)
        return

    await query.edit_message_text("⏳ جاري جلب رصيدك من MEXC...")
    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    try:
        portfolio, _ = await client.get_portfolio()
    except Exception as e:
        await query.edit_message_text(f"❌ تعذّر جلب الرصيد: {str(e)[:80]}", reply_markup=back_to_main_kb())
        return
    finally:
        await client.close()

    coins = [sym.split("/")[0] for sym in symbols if sym.split("/")[0] in portfolio]
    coins.sort(key=lambda s: portfolio.get(s, {}).get("value_usdt", 0), reverse=True)

    context.user_data["_emg_portfolio"] = portfolio
    context.user_data["_emg_coins"]     = coins
    context.user_data["_emg_selected"]  = set(coins)  # محدد كلهم تلقائياً

    await query.edit_message_text(
        f"🐋 *بيع صفقات Whale*\n\n"
        f"عدد الصفقات: *{len(coins)}*\n"
        "كل الصفقات محددة — اضغط على أي عملة لإلغاء تحديدها:",
        parse_mode="Markdown",
        reply_markup=_build_select_kb(coins, set(coins), portfolio),
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
                InlineKeyboardButton("◀️ تعديل", callback_data="emergency:back_to_select"),
            ]
        ]),
    )


# ── Back to select screen (without re-fetching from MEXC) ─────────────────────

async def emergency_back_to_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    portfolio = context.user_data.get("_emg_portfolio")
    coins     = context.user_data.get("_emg_coins")
    selected  = context.user_data.get("_emg_selected", set())

    if not portfolio or not coins:
        # State lost — restart
        await query.edit_message_text(
            "⚠️ انتهت الجلسة، ابدأ من جديد.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ رجوع", callback_data="emergency:menu")]
            ]),
        )
        return

    await query.edit_message_text(
        _select_text(selected, portfolio),
        parse_mode="Markdown",
        reply_markup=_build_select_kb(coins, selected, portfolio),
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
                # Remove from scalping/whale monitors if tracked
                scalping_key = f"{sym}/USDT"
                if scalping_key in trade_monitor.open_trades:
                    await trade_monitor.remove_trade(scalping_key)
                if scalping_key in whale_monitor.open_trades:
                    await whale_monitor.remove_trade(scalping_key)
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
    """
    بيع الكل — يجيب كل عملات الحساب من MEXC ويفتح شاشة التحديد
    بكلهم محددين تلقائياً، فيقدر المستخدم يشيل أي عملة قبل التنفيذ.
    """
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.answer("❌ يجب ربط MEXC API أولاً", show_alert=True)
        return

    await query.edit_message_text("⏳ جاري جلب كل عملاتك من MEXC...")

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

    locked  = _get_grid_locked_symbols(user_id)
    network = NETWORK_COINS

    coins = [
        sym for sym, data in portfolio.items()
        if sym != "USDT"
        and data.get("value_usdt", 0) >= _MIN_VALUE_USD
        and sym not in locked
        and sym not in network
    ]

    if not coins:
        await query.edit_message_text(
            "⚠️ لا يوجد عملات متاحة للبيع.",
            reply_markup=back_to_main_kb(),
        )
        return

    coins.sort(key=lambda s: portfolio[s]["value_usdt"], reverse=True)

    # كل العملات محددة تلقائياً
    selected = set(coins)
    context.user_data["_emg_portfolio"] = portfolio
    context.user_data["_emg_coins"]     = coins
    context.user_data["_emg_selected"]  = selected
    context.user_data["_emg_source"]    = "all"  # للرجوع الصحيح

    excluded = sorted((locked | network) & set(portfolio.keys()))
    excluded_note = f"\n\n🔒 مستثنى: `{'، '.join(excluded)}`" if excluded else ""

    total = sum(portfolio[s]["value_usdt"] for s in selected)
    await query.edit_message_text(
        f"💥 *بيع الكل — {len(coins)} عملة*\n\n"
        f"💰 الإجمالي: `${total:.2f} USDT`\n\n"
        "كل العملات محددة ✅ — اضغط على أي عملة لإلغاء تحديدها قبل التنفيذ:"
        + excluded_note,
        parse_mode="Markdown",
        reply_markup=_build_select_kb(coins, selected, portfolio),
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
                # Remove from scalping/whale monitors if tracked
                if pair in trade_monitor.open_trades:
                    await trade_monitor.remove_trade(pair)
                if pair in whale_monitor.open_trades:
                    await whale_monitor.remove_trade(pair)
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
