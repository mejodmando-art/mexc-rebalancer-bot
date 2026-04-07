"""
Telegram handlers for the Smart Liquidity Flow scalping feature.

Provides:
  - /scalping menu with status, start/stop controls
  - Real-time signal notifications
  - Open trades overview
"""

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.database import db
from bot.keyboards import main_menu_kb, scalping_menu_kb, scalping_settings_kb
from bot.mexc_client import MexcClient
from bot.scalping.scanner import scan
from bot.scalping.executor import execute_trade
from bot.scalping.monitor import trade_monitor

_MIN_TRADE_SIZE = 5.0
_MAX_TRADE_SIZE = 10_000.0

logger = logging.getLogger(__name__)

# ── Keyboards ──────────────────────────────────────────────────────────────────

# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_scalping_settings(user_id: int) -> dict:
    settings = await db.get_settings(user_id) or {}
    return {
        "enabled":        bool(settings.get("scalping_enabled", 0)),
        "trade_size":     float(settings.get("scalping_trade_size", 10.0)),
        "mexc_api_key":   settings.get("mexc_api_key", ""),
        "mexc_secret_key": settings.get("mexc_secret_key", ""),
    }


def _status_text(sc: dict, open_count: int) -> str:
    status = "🟢 يعمل" if sc["enabled"] else "🔴 متوقف"
    return (
        "⚡ *Smart Liquidity Flow*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"  الحالة: {status}\n"
        f"  حجم الصفقة: `${sc['trade_size']:.0f}`\n"
        f"  صفقات مفتوحة: *{open_count}*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 *الاستراتيجية:*\n"
        "  ◈ 4H — مناطق Liquidity (السياق)\n"
        "  ◈ CVD — ضغط الشراء الفوري\n"
        "  ◈ 15M — Liquidity Sweep\n"
        "  ◈ 5M — Engulfing (تأكيد الدخول)\n"
        "━━━━━━━━━━━━━━━━━━━━━"
    )


# ── Handlers ───────────────────────────────────────────────────────────────────

async def scalping_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    sc = await _get_scalping_settings(user_id)
    open_count = len(trade_monitor.open_symbols_for(user_id))

    await query.edit_message_text(
        _status_text(sc, open_count),
        parse_mode="Markdown",
        reply_markup=scalping_menu_kb(sc["enabled"]),
    )


async def scalping_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id

    sc = await _get_scalping_settings(user_id)

    if not sc["mexc_api_key"]:
        await query.answer("❌ يجب ربط MEXC API أولاً من الإعدادات", show_alert=True)
        return

    new_state = 0 if sc["enabled"] else 1
    await db.update_settings(user_id, scalping_enabled=new_state)

    sc["enabled"] = bool(new_state)
    open_count = len(trade_monitor.open_symbols_for(user_id))

    action = "تشغيل" if new_state else "إيقاف"
    await query.answer(f"✅ تم {action} الـ Scalping")

    await query.edit_message_text(
        _status_text(sc, open_count),
        parse_mode="Markdown",
        reply_markup=scalping_menu_kb(sc["enabled"]),
    )


async def scalping_open_trades_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    await query.edit_message_text("⏳ جاري التحقق من الصفقات...")

    # Fetch from DB
    rows = await db.load_scalping_trades()
    trades = [r for r in rows if r.get("user_id") == user_id and r.get("strategy") != "whale"]

    if not trades:
        await query.edit_message_text(
            "📊 *الصفقات المفتوحة*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "لا توجد صفقات مفتوحة حالياً.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ رجوع", callback_data="scalping:menu")]
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
                base       = t["symbol"].replace("/USDT", "")
                qty        = float(free.get(base, 0) or 0)
                entry      = float(t.get("entry_price") or 0)
                value_usdt = qty * entry if entry > 0 else 0.0
                # Treat as stale if position value is below $1
                if value_usdt < 1.0:
                    stale.append(t["symbol"])
            # Auto-clean stale trades from DB and memory
            for sym in stale:
                await trade_monitor.remove_trade(sym)
            trades = [t for t in trades if t["symbol"] not in stale]
        except Exception:
            pass
        finally:
            await client.close()

    if not trades:
        await query.edit_message_text(
            "📊 *الصفقات المفتوحة*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "لا توجد صفقات مفتوحة حالياً.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ رجوع", callback_data="scalping:menu")]
            ]),
        )
        return

    text = "📊 *الصفقات المفتوحة*\n\n━━━━━━━━━━━━━━━━━━━━━\n"
    for t in trades:
        t1_status = "✅" if t["t1_hit"] else "⏳"
        be_status  = " 🔒 Breakeven" if t["breakeven"] else ""
        text += (
            f"◈ *{t['symbol']}*{be_status}\n"
            f"   دخول: `${t['entry_price']:.6g}`\n"
            f"   وقف:  `${t['stop_loss']:.6g}`\n"
            f"   T1: `${t['target1']:.6g}` {t1_status}  ·  T2: `${t['target2']:.6g}`\n\n"
        )
    text += "━━━━━━━━━━━━━━━━━━━━━"

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ رجوع", callback_data="scalping:menu")]
        ]),
    )


async def scalping_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    sc = await _get_scalping_settings(user_id)
    settings = await db.get_settings(user_id) or {}

    max_trades  = int(settings.get("scalping_max_trades", 3))
    daily_limit = float(settings.get("scalping_daily_loss_limit", 0))
    trail_pct   = float(settings.get("scalping_trail_pct", 1.5))

    await query.edit_message_text(
        "⚙️ *إعدادات Scalping*\n\n"
        "اضغط على أي إعداد لتغييره:",
        parse_mode="Markdown",
        reply_markup=scalping_settings_kb(sc["trade_size"], max_trades, daily_limit, trail_pct),
    )


# ── Scalping settings inline buttons ─────────────────────────────────────────

async def scalping_set_size_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sc = await _get_scalping_settings(update.effective_user.id)
    context.user_data["_scalping_setting"] = "size"
    await query.edit_message_text(
        f"💰 *حجم الصفقة*\n\n"
        f"الحالي: `${sc['trade_size']:.0f} USDT`\n\n"
        f"أدخل المبلغ الجديد بالـ USDT:\n"
        f"مثال: `20` أو `50`\n\n"
        f"النطاق: `${_MIN_TRADE_SIZE:.0f}` — `${_MAX_TRADE_SIZE:,.0f}`\n\n"
        "/cancel للإلغاء",
        parse_mode="Markdown",
    )


async def scalping_set_max_trades_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    settings = await db.get_settings(update.effective_user.id) or {}
    current = int(settings.get("scalping_max_trades", 3))
    context.user_data["_scalping_setting"] = "max_trades"
    await query.edit_message_text(
        f"📊 *أقصى صفقات متزامنة*\n\n"
        f"الحالي: `{current}` صفقة\n\n"
        f"أدخل العدد الجديد (1 — 10):\n\n"
        "/cancel للإلغاء",
        parse_mode="Markdown",
    )


async def scalping_set_daily_limit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    settings = await db.get_settings(update.effective_user.id) or {}
    current = float(settings.get("scalping_daily_loss_limit", 0))
    current_str = f"${current:.0f}" if current > 0 else "غير محدد"
    context.user_data["_scalping_setting"] = "daily_limit"
    await query.edit_message_text(
        f"🛑 *حد الخسارة اليومي*\n\n"
        f"الحالي: `{current_str}`\n\n"
        f"أدخل الحد الأقصى للخسارة اليومية بالـ USDT.\n"
        f"أرسل `0` لإلغاء الحد.\n\n"
        "/cancel للإلغاء",
        parse_mode="Markdown",
    )


async def scalping_set_trail_pct_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    settings = await db.get_settings(update.effective_user.id) or {}
    current = float(settings.get("scalping_trail_pct", 1.5))
    context.user_data["_scalping_setting"] = "trail_pct"
    await query.edit_message_text(
        f"📉 *نسبة Trailing Stop*\n\n"
        f"الحالية: `{current:.1f}%`\n\n"
        f"أدخل النسبة المئوية (0.5 — 5.0):\n"
        f"مثال: `1.5` تعني 1.5% تحت أعلى سعر\n\n"
        "/cancel للإلغاء",
        parse_mode="Markdown",
    )


async def scalping_setting_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for any scalping setting."""
    user_id = update.effective_user.id
    setting = context.user_data.pop("_scalping_setting", None)
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
            context.user_data["_scalping_setting"] = setting
            return
        await db.update_settings(user_id, scalping_trade_size=val)
        await update.message.reply_text(
            f"✅ تم تغيير حجم الصفقة إلى `${val:.0f} USDT`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ إعدادات Scalping", callback_data="scalping:settings")
            ]]),
        )

    elif setting == "max_trades":
        try:
            val = int(float(text))
            if not (1 <= val <= 10):
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ أدخل رقماً بين 1 و 10:")
            context.user_data["_scalping_setting"] = setting
            return
        await db.update_settings(user_id, scalping_max_trades=val)
        await update.message.reply_text(
            f"✅ تم تغيير أقصى صفقات متزامنة إلى `{val}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ إعدادات Scalping", callback_data="scalping:settings")
            ]]),
        )

    elif setting == "daily_limit":
        try:
            val = float(text)
            if val < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ أدخل رقماً أكبر من أو يساوي 0:")
            context.user_data["_scalping_setting"] = setting
            return
        await db.update_settings(user_id, scalping_daily_loss_limit=val)
        msg = f"✅ تم تعيين حد الخسارة اليومي إلى `${val:.0f} USDT`" if val > 0 else "✅ تم إلغاء حد الخسارة اليومي"
        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ إعدادات Scalping", callback_data="scalping:settings")
            ]]),
        )

    elif setting == "trail_pct":
        try:
            val = float(text)
            if not (0.5 <= val <= 5.0):
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ أدخل نسبة بين 0.5 و 5.0:")
            context.user_data["_scalping_setting"] = setting
            return
        await db.update_settings(user_id, scalping_trail_pct=val)
        await update.message.reply_text(
            f"✅ تم تغيير نسبة Trailing Stop إلى `{val:.1f}%`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ إعدادات Scalping", callback_data="scalping:settings")
            ]]),
        )


# ── /scalping_size command ────────────────────────────────────────────────────

async def scalping_size_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Usage: /scalping_size 20"""
    user_id = update.effective_user.id
    args = context.args

    if not args:
        sc = await _get_scalping_settings(user_id)
        await update.message.reply_text(
            f"⚙️ حجم الصفقة الحالي: `${sc['trade_size']:.0f}`\n\n"
            f"لتغييره: `/scalping_size <المبلغ>`\n"
            f"مثال: `/scalping_size 20`\n\n"
            f"الحد الأدنى: ${_MIN_TRADE_SIZE:.0f}  ·  الحد الأقصى: ${_MAX_TRADE_SIZE:,.0f}",
            parse_mode="Markdown",
        )
        return

    try:
        size = float(args[0])
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً صحيحاً. مثال: `/scalping_size 20`", parse_mode="Markdown")
        return

    if size < _MIN_TRADE_SIZE or size > _MAX_TRADE_SIZE:
        await update.message.reply_text(
            f"❌ يجب أن يكون المبلغ بين ${_MIN_TRADE_SIZE:.0f} و ${_MAX_TRADE_SIZE:,.0f}",
        )
        return

    await db.update_settings(user_id, scalping_trade_size=size)
    await update.message.reply_text(
        f"✅ تم تغيير حجم الصفقة إلى `${size:.0f}` USDT",
        parse_mode="Markdown",
    )


# ── Scanner job (called by scheduler every 15 min) ─────────────────────────────

async def run_scalping_scan(app) -> None:
    """
    Fetches all users with scalping enabled, runs the scanner for each,
    and executes valid setups.
    """
    try:
        users = await db.get_all_users_with_scalping()
    except Exception as e:
        logger.error(f"Scalping scan: failed to fetch users: {e}")
        return

    for row in users:
        user_id = row["user_id"]
        client = None
        try:
            settings = await db.get_settings(user_id)
            if not settings or not settings.get("mexc_api_key"):
                continue

            trade_size = float(settings.get("scalping_trade_size", 10.0))
            max_trades = int(settings.get("scalping_max_trades", 3))
            client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])

            # ── Pre-scan balance check ─────────────────────────────────────
            try:
                _, usdt_balance = await asyncio.wait_for(
                    client.get_portfolio(), timeout=15
                )
            except asyncio.TimeoutError:
                logger.warning(f"Scalping: balance check timed out for user {user_id}")
                continue
            except Exception as e:
                logger.warning(f"Scalping: balance check failed for user {user_id}: {e}")
                continue

            if usdt_balance < trade_size:
                logger.warning(
                    f"Scalping: low balance for user {user_id} — "
                    f"${usdt_balance:.2f} < ${trade_size:.0f}, scanning anyway"
                )

            user_open_symbols = trade_monitor.open_symbols_for(user_id)

            # ── Max trades cap ─────────────────────────────────────────────
            if len(user_open_symbols) >= max_trades:
                logger.info(
                    f"Scalping: user {user_id} at max_trades={max_trades}, skipping scan"
                )
                continue

            remaining_slots = max_trades - len(user_open_symbols)
            try:
                setups = await asyncio.wait_for(
                    scan(client.exchange, user_open_symbols, trade_size,
                         max_setups=remaining_slots),
                    timeout=120,
                )
            except asyncio.TimeoutError:
                logger.warning(f"Scalping scan timed out for user {user_id}")
                continue

            # Only notify when setups are found — silent when nothing found
            if setups:
                await app.bot.send_message(
                    user_id,
                    f"✨ *Scalping — وُجدت {len(setups)} فرصة!*\n\n"
                    f"جاري تنفيذ الصفقات...",
                    parse_mode="Markdown",
                )

            # Refresh balance before executing setups
            try:
                _, usdt_balance = await asyncio.wait_for(
                    client.get_portfolio(), timeout=15
                )
            except Exception:
                pass  # use last known balance

            for setup in setups:
                symbol = setup["symbol"]

                # Re-check open count before every execution — the count grows
                # as trades are added inside this loop, so the pre-scan check
                # alone is not enough to enforce the limit accurately.
                current_open = len(trade_monitor.open_symbols_for(user_id))
                if current_open >= max_trades:
                    logger.info(
                        f"Scalping: max_trades={max_trades} reached mid-loop "
                        f"(open={current_open}), stopping execution for user {user_id}"
                    )
                    break

                # Per-trade balance check — notify with symbol name
                if usdt_balance < trade_size:
                    await app.bot.send_message(
                        user_id,
                        f"⚠️ *Scalping — رصيد غير كافٍ*\n\n"
                        f"📌 العملة: `{symbol}`\n"
                        f"💰 رصيدك الحالي: `${usdt_balance:.2f} USDT`\n"
                        f"📦 حجم الصفقة المطلوب: `${trade_size:.0f} USDT`\n\n"
                        f"أضف رصيداً أو قلّل حجم الصفقة بـ `/scalping_size`",
                        parse_mode="Markdown",
                    )
                    logger.warning(
                        f"Scalping: skipping {symbol} for user {user_id} — "
                        f"balance ${usdt_balance:.2f} < trade_size ${trade_size:.0f}"
                    )
                    continue

                result = await execute_trade(setup, client.exchange)

                if result["status"] == "ok":
                    # Deduct from local balance to avoid over-trading in same scan
                    usdt_balance -= trade_size
                    await trade_monitor.add_trade(setup, result, user_id)
                    await _send_signal(app.bot, user_id, setup, executed=True)
                    await _send_orders_status(app.bot, user_id, setup, result)
                else:
                    reason = result.get("reason", "")
                    logger.warning(f"Scalping: execute failed {symbol}: {reason}")
                    await _send_signal(app.bot, user_id, setup, executed=False, fail_reason=reason)

        except Exception as e:
            logger.error(f"Scalping scan error for user {user_id}: {e}")
        finally:
            if client is not None:
                try:
                    await client.close()
                except Exception:
                    pass


# ── Monitor job (called by scheduler every 60 sec) ────────────────────────────

async def run_scalping_monitor(app) -> None:
    """Check all open trades against current prices."""
    if not trade_monitor.open_trades:
        return

    try:
        users = await db.get_all_users_with_scalping()
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
                await trade_monitor.check_all(client.exchange, app.bot, user_id)
            finally:
                await client.close()

        except Exception as e:
            logger.error(f"Scalping monitor error for user {user_id}: {e}")


# ── Signal message ─────────────────────────────────────────────────────────────

def _translate_error(reason: str) -> str:
    """Convert common MEXC/ccxt English errors to readable Arabic."""
    r = reason.lower()
    if "insufficient" in r or "balance" in r or "not enough" in r:
        return "رصيد غير كافٍ في حسابك"
    if "minimum" in r or "min" in r or "too small" in r:
        return "المبلغ أقل من الحد الأدنى المسموح"
    if "invalid" in r and ("symbol" in r or "pair" in r):
        return "رمز العملة غير مدعوم"
    if "auth" in r or "api" in r or "key" in r or "signature" in r:
        return "خطأ في مفاتيح API — تحقق من الإعدادات"
    if "timeout" in r or "timed out" in r:
        return "انتهت المهلة — MEXC لم يستجب"
    if "rate limit" in r or "too many" in r:
        return "تجاوزت حد الطلبات — حاول لاحقاً"
    if "market" in r and "close" in r:
        return "السوق مغلق مؤقتاً"
    # Fallback: return first 60 chars as-is
    return reason[:60]


async def _send_signal(
    bot,
    user_id: int,
    setup: dict,
    executed: bool = False,
    fail_reason: str = "",
) -> None:
    sym   = setup["symbol"]
    rr    = setup["risk_reward"]
    entry = setup["entry_price"]
    t1    = setup["target1"]
    t2    = setup["target2"]
    sl    = setup["stop_loss"]

    # Calculate actual % distances from entry
    t1_pct = ((t1 / entry) - 1) * 100 if entry > 0 else 0
    t2_pct = ((t2 / entry) - 1) * 100 if entry > 0 else 0
    sl_pct = ((sl / entry) - 1) * 100 if entry > 0 else 0

    if executed:
        exec_line = "✅ *تم تنفيذ الصفقة تلقائياً*"
    elif fail_reason:
        exec_line = f"⚠️ *لم يُنفَّذ:* {_translate_error(fail_reason)}"
    else:
        exec_line = "📋 *إشعار فرصة — لم يُنفَّذ تلقائياً*"

    text = (
        f"🎯 *Smart Liquidity Flow*\n\n"
        f"📌 `{sym}`\n"
        f"⏱ التقاطع: 4H + CVD + 15M + 5M\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 دخول  : `${entry:.6g}`\n"
        f"🎯 هدف 1 : `${t1:.6g}`  (`+{t1_pct:.2f}%`)  ← بيع 50%\n"
        f"🏆 هدف 2 : `${t2:.6g}`  (`+{t2_pct:.2f}%`)  ← بيع 50%\n"
        f"🛑 وقف   : `${sl:.6g}`  (`{sl_pct:.2f}%`)\n"
        f"📊 R/R   : `1:{rr}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💧 Liquidity Sweep 15M ✅\n"
        f"📈 CVD صاعد ✅\n"
        f"🕯 Engulfing 5M ✅\n\n"
        f"{exec_line}"
    )
    try:
        await bot.send_message(user_id, text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Signal notify failed for {user_id}: {e}")


# ── Manual sell — multi-select ────────────────────────────────────────────────

_SCALPING_SEL_KEY = "scalping_sell_selected"  # set of selected symbols in user_data


def _scalping_sell_kb(trades: list, selected: set) -> InlineKeyboardMarkup:
    """
    Build the multi-select keyboard.
    Each trade row is a toggle button: ☑ if selected, ☐ if not.
    Bottom row: select-all / deselect-all + sell button + back.
    """
    buttons = []
    for t in trades:
        sym    = t["symbol"]
        t1_hit = "✅" if t.get("t1_hit") else "⏳"
        check  = "☑" if sym in selected else "☐"
        buttons.append([
            InlineKeyboardButton(
                f"{check} {sym}  {t1_hit}",
                callback_data=f"scalping:sell_toggle:{sym}",
            )
        ])

    all_syms  = {t["symbol"] for t in trades}
    all_sel   = all_syms == selected and len(selected) > 0
    sel_count = len(selected)

    # Select-all / deselect-all toggle
    if all_sel:
        toggle_btn = InlineKeyboardButton("☐ إلغاء تحديد الكل", callback_data="scalping:sell_selall:0")
    else:
        toggle_btn = InlineKeyboardButton("☑ تحديد الكل", callback_data="scalping:sell_selall:1")

    sell_label = f"🔴 بيع المحدد ({sel_count})" if sel_count > 0 else "🔴 بيع المحدد"
    sell_btn   = InlineKeyboardButton(sell_label, callback_data="scalping:sell_multi_confirm")

    buttons.append([toggle_btn])
    if sel_count > 0:
        buttons.append([sell_btn])
    buttons.append([InlineKeyboardButton("◀️ رجوع", callback_data="scalping:menu")])

    return InlineKeyboardMarkup(buttons)


def _scalping_sell_text(trades: list, selected: set) -> str:
    count = len(selected)
    hint  = f"محدد: *{count}* من {len(trades)}" if count > 0 else "لم تحدد أي صفقة بعد"
    return (
        "🔴 *بيع صفقات Scalping*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "اضغط على الصفقة لتحديدها أو إلغاء تحديدها.\n"
        "✅ = هدف 1 تحقق  ·  ⏳ = لم يتحقق بعد\n\n"
        f"{hint}"
    )


async def scalping_sell_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: show multi-select list, reset selection."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    rows   = await db.load_scalping_trades()
    trades = [r for r in rows if r.get("user_id") == user_id and r.get("strategy") != "whale"]

    if not trades:
        await query.edit_message_text(
            "📊 *بيع صفقة*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "لا توجد صفقات مفتوحة حالياً.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ رجوع", callback_data="scalping:menu")]
            ]),
        )
        return

    # Reset selection on every fresh open
    context.user_data[_SCALPING_SEL_KEY] = set()

    await query.edit_message_text(
        _scalping_sell_text(trades, set()),
        parse_mode="Markdown",
        reply_markup=_scalping_sell_kb(trades, set()),
    )


async def scalping_sell_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle one symbol in the selection."""
    query   = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    symbol  = query.data.split(":", 2)[2]

    selected: set = context.user_data.get(_SCALPING_SEL_KEY, set())
    if symbol in selected:
        selected.discard(symbol)
    else:
        selected.add(symbol)
    context.user_data[_SCALPING_SEL_KEY] = selected

    rows   = await db.load_scalping_trades()
    trades = [r for r in rows if r.get("user_id") == user_id and r.get("strategy") != "whale"]

    await query.edit_message_text(
        _scalping_sell_text(trades, selected),
        parse_mode="Markdown",
        reply_markup=_scalping_sell_kb(trades, selected),
    )


async def scalping_sell_selall_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Select all or deselect all."""
    query   = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    select  = query.data.split(":")[-1] == "1"

    rows   = await db.load_scalping_trades()
    trades = [r for r in rows if r.get("user_id") == user_id and r.get("strategy") != "whale"]

    selected = {t["symbol"] for t in trades} if select else set()
    context.user_data[_SCALPING_SEL_KEY] = selected

    await query.edit_message_text(
        _scalping_sell_text(trades, selected),
        parse_mode="Markdown",
        reply_markup=_scalping_sell_kb(trades, selected),
    )


async def scalping_sell_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show confirmation screen listing all selected symbols."""
    query    = update.callback_query
    await query.answer()
    user_id  = update.effective_user.id
    selected: set = context.user_data.get(_SCALPING_SEL_KEY, set())

    if not selected:
        await query.answer("لم تحدد أي صفقة", show_alert=True)
        return

    lines = "\n".join(f"  • `{s}`" for s in sorted(selected))
    count = len(selected)

    await query.edit_message_text(
        f"⚠️ *تأكيد البيع*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"سيتم إغلاق *{count}* صفقة بسعر السوق:\n\n"
        f"{lines}\n\n"
        "سيتم إلغاء جميع الأوردرات المفتوحة لكل صفقة قبل البيع.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ تأكيد البيع", callback_data="scalping:sell_exec_multi"),
                InlineKeyboardButton("❌ إلغاء",        callback_data="scalping:sell_pick"),
            ]
        ]),
    )


async def scalping_sell_exec_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute market sell for all selected scalping trades."""
    query    = update.callback_query
    await query.answer()
    user_id  = update.effective_user.id
    selected: set = context.user_data.get(_SCALPING_SEL_KEY, set())

    if not selected:
        await query.answer("لم تحدد أي صفقة", show_alert=True)
        return

    await query.edit_message_text(
        f"⏳ جاري إغلاق {len(selected)} صفقة...",
        parse_mode="Markdown",
    )

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.edit_message_text(
            "❌ يجب ربط MEXC API أولاً من الإعدادات.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ رجوع", callback_data="scalping:menu")]
            ]),
        )
        return

    rows = await db.load_scalping_trades()
    trade_map = {
        r["symbol"]: dict(r)
        for r in rows
        if r.get("user_id") == user_id and r["symbol"] in selected
    }
    # Also check in-memory monitor (may have fresher state)
    for sym, t in trade_monitor.open_trades.items():
        if sym in selected:
            trade_map[sym] = t

    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    results = []
    try:
        for symbol in sorted(selected):
            trade = trade_map.get(symbol)
            if not trade:
                results.append(f"⚠️ `{symbol}` — غير موجودة")
                continue
            try:
                await trade_monitor.cancel_all_orders(trade, client.exchange)
                base      = symbol.replace("/USDT", "")
                balance   = await client.exchange.fetch_balance()
                free_qty  = float(balance.get("free", {}).get(base, 0) or 0)

                # Get current price to evaluate position value
                try:
                    ticker     = await client.exchange.fetch_ticker(symbol)
                    cur_price  = float(ticker.get("last") or ticker.get("close") or trade["entry_price"])
                except Exception:
                    cur_price  = float(trade["entry_price"])

                if free_qty * cur_price < 1.0:
                    await trade_monitor.remove_trade(symbol)
                    results.append(f"⚠️ `{symbol}` — قيمة أقل من $1، تم تجاهلها")
                    continue

                sell_order = await client.exchange.create_market_sell_order(symbol, free_qty)
                sell_price = float(
                    sell_order.get("average") or sell_order.get("price") or trade["entry_price"]
                )
                entry   = float(trade["entry_price"])
                pnl_pct = ((sell_price - entry) / entry) * 100
                icon    = "🟢" if pnl_pct >= 0 else "🔴"

                await trade_monitor.remove_trade(symbol)
                results.append(f"{icon} `{symbol}` — `{pnl_pct:+.2f}%`  @ `${sell_price:.6g}`")
                logger.info(
                    f"Multi-sell {symbol} user={user_id}: qty={free_qty} @ {sell_price:.6g} pnl={pnl_pct:.2f}%"
                )
            except Exception as e:
                logger.error(f"Multi-sell failed {symbol} user={user_id}: {e}")
                results.append(f"❌ `{symbol}` — `{str(e)[:60]}`")

    finally:
        await client.close()

    context.user_data[_SCALPING_SEL_KEY] = set()

    summary = "\n".join(results)
    await query.edit_message_text(
        f"📋 *نتائج البيع*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{summary}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ رجوع للـ Scalping", callback_data="scalping:menu")]
        ]),
    )


async def _send_orders_status(bot, user_id: int, setup: dict, result: dict) -> None:
    """Send a follow-up message confirming which orders were placed on MEXC."""
    sym       = setup["symbol"]
    t1_placed = result.get("t1_placed", False)
    sl_placed = result.get("sl_placed", False)
    t1_error  = result.get("t1_error", "")
    sl_error  = result.get("sl_error", "")

    t1_id = result.get("target1_order", {}).get("id", "")
    sl_id = result.get("sl_order", {}).get("id", "")

    t1_line = (
        f"✅ هدف 1 (T1) — وُضع على MEXC  `#{t1_id}`"
        if t1_placed else
        f"❌ هدف 1 (T1) — *فشل الوضع*\n   `{_translate_error(t1_error)}`"
    )
    sl_line = (
        f"✅ وقف الخسارة (SL) — وُضع على MEXC  `#{sl_id}`"
        if sl_placed else
        f"❌ وقف الخسارة (SL) — *فشل الوضع*\n   `{_translate_error(sl_error)}`"
    )

    # Only notify if at least one order failed — success is already implied by the signal message
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
        logger.error(f"Orders status notify failed for {user_id}: {e}")
