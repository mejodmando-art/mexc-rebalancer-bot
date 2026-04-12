"""
Telegram bot interface for the Smart Portfolio rebalancer.

The bot reads MEXC_API_KEY and MEXC_SECRET_KEY from environment variables
(set once in Railway Variables). No key collection via chat.

Commands
--------
/start    – show main menu
/status   – current portfolio snapshot
/rebalance – trigger manual rebalance now
/stop     – stop the running rebalancer loop
/help     – show available commands

Environment variables required
-------------------------------
    TELEGRAM_BOT_TOKEN   – from @BotFather
    TELEGRAM_CHAT_ID     – your Telegram user ID (whitelist)
    MEXC_API_KEY         – set in Railway Variables
    MEXC_SECRET_KEY      – set in Railway Variables
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
)

from mexc_client import MEXCClient
from smart_portfolio import (
    execute_rebalance,
    get_portfolio_value,
    load_config,
    needs_rebalance_proportional,
    next_run_time,
    validate_allocations,
)

log = logging.getLogger(__name__)

_bot_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()


def _allowed(update: Update) -> bool:
    allowed_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not allowed_id:
        return True
    return str(update.effective_chat.id) == allowed_id


def _client() -> MEXCClient:
    return MEXCClient()


def _menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Status", callback_data="status"),
            InlineKeyboardButton("⚖️ Rebalance", callback_data="rebalance"),
        ],
        [
            InlineKeyboardButton("▶️ Start", callback_data="start_bot"),
            InlineKeyboardButton("⏹ Stop", callback_data="stop_bot"),
        ],
    ])


def _portfolio_text(cfg: dict) -> str:
    client = _client()
    portfolio = get_portfolio_value(client, cfg["portfolio"]["assets"])
    targets = {a["symbol"]: a["allocation_pct"] for a in cfg["portfolio"]["assets"]}
    lines = [
        f"*{cfg['bot']['name']}*",
        f"Total: `{portfolio['total_usdt']:.2f} USDT`\n",
    ]
    for r in portfolio["assets"]:
        tgt = targets[r["symbol"]]
        lines.append(
            f"`{r['symbol']:<6}` "
            f"`{r['value_usdt']:>8.2f} USDT` "
            f"actual `{r['actual_pct']:.1f}%` target `{tgt:.1f}%`"
        )
    return "\n".join(lines)


def _is_running() -> bool:
    return _bot_thread is not None and _bot_thread.is_alive()


def _run_loop(cfg: dict) -> None:
    from datetime import datetime
    _stop_event.clear()
    client = _client()
    mode = cfg["rebalance"]["mode"]
    log.info("Rebalancer loop started | mode: %s", mode)

    if mode == "proportional":
        interval = cfg["rebalance"]["proportional"]["check_interval_minutes"] * 60
        while not _stop_event.is_set():
            if needs_rebalance_proportional(client, cfg):
                execute_rebalance(client, cfg)
            _stop_event.wait(interval)

    elif mode == "timed":
        frequency = cfg["rebalance"]["timed"]["frequency"]
        next_run = next_run_time(frequency)
        while not _stop_event.is_set():
            if datetime.utcnow() >= next_run:
                execute_rebalance(client, cfg)
                next_run = next_run_time(frequency)
            _stop_event.wait(60)

    elif mode == "unbalanced":
        _stop_event.wait()

    log.info("Rebalancer loop stopped")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    status = "▶️ شغال" if _is_running() else "⏹ واقف"
    await update.message.reply_text(
        f"*MEXC Smart Portfolio Bot*\nالحالة: {status}\n\nاختار من القائمة:",
        parse_mode="Markdown",
        reply_markup=_menu(),
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    msg = await update.message.reply_text("⏳ جاري جلب البيانات...")
    try:
        cfg = load_config()
        await msg.edit_text(_portfolio_text(cfg), parse_mode="Markdown", reply_markup=_menu())
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")


async def cmd_rebalance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    msg = await update.message.reply_text("⏳ جاري تنفيذ الـ rebalance...")
    try:
        cfg = load_config()
        await asyncio.get_event_loop().run_in_executor(None, execute_rebalance, _client(), cfg)
        await msg.edit_text("✅ تم الـ rebalance بنجاح!", reply_markup=_menu())
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    if _is_running():
        _stop_event.set()
        await update.message.reply_text("⏹ تم إيقاف البوت.", reply_markup=_menu())
    else:
        await update.message.reply_text("البوت مش شغال أصلاً.", reply_markup=_menu())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    await update.message.reply_text(
        "*الأوامر:*\n"
        "/start – القائمة الرئيسية\n"
        "/status – عرض الـ portfolio\n"
        "/rebalance – rebalance يدوي\n"
        "/stop – إيقاف البوت\n"
        "/help – هذه الرسالة",
        parse_mode="Markdown",
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not _allowed(update):
        return

    global _bot_thread

    if query.data == "status":
        await query.edit_message_text("⏳ جاري جلب البيانات...")
        try:
            cfg = load_config()
            await query.edit_message_text(_portfolio_text(cfg), parse_mode="Markdown", reply_markup=_menu())
        except Exception as e:
            await query.edit_message_text(f"❌ خطأ: {e}", reply_markup=_menu())

    elif query.data == "rebalance":
        await query.edit_message_text("⏳ جاري تنفيذ الـ rebalance...")
        try:
            cfg = load_config()
            await asyncio.get_event_loop().run_in_executor(None, execute_rebalance, _client(), cfg)
            await query.edit_message_text("✅ تم الـ rebalance بنجاح!", reply_markup=_menu())
        except Exception as e:
            await query.edit_message_text(f"❌ خطأ: {e}", reply_markup=_menu())

    elif query.data == "start_bot":
        if _is_running():
            await query.edit_message_text("البوت شغال بالفعل.", reply_markup=_menu())
            return
        try:
            cfg = load_config()
            validate_allocations(cfg["portfolio"]["assets"])
            _bot_thread = threading.Thread(target=_run_loop, args=(cfg,), daemon=True)
            _bot_thread.start()
            await query.edit_message_text(
                f"▶️ البوت بدأ | mode: *{cfg['rebalance']['mode']}*",
                parse_mode="Markdown",
                reply_markup=_menu(),
            )
        except Exception as e:
            await query.edit_message_text(f"❌ خطأ: {e}", reply_markup=_menu())

    elif query.data == "stop_bot":
        if _is_running():
            _stop_event.set()
            await query.edit_message_text("⏹ تم إيقاف البوت.", reply_markup=_menu())
        else:
            await query.edit_message_text("البوت مش شغال أصلاً.", reply_markup=_menu())


async def _post_init(app: Application) -> None:
    """Auto-start rebalancer loop and notify user on launch."""
    global _bot_thread
    try:
        cfg = load_config()
        validate_allocations(cfg["portfolio"]["assets"])
        _bot_thread = threading.Thread(target=_run_loop, args=(cfg,), daemon=True)
        _bot_thread.start()
        log.info("Rebalancer auto-started | mode: %s", cfg["rebalance"]["mode"])
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if chat_id:
            await app.bot.send_message(
                chat_id=chat_id,
                text=f"✅ البوت اشتغل تلقائياً\nmode: *{cfg['rebalance']['mode']}*",
                parse_mode="Markdown",
                reply_markup=_menu(),
            )
    except Exception as e:
        log.error("Auto-start failed: %s", e)


def start_telegram_bot() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    app = Application.builder().token(token).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("rebalance", cmd_rebalance))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CallbackQueryHandler(button_handler))

    log.info("Telegram bot polling...")
    app.run_polling()
