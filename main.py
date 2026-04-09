import asyncio
import logging
import re
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, TypeHandler, filters,
    ApplicationHandlerStop,
)
from bot.config import config
from bot.database import db
from bot.handlers.start import start_handler, help_handler, menu_command, home_callback, main_menu_callback
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
    edit_portfolio_capital_start, edit_portfolio_capital_input,
    cancel_portfolio_conv,
    portfolio_sell_all_callback, portfolio_sell_one_callback,
    portfolio_sell_coin_callback,
    portfolio_sell_exec_callback,
    portfolio_edit_allocs_callback,
    portfolio_rebalance_callback,
    portfolio_rebalance_exec_callback,
    portfolio_balance_callback,
    pf_alloc_list_callback,
    pf_alloc_del_callback,
    pf_alloc_clear_callback,
    pf_alloc_text_input,
    CREATE_NAME, CREATE_CAPITAL, EDIT_CAPITAL,
)
from bot.handlers.auto_alloc_handler import (
    auto_alloc_menu_callback,
    auto_alloc_preview_callback,
    auto_alloc_apply_callback,
)
from bot.handlers.momentum_handler import (
    momentum_callback,
    momentum_setting_input,
    momentum_cancel,
    run_momentum_scan,
    SET_SIZE, SET_MAX, SET_LOSS,
)
from bot.handlers.emergency_handler import (
    emergency_menu_callback,
    emergency_pick_coin_callback,
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


async def _auth_gate(update: Update, context) -> None:
    """
    يعمل في group=-1 قبل كل الـ handlers.
    لو المستخدم مش في ALLOWED_USER_IDS — يرد ويوقف المعالجة.
    لو ALLOWED_USER_IDS فارغ — يسمح للكل (وضع التطوير).
    """
    if not config.allowed_user_ids:
        return  # مفتوح للكل
    uid = update.effective_user.id if update.effective_user else None
    logger.info("AUTH: uid=%s allowed=%s", uid, config.allowed_user_ids)
    if uid in config.allowed_user_ids:
        return  # مصرح له — كمّل
    # غير مصرح — رد وأوقف
    if update.callback_query:
        await update.callback_query.answer("⛔ غير مصرح.", show_alert=True)
    elif update.message:
        await update.message.reply_text("⛔ غير مصرح.")
    raise ApplicationHandlerStop


def build_app() -> Application:
    app = Application.builder().token(config.telegram_token).build()

    # ── Auth gate (group -1 يعمل قبل كل الـ handlers) ────────────────────────
    app.add_handler(TypeHandler(Update, _auth_gate), group=-1)

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
            CREATE_CAPITAL: [MessageHandler(TEXT, create_portfolio_capital)],
        },
        fallbacks=[CommandHandler("cancel", cancel_portfolio_conv),
                   CallbackQueryHandler(cancel_portfolio_conv, pattern="^cancel$")],
        conversation_timeout=600,
    )

    edit_capital_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_portfolio_capital_start, pattern="^portfolio_edit_capital:")],
        states={EDIT_CAPITAL: [MessageHandler(TEXT, edit_portfolio_capital_input)]},
        fallbacks=[CommandHandler("cancel", cancel_portfolio_conv),
                   CallbackQueryHandler(cancel_portfolio_conv, pattern="^cancel$")],
        conversation_timeout=300,
    )

    momentum_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(momentum_callback, pattern="^momentum:(set_size|set_max|set_loss)$")],
        states={
            SET_SIZE: [MessageHandler(TEXT, momentum_setting_input)],
            SET_MAX:  [MessageHandler(TEXT, momentum_setting_input)],
            SET_LOSS: [MessageHandler(TEXT, momentum_setting_input)],
        },
        fallbacks=[CommandHandler("cancel", momentum_cancel),
                   CallbackQueryHandler(momentum_cancel, pattern="^cancel$")],
        conversation_timeout=300,
    )

    app.add_handler(api_conv)
    app.add_handler(threshold_conv)
    app.add_handler(interval_conv)
    app.add_handler(alloc_conv)
    app.add_handler(create_portfolio_conv)
    app.add_handler(edit_capital_conv)
    app.add_handler(momentum_conv)
    app.add_handler(build_grid_conv())

    # ── Commands ───────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("menu", menu_command))


    # ── Navigation ─────────────────────────────────────────────────────────────
    # home / menu:main → شاشة المحفظة النشطة مباشرة
    app.add_handler(CallbackQueryHandler(home_callback,        pattern="^home$"))
    app.add_handler(CallbackQueryHandler(main_menu_callback,   pattern="^menu:main$"))
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
    app.add_handler(CallbackQueryHandler(portfolio_rebalance_callback,      pattern="^pf_rebalance:\\d+$"))
    app.add_handler(CallbackQueryHandler(portfolio_rebalance_exec_callback, pattern="^pf_rebalance_exec:\\d+$"))
    app.add_handler(CallbackQueryHandler(portfolio_balance_callback,        pattern="^pf_balance:\\d+$"))

    # ── التوزيع الذكي التلقائي ─────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(auto_alloc_menu_callback,    pattern="^auto_alloc_menu:\\d+$"))
    app.add_handler(CallbackQueryHandler(auto_alloc_preview_callback, pattern="^auto_alloc:(equal|volume|mcap):\\d+$"))
    app.add_handler(CallbackQueryHandler(auto_alloc_apply_callback,   pattern="^auto_alloc_apply:(equal|volume|mcap):\\d+$"))
    app.add_handler(CallbackQueryHandler(switch_portfolio_callback,         pattern="^portfolio_switch:"))
    app.add_handler(CallbackQueryHandler(delete_portfolio_callback,         pattern="^portfolio_delete:\\d+$"))
    app.add_handler(CallbackQueryHandler(delete_portfolio_confirm_callback, pattern="^portfolio_delete_confirm:"))
    app.add_handler(CallbackQueryHandler(portfolio_edit_allocs_callback,    pattern="^portfolio_edit_allocs:"))
    app.add_handler(CallbackQueryHandler(pf_alloc_list_callback,            pattern="^pf_alloc_list:\\d+$"))
    app.add_handler(CallbackQueryHandler(pf_alloc_del_callback,             pattern="^pf_alloc_del:\\d+:"))
    app.add_handler(CallbackQueryHandler(pf_alloc_clear_callback,           pattern="^pf_alloc_clear:\\d+$"))
    app.add_handler(CallbackQueryHandler(pf_alloc_clear_callback,           pattern="^pf_alloc_clear_confirm:\\d+$"))
    app.add_handler(CallbackQueryHandler(portfolio_sell_all_callback,       pattern="^portfolio_sell_all:"))
    app.add_handler(CallbackQueryHandler(portfolio_sell_one_callback,       pattern="^portfolio_sell_one:"))
    app.add_handler(CallbackQueryHandler(portfolio_sell_coin_callback,      pattern="^portfolio_sell_coin:"))
    app.add_handler(CallbackQueryHandler(portfolio_sell_exec_callback,      pattern="^portfolio_sell_exec:"))

    # ── Inline text input router ───────────────────────────────────────────────
    async def _text_router(update, context):
        ud = context.user_data
        if "_alloc_portfolio_id" in ud:
            await pf_alloc_text_input(update, context)
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

    # ── Momentum ───────────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(momentum_callback, pattern="^momentum:"))

    # ── Emergency Sell ─────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(emergency_menu_callback,              pattern="^emergency:menu$"))
    app.add_handler(CallbackQueryHandler(emergency_pick_coin_callback,         pattern="^emergency:pick_coin$"))

    app.add_handler(CallbackQueryHandler(emergency_toggle_callback,            pattern="^emergency:toggle:"))
    app.add_handler(CallbackQueryHandler(emergency_confirm_selected_callback,  pattern="^emergency:confirm_selected$"))
    app.add_handler(CallbackQueryHandler(emergency_back_to_select_callback,    pattern="^emergency:back_to_select$"))
    app.add_handler(CallbackQueryHandler(emergency_exec_selected_callback,     pattern="^emergency:exec_selected$"))
    app.add_handler(CallbackQueryHandler(emergency_confirm_all_callback,       pattern="^emergency:confirm_all$"))
    app.add_handler(CallbackQueryHandler(emergency_exec_all_callback,          pattern="^emergency:exec_all$"))

    return app


async def main():
    import os
    import threading
    from bot.api_server import app as flask_app, set_bot_loop

    await db.init()
    await grid_monitor.load_from_db()
    tg_app = build_app()
    scheduler = await start_scheduler(tg_app)

    # Grid Bot job
    scheduler.add_job(
        run_grid_monitor,
        trigger="interval",
        seconds=30,
        args=[tg_app],
        id="grid_monitor",
        replace_existing=True,
    )

    # Momentum scan job
    scheduler.add_job(
        run_momentum_scan,
        trigger="interval",
        minutes=10,
        args=[tg_app],
        id="momentum_scan",
        replace_existing=True,
    )

    webhook_url = os.environ.get("WEBHOOK_URL", "").strip()
    flask_port  = int(os.environ.get("PORT", os.environ.get("API_PORT", 8080)))

    set_bot_loop(asyncio.get_event_loop())

    if webhook_url:
        # ── Webhook mode ────────────────────────────────────────────────────
        # Telegram sends updates to POST /webhook/<token>
        token = config.telegram_token
        webhook_path = f"/webhook/{token}"
        full_webhook_url = webhook_url.rstrip("/") + webhook_path

        from telegram import Update as TGUpdate

        @flask_app.route(webhook_path, methods=["POST"])
        def telegram_webhook():
            from flask import request as flask_request
            import json
            data = flask_request.get_json(force=True, silent=True)
            if data:
                update = TGUpdate.de_json(data, tg_app.bot)
                asyncio.run_coroutine_threadsafe(
                    tg_app.process_update(update), asyncio.get_event_loop()
                )
            return "", 200

        flask_thread = threading.Thread(
            target=lambda: flask_app.run(
                host="0.0.0.0",
                port=flask_port,
                debug=False,
                use_reloader=False,
            ),
            daemon=True,
            name="flask-api",
        )
        flask_thread.start()
        logger.info("Flask started on port %d", flask_port)

        async with tg_app:
            await tg_app.start()
            await tg_app.bot.set_webhook(
                url=full_webhook_url,
                allowed_updates=TGUpdate.ALL_TYPES,
                drop_pending_updates=True,
            )
            logger.info("Webhook set: %s", full_webhook_url)
            try:
                await asyncio.Event().wait()
            finally:
                await tg_app.bot.delete_webhook()
                await tg_app.stop()
                scheduler.shutdown(wait=False)
    else:
        # ── Polling mode (local dev) ─────────────────────────────────────────
        flask_thread = threading.Thread(
            target=lambda: flask_app.run(
                host="0.0.0.0",
                port=flask_port,
                debug=False,
                use_reloader=False,
            ),
            daemon=True,
            name="flask-api",
        )
        flask_thread.start()
        logger.info("Flask started on port %d (polling mode)", flask_port)

        async with tg_app:
            await tg_app.start()
            await tg_app.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
            )
            logger.info("Bot started polling...")
            try:
                await asyncio.Event().wait()
            finally:
                await tg_app.updater.stop()
                await tg_app.stop()
                scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
