"""
Telegram handler for the Whale Order Flow scalping strategy.

Scan runs every 5 minutes. Monitor runs every 30 seconds.
Targets: T1=+0.5% (sell 60%), T2=+1.0% (sell 40%), SL=-0.4%
"""

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.database import db
from bot.mexc_client import MexcClient
from bot.scalping.whale_scanner import whale_scan
from bot.scalping.whale_monitor import whale_monitor
from bot.scalping.executor import execute_trade

logger = logging.getLogger(__name__)

_MIN_TRADE_SIZE = 5.0
_MAX_TRADE_SIZE = 10_000.0


# ── Keyboards ──────────────────────────────────────────────────────────────────

def whale_menu_kb(enabled: bool) -> InlineKeyboardMarkup:
    toggle = "🔴 إيقاف Whale Strategy" if enabled else "🟢 تشغيل Whale Strategy"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle, callback_data="whale:toggle")],
        [InlineKeyboardButton("📊 الصفقات المفتوحة", callback_data="whale:open_trades")],
        [InlineKeyboardButton("🔴 بيع صفقة", callback_data="whale:sell_pick")],
        [InlineKeyboardButton("⚙️ إعدادات Whale", callback_data="whale:settings")],
        [InlineKeyboardButton("◀️ القائمة الرئيسية", callback_data="menu:main")],
    ])


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_settings(user_id: int) -> dict:
    s = await db.get_settings(user_id) or {}
    return {
        "enabled":         bool(s.get("whale_enabled", 0)),
        "trade_size":      float(s.get("whale_trade_size", 10.0)),
        "mexc_api_key":    s.get("mexc_api_key", ""),
        "mexc_secret_key": s.get("mexc_secret_key", ""),
    }


def _status_text(s: dict, open_count: int) -> str:
    status = "🟢 يعمل" if s["enabled"] else "🔴 متوقف"
    return (
        "🐋 *Whale Order Flow*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"  الحالة: {status}\n"
        f"  حجم الصفقة: `${s['trade_size']:.0f}`\n"
        f"  صفقات مفتوحة: *{open_count}*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 *الاستراتيجية:*\n"
        "  ◈ FVG — فجوة السعر (تجميع الحيتان)\n"
        "  ◈ CVD Shift — تحول ضغط الشراء\n"
        "  ◈ 5M Breakout — كسر أعلى 3 شمعات\n"
        "  ◈ T1: +0.5% · T2: +1.0% · SL: -0.4%\n"
        "━━━━━━━━━━━━━━━━━━━━━"
    )


# ── Handlers ───────────────────────────────────────────────────────────────────

async def whale_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    s = await _get_settings(user_id)
    await query.edit_message_text(
        _status_text(s, len(whale_monitor.open_symbols_for(user_id))),
        parse_mode="Markdown",
        reply_markup=whale_menu_kb(s["enabled"]),
    )


async def whale_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    s = await _get_settings(user_id)

    if not s["mexc_api_key"]:
        await query.answer("❌ يجب ربط MEXC API أولاً من الإعدادات", show_alert=True)
        return

    new_state = 0 if s["enabled"] else 1
    await db.update_settings(user_id, whale_enabled=new_state)
    s["enabled"] = bool(new_state)

    action = "تشغيل" if new_state else "إيقاف"
    await query.answer(f"✅ تم {action} Whale Strategy")
    await query.edit_message_text(
        _status_text(s, len(whale_monitor.open_symbols_for(user_id))),
        parse_mode="Markdown",
        reply_markup=whale_menu_kb(s["enabled"]),
    )


async def whale_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    s = await _get_settings(user_id)
    settings = await db.get_settings(user_id) or {}

    max_trades  = int(settings.get("whale_max_trades", 3))
    daily_limit = float(settings.get("whale_daily_loss_limit", 0))
    daily_line  = f"`${daily_limit:.0f} USDT`" if daily_limit > 0 else "`غير محدد`"

    await query.edit_message_text(
        "⚙️ *إعدادات Whale Order Flow*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"  💰 حجم الصفقة: `${s['trade_size']:.0f} USDT`\n"
        f"  📊 أقصى صفقات متزامنة: `{max_trades}`\n"
        f"  🛑 حد الخسارة اليومي: {daily_line}\n"
        "━━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 تغيير حجم الصفقة",   callback_data="whale:set_size")],
            [InlineKeyboardButton("📊 أقصى صفقات متزامنة", callback_data="whale:set_max_trades")],
            [InlineKeyboardButton("🛑 حد الخسارة اليومي",  callback_data="whale:set_daily_limit")],
            [InlineKeyboardButton("◀️ رجوع", callback_data="whale:menu")],
        ]),
    )


async def whale_set_size_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    s = await _get_settings(update.effective_user.id)
    context.user_data["_whale_setting"] = "size"
    await query.edit_message_text(
        f"💰 *حجم الصفقة — Whale*\n\n"
        f"الحالي: `${s['trade_size']:.0f} USDT`\n\n"
        f"أدخل المبلغ الجديد بالـ USDT:\n"
        f"النطاق: `${_MIN_TRADE_SIZE:.0f}` — `${_MAX_TRADE_SIZE:,.0f}`\n\n"
        "/cancel للإلغاء",
        parse_mode="Markdown",
    )


async def whale_set_max_trades_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    settings = await db.get_settings(update.effective_user.id) or {}
    current = int(settings.get("whale_max_trades", 3))
    context.user_data["_whale_setting"] = "max_trades"
    await query.edit_message_text(
        f"📊 *أقصى صفقات متزامنة — Whale*\n\n"
        f"الحالي: `{current}` صفقة\n\n"
        f"أدخل العدد الجديد (1 — 10):\n\n"
        "/cancel للإلغاء",
        parse_mode="Markdown",
    )


async def whale_set_daily_limit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    settings = await db.get_settings(update.effective_user.id) or {}
    current = float(settings.get("whale_daily_loss_limit", 0))
    current_str = f"${current:.0f}" if current > 0 else "غير محدد"
    context.user_data["_whale_setting"] = "daily_limit"
    await query.edit_message_text(
        f"🛑 *حد الخسارة اليومي — Whale*\n\n"
        f"الحالي: `{current_str}`\n\n"
        f"أدخل الحد الأقصى للخسارة اليومية بالـ USDT.\n"
        f"أرسل `0` لإلغاء الحد.\n\n"
        "/cancel للإلغاء",
        parse_mode="Markdown",
    )


async def whale_setting_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for any whale setting."""
    user_id = update.effective_user.id
    setting = context.user_data.pop("_whale_setting", None)
    if not setting:
        return

    text = update.message.text.strip()

    if setting == "size":
        try:
            val = float(text)
            if not (_MIN_TRADE_SIZE <= val <= _MAX_TRADE_SIZE):
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                f"❌ أدخل رقماً بين ${_MIN_TRADE_SIZE:.0f} و ${_MAX_TRADE_SIZE:,.0f}:"
            )
            context.user_data["_whale_setting"] = setting
            return
        await db.update_settings(user_id, whale_trade_size=val)
        await update.message.reply_text(
            f"✅ تم تغيير حجم صفقة Whale إلى `${val:.0f} USDT`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ إعدادات Whale", callback_data="whale:settings")
            ]]),
        )

    elif setting == "max_trades":
        try:
            val = int(float(text))
            if not (1 <= val <= 10):
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ أدخل رقماً بين 1 و 10:")
            context.user_data["_whale_setting"] = setting
            return
        await db.update_settings(user_id, whale_max_trades=val)
        await update.message.reply_text(
            f"✅ تم تغيير أقصى صفقات Whale إلى `{val}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ إعدادات Whale", callback_data="whale:settings")
            ]]),
        )

    elif setting == "daily_limit":
        try:
            val = float(text)
            if val < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ أدخل رقماً أكبر من أو يساوي 0:")
            context.user_data["_whale_setting"] = setting
            return
        await db.update_settings(user_id, whale_daily_loss_limit=val)
        msg = f"✅ تم تعيين حد الخسارة اليومي لـ Whale إلى `${val:.0f} USDT`" if val > 0 else "✅ تم إلغاء حد الخسارة اليومي لـ Whale"
        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ إعدادات Whale", callback_data="whale:settings")
            ]]),
        )


async def whale_size_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Usage: /whale_size 20"""
    user_id = update.effective_user.id
    args = context.args

    if not args:
        s = await _get_settings(user_id)
        await update.message.reply_text(
            f"⚙️ حجم الصفقة الحالي: `${s['trade_size']:.0f}`\n\n"
            f"لتغييره: `/whale_size <المبلغ>`\n"
            f"مثال: `/whale_size 20`\n\n"
            f"الحد الأدنى: ${_MIN_TRADE_SIZE:.0f}  ·  الحد الأقصى: ${_MAX_TRADE_SIZE:,.0f}",
            parse_mode="Markdown",
        )
        return

    try:
        size = float(args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ أدخل رقماً صحيحاً. مثال: `/whale_size 20`",
            parse_mode="Markdown",
        )
        return

    if size < _MIN_TRADE_SIZE or size > _MAX_TRADE_SIZE:
        await update.message.reply_text(
            f"❌ يجب أن يكون المبلغ بين ${_MIN_TRADE_SIZE:.0f} و ${_MAX_TRADE_SIZE:,.0f}",
        )
        return

    await db.update_settings(user_id, whale_trade_size=size)
    await update.message.reply_text(
        f"✅ تم تغيير حجم صفقة Whale إلى `${size:.0f}` USDT",
        parse_mode="Markdown",
    )


async def whale_open_trades_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    await query.edit_message_text("⏳ جاري التحقق من الصفقات...")

    # Fetch from DB
    rows = await db.load_scalping_trades()
    trades = [r for r in rows if r.get("user_id") == user_id and r.get("strategy") == "whale"]

    if not trades:
        await query.edit_message_text(
            "📊 *Whale — الصفقات المفتوحة*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "لا توجد صفقات مفتوحة حالياً.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ رجوع", callback_data="whale:menu")]
            ]),
        )
        return

    # Cross-check with actual MEXC balance — remove stale trades
    settings = await db.get_settings(user_id)
    if settings and settings.get("mexc_api_key"):
        client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
        try:
            balance = await client.exchange.fetch_balance()
            free = balance.get("free", {})
            stale = []
            for t in trades:
                base = t["symbol"].replace("/USDT", "")
                qty  = float(free.get(base, 0) or 0)
                if qty < 1e-6:
                    stale.append(t["symbol"])
            for sym in stale:
                await whale_monitor.remove_trade(sym)
            trades = [t for t in trades if t["symbol"] not in stale]
        except Exception:
            pass
        finally:
            await client.close()

    if not trades:
        await query.edit_message_text(
            "📊 *Whale — الصفقات المفتوحة*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "لا توجد صفقات مفتوحة حالياً.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ رجوع", callback_data="whale:menu")]
            ]),
        )
        return

    text = "📊 *Whale — الصفقات المفتوحة*\n\n━━━━━━━━━━━━━━━━━━━━━\n"
    for t in trades:
        t1 = "✅" if t["t1_hit"] else "⏳"
        text += (
            f"◈ *{t['symbol']}*\n"
            f"   دخول: `${t['entry_price']:.6g}`\n"
            f"   T1: `${t['target1']:.6g}` {t1}  ·  T2: `${t['target2']:.6g}`\n"
            f"   وقف: `${t['stop_loss']:.6g}`\n\n"
        )
    text += "━━━━━━━━━━━━━━━━━━━━━"

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ رجوع", callback_data="whale:menu")]
        ]),
    )


# ── Manual sell — Whale ────────────────────────────────────────────────────────

async def whale_sell_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    rows = await db.load_scalping_trades()
    trades = [r for r in rows if r.get("user_id") == user_id and r.get("strategy") == "whale"]

    if not trades:
        await query.edit_message_text(
            "📊 *بيع صفقة Whale*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "لا توجد صفقات مفتوحة حالياً.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ رجوع", callback_data="whale:menu")]
            ]),
        )
        return

    buttons = []
    for t in trades:
        sym = t["symbol"]
        t1_mark = "✅" if t.get("t1_hit") else "⏳"
        buttons.append([InlineKeyboardButton(f"🔴 {sym}  {t1_mark}", callback_data=f"whale:sell_confirm:{sym}")])
    buttons.append([InlineKeyboardButton("◀️ رجوع", callback_data="whale:menu")])

    await query.edit_message_text(
        "🔴 *بيع صفقة Whale يدوياً*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "اختر الصفقة التي تريد إغلاقها:\n\n"
        "✅ = هدف 1 تحقق  ·  ⏳ = لم يتحقق بعد",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def whale_sell_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    symbol = query.data.split(":", 2)[2]

    trade = whale_monitor.open_trades.get(symbol)
    if not trade:
        rows = await db.load_scalping_trades()
        for r in rows:
            if r["symbol"] == symbol and r.get("user_id") == user_id:
                trade = r
                break

    if not trade:
        await query.answer("❌ الصفقة غير موجودة أو أُغلقت بالفعل", show_alert=True)
        return

    entry  = float(trade["entry_price"])
    sl     = float(trade["stop_loss"])
    t1     = float(trade["target1"])
    t2     = float(trade["target2"])
    t1_hit = bool(trade.get("t1_hit"))

    await query.edit_message_text(
        f"⚠️ *تأكيد بيع {symbol} — Whale*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 دخول : `${entry:.6g}`\n"
        f"🎯 هدف 1: `${t1:.6g}`  {'✅ تحقق' if t1_hit else '⏳ لم يتحقق'}\n"
        f"🏆 هدف 2: `${t2:.6g}`\n"
        f"🛑 وقف  : `${sl:.6g}`\n\n"
        "سيتم إلغاء جميع الأوردرات وبيع الكمية بسعر السوق.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ تأكيد البيع", callback_data=f"whale:sell_exec:{symbol}"),
                InlineKeyboardButton("❌ إلغاء", callback_data="whale:sell_pick"),
            ]
        ]),
    )


async def whale_sell_exec_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    symbol = query.data.split(":", 2)[2]

    await query.edit_message_text(f"⏳ جاري إغلاق صفقة Whale `{symbol}`...", parse_mode="Markdown")

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.edit_message_text(
            "❌ يجب ربط MEXC API أولاً من الإعدادات.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="whale:menu")]]),
        )
        return

    trade = whale_monitor.open_trades.get(symbol)
    if not trade:
        rows = await db.load_scalping_trades()
        for r in rows:
            if r["symbol"] == symbol and r.get("user_id") == user_id:
                trade = dict(r)
                break

    if not trade:
        await query.edit_message_text(
            f"❌ الصفقة `{symbol}` غير موجودة أو أُغلقت بالفعل.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="whale:menu")]]),
        )
        return

    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    try:
        # Cancel all open orders
        from bot.scalping.monitor import trade_monitor as scalping_monitor
        await scalping_monitor.cancel_all_orders(trade, client.exchange)

        base = symbol.replace("/USDT", "")
        balance = await client.exchange.fetch_balance()
        free_qty = float(balance.get("free", {}).get(base, 0) or 0)

        if free_qty < 1e-8:
            await query.edit_message_text(
                f"⚠️ *{symbol}* — رصيد صفر\n\nلا يوجد رصيد لبيعه.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="whale:menu")]]),
            )
            await whale_monitor.remove_trade(symbol)
            return

        sell_order = await client.exchange.create_market_sell_order(symbol, free_qty)
        sell_price = float(sell_order.get("average") or sell_order.get("price") or trade["entry_price"])
        entry = float(trade["entry_price"])
        pnl_pct = ((sell_price - entry) / entry) * 100
        pnl_icon = "🟢" if pnl_pct >= 0 else "🔴"

        await whale_monitor.remove_trade(symbol)

        await query.edit_message_text(
            f"✅ *{symbol}* — تم البيع اليدوي (Whale)\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 سعر البيع: `${sell_price:.6g}`\n"
            f"🟢 سعر الدخول: `${entry:.6g}`\n"
            f"{pnl_icon} الربح/الخسارة: `{pnl_pct:+.2f}%`\n"
            f"📦 الكمية: `{free_qty:.6g}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع لـ Whale", callback_data="whale:menu")]]),
        )
        logger.info(f"Whale manual sell {symbol} user {user_id}: qty={free_qty} @ {sell_price:.6g} pnl={pnl_pct:.2f}%")

    except Exception as e:
        logger.error(f"Whale manual sell failed {symbol} user {user_id}: {e}")
        await query.edit_message_text(
            f"❌ *فشل البيع*\n\n`{str(e)[:120]}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="whale:menu")]]),
        )
    finally:
        await client.close()


# ── Scanner job (every 5 min) ──────────────────────────────────────────────────

async def run_whale_scan(app) -> None:
    try:
        users = await db.get_all_users_with_whale()
    except Exception as e:
        logger.error(f"WhaleScan: failed to fetch users: {e}")
        return

    for row in users:
        user_id = row["user_id"]
        client  = None
        try:
            settings = await db.get_settings(user_id)
            if not settings or not settings.get("mexc_api_key"):
                continue

            trade_size = float(settings.get("whale_trade_size", 10.0))
            max_trades = int(settings.get("whale_max_trades", 3))
            client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])

            # Balance check
            try:
                _, usdt_balance = await asyncio.wait_for(
                    client.get_portfolio(), timeout=15
                )
            except Exception as e:
                logger.warning(f"WhaleScan: balance check failed user {user_id}: {e}")
                continue

            if usdt_balance < trade_size:
                logger.warning(
                    f"WhaleScan: low balance for user {user_id} — "
                    f"${usdt_balance:.2f} < ${trade_size:.0f}, scanning anyway"
                )

            # Run scan — only pass this user's open symbols to avoid blocking
            # symbols that belong to other users
            all_open = whale_monitor.open_symbols_for(user_id)

            # ── Max trades cap ─────────────────────────────────────────────
            if len(all_open) >= max_trades:
                logger.info(
                    f"WhaleScan: user {user_id} at max_trades={max_trades}, skipping scan"
                )
                continue
            try:
                setups = await asyncio.wait_for(
                    whale_scan(client.exchange, all_open, trade_size),
                    timeout=90,
                )
            except asyncio.TimeoutError:
                logger.warning(f"WhaleScan: timed out for user {user_id}")
                continue

            if not setups:
                logger.info(f"WhaleScan: no setups for user {user_id}")
                continue

            # Refresh balance before executing
            try:
                _, usdt_balance = await asyncio.wait_for(
                    client.get_portfolio(), timeout=15
                )
            except Exception:
                pass  # use last known balance

            for setup in setups:
                symbol = setup["symbol"]

                if usdt_balance < trade_size:
                    await app.bot.send_message(
                        user_id,
                        f"⚠️ *Whale — رصيد غير كافٍ*\n\n"
                        f"📌 العملة: `{symbol}`\n"
                        f"💰 رصيدك: `${usdt_balance:.2f} USDT`\n"
                        f"📦 المطلوب: `${trade_size:.0f} USDT`",
                        parse_mode="Markdown",
                    )
                    continue

                result = await execute_trade(setup, client.exchange)

                if result["status"] == "ok":
                    usdt_balance -= trade_size
                    await whale_monitor.add_trade(setup, result, user_id)
                    await _send_signal(app.bot, user_id, setup, executed=True)
                    await _send_orders_status(app.bot, user_id, setup, result)
                else:
                    reason = result.get("reason", "")
                    logger.warning(f"WhaleScan: execute failed {symbol}: {reason}")
                    await _send_signal(app.bot, user_id, setup, executed=False, fail_reason=reason)

        except Exception as e:
            logger.error(f"WhaleScan: error user {user_id}: {e}")
        finally:
            if client:
                try:
                    await client.close()
                except Exception:
                    pass


# ── Monitor job (every 30 sec) ─────────────────────────────────────────────────

async def run_whale_monitor(app) -> None:
    if not whale_monitor.open_trades:
        return

    try:
        users = await db.get_all_users_with_whale()
    except Exception:
        return

    for row in users:
        user_id = row["user_id"]
        try:
            settings = await db.get_settings(user_id)
            if not settings or not settings.get("mexc_api_key"):
                continue
            client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
            try:
                await whale_monitor.check_all(client.exchange, app.bot, user_id)
            finally:
                await client.close()
        except Exception as e:
            logger.error(f"WhaleMonitor: error user {user_id}: {e}")


# ── Signal message ─────────────────────────────────────────────────────────────

async def _send_signal(bot, user_id: int, setup: dict,
                       executed: bool = False, fail_reason: str = "") -> None:
    sym   = setup["symbol"]
    entry = setup["entry_price"]
    t1    = setup["target1"]
    t2    = setup["target2"]
    sl    = setup["stop_loss"]
    rr    = setup["risk_reward"]

    t1_pct = ((t1 / entry) - 1) * 100
    t2_pct = ((t2 / entry) - 1) * 100
    sl_pct = ((sl / entry) - 1) * 100

    exec_line = (
        "✅ *تم تنفيذ الصفقة تلقائياً*" if executed
        else f"⚠️ *لم يُنفَّذ:* {fail_reason[:60]}" if fail_reason
        else "📋 *إشعار فرصة*"
    )

    text = (
        f"🐋 *Whale Order Flow*\n\n"
        f"📌 `{sym}`\n"
        f"⏱ FVG + CVD Shift + 5M Breakout\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 دخول  : `${entry:.6g}`\n"
        f"🎯 هدف 1 : `${t1:.6g}`  (`+{t1_pct:.2f}%`) — بيع 60%\n"
        f"🎯 هدف 2 : `${t2:.6g}`  (`+{t2_pct:.2f}%`) — بيع 40%\n"
        f"🛑 وقف   : `${sl:.6g}`  (`{sl_pct:.2f}%`)\n"
        f"📊 R/R   : `1:{rr}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💧 FVG تجميع ✅\n"
        f"📈 CVD Shift ✅\n"
        f"🕯 5M Breakout ✅\n\n"
        f"{exec_line}"
    )
    try:
        await bot.send_message(user_id, text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"WhaleSignal: notify failed {user_id}: {e}")


async def _send_orders_status(bot, user_id: int, setup: dict, result: dict) -> None:
    """Send a follow-up message confirming which orders were placed on MEXC."""
    sym       = setup["symbol"]
    t1_placed = result.get("t1_placed", False)
    sl_placed = result.get("sl_placed", False)
    t1_error  = result.get("t1_error", "")
    sl_error  = result.get("sl_error", "")

    t1_id = result.get("target1_order", {}).get("id", "")
    sl_id = result.get("sl_order", {}).get("id", "")

    def _translate(err: str) -> str:
        r = err.lower()
        if "insufficient" in r or "balance" in r or "not enough" in r:
            return "رصيد غير كافٍ"
        if "minimum" in r or "min" in r or "too small" in r:
            return "المبلغ أقل من الحد الأدنى"
        if "invalid" in r and ("symbol" in r or "pair" in r):
            return "رمز العملة غير مدعوم"
        if "auth" in r or "api" in r or "key" in r or "signature" in r:
            return "خطأ في مفاتيح API"
        if "timeout" in r or "timed out" in r:
            return "انتهت المهلة"
        return err[:60]

    t1_line = (
        f"✅ هدف 1 (T1) — وُضع على MEXC  `#{t1_id}`"
        if t1_placed else
        f"❌ هدف 1 (T1) — *فشل الوضع*\n   `{_translate(t1_error)}`"
    )
    sl_line = (
        f"✅ وقف الخسارة (SL) — وُضع على MEXC  `#{sl_id}`"
        if sl_placed else
        f"❌ وقف الخسارة (SL) — *فشل الوضع*\n   `{_translate(sl_error)}`"
    )

    if t1_placed and sl_placed:
        text = (
            f"📋 *{sym}* — أوردرات MEXC\n\n"
            f"{t1_line}\n"
            f"{sl_line}"
        )
    else:
        text = (
            f"⚠️ *{sym}* — تحقق من أوردرات MEXC\n\n"
            f"{t1_line}\n"
            f"{sl_line}\n\n"
            f"_الصفقة مفتوحة لكن بعض الأوردرات لم تُوضع على المنصة — راجع حسابك يدوياً._"
        )

    try:
        await bot.send_message(user_id, text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"WhaleOrdersStatus: notify failed {user_id}: {e}")
