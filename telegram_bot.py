"""
Telegram bot interface for the Smart Portfolio bot.

Commands
--------
/start       – Welcome + show current status
/setup       – Enter MEXC API keys (private chat, step by step)
/status      – Show current portfolio snapshot
/rebalance   – Trigger manual rebalance now
/config      – Show current config (assets, mode, allocations)
/stop        – Stop the rebalancing bot
/run         – Start the rebalancing bot
/help        – List all commands

Required env vars
-----------------
TELEGRAM_BOT_TOKEN  – BotFather token
TELEGRAM_CHAT_ID    – Your Telegram user/chat ID (whitelist)
"""

import asyncio
import logging
import os
import threading
from typing import Optional

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from mexc_client import MEXCClient
from smart_portfolio import (
    execute_rebalance,
    get_portfolio_value,
    load_config,
    run,
    save_config,
    validate_allocations,
)

log = logging.getLogger(__name__)

# Conversation states
ASK_API_KEY, ASK_SECRET_KEY = range(2)

# Global bot state
_bot_thread: Optional[threading.Thread] = None
_bot_running = False
_bot_stop_event = threading.Event()


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def _allowed(update: Update) -> bool:
    allowed_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not allowed_id:
        return True  # No whitelist set → allow all (not recommended)
    return str(update.effective_chat.id) == allowed_id


async def _deny(update: Update) -> None:
    await update.message.reply_text("⛔ غير مصرح.")


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return await _deny(update)

    has_keys = bool(os.environ.get("MEXC_API_KEY")) and bool(os.environ.get("MEXC_SECRET_KEY"))
    status = "✅ مفاتيح API موجودة" if has_keys else "⚠️ مفاتيح API غير موجودة"

    text = (
        f"مرحباً! أنا بوت Smart Portfolio على MEXC.\n\n"
        f"الحالة: {status}\n\n"
        f"الأوامر المتاحة:\n"
        f"/setup – إدخال مفاتيح API\n"
        f"/status – حالة المحفظة\n"
        f"/rebalance – إعادة توازن فورية\n"
        f"/config – عرض الإعدادات\n"
        f"/run – تشغيل البوت\n"
        f"/stop – إيقاف البوت\n"
        f"/help – المساعدة"
    )
    await update.message.reply_text(text)


# ---------------------------------------------------------------------------
# /setup – Conversation to collect API keys
# ---------------------------------------------------------------------------

async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        await _deny(update)
        return ConversationHandler.END

    await update.message.reply_text(
        "🔑 إدخال مفاتيح MEXC API\n\n"
        "أرسل لي الـ API Key الخاص بك.\n"
        "⚠️ تأكد إنك في محادثة خاصة معي وليس في مجموعة.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ASK_API_KEY


async def received_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["api_key"] = update.message.text.strip()
    # Delete the message for security
    try:
        await update.message.delete()
    except Exception:
        pass
    await update.message.reply_text("✅ تم استلام API Key.\n\nأرسل لي الـ Secret Key الآن.")
    return ASK_SECRET_KEY


async def received_secret_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    secret_key = update.message.text.strip()
    api_key = context.user_data.get("api_key", "")

    # Delete the message for security
    try:
        await update.message.delete()
    except Exception:
        pass

    # Set in environment for this process
    os.environ["MEXC_API_KEY"] = api_key
    os.environ["MEXC_SECRET_KEY"] = secret_key

    # Test the keys
    await update.message.reply_text("⏳ جاري التحقق من المفاتيح...")
    try:
        client = MEXCClient(api_key=api_key, secret_key=secret_key)
        client.get_account()
        await update.message.reply_text(
            "✅ المفاتيح صحيحة! تم الاتصال بـ MEXC بنجاح.\n\n"
            "استخدم /run لتشغيل البوت."
        )
    except Exception as e:
        os.environ.pop("MEXC_API_KEY", None)
        os.environ.pop("MEXC_SECRET_KEY", None)
        await update.message.reply_text(
            f"❌ المفاتيح غير صحيحة أو لا تملك صلاحية Spot Trading.\n\nالخطأ: {e}\n\nحاول مرة أخرى بـ /setup"
        )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ تم إلغاء الإعداد.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return await _deny(update)

    if not os.environ.get("MEXC_API_KEY"):
        await update.message.reply_text("⚠️ لم يتم إدخال مفاتيح API بعد. استخدم /setup")
        return

    await update.message.reply_text("⏳ جاري جلب بيانات المحفظة...")
    try:
        cfg = load_config()
        client = MEXCClient()
        portfolio = get_portfolio_value(client, cfg["portfolio"]["assets"])
        targets = {a["symbol"]: a["allocation_pct"] for a in cfg["portfolio"]["assets"]}

        lines = [f"📊 *{cfg['bot']['name']}*\n💰 الإجمالي: `{portfolio['total_usdt']:.2f} USDT`\n"]
        for r in portfolio["assets"]:
            deviation = r["actual_pct"] - targets[r["symbol"]]
            arrow = "🔴" if deviation > 2 else "🟢" if deviation < -2 else "⚪"
            lines.append(
                f"{arrow} *{r['symbol']}*: `{r['balance']:.6f}`\n"
                f"   القيمة: `{r['value_usdt']:.2f} USDT`\n"
                f"   الفعلي: `{r['actual_pct']:.1f}%` | الهدف: `{targets[r['symbol']]:.1f}%`"
            )

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")


# ---------------------------------------------------------------------------
# /rebalance
# ---------------------------------------------------------------------------

async def cmd_rebalance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return await _deny(update)

    if not os.environ.get("MEXC_API_KEY"):
        await update.message.reply_text("⚠️ لم يتم إدخال مفاتيح API بعد. استخدم /setup")
        return

    await update.message.reply_text("⚙️ جاري تنفيذ إعادة التوازن...")
    try:
        cfg = load_config()
        client = MEXCClient()
        execute_rebalance(client, cfg)
        await update.message.reply_text("✅ تمت إعادة التوازن بنجاح.\n\nاستخدم /status لرؤية النتيجة.")
    except Exception as e:
        await update.message.reply_text(f"❌ فشلت إعادة التوازن: {e}")


# ---------------------------------------------------------------------------
# /config
# ---------------------------------------------------------------------------

async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return await _deny(update)

    try:
        cfg = load_config()
        mode = cfg["rebalance"]["mode"]
        assets = cfg["portfolio"]["assets"]
        total = cfg["portfolio"]["total_usdt"]

        lines = [
            f"⚙️ *إعدادات البوت*\n",
            f"الاسم: `{cfg['bot']['name']}`",
            f"المبلغ: `{total} USDT`",
            f"وضع إعادة التوازن: `{mode}`",
        ]

        if mode == "proportional":
            p = cfg["rebalance"]["proportional"]
            lines.append(f"العتبة: `{p['threshold_pct']}%` | الفحص كل `{p['check_interval_minutes']} دقائق`")
        elif mode == "timed":
            lines.append(f"التكرار: `{cfg['rebalance']['timed']['frequency']}`")

        lines.append("\n*العملات:*")
        for a in assets:
            lines.append(f"  • `{a['symbol']}`: `{a['allocation_pct']}%`")

        lines.append(f"\nبيع عند الإنهاء: `{'نعم' if cfg['termination']['sell_at_termination'] else 'لا'}`")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ في قراءة الإعدادات: {e}")


# ---------------------------------------------------------------------------
# /run – Start the portfolio bot in background thread
# ---------------------------------------------------------------------------

async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _bot_thread, _bot_running, _bot_stop_event

    if not _allowed(update):
        return await _deny(update)

    if not os.environ.get("MEXC_API_KEY"):
        await update.message.reply_text("⚠️ لم يتم إدخال مفاتيح API بعد. استخدم /setup")
        return

    if _bot_running:
        await update.message.reply_text("⚠️ البوت شغّال بالفعل.")
        return

    _bot_stop_event.clear()
    _bot_running = True

    def _run_portfolio():
        global _bot_running
        try:
            cfg = load_config()
            run(cfg)
        except Exception as e:
            log.error("Portfolio bot error: %s", e)
        finally:
            _bot_running = False

    _bot_thread = threading.Thread(target=_run_portfolio, daemon=True)
    _bot_thread.start()

    cfg = load_config()
    await update.message.reply_text(
        f"✅ تم تشغيل البوت!\n\n"
        f"الوضع: `{cfg['rebalance']['mode']}`\n"
        f"استخدم /status لمتابعة المحفظة.",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# /stop
# ---------------------------------------------------------------------------

async def cmd_stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _bot_running

    if not _allowed(update):
        return await _deny(update)

    if not _bot_running:
        await update.message.reply_text("⚠️ البوت مش شغّال أصلاً.")
        return

    _bot_running = False
    _bot_stop_event.set()
    await update.message.reply_text("🛑 تم إيقاف البوت.")


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return await _deny(update)

    text = (
        "📋 *الأوامر المتاحة:*\n\n"
        "/start – الشاشة الرئيسية\n"
        "/setup – إدخال مفاتيح MEXC API\n"
        "/status – حالة المحفظة الحالية\n"
        "/rebalance – إعادة توازن فورية\n"
        "/config – عرض إعدادات البوت\n"
        "/run – تشغيل البوت التلقائي\n"
        "/stop – إيقاف البوت التلقائي\n"
        "/help – هذه القائمة"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ---------------------------------------------------------------------------
# App builder
# ---------------------------------------------------------------------------

def build_app() -> Application:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN غير موجود في متغيرات البيئة.")

    app = Application.builder().token(token).build()

    # Setup conversation
    setup_conv = ConversationHandler(
        entry_points=[CommandHandler("setup", cmd_setup)],
        states={
            ASK_API_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_api_key)],
            ASK_SECRET_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_secret_key)],
        },
        fallbacks=[CommandHandler("cancel", cancel_setup)],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(setup_conv)
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("rebalance", cmd_rebalance))
    app.add_handler(CommandHandler("config", cmd_config))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("stop", cmd_stop_bot))
    app.add_handler(CommandHandler("help", cmd_help))

    return app


def start_telegram_bot() -> None:
    app = build_app()
    log.info("Telegram bot started.")
    app.run_polling(drop_pending_updates=True)
