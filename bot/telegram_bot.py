"""
Telegram bot — Arabic inline-keyboard interface for the MEXC Rebalancer.

Commands
--------
/start  /menu  — main menu
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

log = logging.getLogger("telegram_bot")

# ── Auth ───────────────────────────────────────────────────────────────────────
def _allowed(update: Update) -> bool:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not chat_id:
        return True
    uid = str(update.effective_user.id) if update.effective_user else ""
    return uid == chat_id

async def _deny(update: Update) -> None:
    if update.message:
        await update.message.reply_text("⛔ غير مصرح.")
    elif update.callback_query:
        await update.callback_query.answer("⛔ غير مصرح.", show_alert=True)

# ── Keyboards ──────────────────────────────────────────────────────────────────
def _kb_main(is_running: bool) -> InlineKeyboardMarkup:
    run_btn = (
        InlineKeyboardButton("⏹️ إيقاف البوت",   callback_data="action:stop")
        if is_running else
        InlineKeyboardButton("▶️ تشغيل البوت",   callback_data="action:start")
    )
    return InlineKeyboardMarkup([
        [run_btn],
        [
            InlineKeyboardButton("📊 حالة المحفظة",    callback_data="action:status"),
            InlineKeyboardButton("🔄 إعادة توازن",     callback_data="action:rebalance"),
        ],
        [
            InlineKeyboardButton("📋 المحافظ",          callback_data="action:portfolios"),
            InlineKeyboardButton("📜 آخر العمليات",     callback_data="action:history"),
        ],
    ])

def _kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="action:menu")]])

def _kb_portfolios(portfolios: list) -> InlineKeyboardMarkup:
    rows = []
    for p in portfolios:
        pid   = p["id"]
        name  = p.get("config", {}).get("bot", {}).get("name", f"محفظة {pid}")
        run   = p.get("running", False)
        icon  = "🟢" if run else "⚫"
        rows.append([InlineKeyboardButton(f"{icon} {name}", callback_data=f"portfolio:{pid}")])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="action:menu")])
    return InlineKeyboardMarkup(rows)

def _kb_portfolio_actions(pid: int, running: bool) -> InlineKeyboardMarkup:
    toggle = (
        InlineKeyboardButton("⏹️ إيقاف",    callback_data=f"paction:stop:{pid}")
        if running else
        InlineKeyboardButton("▶️ تشغيل",    callback_data=f"paction:start:{pid}")
    )
    return InlineKeyboardMarkup([
        [toggle, InlineKeyboardButton("🔄 إعادة توازن", callback_data=f"paction:rebalance:{pid}")],
        [InlineKeyboardButton("🔙 رجوع للمحافظ", callback_data="action:portfolios")],
    ])

# ── Helpers ────────────────────────────────────────────────────────────────────
async def _edit(query, text: str, kb: InlineKeyboardMarkup) -> None:
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

def _fmt_status(data: dict) -> str:
    assets = data.get("assets", [])
    pnl    = data.get("pnl", {})
    mode_map = {"proportional": "نسبي", "timed": "مجدول", "unbalanced": "يدوي"}
    mode = mode_map.get(data.get("mode", ""), data.get("mode", "—"))
    paper = " 🧪 ورقي" if data.get("paper_trading") else ""

    lines = [
        f"📊 *{data.get('bot_name', 'المحفظة')}*{paper}\n",
        f"💰 القيمة الإجمالية: `{data.get('total_usdt', 0):.2f} USDT`",
        f"📈 الربح: `{pnl.get('pnl_usdt', 0):+.2f} USDT` (`{pnl.get('pnl_pct', 0):+.2f}%`)",
        f"⚙️ الوضع: `{mode}`",
        "",
        "*الأصول:*",
    ]
    for a in assets:
        dev = a.get("deviation", 0)
        icon = "🔴" if abs(dev) >= 5 else "🟡" if abs(dev) >= 2 else "🟢"
        lines.append(
            f"{icon} `{a['symbol']}` — "
            f"فعلي: `{a.get('actual_pct', 0):.1f}%` | "
            f"هدف: `{a.get('target_pct', 0):.1f}%` | "
            f"انحراف: `{dev:+.1f}%`"
        )
    if data.get("warning"):
        lines.append(f"\n⚠️ _{data['warning']}_")
    return "\n".join(lines)

def _fmt_history(history: list) -> str:
    if not history:
        return "📜 لا توجد عمليات بعد."
    lines = ["📜 *آخر العمليات:*\n"]
    for h in history[:10]:
        action = h.get("action", "")
        symbol = h.get("symbol", "")
        amount = h.get("amount_usdt", h.get("diff_usdt", 0))
        ts     = str(h.get("timestamp", h.get("created_at", "")))[:16]
        icon   = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "⚪"
        lines.append(f"{icon} `{symbol}` {action} `{amount:+.2f}$` — {ts}")
    return "\n".join(lines)

# ── Handlers ───────────────────────────────────────────────────────────────────
# Injected functions from api/main.py
_get_status:      Callable = lambda: {}
_start_fn:        Callable = lambda pid: None
_stop_fn:         Callable = lambda pid: None
_rebalance_fn:    Callable = lambda pid: []
_list_portfolios: Callable = lambda: []
_is_running_fn:   Callable = lambda pid: False
_get_history_fn:  Callable = lambda limit, portfolio_id: []
_get_portfolio_fn:Callable = lambda pid: None


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return await _deny(update)
    running = any(p.get("running") for p in _list_portfolios())
    await update.message.reply_text(
        "🤖 *MEXC Portfolio Rebalancer*\n\nاختر من القائمة:",
        reply_markup=_kb_main(running),
        parse_mode=ParseMode.MARKDOWN,
    )


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not _allowed(update):
        return await _deny(update)

    data = query.data

    # ── Main menu ──────────────────────────────────────────────────────────────
    if data == "action:menu":
        running = any(p.get("running") for p in _list_portfolios())
        await _edit(query, "🤖 *MEXC Portfolio Rebalancer*\n\nاختر من القائمة:", _kb_main(running))

    elif data == "action:start":
        portfolios = _list_portfolios()
        active = next((p for p in portfolios if p.get("active")), portfolios[0] if portfolios else None)
        if not active:
            await query.answer("لا توجد محافظ.", show_alert=True)
            return
        pid = active["id"]
        if _is_running_fn(pid):
            await query.answer("البوت شغال بالفعل.", show_alert=True)
            return
        _start_fn(pid)
        await _edit(query, "✅ *البوت بدأ بنجاح!*", _kb_main(True))

    elif data == "action:stop":
        portfolios = _list_portfolios()
        for p in portfolios:
            if p.get("running"):
                _stop_fn(p["id"])
        await _edit(query, "⏹️ *البوت أُوقف.*", _kb_main(False))

    elif data == "action:status":
        try:
            status = _get_status()
            await _edit(query, _fmt_status(status), _kb_back())
        except Exception as e:
            await _edit(query, f"❌ خطأ: `{e}`", _kb_back())

    elif data == "action:rebalance":
        portfolios = _list_portfolios()
        active = next((p for p in portfolios if p.get("active")), portfolios[0] if portfolios else None)
        if not active:
            await query.answer("لا توجد محافظ.", show_alert=True)
            return
        pid = active["id"]
        await _edit(query, "⏳ *جاري إعادة التوازن...*", _kb_back())
        try:
            result = _rebalance_fn(pid)
            trades = [r for r in result if r.get("action") in ("BUY", "SELL")]
            if trades:
                lines = ["✅ *تمت إعادة التوازن:*\n"]
                for r in trades:
                    icon = "🟢" if r["action"] == "BUY" else "🔴"
                    lines.append(f"{icon} `{r['symbol']}` {r['action']} `{r.get('diff_usdt', 0):+.2f}$`")
                await _edit(query, "\n".join(lines), _kb_back())
            else:
                await _edit(query, "✅ *المحفظة متوازنة — لا توجد تعديلات مطلوبة.*", _kb_back())
        except Exception as e:
            await _edit(query, f"❌ فشلت إعادة التوازن: `{e}`", _kb_back())

    elif data == "action:history":
        portfolios = _list_portfolios()
        active = next((p for p in portfolios if p.get("active")), portfolios[0] if portfolios else None)
        pid = active["id"] if active else 1
        history = _get_history_fn(10, portfolio_id=pid)
        await _edit(query, _fmt_history(history), _kb_back())

    elif data == "action:portfolios":
        portfolios = _list_portfolios()
        if not portfolios:
            await _edit(query, "📋 لا توجد محافظ محفوظة.", _kb_back())
            return
        await _edit(query, "📋 *المحافظ:*\n\nاختر محفظة للتفاصيل:", _kb_portfolios(portfolios))

    # ── Portfolio detail ───────────────────────────────────────────────────────
    elif data.startswith("portfolio:"):
        pid = int(data.split(":")[1])
        cfg = _get_portfolio_fn(pid)
        if not cfg:
            await query.answer("المحفظة غير موجودة.", show_alert=True)
            return
        running = _is_running_fn(pid)
        name    = cfg.get("bot", {}).get("name", f"محفظة {pid}")
        mode_map = {"proportional": "نسبي", "timed": "مجدول", "unbalanced": "يدوي"}
        mode    = mode_map.get(cfg.get("rebalance", {}).get("mode", ""), "—")
        assets  = cfg.get("portfolio", {}).get("assets", [])
        asset_lines = "\n".join(f"  • `{a['symbol']}` — `{a['allocation_pct']}%`" for a in assets)
        status_icon = "🟢 شغالة" if running else "⚫ موقوفة"
        text = (
            f"📋 *{name}*\n\n"
            f"الحالة: {status_icon}\n"
            f"الوضع: `{mode}`\n\n"
            f"*الأصول:*\n{asset_lines}"
        )
        await _edit(query, text, _kb_portfolio_actions(pid, running))

    # ── Portfolio actions ──────────────────────────────────────────────────────
    elif data.startswith("paction:"):
        _, action, pid_str = data.split(":")
        pid = int(pid_str)

        if action == "start":
            if _is_running_fn(pid):
                await query.answer("المحفظة شغالة بالفعل.", show_alert=True)
                return
            _start_fn(pid)
            await query.answer("✅ بدأت المحفظة.")
            cfg = _get_portfolio_fn(pid)
            await _edit(query,
                f"✅ *محفظة {pid} بدأت*",
                _kb_portfolio_actions(pid, True))

        elif action == "stop":
            _stop_fn(pid)
            await query.answer("⏹️ أُوقفت المحفظة.")
            await _edit(query,
                f"⏹️ *محفظة {pid} أُوقفت*",
                _kb_portfolio_actions(pid, False))

        elif action == "rebalance":
            await _edit(query, f"⏳ *جاري إعادة توازن محفظة {pid}...*", _kb_back())
            try:
                result = _rebalance_fn(pid)
                trades = [r for r in result if r.get("action") in ("BUY", "SELL")]
                if trades:
                    lines = [f"✅ *إعادة توازن محفظة {pid}:*\n"]
                    for r in trades:
                        icon = "🟢" if r["action"] == "BUY" else "🔴"
                        lines.append(f"{icon} `{r['symbol']}` {r['action']} `{r.get('diff_usdt', 0):+.2f}$`")
                    await _edit(query, "\n".join(lines), _kb_portfolio_actions(pid, _is_running_fn(pid)))
                else:
                    await _edit(query, f"✅ *محفظة {pid} متوازنة.*", _kb_portfolio_actions(pid, _is_running_fn(pid)))
            except Exception as e:
                await _edit(query, f"❌ فشل: `{e}`", _kb_back())


# ── Entry point ────────────────────────────────────────────────────────────────
def run_bot(
    get_status_fn: Callable,
    start_fn: Callable,
    stop_fn: Callable,
    rebalance_fn: Callable,
    list_portfolios_fn: Callable,
    is_running_fn: Callable,
    get_history_fn: Callable,
    get_portfolio_fn: Callable,
) -> None:
    global _get_status, _start_fn, _stop_fn, _rebalance_fn
    global _list_portfolios, _is_running_fn, _get_history_fn, _get_portfolio_fn

    _get_status       = get_status_fn
    _start_fn         = start_fn
    _stop_fn          = stop_fn
    _rebalance_fn     = rebalance_fn
    _list_portfolios  = list_portfolios_fn
    _is_running_fn    = is_running_fn
    _get_history_fn   = get_history_fn
    _get_portfolio_fn = get_portfolio_fn

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        log.warning("TELEGRAM_BOT_TOKEN not set — bot disabled")
        return

    import asyncio

    async def _main():
        app = Application.builder().token(token).build()
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("menu",  cmd_start))
        app.add_handler(CallbackQueryHandler(handle_callback))
        log.info("Telegram bot polling started")
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        # Run forever
        import signal
        stop = asyncio.Event()
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:
                pass
        await stop.wait()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

    asyncio.run(_main())
