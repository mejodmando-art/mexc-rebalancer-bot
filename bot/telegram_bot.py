"""
Telegram bot — Arabic inline-keyboard interface for the MEXC Rebalancer.

Commands
--------
/start  /menu  — main menu
/done         — finalise bot creation wizard
"""
from __future__ import annotations

import logging
import os
from typing import Callable

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
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

# ── Injected functions ─────────────────────────────────────────────────────────
_start_fn:         Callable = lambda pid: None
_stop_fn:          Callable = lambda pid: None
_rebalance_fn:     Callable = lambda pid: []
_list_portfolios:  Callable = lambda: []
_is_running_fn:    Callable = lambda pid: False
_get_portfolio_fn: Callable = lambda pid: None
_save_portfolio_fn:Callable = lambda name, cfg: None
_buy_fn:           Callable = lambda symbol, usdt: {}
_sell_fn:          Callable = lambda symbol, amount: {}
_get_balances_fn:  Callable = lambda: {}

# ── Keyboards ──────────────────────────────────────────────────────────────────
def _kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ إنشاء بوت",   callback_data="action:create_bot"),
            InlineKeyboardButton("📋 المحافظ",      callback_data="action:portfolios"),
        ],
        [
            InlineKeyboardButton("💰 الرصيد العام", callback_data="action:balance_all"),
        ],
    ])

def _kb_back(target: str = "action:menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=target)]])

def _kb_portfolios(portfolios: list) -> InlineKeyboardMarkup:
    rows = []
    for p in portfolios:
        pid  = p["id"]
        name = p.get("name", f"محفظة {pid}")
        icon = "🟢" if p.get("running") else "⚫"
        rows.append([InlineKeyboardButton(f"{icon} {name}", callback_data=f"portfolio:{pid}")])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="action:menu")])
    return InlineKeyboardMarkup(rows)

def _kb_portfolio_detail(pid: int, running: bool) -> InlineKeyboardMarkup:
    toggle = (
        InlineKeyboardButton("⏹️ إيقاف",  callback_data=f"paction:stop:{pid}")
        if running else
        InlineKeyboardButton("▶️ تشغيل",  callback_data=f"paction:start:{pid}")
    )
    return InlineKeyboardMarkup([
        [toggle,
         InlineKeyboardButton("🔄 إعادة توازن", callback_data=f"paction:rebalance:{pid}")],
        [
            InlineKeyboardButton("🟢 شراء",       callback_data=f"paction:buy:{pid}"),
            InlineKeyboardButton("🔴 بيع",         callback_data=f"paction:sell:{pid}"),
        ],
        [InlineKeyboardButton("💼 رصيد المحفظة",  callback_data=f"paction:balance:{pid}")],
        [InlineKeyboardButton("🔙 رجوع للمحافظ",  callback_data="action:portfolios")],
    ])

def _kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="action:menu")]])

# ── Formatters ─────────────────────────────────────────────────────────────────
def _fmt_portfolio_balance(pid: int) -> str:
    cfg = _get_portfolio_fn(pid)
    if not cfg:
        return "❌ المحفظة غير موجودة."
    assets = cfg.get("portfolio", {}).get("assets", [])
    if not assets:
        return "⚠️ لا توجد عملات في هذه المحفظة."
    try:
        balances = _get_balances_fn()
    except Exception as e:
        return f"❌ خطأ في جلب الأرصدة: `{e}`"
    name = cfg.get("bot", {}).get("name", f"محفظة {pid}")
    lines = [f"💼 *رصيد {name}:*\n"]
    total = 0.0
    from mexc_client import MEXCClient
    client = MEXCClient()
    for a in assets:
        sym = a["symbol"].upper()
        bal = balances.get(sym, 0.0)
        try:
            price = 1.0 if sym == "USDT" else client.get_price(f"{sym}USDT")
        except Exception:
            price = 0.0
        val = bal * price
        total += val
        lines.append(f"• `{sym}`: `{bal:.6f}` ≈ `{val:.2f} USDT`")
    lines.append(f"\n💰 *الإجمالي:* `{total:.2f} USDT`")
    return "\n".join(lines)

def _fmt_all_balances() -> str:
    try:
        balances = _get_balances_fn()
    except Exception as e:
        return f"❌ خطأ: `{e}`"
    non_zero = {s: b for s, b in balances.items() if b > 0}
    if not non_zero:
        return "💼 لا توجد أرصدة."
    from mexc_client import MEXCClient
    client = MEXCClient()
    lines = ["💰 *الرصيد العام:*\n"]
    total = 0.0
    for sym, bal in sorted(non_zero.items()):
        try:
            price = 1.0 if sym == "USDT" else client.get_price(f"{sym}USDT")
        except Exception:
            price = 0.0
        val = bal * price
        total += val
        lines.append(f"• `{sym}`: `{bal:.6f}` ≈ `{val:.2f} USDT`")
    lines.append(f"\n💰 *الإجمالي:* `{total:.2f} USDT`")
    return "\n".join(lines)

# ── Helpers ────────────────────────────────────────────────────────────────────
async def _edit(query, text: str, kb: InlineKeyboardMarkup) -> None:
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

async def _reply(update: Update, text: str, kb=None) -> None:
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

# ── /start ─────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return await _deny(update)
    ctx.user_data.clear()
    await _reply(update, "🤖 *MEXC Portfolio Rebalancer*\n\nاختر من القائمة:", _kb_main())

# ── Callback handler ───────────────────────────────────────────────────────────
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not _allowed(update):
        return await _deny(update)

    data = query.data

    if data == "action:menu":
        ctx.user_data.clear()
        await _edit(query, "🤖 *MEXC Portfolio Rebalancer*\n\nاختر من القائمة:", _kb_main())

    elif data == "action:create_bot":
        ctx.user_data["state"] = "await_bot_name"
        await _edit(query, "➕ *إنشاء بوت جديد*\n\nأرسل *اسم البوت*:", _kb_cancel())

    elif data == "action:balance_all":
        await _edit(query, "⏳ جاري جلب الأرصدة...", _kb_back())
        text = _fmt_all_balances()
        await _edit(query, text, _kb_back())

    elif data == "action:portfolios":
        portfolios = _list_portfolios()
        if not portfolios:
            await _edit(query, "📋 لا توجد محافظ. أنشئ بوتاً أولاً.", _kb_back())
            return
        for p in portfolios:
            p["running"] = _is_running_fn(p["id"])
        await _edit(query, "📋 *المحافظ:*\n\nاختر محفظة:", _kb_portfolios(portfolios))

    elif data.startswith("portfolio:"):
        pid = int(data.split(":")[1])
        cfg = _get_portfolio_fn(pid)
        if not cfg:
            await query.answer("المحفظة غير موجودة.", show_alert=True)
            return
        running = _is_running_fn(pid)
        name = cfg.get("bot", {}).get("name", f"محفظة {pid}")
        mode_map = {"proportional": "نسبي", "timed": "مجدول", "unbalanced": "يدوي"}
        mode = mode_map.get(cfg.get("rebalance", {}).get("mode", ""), "—")
        assets = cfg.get("portfolio", {}).get("assets", [])
        asset_lines = "\n".join(
            f"  • `{a['symbol']}` — `{a['allocation_pct']}%`" for a in assets
        )
        status_icon = "🟢 شغالة" if running else "⚫ موقوفة"
        text = (
            f"📋 *{name}*\n\n"
            f"الحالة: {status_icon}\n"
            f"الوضع: `{mode}`\n\n"
            f"*الأصول:*\n{asset_lines}"
        )
        await _edit(query, text, _kb_portfolio_detail(pid, running))

    elif data.startswith("paction:"):
        parts  = data.split(":")
        action = parts[1]
        pid    = int(parts[2])

        if action == "start":
            if _is_running_fn(pid):
                await query.answer("المحفظة شغالة بالفعل.", show_alert=True)
                return
            _start_fn(pid)
            await _edit(query, "✅ *البوت بدأ*", _kb_portfolio_detail(pid, True))

        elif action == "stop":
            _stop_fn(pid)
            await _edit(query, "⏹️ *البوت أُوقف*", _kb_portfolio_detail(pid, False))

        elif action == "rebalance":
            await _edit(query, "⏳ *جاري إعادة التوازن...*", _kb_back("action:portfolios"))
            try:
                result = _rebalance_fn(pid)
                trades = [r for r in result if r.get("action") in ("BUY", "SELL")]
                if trades:
                    lines = ["✅ *تمت إعادة التوازن:*\n"]
                    for r in trades:
                        icon = "🟢" if r["action"] == "BUY" else "🔴"
                        lines.append(
                            f"{icon} `{r['symbol']}` {r['action']} `{r.get('diff_usdt', 0):+.2f}$`"
                        )
                    await _edit(query, "\n".join(lines), _kb_portfolio_detail(pid, _is_running_fn(pid)))
                else:
                    await _edit(
                        query,
                        "✅ *المحفظة متوازنة — لا توجد تعديلات.*",
                        _kb_portfolio_detail(pid, _is_running_fn(pid)),
                    )
            except Exception as e:
                await _edit(query, f"❌ فشلت إعادة التوازن: `{e}`", _kb_back("action:portfolios"))

        elif action == "buy":
            ctx.user_data["state"]     = "await_buy_symbol"
            ctx.user_data["trade_pid"] = pid
            cfg = _get_portfolio_fn(pid)
            assets = cfg.get("portfolio", {}).get("assets", []) if cfg else []
            sym_list = "  ".join(f"`{a['symbol']}`" for a in assets) or "—"
            await _edit(
                query,
                f"🟢 *شراء*\n\nعملات المحفظة: {sym_list}\n\n"
                "أرسل: `SYMBOL USDT_AMOUNT`\nمثال: `BTC 50`",
                _kb_cancel(),
            )

        elif action == "sell":
            ctx.user_data["state"]     = "await_sell_symbol"
            ctx.user_data["trade_pid"] = pid
            cfg = _get_portfolio_fn(pid)
            assets = cfg.get("portfolio", {}).get("assets", []) if cfg else []
            sym_list = "  ".join(f"`{a['symbol']}`" for a in assets) or "—"
            await _edit(
                query,
                f"🔴 *بيع*\n\nعملات المحفظة: {sym_list}\n\n"
                "أرسل: `SYMBOL AMOUNT`\nمثال: `BTC 0.001`",
                _kb_cancel(),
            )

        elif action == "balance":
            await _edit(query, "⏳ جاري جلب الرصيد...", _kb_back("action:portfolios"))
            text = _fmt_portfolio_balance(pid)
            await _edit(query, text, _kb_portfolio_detail(pid, _is_running_fn(pid)))


# ── Message handler (wizard steps) ────────────────────────────────────────────
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return await _deny(update)

    state = ctx.user_data.get("state")
    text  = (update.message.text or "").strip()

    # Step 1: bot name
    if state == "await_bot_name":
        if not text:
            await _reply(update, "⚠️ أرسل اسماً صحيحاً.", _kb_cancel())
            return
        ctx.user_data["new_bot_name"]   = text
        ctx.user_data["new_bot_assets"] = []
        ctx.user_data["state"]          = "await_assets"
        await _reply(
            update,
            f"✅ الاسم: *{text}*\n\n"
            "أرسل العملات والنسب:\n"
            "`BTC 40, ETH 30, BNB 30`\n\n"
            "أو عملة في كل رسالة: `BTC 40`\n\n"
            "حتى *20 عملة* — أرسل /done عند الانتهاء.",
            _kb_cancel(),
        )

    # Step 2: assets
    elif state == "await_assets":
        assets: list = ctx.user_data.get("new_bot_assets", [])
        existing_syms = {a["symbol"].upper() for a in assets}
        errors = []

        entries = [e.strip() for e in text.replace(",", " ").split() if e.strip()]
        pairs = []
        i = 0
        while i < len(entries) - 1:
            sym_c = entries[i].upper()
            pct_c = entries[i + 1]
            try:
                float(pct_c)
                pairs.append((sym_c, pct_c))
                i += 2
            except ValueError:
                errors.append(f"تجاهلت `{entries[i]}`")
                i += 1

        for sym, pct_str in pairs:
            try:
                pct = float(pct_str)
            except ValueError:
                errors.append(f"نسبة غير صحيحة: `{pct_str}`")
                continue
            if pct <= 0 or pct > 100:
                errors.append(f"النسبة يجب أن تكون 1-100: `{sym} {pct}`")
                continue
            if sym in existing_syms:
                errors.append(f"`{sym}` مضافة بالفعل")
                continue
            if len(assets) >= 20:
                errors.append("وصلت للحد الأقصى (20 عملة)")
                break
            assets.append({"symbol": sym, "allocation_pct": pct})
            existing_syms.add(sym)

        ctx.user_data["new_bot_assets"] = assets
        total_pct = sum(a["allocation_pct"] for a in assets)
        lines = [f"📋 *العملات المضافة ({len(assets)}/20):*\n"]
        for a in assets:
            lines.append(f"  • `{a['symbol']}` — `{a['allocation_pct']}%`")
        lines.append(f"\n*المجموع:* `{total_pct:.1f}%`")
        if errors:
            lines.append("\n⚠️ " + "\n⚠️ ".join(errors))
        if abs(total_pct - 100) > 0.01:
            lines.append(f"\n_المجموع يجب أن يساوي 100% — حالياً {total_pct:.1f}%_")
        lines.append("\nأرسل /done للحفظ أو أضف المزيد.")
        await _reply(update, "\n".join(lines), _kb_cancel())

    # Trade: buy
    elif state == "await_buy_symbol":
        parts = text.upper().split()
        if len(parts) != 2:
            await _reply(update, "⚠️ الصيغة: `SYMBOL USDT_AMOUNT`\nمثال: `BTC 50`", _kb_cancel())
            return
        sym, amt_str = parts
        try:
            amt = float(amt_str)
            assert amt > 0
        except Exception:
            await _reply(update, "⚠️ المبلغ غير صحيح.", _kb_cancel())
            return
        await _reply(update, f"⏳ جاري شراء `{sym}` بـ `{amt} USDT`...")
        try:
            result = _buy_fn(f"{sym}USDT", amt)
            await _reply(
                update,
                f"✅ *تم الشراء*\n`{sym}` بـ `{amt} USDT`\nOrder ID: `{result.get('orderId', '—')}`",
                _kb_main(),
            )
        except Exception as e:
            await _reply(update, f"❌ فشل الشراء: `{e}`", _kb_main())
        ctx.user_data.clear()

    # Trade: sell
    elif state == "await_sell_symbol":
        parts = text.upper().split()
        if len(parts) != 2:
            await _reply(update, "⚠️ الصيغة: `SYMBOL AMOUNT`\nمثال: `BTC 0.001`", _kb_cancel())
            return
        sym, amt_str = parts
        try:
            amt = float(amt_str)
            assert amt > 0
        except Exception:
            await _reply(update, "⚠️ الكمية غير صحيحة.", _kb_cancel())
            return
        await _reply(update, f"⏳ جاري بيع `{amt}` من `{sym}`...")
        try:
            result = _sell_fn(f"{sym}USDT", amt)
            await _reply(
                update,
                f"✅ *تم البيع*\n`{amt}` من `{sym}`\nOrder ID: `{result.get('orderId', '—')}`",
                _kb_main(),
            )
        except Exception as e:
            await _reply(update, f"❌ فشل البيع: `{e}`", _kb_main())
        ctx.user_data.clear()

    else:
        await _reply(update, "اختر من القائمة:", _kb_main())


# ── /done — finalise bot creation ─────────────────────────────────────────────
async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return await _deny(update)
    if ctx.user_data.get("state") != "await_assets":
        await _reply(update, "لا يوجد شيء لحفظه.", _kb_main())
        return

    assets   = ctx.user_data.get("new_bot_assets", [])
    bot_name = ctx.user_data.get("new_bot_name", "بوت جديد")

    if not assets:
        await _reply(update, "⚠️ أضف عملة واحدة على الأقل.", _kb_cancel())
        return

    total_pct = sum(a["allocation_pct"] for a in assets)
    if abs(total_pct - 100) > 0.01:
        await _reply(
            update,
            f"⚠️ مجموع النسب `{total_pct:.1f}%` — يجب أن يساوي 100%.",
            _kb_cancel(),
        )
        return

    cfg = {
        "bot": {"name": bot_name},
        "portfolio": {
            "assets": assets,
            "total_usdt": 0,
            "initial_value_usdt": 0,
            "allocation_mode": "ai_balance",
        },
        "rebalance": {
            "mode": "proportional",
            "proportional": {
                "threshold_pct": 5,
                "check_interval_minutes": 5,
                "min_deviation_to_execute_pct": 3,
            },
            "timed": {"frequency": "daily", "hour": 10},
            "unbalanced": {},
        },
        "risk": {"stop_loss_pct": None, "take_profit_pct": None},
        "termination": {"sell_at_termination": False},
        "asset_transfer": {"enable_asset_transfer": False},
        "paper_trading": False,
        "last_rebalance": None,
    }

    try:
        pid = _save_portfolio_fn(bot_name, cfg)
        asset_lines = "\n".join(
            f"  • `{a['symbol']}` — `{a['allocation_pct']}%`" for a in assets
        )
        await _reply(
            update,
            f"✅ *تم إنشاء البوت بنجاح!*\n\n"
            f"الاسم: *{bot_name}*\n"
            f"ID: `{pid}`\n\n"
            f"*الأصول:*\n{asset_lines}\n\n"
            "اذهب للمحافظ لتشغيله.",
            _kb_main(),
        )
    except Exception as e:
        await _reply(update, f"❌ فشل الحفظ: `{e}`", _kb_main())

    ctx.user_data.clear()


# ── Entry point ────────────────────────────────────────────────────────────────
def run_bot(
    start_fn:           Callable,
    stop_fn:            Callable,
    rebalance_fn:       Callable,
    list_portfolios_fn: Callable,
    is_running_fn:      Callable,
    get_portfolio_fn:   Callable,
    save_portfolio_fn:  Callable,
    buy_fn:             Callable,
    sell_fn:            Callable,
    get_balances_fn:    Callable,
    # backward-compat — unused
    get_status_fn:      Callable = lambda: {},
    get_history_fn:     Callable = lambda limit, portfolio_id=1: [],
) -> None:
    global _start_fn, _stop_fn, _rebalance_fn, _list_portfolios
    global _is_running_fn, _get_portfolio_fn, _save_portfolio_fn
    global _buy_fn, _sell_fn, _get_balances_fn

    _start_fn          = start_fn
    _stop_fn           = stop_fn
    _rebalance_fn      = rebalance_fn
    _list_portfolios   = list_portfolios_fn
    _is_running_fn     = is_running_fn
    _get_portfolio_fn  = get_portfolio_fn
    _save_portfolio_fn = save_portfolio_fn
    _buy_fn            = buy_fn
    _sell_fn           = sell_fn
    _get_balances_fn   = get_balances_fn

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        log.warning("TELEGRAM_BOT_TOKEN not set — bot disabled")
        return

    import asyncio
    import signal

    async def _main():
        app = Application.builder().token(token).build()
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("menu",  cmd_start))
        app.add_handler(CommandHandler("done",  cmd_done))
        app.add_handler(CallbackQueryHandler(handle_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        log.info("Telegram bot polling started")
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
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
