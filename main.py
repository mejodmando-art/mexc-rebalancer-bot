import asyncio
import logging
import os
import re
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters
)
from bot.config import config
from bot.database import db
from bot.handlers.start import start_handler, help_handler, menu_command
from bot.handlers.portfolio import portfolio_callback
from bot.handlers.rebalance import rebalance_callback
from bot.handlers.history import history_callback
from bot.handlers.menu import handle_menu_callback
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
from bot.handlers.momentum_handler import (
    momentum_callback,
    momentum_setting_input,
    momentum_cancel,
    run_momentum_scan,
)
from bot.momentum.monitor import momentum_monitor
from bot.handlers.grid_handler import (
    build_grid_conv,
    grid_menu_callback,
    grid_detail_callback,
    grid_live_callback,
    grid_stop_callback,
    run_grid_monitor,
    grid_edit_tpsl_callback, grid_edit_tpsl_input,
    grid_edit_range_callback, grid_edit_range_input,
    grid_add_funds_callback, grid_add_funds_input,
    grid_remove_funds_callback, grid_remove_funds_input,
)
from bot.grid.monitor import grid_monitor
from bot.handlers.portfolio_manager import (
    portfolios_callback, portfolio_detail_callback,
    switch_portfolio_callback, delete_portfolio_callback,
    delete_portfolio_confirm_callback,
    create_portfolio_start, create_portfolio_name, create_portfolio_capital,
    create_tp1_type_callback, create_tp1_value_input,
    create_tp2_value_input, create_sl_value_input,
    edit_portfolio_name_start, edit_portfolio_name_input,
    edit_portfolio_capital_start, edit_portfolio_capital_input,
    cancel_portfolio_conv,
    portfolio_sell_all_callback, portfolio_sell_one_callback,
    portfolio_sell_coin_callback, portfolio_rebalance_sell_callback,
    portfolio_sell_exec_callback,
    portfolio_edit_allocs_callback,
    portfolio_set_threshold_start, portfolio_set_threshold_input,
    portfolio_set_interval_start, portfolio_set_interval_input,
    portfolio_toggle_auto_callback,
    portfolio_tp_menu_callback,
    portfolio_tp_activate_callback, portfolio_tp_deactivate_callback,
    portfolio_tp_setup_start, tp_type_callback,
    tp1_value_input, tp1_sell_input,
    tp2_value_input, tp2_sell_input,
    sl_value_input,
    portfolio_rebalance_callback,
    CREATE_NAME, CREATE_CAPITAL, EDIT_NAME, EDIT_CAPITAL,
    PORTFOLIO_SET_THRESHOLD, PORTFOLIO_SET_INTERVAL,
    TP_TP1_TYPE, TP_TP1_VALUE, TP_TP1_SELL,
    TP_TP2_TYPE, TP_TP2_VALUE, TP_TP2_SELL,
    TP_SL_TYPE, TP_SL_VALUE,
    CREATE_TP1_TYPE, CREATE_TP1_VALUE, CREATE_TP2_VALUE, CREATE_SL_VALUE,
)
from bot.portfolio_monitor import run_portfolio_monitor
from bot.handlers.emergency_handler import (
    emergency_menu_callback,
    emergency_pick_coin_callback,
    emergency_pick_momentum_callback,

    emergency_toggle_callback,
    emergency_confirm_selected_callback,
    emergency_back_to_select_callback,
    emergency_exec_selected_callback,
    emergency_confirm_all_callback,
    emergency_exec_all_callback,
)
from bot.scheduler import start_scheduler


class _RedactTokenFilter(logging.Filter):
    """Remove the Telegram bot token from log records."""
    _pattern = re.compile(r"bot\d+:[A-Za-z0-9_-]{35,}")

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._pattern.sub("bot<REDACTED>", str(record.msg))
        return True


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger().addFilter(_RedactTokenFilter())
logger = logging.getLogger(__name__)


def build_app() -> Application:
    app = Application.builder().token(config.telegram_token).build()

    TEXT = filters.TEXT & ~filters.COMMAND

    # ── Conversations (must be registered before simple CallbackQueryHandlers) ─
    api_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_api_key_start, pattern="^settings:set_api")],
        states={
            SET_API_KEY:    [MessageHandler(TEXT, set_api_key_input)],
            SET_SECRET_KEY: [MessageHandler(TEXT, set_secret_key_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv),
                   CallbackQueryHandler(cancel_conv, pattern="^cancel$")],
        conversation_timeout=300,
    )

    threshold_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_threshold_start, pattern="^settings:set_threshold")],
        states={SET_THRESHOLD: [MessageHandler(TEXT, set_threshold_input)]},
        fallbacks=[CommandHandler("cancel", cancel_conv),
                   CallbackQueryHandler(cancel_conv, pattern="^cancel$")],
        conversation_timeout=300,
    )

    interval_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_interval_start, pattern="^settings:set_interval")],
        states={SET_INTERVAL: [MessageHandler(TEXT, set_interval_input)]},
        fallbacks=[CommandHandler("cancel", cancel_conv),
                   CallbackQueryHandler(cancel_conv, pattern="^cancel$")],
        conversation_timeout=300,
    )

    alloc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_alloc_start, pattern="^settings:add_alloc")],
        states={
            SET_ALLOC_COINS:  [MessageHandler(TEXT, set_alloc_coins_input)],
            SET_ALLOC_MODE:   [CallbackQueryHandler(alloc_mode_callback, pattern="^alloc_mode:")],
            SET_ALLOC_CUSTOM: [MessageHandler(TEXT, set_alloc_custom_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv),
                   CallbackQueryHandler(cancel_conv, pattern="^cancel$")],
        conversation_timeout=600,
    )

    create_portfolio_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_portfolio_start, pattern="^portfolio_new$")],
        states={
            CREATE_NAME: [
                MessageHandler(TEXT, create_portfolio_name),
                CallbackQueryHandler(create_portfolio_name, pattern="^portfolio_capital:"),
            ],
            CREATE_CAPITAL:   [MessageHandler(TEXT, create_portfolio_capital)],
            CREATE_TP1_TYPE:  [CallbackQueryHandler(create_tp1_type_callback, pattern="^create_tp_type:")],
            CREATE_TP1_VALUE: [MessageHandler(TEXT, create_tp1_value_input)],
            CREATE_TP2_VALUE: [MessageHandler(TEXT, create_tp2_value_input)],
            CREATE_SL_VALUE:  [MessageHandler(TEXT, create_sl_value_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_portfolio_conv),
                   CallbackQueryHandler(cancel_portfolio_conv, pattern="^cancel$")],
        conversation_timeout=600,
    )

    edit_name_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_portfolio_name_start, pattern="^portfolio_edit_name:")],
        states={EDIT_NAME: [MessageHandler(TEXT, edit_portfolio_name_input)]},
        fallbacks=[CommandHandler("cancel", cancel_portfolio_conv),
                   CallbackQueryHandler(cancel_portfolio_conv, pattern="^cancel$")],
        conversation_timeout=300,
    )

    edit_capital_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_portfolio_capital_start, pattern="^portfolio_edit_capital:")],
        states={EDIT_CAPITAL: [MessageHandler(TEXT, edit_portfolio_capital_input)]},
        fallbacks=[CommandHandler("cancel", cancel_portfolio_conv),
                   CallbackQueryHandler(cancel_portfolio_conv, pattern="^cancel$")],
        conversation_timeout=300,
    )

    portfolio_threshold_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(portfolio_set_threshold_start, pattern="^portfolio_set_threshold:")],
        states={PORTFOLIO_SET_THRESHOLD: [MessageHandler(TEXT, portfolio_set_threshold_input)]},
        fallbacks=[CommandHandler("cancel", cancel_portfolio_conv),
                   CallbackQueryHandler(cancel_portfolio_conv, pattern="^cancel$")],
        conversation_timeout=300,
    )

    portfolio_interval_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(portfolio_set_interval_start, pattern="^portfolio_set_interval:")],
        states={PORTFOLIO_SET_INTERVAL: [MessageHandler(TEXT, portfolio_set_interval_input)]},
        fallbacks=[CommandHandler("cancel", cancel_portfolio_conv),
                   CallbackQueryHandler(cancel_portfolio_conv, pattern="^cancel$")],
        conversation_timeout=300,
    )

    tp_setup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(portfolio_tp_setup_start, pattern="^portfolio_tp_setup:")],
        states={
            TP_TP1_TYPE:  [CallbackQueryHandler(tp_type_callback,  pattern="^tp_type:")],
            TP_TP1_VALUE: [MessageHandler(TEXT, tp1_value_input)],
            TP_TP1_SELL:  [MessageHandler(TEXT, tp1_sell_input)],
            TP_TP2_TYPE:  [CallbackQueryHandler(tp_type_callback,  pattern="^tp_type:")],
            TP_TP2_VALUE: [MessageHandler(TEXT, tp2_value_input)],
            TP_TP2_SELL:  [MessageHandler(TEXT, tp2_sell_input)],
            TP_SL_TYPE:   [CallbackQueryHandler(tp_type_callback,  pattern="^tp_type:")],
            TP_SL_VALUE:  [MessageHandler(TEXT, sl_value_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_portfolio_conv),
                   CallbackQueryHandler(cancel_portfolio_conv, pattern="^cancel$")],
        conversation_timeout=600,
    )

    app.add_handler(api_conv)
    app.add_handler(threshold_conv)
    app.add_handler(interval_conv)
    app.add_handler(alloc_conv)
    app.add_handler(create_portfolio_conv)
    app.add_handler(edit_name_conv)
    app.add_handler(edit_capital_conv)
    app.add_handler(portfolio_threshold_conv)
    app.add_handler(portfolio_interval_conv)
    app.add_handler(tp_setup_conv)
    app.add_handler(build_grid_conv())

    # ── Commands ───────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("menu", menu_command))


    # ── Navigation ─────────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(handle_menu_callback, pattern="^menu:"))
    app.add_handler(CallbackQueryHandler(portfolio_callback,   pattern="^balance$"))
    app.add_handler(CallbackQueryHandler(history_callback,     pattern="^history$"))

    # ── Rebalance ──────────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(rebalance_callback, pattern="^rebalance:"))

    # ── Settings ───────────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(settings_callback,     pattern="^settings:(view|view_allocs)"))
    app.add_handler(CallbackQueryHandler(toggle_auto_callback,  pattern="^toggle_auto$"))
    app.add_handler(CallbackQueryHandler(del_alloc_callback,    pattern="^del_alloc:"))
    app.add_handler(CallbackQueryHandler(clear_allocs_callback, pattern="^clear_allocs"))

    # ── Momentum Breakout ──────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(momentum_callback, pattern="^momentum:"))

    # ── Grid Bot ───────────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(grid_menu_callback,         pattern="^grid:menu$"))
    app.add_handler(CallbackQueryHandler(grid_detail_callback,       pattern="^grid_detail:\\d+$"))
    app.add_handler(CallbackQueryHandler(grid_live_callback,         pattern="^grid_live:\\d+$"))
    app.add_handler(CallbackQueryHandler(grid_stop_callback,         pattern="^grid_stop:\\d+$"))
    app.add_handler(CallbackQueryHandler(grid_edit_tpsl_callback,    pattern="^grid_edit_tpsl:\\d+$"))
    app.add_handler(CallbackQueryHandler(grid_edit_range_callback,   pattern="^grid_edit_range:\\d+$"))
    app.add_handler(CallbackQueryHandler(grid_add_funds_callback,    pattern="^grid_add_funds:\\d+$"))
    app.add_handler(CallbackQueryHandler(grid_remove_funds_callback, pattern="^grid_remove_funds:\\d+$"))

    # ── Portfolio Management ───────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(portfolios_callback,               pattern="^portfolios$"))
    app.add_handler(CallbackQueryHandler(portfolio_detail_callback,         pattern="^portfolio:\\d+$"))
    app.add_handler(CallbackQueryHandler(portfolio_rebalance_callback,      pattern="^pf_rebalance:"))
    app.add_handler(CallbackQueryHandler(switch_portfolio_callback,         pattern="^portfolio_switch:"))
    app.add_handler(CallbackQueryHandler(delete_portfolio_callback,         pattern="^portfolio_delete:\\d+$"))
    app.add_handler(CallbackQueryHandler(delete_portfolio_confirm_callback, pattern="^portfolio_delete_confirm:"))
    app.add_handler(CallbackQueryHandler(portfolio_edit_allocs_callback,    pattern="^portfolio_edit_allocs:"))
    app.add_handler(CallbackQueryHandler(portfolio_toggle_auto_callback,    pattern="^portfolio_toggle_auto:"))
    app.add_handler(CallbackQueryHandler(portfolio_tp_menu_callback,        pattern="^portfolio_tp_menu:"))
    app.add_handler(CallbackQueryHandler(portfolio_tp_activate_callback,    pattern="^portfolio_tp_activate:"))
    app.add_handler(CallbackQueryHandler(portfolio_tp_deactivate_callback,  pattern="^portfolio_tp_deactivate:"))
    app.add_handler(CallbackQueryHandler(portfolio_sell_all_callback,       pattern="^portfolio_sell_all:"))
    app.add_handler(CallbackQueryHandler(portfolio_sell_one_callback,       pattern="^portfolio_sell_one:"))
    app.add_handler(CallbackQueryHandler(portfolio_sell_coin_callback,      pattern="^portfolio_sell_coin:"))
    app.add_handler(CallbackQueryHandler(portfolio_rebalance_sell_callback, pattern="^portfolio_rebalance_sell:"))
    app.add_handler(CallbackQueryHandler(portfolio_sell_exec_callback,      pattern="^portfolio_sell_exec:"))

    # ── Inline text input router ───────────────────────────────────────────────
    async def _text_router(update, context):
        ud = context.user_data
        if "_momentum_setting" in ud:
            await momentum_setting_input(update, context)
        elif "_grid_edit_tpsl" in ud:
            await grid_edit_tpsl_input(update, context)
        elif "_grid_edit_range" in ud:
            await grid_edit_range_input(update, context)
        elif "_grid_add_funds" in ud:
            await grid_add_funds_input(update, context)
        elif "_grid_remove_funds" in ud:
            await grid_remove_funds_input(update, context)

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.UpdateType.MESSAGE,
        _text_router,
    ))

    # ── Emergency Sell ─────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(emergency_menu_callback,              pattern="^emergency:menu$"))
    app.add_handler(CallbackQueryHandler(emergency_pick_coin_callback,         pattern="^emergency:pick_coin$"))
    app.add_handler(CallbackQueryHandler(emergency_pick_momentum_callback,     pattern="^emergency:pick_momentum$"))

    app.add_handler(CallbackQueryHandler(emergency_toggle_callback,            pattern="^emergency:toggle:"))
    app.add_handler(CallbackQueryHandler(emergency_confirm_selected_callback,  pattern="^emergency:confirm_selected$"))
    app.add_handler(CallbackQueryHandler(emergency_back_to_select_callback,    pattern="^emergency:back_to_select$"))
    app.add_handler(CallbackQueryHandler(emergency_exec_selected_callback,     pattern="^emergency:exec_selected$"))
    app.add_handler(CallbackQueryHandler(emergency_confirm_all_callback,       pattern="^emergency:confirm_all$"))
    app.add_handler(CallbackQueryHandler(emergency_exec_all_callback,          pattern="^emergency:exec_all$"))

    return app


async def main():
    await db.init()
    await momentum_monitor.restore_from_db()
    await grid_monitor.load_from_db()
    app = build_app()
    scheduler = await start_scheduler(app)


    # Momentum Breakout jobs
    scheduler.add_job(
        run_momentum_scan,
        trigger="interval",
        minutes=10,
        args=[app],
        id="momentum_scan",
        replace_existing=True,
    )
    scheduler.add_job(
        momentum_monitor.tick,
        trigger="interval",
        seconds=60,
        args=[app],
        id="momentum_monitor",
        replace_existing=True,
    )

    # Grid Bot job
    scheduler.add_job(
        run_grid_monitor,
        trigger="interval",
        seconds=30,
        args=[app],
        id="grid_monitor",
        replace_existing=True,
    )

    # Portfolio TP/SL monitor
    scheduler.add_job(
        run_portfolio_monitor,
        trigger="interval",
        minutes=5,
        args=[app],
        id="portfolio_tp_monitor",
        replace_existing=True,
    )
    # Health check HTTP server — required by Koyeb to confirm the process is alive
    port = int(os.environ.get("PORT", 8000))

    async def _health(_request):
        return web.Response(text="ok")

    http_app = web.Application()
    http_app.router.add_get("/", _health)
    http_app.router.add_get("/health", _health)
    runner = web.AppRunner(http_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health check server listening on port {port}")

    logger.info("🤖 Bot started polling...")
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
            await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
