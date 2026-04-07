"""
Telegram handler for the Momentum Breakout strategy.

Menu flow:
  momentum:menu       — main menu (toggle on/off, open trades, settings)
  momentum:toggle     — enable / disable scanning
  momentum:trades     — list open trades
  momentum:sell_pick  — pick a trade to close manually
  momentum:sell:<sym> — confirm manual close
  momentum:settings   — show/edit settings
  momentum:set_size   — set trade size
  momentum:set_max    — set max open trades
  momentum:set_loss   — set daily loss limit
"""

import asyncio
import logging
from datetime import datetime, timezone

import ccxt.async_support as ccxt

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.database import db
from bot.keyboards import momentum_menu_kb, momentum_settings_kb, back_to_main_kb
from bot.momentum.monitor import momentum_monitor
from bot.momentum.scanner import get_setups
from bot.momentum.executor import execute_setup

logger = logging.getLogger(__name__)

# ConversationHandler states
SET_SIZE, SET_MAX, SET_LOSS = range(3)


# ── Menu ───────────────────────────────────────────────────────────────────────

async def momentum_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    action  = query.data.split(":", 1)[1] if ":" in query.data else "menu"
    user_id = update.effective_user.id

    if action == "menu":
        await _show_menu(query, user_id)

    elif action == "toggle":
        settings   = await db.get_settings(user_id) or {}
        current    = bool(settings.get("momentum_enabled"))
        await db.update_settings(user_id, momentum_enabled=0 if current else 1)
        await _show_menu(query, user_id)

    elif action == "trades":
        trades = momentum_monitor.open_trades_for(user_id)
        if not trades:
            await query.edit_message_text(
                "📊 *Momentum — الصفقات المفتوحة*\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "لا توجد صفقات مفتوحة حالياً.\n\n"
                "_سيبدأ البوت بالبحث تلقائياً عند تفعيله_",
                parse_mode="Markdown",
                reply_markup=momentum_menu_kb(False),
            )
            return
        lines = []
        for t in trades:
            entry  = float(t["entry_price"])
            sl     = float(t["stop_loss"])
            t1     = float(t["target1"])
            t2     = float(t["target2"])
            t1_hit = "✅" if t.get("t1_hit") else "⬜"
            vol    = float(t.get("volume_ratio", 0))
            lines.append(
                f"🔹 *{t['symbol']}*\n"
                f"  💰 دخول: `${entry:.6g}`\n"
                f"  🛑 SL: `${sl:.6g}`\n"
                f"  🎯 T1: `${t1:.6g}` {t1_hit}  🏆 T2: `${t2:.6g}`\n"
                f"  📊 حجم: `{vol:.1f}x`  🕐 `{t.get('opened_at', '')}`"
            )
        await query.edit_message_text(
            f"📊 *Momentum — {len(trades)} صفقة مفتوحة*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            + "\n\n".join(lines),
            parse_mode="Markdown",
            reply_markup=momentum_menu_kb(True),
        )

    elif action == "sell_pick":
        trades = momentum_monitor.open_trades_for(user_id)
        if not trades:
            await query.edit_message_text(
                "لا توجد صفقات مفتوحة.", reply_markup=back_to_main_kb()
            )
            return
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        buttons = [
            [InlineKeyboardButton(
                f"🔴 {t['symbol']}  ·  دخول ${float(t['entry_price']):.6g}",
                callback_data=f"momentum:sell:{t['symbol']}"
            )]
            for t in trades
        ]
        buttons.append([InlineKeyboardButton("◀️ رجوع", callback_data="momentum:menu")])
        await query.edit_message_text(
            "اختر الصفقة التي تريد إغلاقها:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif action.startswith("sell:"):
        symbol = action.split(":", 1)[1]
        await _manual_sell(query, user_id, symbol)

    elif action == "settings":
        # الإعدادات مدمجة في القائمة الرئيسية
        await _show_menu(query, user_id)

    elif action == "set_size":
        settings = await db.get_settings(user_id) or {}
        current  = settings.get("momentum_trade_size", 20.0)
        context.user_data["_momentum_setting"] = "size"
        await query.edit_message_text(
            f"💵 *حجم الصفقة*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"الحالي: `${current:.0f}`\n\n"
            f"أرسل القيمة الجديدة بالدولار:\n"
            f"مثال: `25`\n\n"
            f"`/cancel` للإلغاء",
            parse_mode="Markdown",
        )
        return SET_SIZE

    elif action == "set_max":
        settings = await db.get_settings(user_id) or {}
        current  = settings.get("momentum_max_trades", 3)
        context.user_data["_momentum_setting"] = "max"
        await query.edit_message_text(
            f"📊 *أقصى صفقات مفتوحة*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"الحالي: `{current}`\n\n"
            f"أرسل الرقم الجديد \\(1 إلى 10\\):\n\n"
            f"`/cancel` للإلغاء",
            parse_mode="Markdown",
        )
        return SET_MAX

    elif action == "set_loss":
        settings = await db.get_settings(user_id) or {}
        current  = settings.get("momentum_daily_loss", 0.0)
        context.user_data["_momentum_setting"] = "loss"
        current_str = "غير محدد" if not current else f"${current:.0f}"
        await query.edit_message_text(
            f"🛑 *حد الخسارة اليومي*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"الحالي: `{current_str}`\n\n"
            f"أرسل القيمة بالدولار \\(0 = غير محدد\\):\n\n"
            f"`/cancel` للإلغاء",
            parse_mode="Markdown",
        )
        return SET_LOSS


async def _show_menu(query, user_id: int) -> None:
    settings   = await db.get_settings(user_id) or {}
    enabled    = bool(settings.get("momentum_enabled"))
    trades     = momentum_monitor.open_trades_for(user_id)
    trade_size = float(settings.get("momentum_trade_size", 20.0))
    max_trades = int(settings.get("momentum_max_trades", 3))
    daily_loss = float(settings.get("momentum_daily_loss", 0.0))

    status_icon = "🟢" if enabled else "🔴"
    status_text = "يعمل — يبحث كل 10 دقائق" if enabled else "متوقف"

    slots_used = len(trades)
    slots_bar  = "🟩" * slots_used + "⬜" * (max_trades - slots_used)

    loss_line = f"\n🛑 حد الخسارة اليومي: *${daily_loss:.0f}*" if daily_loss > 0 else ""

    await query.edit_message_text(
        f"⚡ *Momentum Breakout*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{status_icon} الحالة: *{status_text}*\n"
        f"📊 الصفقات: {slots_bar} *{slots_used}/{max_trades}*\n"
        f"💵 حجم الصفقة: *${trade_size:.0f}*{loss_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 T1: +2% → بيع 50% + SL للـ Breakeven\n"
        f"🏆 T2: +4% → بيع الباقي\n"
        f"⏰ إغلاق تلقائي بعد ساعتين",
        parse_mode="Markdown",
        reply_markup=momentum_menu_kb(enabled, trade_size, max_trades, daily_loss),
    )



async def _manual_sell(query, user_id: int, symbol: str) -> None:
    trades = momentum_monitor.open_trades_for(user_id)
    trade = next((t for t in trades if t["symbol"] == symbol), None)
    if not trade:
        await query.edit_message_text("الصفقة غير موجودة.", reply_markup=back_to_main_kb())
        return

    settings = await db.get_settings(user_id) or {}
    if not settings.get("mexc_api_key"):
        await query.edit_message_text("مفاتيح API غير موجودة.", reply_markup=back_to_main_kb())
        return

    await query.edit_message_text(f"⏳ جاري إغلاق `{symbol}`...", parse_mode="Markdown")

    exchange = ccxt.mexc({
        "apiKey":          settings["mexc_api_key"],
        "secret":          settings["mexc_secret_key"],
        "enableRateLimit": True,
        "timeout":         10000,
        "options":         {"defaultType": "spot"},
    })
    try:
        pair    = f"{symbol}/USDT"
        ticker  = await exchange.fetch_ticker(pair)
        price   = float(ticker.get("last") or 0)
        t1_hit  = bool(trade.get("t1_hit"))
        qty     = float(trade["qty_half"] if t1_hit else trade["qty"])
        entry   = float(trade["entry_price"])

        await exchange.create_market_sell_order(pair, qty)

        pnl_pct  = ((price - entry) / entry) * 100
        pnl_usdt = qty * (price - entry)
        sign     = "+" if pnl_usdt >= 0 else ""

        momentum_monitor.remove_trade(symbol)
        await db.delete_momentum_trade(symbol)

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        await query.edit_message_text(
            f"{'✅' if pnl_usdt >= 0 else '❌'} *تم الإغلاق اليدوي*\n\n"
            f"📈 `{symbol}`\n"
            f"💰 سعر البيع: `${price:.6g}`\n"
            f"📊 نتيجة: `{sign}{pnl_pct:.2f}%`  (`{sign}${pnl_usdt:.2f}`)\n"
            f"🕐 {now_str}",
            parse_mode="Markdown",
            reply_markup=back_to_main_kb(),
        )
    except Exception as e:
        await query.edit_message_text(
            f"❌ فشل الإغلاق: {str(e)[:80]}", reply_markup=back_to_main_kb()
        )
    finally:
        await exchange.close()


# ── Settings conversation ──────────────────────────────────────────────────────

async def momentum_setting_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text    = update.message.text.strip()
    setting = context.user_data.get("_momentum_setting")

    try:
        val = float(text)
    except ValueError:
        await update.message.reply_text("❌ أرسل رقماً صحيحاً.", reply_markup=back_to_main_kb())
        return ConversationHandler.END

    from bot.keyboards import momentum_menu_kb as _mkb
    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="momentum:menu")]])

    if setting == "size":
        if val < 5:
            await update.message.reply_text("❌ الحد الأدنى $5.", reply_markup=back_kb)
            return ConversationHandler.END
        await db.update_settings(user_id, momentum_trade_size=val)
        await update.message.reply_text(
            f"✅ *تم الحفظ*\n💵 حجم الصفقة: `${val:.0f}`",
            parse_mode="Markdown", reply_markup=back_kb
        )

    elif setting == "max":
        val = int(val)
        if not 1 <= val <= 10:
            await update.message.reply_text("❌ أدخل رقماً بين 1 و 10.", reply_markup=back_kb)
            return ConversationHandler.END
        await db.update_settings(user_id, momentum_max_trades=val)
        await update.message.reply_text(
            f"✅ *تم الحفظ*\n📊 أقصى صفقات: `{val}`",
            parse_mode="Markdown", reply_markup=back_kb
        )

    elif setting == "loss":
        await db.update_settings(user_id, momentum_daily_loss=val)
        label = f"${val:.0f}" if val > 0 else "غير محدد"
        await update.message.reply_text(
            f"✅ *تم الحفظ*\n🛑 حد الخسارة اليومي: `{label}`",
            parse_mode="Markdown", reply_markup=back_kb
        )

    context.user_data.pop("_momentum_setting", None)
    return ConversationHandler.END


async def momentum_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("_momentum_setting", None)
    await update.message.reply_text("تم الإلغاء.", reply_markup=back_to_main_kb())
    return ConversationHandler.END


# ── Background scan job ────────────────────────────────────────────────────────

async def run_momentum_scan(app) -> None:
    """
    Called every 10 minutes by the scheduler.
    Scans for setups and executes entries for all enabled users.
    """
    users = await db.get_all_users_with_momentum()
    if not users:
        return

    for row in users:
        user_id    = row["user_id"]
        trade_size = float(row.get("momentum_trade_size") or 20.0)
        max_trades = int(row.get("momentum_max_trades") or 3)
        daily_loss = float(row.get("momentum_daily_loss") or 0.0)

        settings = await db.get_settings(user_id)
        if not settings or not settings.get("mexc_api_key"):
            continue

        open_syms = momentum_monitor.open_symbols_for(user_id)
        remaining = max_trades - len(open_syms)
        if remaining <= 0:
            continue

        # Daily loss guard
        if daily_loss > 0:
            today_loss = await db.get_momentum_daily_loss(user_id)
            if today_loss >= daily_loss:
                logger.info(f"Momentum: user {user_id} hit daily loss limit, skipping")
                continue

        exchange = ccxt.mexc({
            "apiKey":          settings["mexc_api_key"],
            "secret":          settings["mexc_secret_key"],
            "enableRateLimit": True,
            "timeout":         10000,
            "options":         {"defaultType": "spot"},
        })
        try:
            setups = await asyncio.wait_for(
                get_setups(exchange, open_syms, trade_size, max_setups=remaining),
                timeout=90,
            )
            for setup in setups:
                # Re-check remaining slots — previous setup may have filled one
                if len(momentum_monitor.open_symbols_for(user_id)) >= max_trades:
                    break
                success, msg = await execute_setup(exchange, setup, user_id, trade_size)
                try:
                    await app.bot.send_message(user_id, msg, parse_mode="Markdown")
                except Exception:
                    pass
                if not success:
                    logger.warning(f"Momentum: execute failed for {setup['symbol']}: {msg}")

        except asyncio.TimeoutError:
            logger.warning(f"Momentum scan timed out for user {user_id}")
        except Exception as e:
            logger.error(f"Momentum scan error user={user_id}: {e}")
        finally:
            try:
                await exchange.close()
            except Exception:
                pass
