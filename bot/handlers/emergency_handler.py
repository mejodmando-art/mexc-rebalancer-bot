"""
Emergency sell handler — allows the user to sell any coin or all coins
at market price immediately, regardless of portfolio configuration.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.database import db
from bot.mexc_client import MexcClient
from bot.keyboards import back_to_main_kb

logger = logging.getLogger(__name__)

_MIN_VALUE_USD = 1.0  # skip dust below this value


# ── Menu ───────────────────────────────────────────────────────────────────────

async def emergency_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show emergency sell options."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🚨 *بيع طوارئ*\n\n"
        "⚠️ سيتم تنفيذ البيع *فوراً* بسعر السوق الحالي.\n\n"
        "اختر نوع البيع:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔴 بيع عملة واحدة", callback_data="emergency:pick_coin")],
            [InlineKeyboardButton("💥 بيع الكل (كل العملات)", callback_data="emergency:confirm_all")],
            [InlineKeyboardButton("◀️ القائمة الرئيسية", callback_data="menu:main")],
        ]),
    )


# ── Pick a single coin ─────────────────────────────────────────────────────────

async def emergency_pick_coin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetch live balance and show all non-dust coins as buttons."""
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

    # Filter out USDT and dust
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

    buttons = []
    row = []
    for sym in sorted(coins):
        val = portfolio[sym]["value_usdt"]
        row.append(InlineKeyboardButton(
            f"{sym} (${val:.1f})",
            callback_data=f"emergency:confirm_one:{sym}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("◀️ رجوع", callback_data="emergency:menu")])

    await query.edit_message_text(
        "🔴 *اختر العملة للبيع الفوري:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ── Confirm single coin ────────────────────────────────────────────────────────

async def emergency_confirm_one_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    symbol = query.data.split(":")[2]

    await query.edit_message_text(
        f"⚠️ *تأكيد بيع {symbol}*\n\n"
        f"سيتم بيع كامل رصيد `{symbol}` بسعر السوق الحالي فوراً.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ تأكيد البيع", callback_data=f"emergency:exec_one:{symbol}"),
                InlineKeyboardButton("❌ إلغاء", callback_data="emergency:menu"),
            ]
        ]),
    )


# ── Confirm sell all ───────────────────────────────────────────────────────────

async def emergency_confirm_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "💥 *تأكيد بيع الكل*\n\n"
        "⚠️ سيتم بيع *جميع العملات* في حسابك بسعر السوق الحالي فوراً.\n\n"
        "هذا الإجراء لا يمكن التراجع عنه.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💥 نعم، بيع الكل", callback_data="emergency:exec_all"),
                InlineKeyboardButton("❌ إلغاء", callback_data="emergency:menu"),
            ]
        ]),
    )


# ── Execute single coin sell ───────────────────────────────────────────────────

async def emergency_exec_one_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    symbol = query.data.split(":")[2]

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.answer("❌ يجب ربط MEXC API أولاً", show_alert=True)
        return

    await query.edit_message_text(f"⏳ جاري بيع `{symbol}` بسعر السوق...")

    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    try:
        balance = await client.exchange.fetch_balance()
        qty = float(balance.get("free", {}).get(symbol, 0) or 0)
        if qty < 1e-8:
            await query.edit_message_text(
                f"⚠️ لا يوجد رصيد `{symbol}` للبيع.",
                reply_markup=back_to_main_kb(),
            )
            return

        pair = f"{symbol}/USDT"
        order = await client.exchange.create_market_sell_order(pair, qty)
        filled = float(order.get("filled") or qty)
        cost   = float(order.get("cost") or 0)

        await query.edit_message_text(
            f"✅ *تم بيع {symbol} بنجاح*\n\n"
            f"الكمية: `{filled:.6g}`\n"
            f"القيمة التقريبية: `${cost:.2f} USDT`",
            parse_mode="Markdown",
            reply_markup=back_to_main_kb(),
        )
    except Exception as e:
        logger.error(f"Emergency sell {symbol}: {e}")
        await query.edit_message_text(
            f"❌ فشل البيع: {str(e)[:100]}",
            reply_markup=back_to_main_kb(),
        )
    finally:
        await client.close()


# ── Execute sell all ───────────────────────────────────────────────────────────

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
        portfolio, total = await client.get_portfolio()

        for sym, data in portfolio.items():
            if sym == "USDT":
                continue
            if data.get("value_usdt", 0) < _MIN_VALUE_USD:
                continue

            pair = f"{sym}/USDT"
            try:
                balance = await client.exchange.fetch_balance()
                qty = float(balance.get("free", {}).get(sym, 0) or 0)
                if qty < 1e-8:
                    results.append(f"⏭ `{sym}`: رصيد صفر")
                    continue
                order = await client.exchange.create_market_sell_order(pair, qty)
                cost = float(order.get("cost") or 0)
                results.append(f"🔴 `{sym}` — `${cost:.2f}` ✅")
            except Exception as e:
                results.append(f"❌ `{sym}`: {str(e)[:60]}")

    except Exception as e:
        logger.error(f"Emergency sell all: {e}")
        await query.edit_message_text(
            f"❌ خطأ أثناء جلب الرصيد: {str(e)[:100]}",
            reply_markup=back_to_main_kb(),
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
