"""
Telegram bot – MEXC Smart Portfolio rebalancer.

Commands: /start /status /rebalance /settings /history /stats /export /stop /help
"""

import asyncio
import io
import logging
import os
import threading
from datetime import datetime
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler,
    ContextTypes, ConversationHandler, MessageHandler, filters,
)

from database import get_rebalance_history, get_snapshots, init_db
from mexc_client import MEXCClient
from smart_portfolio import (
    execute_rebalance, get_pnl, get_portfolio_value,
    load_config, needs_rebalance_proportional, next_run_time,
    save_config, validate_allocations,
)

log = logging.getLogger(__name__)
init_db()

# Conversation states
(ST_ASSETS_COUNT, ST_ASSET_SYMBOL, ST_ASSET_PCT, ST_EQUAL_ALLOC,
 ST_USDT_AMOUNT, ST_REBALANCE_MODE, ST_THRESHOLD, ST_FREQUENCY,
 ST_SELL_TERM, ST_ASSET_TRANSFER, ST_PAPER_MODE) = range(11)

_bot_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_app_ref: Optional[Application] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _allowed(update: Update) -> bool:
    allowed_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not allowed_id:
        return True
    uid = update.effective_user.id if update.effective_user else None
    return str(uid) == allowed_id


def _client() -> MEXCClient:
    return MEXCClient()


def _is_running() -> bool:
    return _bot_thread is not None and _bot_thread.is_alive()


def _main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Status", callback_data="status"),
            InlineKeyboardButton("⚖️ Rebalance", callback_data="rebalance"),
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
            InlineKeyboardButton("📜 History", callback_data="history"),
        ],
        [
            InlineKeyboardButton("📈 Stats / P&L", callback_data="stats"),
            InlineKeyboardButton("📥 Export CSV", callback_data="export"),
        ],
        [
            InlineKeyboardButton("▶️ Start Bot", callback_data="start_bot"),
            InlineKeyboardButton("⏹ Stop Bot", callback_data="stop_bot"),
        ],
    ])


def _portfolio_text(cfg: dict) -> str:
    client = _client()
    portfolio = get_portfolio_value(client, cfg["portfolio"]["assets"])
    targets = {a["symbol"]: a["allocation_pct"] for a in cfg["portfolio"]["assets"]}
    paper_tag = " 🧪 *PAPER MODE*" if cfg.get("paper_trading") else ""
    mode = cfg["rebalance"]["mode"]
    last = cfg.get("last_rebalance") or "—"
    lines = [
        f"*{cfg['bot']['name']}*{paper_tag}",
        f"💰 Total: `{portfolio['total_usdt']:.2f} USDT`",
        f"🔄 Mode: `{mode}` | Last: `{last}`\n",
        f"{'Asset':<6} {'Actual':>7} {'Target':>7} {'Dev':>7}",
        "─" * 32,
    ]
    for r in portfolio["assets"]:
        tgt = targets[r["symbol"]]
        dev = r["actual_pct"] - tgt
        arrow = "🔴" if dev > 3 else ("🟡" if dev > 1 else "🟢")
        lines.append(
            f"{arrow} `{r['symbol']:<5}` "
            f"`{r['actual_pct']:>5.1f}%` "
            f"`{tgt:>5.1f}%` "
            f"`{dev:>+5.1f}%`"
        )
    return "\n".join(lines)


def _history_text(limit: int = 10) -> str:
    rows = get_rebalance_history(limit)
    if not rows:
        return "📜 لا توجد عمليات إعادة توازن بعد."
    lines = [f"*آخر {limit} عمليات إعادة توازن:*\n"]
    for r in rows:
        paper = " 🧪" if r["paper"] else ""
        trades = [d for d in r["details"] if d["action"] in ("BUY", "SELL")]
        lines.append(
            f"🕐 `{r['ts']}`{paper}\n"
            f"   Mode: `{r['mode']}` | Total: `{r['total_usdt']:.2f} USDT`"
        )
        for d in trades:
            emoji = "🟢" if d["action"] == "BUY" else "🔴"
            lines.append(
                f"   {emoji} {d['action']} {d['symbol']}: "
                f"`{d['diff_usdt']:+.2f}` USDT "
                f"(dev `{d['deviation']:+.1f}%`)"
            )
        if not trades:
            lines.append("   ✅ لا توجد تعديلات (المحفظة متوازنة)")
        lines.append("")
    return "\n".join(lines)


def _stats_text(cfg: dict) -> str:
    pnl = get_pnl(cfg)
    snaps = get_snapshots(30)
    sign = "+" if pnl["pnl_usdt"] >= 0 else ""
    emoji = "📈" if pnl["pnl_usdt"] >= 0 else "📉"
    lines = [
        f"*إحصائيات المحفظة* {emoji}",
        f"💵 الاستثمار الأولي: `{pnl['initial_usdt']:.2f} USDT`",
        f"💰 القيمة الحالية:   `{pnl['current_usdt']:.2f} USDT`",
        f"📊 الربح/الخسارة:    `{sign}{pnl['pnl_usdt']:.2f} USDT` (`{sign}{pnl['pnl_pct']:.2f}%`)",
        f"\n📅 نقاط البيانات المتاحة: `{len(snaps)}` يوم",
    ]
    history = get_rebalance_history(100)
    lines.append(f"🔄 إجمالي عمليات إعادة التوازن: `{len(history)}`")
    return "\n".join(lines)


def _build_csv(cfg: dict) -> bytes:
    import csv
    rows = get_rebalance_history(100)
    buf = __import__("io").StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp", "mode", "total_usdt", "paper", "symbol",
                "target_pct", "actual_pct", "deviation", "diff_usdt", "action"])
    for r in rows:
        for d in r["details"]:
            w.writerow([
                r["ts"], r["mode"], r["total_usdt"], bool(r["paper"]),
                d["symbol"], d["target_pct"], d["actual_pct"],
                d["deviation"], d["diff_usdt"], d["action"],
            ])
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    status = "▶️ شغال" if _is_running() else "⏹ واقف"
    cfg = load_config()
    paper = " 🧪 Paper Mode" if cfg.get("paper_trading") else ""
    await update.message.reply_text(
        f"*MEXC Smart Portfolio Bot*{paper}\nالحالة: {status}\n\nاختار من القائمة:",
        parse_mode="Markdown",
        reply_markup=_main_menu(),
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    msg = await update.message.reply_text("⏳ جاري جلب البيانات...")
    try:
        cfg = load_config()
        await msg.edit_text(_portfolio_text(cfg), parse_mode="Markdown", reply_markup=_main_menu())
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}", reply_markup=_main_menu())


async def cmd_rebalance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    msg = await update.message.reply_text("⏳ جاري تنفيذ الـ rebalance...")
    try:
        cfg = load_config()
        loop = asyncio.get_running_loop()
        details = await loop.run_in_executor(None, execute_rebalance, _client(), cfg)
        paper = " 🧪 (Paper)" if cfg.get("paper_trading") else ""
        buys  = [d for d in details if d["action"] == "BUY"]
        sells = [d for d in details if d["action"] == "SELL"]
        lines = [f"✅ تم الـ rebalance{paper}!"]
        for d in sells:
            lines.append(f"🔴 SELL {d['symbol']}: `{d['diff_usdt']:+.2f}` USDT")
        for d in buys:
            lines.append(f"🟢 BUY  {d['symbol']}: `{d['diff_usdt']:+.2f}` USDT")
        await msg.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=_main_menu())
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}", reply_markup=_main_menu())


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    # Allow /history 20 to get more records
    limit = 10
    if context.args:
        try:
            limit = max(1, min(50, int(context.args[0])))
        except ValueError:
            pass
    text = _history_text(limit)
    # Telegram message limit is 4096 chars
    if len(text) > 4000:
        text = text[:4000] + "\n...(مقتطع)"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=_main_menu())


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    cfg = load_config()
    await update.message.reply_text(_stats_text(cfg), parse_mode="Markdown", reply_markup=_main_menu())


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    cfg = load_config()
    data = _build_csv(cfg)
    fname = f"rebalance_history_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    await update.message.reply_document(
        document=io.BytesIO(data),
        filename=fname,
        caption="📥 تقرير عمليات إعادة التوازن",
    )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    if _is_running():
        _stop_event.set()
        await update.message.reply_text("⏹ تم إيقاف البوت.", reply_markup=_main_menu())
    else:
        await update.message.reply_text("البوت مش شغال أصلاً.", reply_markup=_main_menu())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    await update.message.reply_text(
        "*🤖 MEXC Smart Portfolio Bot*\n\n"
        "*الأوامر المتاحة:*\n"
        "/start – القائمة الرئيسية\n"
        "/status – عرض المحفظة الحالية (النسب الحالية vs المستهدفة)\n"
        "/rebalance – إعادة توازن يدوي فوري\n"
        "/settings – إعداد المحفظة (عملات، نسب، وضع)\n"
        "/history \\[N\\] – آخر N عملية (افتراضي 10، أقصى 50)\n"
        "/stats – إحصائيات وأرباح/خسائر\n"
        "/export – تحميل تقرير CSV\n"
        "/stop – إيقاف البوت\n"
        "/help – هذه الرسالة\n\n"
        "*ملاحظات:*\n"
        "• البوت يعمل على Spot فقط\n"
        "• جميع الأزواج بـ USDT\n"
        "• الإشعارات تُرسل تلقائياً عند كل Rebalance",
        parse_mode="Markdown",
        reply_markup=_main_menu(),
    )


# ---------------------------------------------------------------------------
# Settings wizard (ConversationHandler)
# ---------------------------------------------------------------------------

async def settings_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point – ask how many assets."""
    query = update.callback_query
    if query:
        await query.answer()
        send = query.message.reply_text
    else:
        send = update.message.reply_text
    context.user_data.clear()
    context.user_data["assets"] = []
    await send(
        "⚙️ *إعداد المحفظة*\n\nكم عدد العملات؟ (من 2 إلى 10)",
        parse_mode="Markdown",
    )
    return ST_ASSETS_COUNT


async def settings_assets_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        n = int(update.message.text.strip())
        if not (2 <= n <= 10):
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقم بين 2 و 10.")
        return ST_ASSETS_COUNT
    context.user_data["total_assets"] = n
    context.user_data["current_idx"] = 0
    await update.message.reply_text(
        f"أدخل رمز العملة الأولى (مثال: BTC):"
    )
    return ST_ASSET_SYMBOL


async def settings_asset_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    sym = update.message.text.strip().upper()
    context.user_data["current_symbol"] = sym
    idx = context.user_data["current_idx"]
    total = context.user_data["total_assets"]
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📐 توزيع متساوي", callback_data="equal_alloc")]])
    if idx == total - 1:
        # last asset – auto-assign remaining
        assets = context.user_data["assets"]
        used = sum(a["allocation_pct"] for a in assets)
        remaining = round(100.0 - used, 4)
        assets.append({"symbol": sym, "allocation_pct": remaining})
        await update.message.reply_text(
            f"✅ {sym}: `{remaining}%` (تم تعيينها تلقائياً)",
            parse_mode="Markdown",
        )
        context.user_data["current_idx"] += 1
        return await _ask_usdt(update, context)
    await update.message.reply_text(
        f"أدخل نسبة {sym} (المتبقي: "
        f"{round(100 - sum(a['allocation_pct'] for a in context.user_data['assets']), 2)}%):",
        reply_markup=kb,
    )
    return ST_ASSET_PCT


async def settings_asset_pct(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assets = context.user_data["assets"]
    used = sum(a["allocation_pct"] for a in assets)
    remaining = round(100.0 - used, 4)
    try:
        pct = float(update.message.text.strip())
        if pct <= 0 or pct >= remaining:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"❌ أدخل رقم بين 0 و {remaining:.2f}.")
        return ST_ASSET_PCT
    sym = context.user_data["current_symbol"]
    assets.append({"symbol": sym, "allocation_pct": round(pct, 4)})
    context.user_data["current_idx"] += 1
    idx = context.user_data["current_idx"]
    total = context.user_data["total_assets"]
    await update.message.reply_text(f"✅ {sym}: {pct}%")
    if idx >= total:
        return await _ask_usdt(update, context)
    await update.message.reply_text(f"أدخل رمز العملة {idx + 1}:")
    return ST_ASSET_SYMBOL


async def settings_equal_alloc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Callback: distribute equally across all assets entered so far + remaining."""
    query = update.callback_query
    await query.answer()
    total = context.user_data["total_assets"]
    pct = round(100.0 / total, 4)
    # rebuild assets list with equal allocation using symbols already entered
    existing = [a["symbol"] for a in context.user_data["assets"]]
    existing.append(context.user_data.get("current_symbol", ""))
    # we only have symbols up to current_idx; ask for remaining symbols first
    # Simpler: assign equal pct to all already-named, then ask remaining symbols
    assets = [{"symbol": s, "allocation_pct": pct} for s in existing if s]
    # fix rounding on last
    diff = round(100.0 - sum(a["allocation_pct"] for a in assets), 4)
    if assets:
        assets[-1]["allocation_pct"] = round(assets[-1]["allocation_pct"] + diff, 4)
    context.user_data["assets"] = assets
    context.user_data["current_idx"] = len(assets)
    if len(assets) >= total:
        await query.message.reply_text(
            "✅ تم التوزيع المتساوي:\n" +
            "\n".join(f"  {a['symbol']}: {a['allocation_pct']}%" for a in assets)
        )
        return await _ask_usdt(query.message, context)
    await query.message.reply_text(
        f"✅ تم تعيين {len(assets)} عملات بالتساوي.\nأدخل رمز العملة {len(assets)+1}:"
    )
    return ST_ASSET_SYMBOL


async def _ask_usdt(update_or_msg, context) -> int:
    send = update_or_msg.reply_text if hasattr(update_or_msg, "reply_text") else update_or_msg.message.reply_text
    await send("💵 أدخل المبلغ الإجمالي بـ USDT:")
    return ST_USDT_AMOUNT


async def settings_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقم موجب.")
        return ST_USDT_AMOUNT
    context.user_data["total_usdt"] = amount
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Proportional", callback_data="mode_proportional")],
        [InlineKeyboardButton("⏰ Timed", callback_data="mode_timed")],
        [InlineKeyboardButton("🔓 Unbalanced", callback_data="mode_unbalanced")],
    ])
    await update.message.reply_text("اختار وضع إعادة التوازن:", reply_markup=kb)
    return ST_REBALANCE_MODE


async def settings_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    mode = query.data.replace("mode_", "")
    context.user_data["mode"] = mode
    if mode == "proportional":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("1%", callback_data="thr_1"),
             InlineKeyboardButton("3%", callback_data="thr_3"),
             InlineKeyboardButton("5%", callback_data="thr_5")],
        ])
        await query.message.reply_text("اختار عتبة الانحراف:", reply_markup=kb)
        return ST_THRESHOLD
    elif mode == "timed":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("يومي", callback_data="freq_daily"),
             InlineKeyboardButton("أسبوعي", callback_data="freq_weekly"),
             InlineKeyboardButton("شهري", callback_data="freq_monthly")],
        ])
        await query.message.reply_text("اختار التكرار:", reply_markup=kb)
        return ST_FREQUENCY
    else:
        return await _ask_sell_term(query.message, context)


async def settings_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["threshold"] = int(query.data.replace("thr_", ""))
    return await _ask_sell_term(query.message, context)


async def settings_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["frequency"] = query.data.replace("freq_", "")
    return await _ask_sell_term(query.message, context)


async def _ask_sell_term(msg, context) -> int:
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ نعم", callback_data="sell_yes"),
        InlineKeyboardButton("❌ لا", callback_data="sell_no"),
    ]])
    await msg.reply_text("بيع كل الأصول عند الإيقاف؟", reply_markup=kb)
    return ST_SELL_TERM


async def settings_sell_term(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["sell_at_termination"] = query.data == "sell_yes"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ نعم", callback_data="transfer_yes"),
        InlineKeyboardButton("❌ لا", callback_data="transfer_no"),
    ]])
    await query.message.reply_text("تفعيل تحويل الأصول؟", reply_markup=kb)
    return ST_ASSET_TRANSFER


async def settings_asset_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["enable_asset_transfer"] = query.data == "transfer_yes"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🧪 Paper (تجريبي)", callback_data="paper_yes"),
        InlineKeyboardButton("💰 Live (حقيقي)", callback_data="paper_no"),
    ]])
    await query.message.reply_text("وضع التشغيل:", reply_markup=kb)
    return ST_PAPER_MODE


async def settings_paper_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    paper = query.data == "paper_yes"
    ud = context.user_data
    cfg = load_config()
    cfg["portfolio"]["assets"] = ud["assets"]
    cfg["portfolio"]["total_usdt"] = ud["total_usdt"]
    cfg["portfolio"]["initial_value_usdt"] = ud["total_usdt"]
    cfg["rebalance"]["mode"] = ud["mode"]
    if ud["mode"] == "proportional":
        cfg["rebalance"]["proportional"]["threshold_pct"] = ud.get("threshold", 5)
    elif ud["mode"] == "timed":
        cfg["rebalance"]["timed"]["frequency"] = ud.get("frequency", "daily")
    cfg["termination"]["sell_at_termination"] = ud.get("sell_at_termination", False)
    cfg["asset_transfer"]["enable_asset_transfer"] = ud.get("enable_asset_transfer", False)
    cfg["paper_trading"] = paper
    save_config(cfg)
    paper_label = "🧪 Paper" if paper else "💰 Live"
    await query.message.reply_text(
        f"✅ *تم حفظ الإعدادات!*\n"
        f"العملات: {len(ud['assets'])} | Mode: `{ud['mode']}` | {paper_label}",
        parse_mode="Markdown",
        reply_markup=_main_menu(),
    )
    return ConversationHandler.END


async def settings_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ تم إلغاء الإعداد.", reply_markup=_main_menu())
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Rebalancer background loop
# ---------------------------------------------------------------------------

def _run_loop(cfg: dict, app: Application, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    """Background thread: runs the rebalance loop and sends Telegram notifications."""
    from datetime import datetime as _dt
    _stop_event.clear()
    client = _client()
    mode = cfg["rebalance"]["mode"]
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    log.info("Rebalancer loop started | mode: %s", mode)

    async def _notify(text: str) -> None:
        if chat_id and app:
            try:
                await app.bot.send_message(chat_id=chat_id, text=text,
                                           parse_mode="Markdown",
                                           reply_markup=_main_menu())
            except Exception as e:
                log.error("Notify failed: %s", e)

    def _sync_notify(text: str) -> None:
        # loop is the asyncio event loop running the Telegram Application
        if app and app.running and loop is not None:
            asyncio.run_coroutine_threadsafe(_notify(text), loop)

    try:
        if mode == "proportional":
            interval = cfg["rebalance"]["proportional"]["check_interval_minutes"] * 60
            while not _stop_event.is_set():
                try:
                    cfg = load_config()
                    if needs_rebalance_proportional(client, cfg):
                        details = execute_rebalance(client, cfg)
                        paper = " 🧪" if cfg.get("paper_trading") else ""
                        buys  = [d for d in details if d["action"] == "BUY"]
                        sells = [d for d in details if d["action"] == "SELL"]
                        ts    = _dt.utcnow().strftime("%Y-%m-%d %H:%M UTC")
                        pnl   = get_pnl(cfg)
                        sign  = "+" if pnl["pnl_usdt"] >= 0 else ""
                        lines = [
                            f"🔄 *Rebalance تلقائي*{paper}",
                            f"🕐 `{ts}`",
                            f"💰 الإجمالي: `{pnl['current_usdt']:.2f} USDT`",
                            f"📊 P&L: `{sign}{pnl['pnl_usdt']:.2f} USDT` (`{sign}{pnl['pnl_pct']:.2f}%`)",
                            "",
                        ]
                        for d in sells:
                            lines.append(f"🔴 SELL {d['symbol']}: `{d['diff_usdt']:+.2f}` USDT  (انحراف `{d['deviation']:+.1f}%`)")
                        for d in buys:
                            lines.append(f"🟢 BUY  {d['symbol']}: `{d['diff_usdt']:+.2f}` USDT  (انحراف `{d['deviation']:+.1f}%`)")
                        _sync_notify("\n".join(lines))
                except Exception as e:
                    log.error("Loop error: %s", e)
                    _sync_notify(f"⚠️ خطأ في الـ loop: `{e}`")
                _stop_event.wait(interval)

        elif mode == "timed":
            timed_cfg = cfg["rebalance"]["timed"]
            frequency = timed_cfg["frequency"]
            target_hour = timed_cfg.get("hour", 0)
            next_run = next_run_time(frequency, target_hour=target_hour)
            while not _stop_event.is_set():
                try:
                    if _dt.utcnow() >= next_run:
                        cfg = load_config()
                        details = execute_rebalance(client, cfg)
                        paper = " 🧪" if cfg.get("paper_trading") else ""
                        frequency = cfg["rebalance"]["timed"]["frequency"]
                        target_hour = cfg["rebalance"]["timed"].get("hour", 0)
                        next_run = next_run_time(frequency, target_hour=target_hour)
                        buys  = [d for d in details if d["action"] == "BUY"]
                        sells = [d for d in details if d["action"] == "SELL"]
                        lines = [f"⏰ *Rebalance مجدول ({frequency})*{paper}"]
                        for d in sells:
                            lines.append(f"🔴 SELL {d['symbol']}: `{d['diff_usdt']:+.2f}` USDT")
                        for d in buys:
                            lines.append(f"🟢 BUY  {d['symbol']}: `{d['diff_usdt']:+.2f}` USDT")
                        lines.append(f"⏭ التالي: `{next_run.strftime('%Y-%m-%d %H:%M')} UTC`")
                        _sync_notify("\n".join(lines))
                except Exception as e:
                    log.error("Loop error: %s", e)
                    _sync_notify(f"⚠️ خطأ في الـ loop: `{e}`")
                _stop_event.wait(60)

        elif mode == "unbalanced":
            _stop_event.wait()

    except Exception as e:
        log.error("Rebalancer loop crashed: %s", e)
        _sync_notify(f"🚨 *البوت توقف بسبب خطأ:*\n`{e}`\nأعد تشغيله بـ ▶️ Start Bot")

    log.info("Rebalancer loop stopped")


# ---------------------------------------------------------------------------
# Inline button handler
# ---------------------------------------------------------------------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not _allowed(update):
        return

    global _bot_thread

    data = query.data

    if data == "status":
        await query.edit_message_text("⏳ جاري جلب البيانات...")
        try:
            cfg = load_config()
            await query.edit_message_text(_portfolio_text(cfg),
                                          parse_mode="Markdown",
                                          reply_markup=_main_menu())
        except Exception as e:
            await query.edit_message_text(f"❌ خطأ: {e}", reply_markup=_main_menu())

    elif data == "rebalance":
        await query.edit_message_text("⏳ جاري تنفيذ الـ rebalance...")
        try:
            cfg = load_config()
            loop = asyncio.get_running_loop()
            details = await loop.run_in_executor(None, execute_rebalance, _client(), cfg)
            paper = " 🧪 (Paper)" if cfg.get("paper_trading") else ""
            buys  = [d for d in details if d["action"] == "BUY"]
            sells = [d for d in details if d["action"] == "SELL"]
            lines = [f"✅ تم الـ rebalance{paper}!"]
            for d in sells:
                lines.append(f"🔴 SELL {d['symbol']}: `{d['diff_usdt']:+.2f}` USDT")
            for d in buys:
                lines.append(f"🟢 BUY  {d['symbol']}: `{d['diff_usdt']:+.2f}` USDT")
            await query.edit_message_text("\n".join(lines),
                                          parse_mode="Markdown",
                                          reply_markup=_main_menu())
        except Exception as e:
            await query.edit_message_text(f"❌ خطأ: {e}", reply_markup=_main_menu())

    elif data == "history":
        await query.edit_message_text(_history_text(),
                                      parse_mode="Markdown",
                                      reply_markup=_main_menu())

    elif data == "stats":
        cfg = load_config()
        await query.edit_message_text(_stats_text(cfg),
                                      parse_mode="Markdown",
                                      reply_markup=_main_menu())

    elif data == "export":
        cfg = load_config()
        data_bytes = _build_csv(cfg)
        fname = f"rebalance_{__import__('datetime').datetime.utcnow().strftime('%Y%m%d')}.csv"
        await query.message.reply_document(
            document=__import__("io").BytesIO(data_bytes),
            filename=fname,
            caption="📥 تقرير عمليات إعادة التوازن",
        )
        await query.edit_message_reply_markup(reply_markup=_main_menu())

    elif data == "settings":
        await settings_start(update, context)

    elif data == "start_bot":
        if _is_running():
            await query.edit_message_text("البوت شغال بالفعل.", reply_markup=_main_menu())
            return
        try:
            cfg = load_config()
            validate_allocations(cfg["portfolio"]["assets"])
            _bot_thread = threading.Thread(
                target=_run_loop,
                args=(cfg, _app_ref, asyncio.get_running_loop()),
                daemon=True,
            )
            _bot_thread.start()
            paper = " 🧪 Paper" if cfg.get("paper_trading") else ""
            await query.edit_message_text(
                f"▶️ البوت بدأ | mode: *{cfg['rebalance']['mode']}*{paper}",
                parse_mode="Markdown",
                reply_markup=_main_menu(),
            )
        except Exception as e:
            await query.edit_message_text(f"❌ خطأ: {e}", reply_markup=_main_menu())

    elif data == "stop_bot":
        if _is_running():
            _stop_event.set()
            await query.edit_message_text("⏹ تم إيقاف البوت.", reply_markup=_main_menu())
        else:
            await query.edit_message_text("البوت مش شغال أصلاً.", reply_markup=_main_menu())


# ---------------------------------------------------------------------------
# Auto-start on launch
# ---------------------------------------------------------------------------

async def _post_init(app: Application) -> None:
    global _bot_thread, _app_ref
    _app_ref = app
    try:
        cfg = load_config()
        validate_allocations(cfg["portfolio"]["assets"])
        _bot_thread = threading.Thread(
            target=_run_loop,
            args=(cfg, app, asyncio.get_running_loop()),
            daemon=True,
        )
        _bot_thread.start()
        log.info("Rebalancer auto-started | mode: %s", cfg["rebalance"]["mode"])
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if chat_id:
            paper = " 🧪 Paper Mode" if cfg.get("paper_trading") else ""
            await app.bot.send_message(
                chat_id=chat_id,
                text=f"✅ *البوت اشتغل تلقائياً*{paper}\nmode: `{cfg['rebalance']['mode']}`",
                parse_mode="Markdown",
                reply_markup=_main_menu(),
            )
    except Exception as e:
        log.error("Auto-start failed: %s", e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def start_telegram_bot() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    app = Application.builder().token(token).post_init(_post_init).build()

    # Settings conversation
    settings_conv = ConversationHandler(
        entry_points=[
            CommandHandler("settings", settings_start),
            CallbackQueryHandler(settings_start, pattern="^settings$"),
        ],
        states={
            ST_ASSETS_COUNT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_assets_count)],
            ST_ASSET_SYMBOL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_asset_symbol)],
            ST_ASSET_PCT:       [
                MessageHandler(filters.TEXT & ~filters.COMMAND, settings_asset_pct),
                CallbackQueryHandler(settings_equal_alloc, pattern="^equal_alloc$"),
            ],
            ST_EQUAL_ALLOC:     [CallbackQueryHandler(settings_equal_alloc, pattern="^equal_alloc$")],
            ST_USDT_AMOUNT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_usdt)],
            ST_REBALANCE_MODE:  [CallbackQueryHandler(settings_mode, pattern="^mode_")],
            ST_THRESHOLD:       [CallbackQueryHandler(settings_threshold, pattern="^thr_")],
            ST_FREQUENCY:       [CallbackQueryHandler(settings_frequency, pattern="^freq_")],
            ST_SELL_TERM:       [CallbackQueryHandler(settings_sell_term, pattern="^sell_")],
            ST_ASSET_TRANSFER:  [CallbackQueryHandler(settings_asset_transfer, pattern="^transfer_")],
            ST_PAPER_MODE:      [CallbackQueryHandler(settings_paper_mode, pattern="^paper_")],
        },
        fallbacks=[CommandHandler("cancel", settings_cancel)],
        allow_reentry=True,
    )

    app.add_handler(settings_conv)
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("rebalance", cmd_rebalance))
    app.add_handler(CommandHandler("history",   cmd_history))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("export",    cmd_export))
    app.add_handler(CommandHandler("stop",      cmd_stop))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CallbackQueryHandler(button_handler))

    log.info("Telegram bot polling...")
    app.run_polling()
