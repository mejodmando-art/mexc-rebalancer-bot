import asyncio
import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters
)
from bot.config import config
from bot.database import db
from bot.handlers.start import start_handler, help_handler, main_menu_callback
from bot.handlers.portfolio import portfolio_callback
from bot.handlers.rebalance import rebalance_callback
from bot.handlers.history import history_callback
from bot.handlers.settings import (
    settings_callback, toggle_auto_callback,
    set_api_key_start, set_api_key_input, set_secret_key_input,
    set_threshold_start, set_threshold_input,
    set_interval_start, set_interval_input,
    set_alloc_start, set_alloc_coins_input,
    alloc_mode_callback, set_alloc_custom_input,
    del_alloc_callback, clear_allocs_callback,
    cancel_conv,
    SET_API_KEY, SET_SECRET_KEY,
    SET_THRESHOLD, SET_INTERVAL,
    SET_ALLOC_COINS, SET_ALLOC_MODE, SET_ALLOC_CUSTOM,
)
from bot.scheduler import start_scheduler
from bot.keyboards import settings_kb

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def settings_menu_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    from bot.database import db
    settings = await db.get_settings(update.effective_user.id)
    auto_on = bool(settings.get("auto_enabled")) if settings else False
    threshold = settings.get("threshold", 5.0) if settings else 5.0
    allocs = await db.get_allocations(update.effective_user.id)
    has_api = bool(settings.get("mexc_api_key")) if settings else False
    interval = settings.get("auto_interval_hours", 24) if settings else 24

    text = (
        "⚙️ *الإعدادات*\n\n"
        f"{'✅ MEXC API مربوطة' if has_api else '❌ MEXC API غير مربوطة'}\n"
        f"{'📊 ' + str(len(allocs)) + ' عملة محددة' if allocs else '📊 لا يوجد توزيع'}\n"
        f"🎯 حد الانحراف العام: *{threshold}%* (لجميع العملات)\n"
        f"{'🟢 تلقائي كل ' + str(interval) + ' ساعة' if auto_on else '🔴 التوازن التلقائي معطل'}\n"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=settings_kb(auto_on))


def build_app() -> Application:
    app = Application.builder().token(config.telegram_token).build()
    TEXT = filters.TEXT & ~filters.COMMAND

    # Commands
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))

    # Conversations
    api_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_api_key_start, pattern="^settings:set_api$")],
        states={
            SET_API_KEY:    [MessageHandler(TEXT, set_api_key_input)],
            SET_SECRET_KEY: [MessageHandler(TEXT, set_secret_key_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv),
                   CallbackQueryHandler(cancel_conv, pattern="^cancel$")],
        conversation_timeout=300,
    )

    threshold_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_threshold_start, pattern="^settings:set_threshold$")],
        states={SET_THRESHOLD: [MessageHandler(TEXT, set_threshold_input)]},
        fallbacks=[CommandHandler("cancel", cancel_conv),
                   CallbackQueryHandler(cancel_conv, pattern="^cancel$")],
        conversation_timeout=300,
    )

    interval_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_interval_start, pattern="^settings:set_interval$")],
        states={SET_INTERVAL: [MessageHandler(TEXT, set_interval_input)]},
        fallbacks=[CommandHandler("cancel", cancel_conv),
                   CallbackQueryHandler(cancel_conv, pattern="^cancel$")],
        conversation_timeout=300,
    )

    alloc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_alloc_start, pattern="^settings:set_alloc$")],
        states={
            SET_ALLOC_COINS:  [MessageHandler(TEXT, set_alloc_coins_input)],
            SET_ALLOC_MODE:   [CallbackQueryHandler(alloc_mode_callback, pattern="^alloc_mode:")],
            SET_ALLOC_CUSTOM: [MessageHandler(TEXT, set_alloc_custom_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv),
                   CallbackQueryHandler(cancel_conv, pattern="^cancel$")],
        conversation_timeout=600,
    )

    app.add_handler(api_conv)
    app.add_handler(threshold_conv)
    app.add_handler(interval_conv)
    app.add_handler(alloc_conv)

    # Callbacks
    app.add_handler(CallbackQueryHandler(portfolio_callback,    pattern="^portfolio:"))
    app.add_handler(CallbackQueryHandler(rebalance_callback,    pattern="^rebalance:"))
    app.add_handler(CallbackQueryHandler(history_callback,      pattern="^history:"))
    app.add_handler(CallbackQueryHandler(settings_callback,     pattern="^settings:view"))
    app.add_handler(CallbackQueryHandler(toggle_auto_callback,  pattern="^settings:toggle_auto$"))
    app.add_handler(CallbackQueryHandler(del_alloc_callback,    pattern="^del_alloc:"))
    app.add_handler(CallbackQueryHandler(clear_allocs_callback, pattern="^clear_allocs$"))
    app.add_handler(CallbackQueryHandler(settings_menu_callback, pattern="^settings:menu$"))
    app.add_handler(CallbackQueryHandler(main_menu_callback,    pattern="^main_menu$"))

    return app


async def main():
    await db.init()
    app = build_app()
    scheduler = await start_scheduler(app)
    logger.info("🤖 MEXC Rebalancer Bot started")
    async with app:
        await app.start()
        await app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
        try:
            await asyncio.Event().wait()
        finally:
            await app.updater.stop()
            await app.stop()
            scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
