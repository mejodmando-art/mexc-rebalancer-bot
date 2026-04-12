"""
Telegram bot interface for the Smart Portfolio rebalancer.

Conversation flow
-----------------
1. /start        → welcome + ask for MEXC API Key
2. API Key       → ask for Secret Key
3. Secret Key    → validate keys against MEXC, then show main menu
4. Main menu     → inline keyboard with all controls

Commands
--------
/start    – setup or re-enter keys
/status   – current portfolio snapshot
/rebalance – trigger manual rebalance now
/stop     – stop the running bot loop
/help     – show available commands

Environment variables required
-------------------------------
    TELEGRAM_BOT_TOKEN   – from @BotFather
    TELEGRAM_CHAT_ID     – your Telegram user/chat ID (whitelist)
    MEXC_API_KEY         – set automatically after /start flow
    MEXC_SECRET_KEY      – set automatically after /start flow
"""

import asyncio
import logging
import os
import threading
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
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

# Global bot loop state
_bot_thread: Optional[threading.Thread] = None
_bot_stop_event = threading.Event()


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def _allowed(update: Update) -> bool:
    """Only allow the whitelisted chat ID (if set)."""
    allowed_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not allowed_id:
        return True
    return str(update.effective_chat.id) == allowed_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Status", callback_data="status"),
            InlineKeyboardButton("⚖️ Rebalance Now", callback_data="rebalance"),
        ],
        [
            InlineKeyboardButton("▶️ Start Bot", callback_data="start_bot"),
            InlineKeyboardButton("⏹ Stop Bot", callback_data="stop_bot"),
        ],
        [
            InlineKeyboardButton("🔑 Change API Keys", callback_data="change_keys"),
        ],
    ])


def _build_client() -> MEXCClient:
    return MEXCClient(
        api_key=os.environ.get("MEXC_API_KEY", ""),
        secret_key=os.environ.get("MEXC_SECRET_KEY", ""),
    )


def _validate_keys(api_key: str, secret_key: str) -> bool:
    """Try a lightweight authenticated call to verify the keys."""
    try:
        client = MEXCClient(api_key=api_key, secret_key=secret_key)
        client.get_account()
        return True
    except Exception:
        return False


def _portfolio_text(client: MEXCClient, cfg: dict) -> str:
    portfolio = get_portfolio_value(client, cfg["portfolio"]["assets"])
    targets = {a["symbol"]: a["allocation_pct"] for a in cfg["portfolio"]["assets"]}
    lines = [
        f"*Portfolio:* {cfg['bot']['name']}",
        f"*Total:* `{portfolio['total_usdt']:.2f} USDT`\n",
        f"`{'Asset':<8} {'Balance':>14} {'Price':>10} {'Value':>10} {'Act%':>6} {'Tgt%':>6}`",
        "`" + "-" * 58 + "`",
    ]
    for r in portfolio["assets"]:
        lines.append(
            f"`{r['symbol']:<8} {r['balance']:>14.6f} {r['price']:>10.4f}"
            f" {r['value_usdt']:>10.2f} {r['actual_pct']:>5.1f}% {targets[r['symbol']]:>5.1f}%`"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Bot loop (runs in background thread)
# ---------------------------------------------------------------------------

def _run_bot_loop(cfg: dict) -> None:
    """Run the rebalancer loop in a background thread."""
    _bot_stop_event.clear()
    client = _build_client()
    mode = cfg["rebalance"]["mode"]

    import time
    from datetime import datetime
    from smart_portfolio import (
        needs_rebalance_proportional,
        next_run_time,
        terminate,
    )

    log.info("Bot loop started | mode: %s", mode)

    if mode == "proportional":
        interval = cfg["rebalance"]["proportional"]["check_interval_minutes"] * 60
        while not _bot_stop_event.is_set():
            if needs_rebalance_proportional(client, cfg):
                execute_rebalance(client, cfg)
            _bot_stop_event.wait(interval)

    elif mode == "timed":
        frequency = cfg["rebalance"]["timed"]["frequency"]
        next_run = next_run_time(frequency)
        while not _bot_stop_event.is_set():
            if datetime.utcnow() >= next_run:
                execute_rebalance(client, cfg)
                next_run = next_run_time(frequency)
            _bot_stop_event.wait(60)

    elif mode == "unbalanced":
        log.info("Mode: unbalanced – waiting for manual trigger")
        _bot_stop_event.wait()

    log.info("Bot loop stopped")


# ---------------------------------------------------------------------------
# Conversation: /start → collect keys
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END

    await update.message.reply_text(
        "👋 *MEXC Smart Portfolio Bot*\n\n"
        "أرسل لي الـ *MEXC API Key* الخاص بك:",
        parse_mode="Markdown",
    )
    return ASK_API_KEY


async def received_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END

    context.user_data["api_key"] = update.message.text.strip()
    await update.message.delete()  # delete the key from chat for security
    await update.message.reply_text(
        "✅ تم استلام الـ API Key.\n\nأرسل الـ *Secret Key* الآن:",
        parse_mode="Markdown",
    )
    return ASK_SECRET_KEY


async def received_secret_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _allowed(update):
        return ConversationHandler.END

    secret_key = update.message.text.strip()
    api_key = context.user_data.get("api_key", "")

    await update.message.delete()
    msg = await update.message.reply_text("⏳ جاري التحقق من الـ keys...")

    valid = await asyncio.get_event_loop().run_in_executor(
        None, _validate_keys, api_key, secret_key
    )

    if not valid:
        await msg.edit_text(
            "❌ الـ keys غلط أو مفيش صلاحية.\n"
            "ابعت /start وحاول تاني."
        )
        return ConversationHandler.END

    # Store in environment for this process
    os.environ["MEXC_API_KEY"] = api_key
    os.environ["MEXC_SECRET_KEY"] = secret_key
    context.user_data.clear()

    await msg.edit_text(
        "✅ *تم التحقق من الـ keys بنجاح!*\n\n"
        "اختار من القائمة:",
        parse_mode="Markdown",
        reply_markup=_main_menu_keyboard(),
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("تم الإلغاء.")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    await update.message.reply_text(
        "القائمة الرئيسية:",
        reply_markup=_main_menu_keyboard(),
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    msg = await update.message.reply_text("⏳ جاري جلب البيانات...")
    try:
        cfg = load_config()
        client = _build_client()
        text = _portfolio_text(client, cfg)
        await msg.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")


async def cmd_rebalance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    msg = await update.message.reply_text("⏳ جاري تنفيذ الـ rebalance...")
    try:
        cfg = load_config()
        client = _build_client()
        await asyncio.get_event_loop().run_in_executor(
            None, execute_rebalance, client, cfg
        )
        await msg.edit_text("✅ تم الـ rebalance بنجاح!")
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    global _bot_thread
    if _bot_thread and _bot_thread.is_alive():
        _bot_stop_event.set()
        await update.message.reply_text("⏹ تم إيقاف البوت.")
    else:
        await update.message.reply_text("البوت مش شغال أصلاً.")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    await update.message.reply_text(
        "*الأوامر المتاحة:*\n\n"
        "/start – إدخال الـ API keys\n"
        "/status – عرض الـ portfolio الحالي\n"
        "/rebalance – rebalance يدوي فوري\n"
        "/stop – إيقاف البوت\n"
        "/help – هذه الرسالة",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Inline keyboard callbacks
# ---------------------------------------------------------------------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if not _allowed(update):
        return

    data = query.data

    if data == "status":
        await query.edit_message_text("⏳ جاري جلب البيانات...")
        try:
            cfg = load_config()
            client = _build_client()
            text = _portfolio_text(client, cfg)
            await query.edit_message_text(
                text, parse_mode="Markdown", reply_markup=_main_menu_keyboard()
            )
        except Exception as e:
            await query.edit_message_text(
                f"❌ خطأ: {e}", reply_markup=_main_menu_keyboard()
            )

    elif data == "rebalance":
        await query.edit_message_text("⏳ جاري تنفيذ الـ rebalance...")
        try:
            cfg = load_config()
            client = _build_client()
            await asyncio.get_event_loop().run_in_executor(
                None, execute_rebalance, client, cfg
            )
            await query.edit_message_text(
                "✅ تم الـ rebalance بنجاح!", reply_markup=_main_menu_keyboard()
            )
        except Exception as e:
            await query.edit_message_text(
                f"❌ خطأ: {e}", reply_markup=_main_menu_keyboard()
            )

    elif data == "start_bot":
        global _bot_thread
        if _bot_thread and _bot_thread.is_alive():
            await query.edit_message_text(
                "البوت شغال بالفعل.", reply_markup=_main_menu_keyboard()
            )
            return
        try:
            cfg = load_config()
            validate_allocations(cfg["portfolio"]["assets"])
            _bot_thread = threading.Thread(
                target=_run_bot_loop, args=(cfg,), daemon=True
            )
            _bot_thread.start()
            await query.edit_message_text(
                f"▶️ البوت بدأ | mode: *{cfg['rebalance']['mode']}*",
                parse_mode="Markdown",
                reply_markup=_main_menu_keyboard(),
            )
        except Exception as e:
            await query.edit_message_text(
                f"❌ خطأ: {e}", reply_markup=_main_menu_keyboard()
            )

    elif data == "stop_bot":
        if _bot_thread and _bot_thread.is_alive():
            _bot_stop_event.set()
            await query.edit_message_text(
                "⏹ تم إيقاف البوت.", reply_markup=_main_menu_keyboard()
            )
        else:
            await query.edit_message_text(
                "البوت مش شغال أصلاً.", reply_markup=_main_menu_keyboard()
            )

    elif data == "change_keys":
        await query.edit_message_text(
            "أرسل /start لإدخال keys جديدة."
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def start_telegram_bot() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    app = Application.builder().token(token).build()

    # Conversation handler for key setup
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            ASK_API_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_api_key)],
            ASK_SECRET_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_secret_key)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("rebalance", cmd_rebalance))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CallbackQueryHandler(button_handler))

    log.info("Telegram bot started. Polling...")
    app.run_polling()
