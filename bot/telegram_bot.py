"""
Telegram bot — Arabic inline-keyboard interface for the MEXC Rebalancer.

Commands
--------
/start  /menu  — main menu
/done         — finalise bot creation wizard (manual allocation mode)
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
_start_fn:            Callable = lambda pid: None
_stop_fn:             Callable = lambda pid: None
_rebalance_fn:        Callable = lambda pid: []
_list_portfolios:     Callable = lambda: []
_is_running_fn:       Callable = lambda pid: False
_get_portfolio_fn:    Callable = lambda pid: None
_save_portfolio_fn:   Callable = lambda name, cfg: None
_update_portfolio_fn: Callable = lambda pid, cfg: None
_buy_fn:              Callable = lambda symbol, usdt: {}
_sell_fn:             Callable = lambda symbol, amount: {}
_get_balances_fn:     Callable = lambda: {}

# ── Keyboards ──────────────────────────────────────────────────────────────────
def _kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ إنشاء بوت",    callback_data="action:create_bot"),
            InlineKeyboardButton("📋 المحافظ",       callback_data="action:portfolios"),
        ],
        [
            InlineKeyboardButton("💰 الرصيد العام",  callback_data="action:balance_all"),
        ],
    ])

def _kb_back(target: str = "action:menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=target)]])

def _kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="action:menu")]])

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
            InlineKeyboardButton("🟢 شراء",        callback_data=f"paction:buy:{pid}"),
            InlineKeyboardButton("🔴 بيع",          callback_data=f"paction:sell:{pid}"),
        ],
        [
            InlineKeyboardButton("🗑️ حذف عملة",    callback_data=f"paction:remove:{pid}"),
            InlineKeyboardButton("🔁 استبدال عملة", callback_data=f"paction:replace:{pid}"),
        ],
        [InlineKeyboardButton("💼 رصيد المحفظة",   callback_data=f"paction:balance:{pid}")],
        [InlineKeyboardButton("🔙 رجوع للمحافظ",   callback_data="action:portfolios")],
    ])

# ── Wizard keyboards ───────────────────────────────────────────────────────────
def _kb_alloc_mode() -> InlineKeyboardMarkup:
    """Step: choose allocation mode after entering symbols."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚖️ متساوي تلقائي", callback_data="wizard:alloc:equal"),
            InlineKeyboardButton("✏️ يدوي",           callback_data="wizard:alloc:manual"),
        ],
        [InlineKeyboardButton("❌ إلغاء", callback_data="action:menu")],
    ])

def _kb_deviation() -> InlineKeyboardMarkup:
    """Step: choose rebalance deviation threshold."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1%",  callback_data="wizard:dev:1"),
            InlineKeyboardButton("3%",  callback_data="wizard:dev:3"),
            InlineKeyboardButton("5%",  callback_data="wizard:dev:5"),
            InlineKeyboardButton("10%", callback_data="wizard:dev:10"),
        ],
        [InlineKeyboardButton("🔢 مخصص", callback_data="wizard:dev:custom")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="action:menu")],
    ])

def _kb_balance_mode() -> InlineKeyboardMarkup:
    """Step: choose how much capital to use."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💯 كل الرصيد",   callback_data="wizard:bal:all"),
            InlineKeyboardButton("💵 مبلغ محدد",   callback_data="wizard:bal:custom"),
        ],
        [InlineKeyboardButton("❌ إلغاء", callback_data="action:menu")],
    ])

def _kb_asset_pick(assets: list, action: str, pid: int) -> InlineKeyboardMarkup:
    """Inline keyboard listing each asset as a button. action: sell|remove|replace."""
    rows = []
    for i in range(0, len(assets), 3):
        row = []
        for a in assets[i:i+3]:
            sym = a["symbol"]
            row.append(InlineKeyboardButton(
                f"{sym}",
                callback_data=f"asset:{action}:{pid}:{sym}",
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton("❌ إلغاء", callback_data=f"portfolio:{pid}")])
    return InlineKeyboardMarkup(rows)

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
    from mexc_client import MEXCClient
    client = MEXCClient()
    lines = [f"💼 *رصيد {name}:*\n"]
    total = 0.0
    for a in assets:
        sym = a["symbol"].upper()
        bal = balances.get(sym, 0.0)
        try:
            price = 1.0 if sym == "USDT" else client.get_price(f"{sym}USDT")
        except Exception:
            price = 0.0
        val = bal * price
        total += val
        if val > 0:
            lines.append(f"• `{sym}`: `{val:.2f} USDT`")
    if len(lines) == 1:
        lines.append("_لا توجد أرصدة._")
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
        lines.append(f"• `{sym}`: `{val:.2f} USDT`")
    lines.append(f"\n💰 *الإجمالي:* `{total:.2f} USDT`")
    return "\n".join(lines)

def _fmt_wizard_summary(ctx: ContextTypes.DEFAULT_TYPE) -> str:
    """Build a readable summary of wizard state so far."""
    ud = ctx.user_data
    name   = ud.get("new_bot_name", "—")
    syms   = ud.get("new_bot_symbols", [])
    mode   = ud.get("alloc_mode", "—")
    dev    = ud.get("deviation_pct")
    bal    = ud.get("balance_mode", "—")
    amount = ud.get("balance_usdt")

    sym_str  = "  ".join(f"`{s}`" for s in syms) if syms else "—"
    mode_str = "⚖️ متساوي تلقائي" if mode == "equal" else "✏️ يدوي"
    dev_str  = f"`{dev}%`" if dev is not None else "—"
    bal_str  = "💯 كل الرصيد" if bal == "all" else (f"💵 `{amount} USDT`" if amount else "—")

    return (
        f"📝 *ملخص البوت:*\n\n"
        f"الاسم: *{name}*\n"
        f"العملات: {sym_str}\n"
        f"التوزيع: {mode_str}\n"
        f"الانحراف: {dev_str}\n"
        f"الرصيد: {bal_str}"
    )

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

    # ── Main menu ──────────────────────────────────────────────────────────────
    if data == "action:menu":
        ctx.user_data.clear()
        await _edit(query, "🤖 *MEXC Portfolio Rebalancer*\n\nاختر من القائمة:", _kb_main())

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

    # ── Wizard: start ──────────────────────────────────────────────────────────
    elif data == "action:create_bot":
        ctx.user_data.clear()
        ctx.user_data["state"] = "wizard_name"
        await _edit(
            query,
            "➕ *إنشاء بوت جديد*\n\n"
            "*الخطوة 1/5* — أرسل *اسم البوت:*",
            _kb_cancel(),
        )

    # ── Wizard: allocation mode ────────────────────────────────────────────────
    elif data == "wizard:alloc:equal":
        ctx.user_data["alloc_mode"] = "equal"
        ctx.user_data["state"]      = "wizard_deviation"
        syms = ctx.user_data.get("new_bot_symbols", [])
        n    = len(syms)
        pct  = round(100 / n, 2) if n else 0
        sym_lines = "\n".join(f"  • `{s}` — `{pct}%`" for s in syms)
        await _edit(
            query,
            f"✅ التوزيع المتساوي: كل عملة `{pct}%`\n\n"
            f"{sym_lines}\n\n"
            "*الخطوة 3/5* — اختر نسبة الانحراف لإعادة التوازن:",
            _kb_deviation(),
        )

    elif data == "wizard:alloc:manual":
        ctx.user_data["alloc_mode"] = "manual"
        ctx.user_data["state"]      = "wizard_manual_alloc"
        syms = ctx.user_data.get("new_bot_symbols", [])
        sym_str = "  ".join(f"`{s}`" for s in syms)
        await _edit(
            query,
            f"✏️ *التوزيع اليدوي*\n\n"
            f"العملات: {sym_str}\n\n"
            "*الخطوة 3/5* — أرسل النسب بالترتيب:\n"
            f"`{' '.join(syms)}`\n"
            "مثال: `40 30 20 10`\n\n"
            "_المجموع يجب أن يساوي 100%_",
            _kb_cancel(),
        )

    # ── Wizard: deviation preset ───────────────────────────────────────────────
    elif data.startswith("wizard:dev:"):
        val = data.split(":")[2]
        if val == "custom":
            ctx.user_data["state"] = "wizard_deviation_custom"
            await _edit(
                query,
                "*الخطوة 3/5* — أرسل نسبة الانحراف المخصصة (مثال: `2.5`):",
                _kb_cancel(),
            )
        else:
            ctx.user_data["deviation_pct"] = float(val)
            ctx.user_data["state"]         = "wizard_balance"
            await _edit(
                query,
                f"✅ الانحراف: `{val}%`\n\n"
                "*الخطوة 4/5* — كيف تريد تحديد رأس المال؟",
                _kb_balance_mode(),
            )

    # ── Wizard: balance mode ───────────────────────────────────────────────────
    elif data == "wizard:bal:all":
        ctx.user_data["balance_mode"] = "all"
        ctx.user_data["balance_usdt"] = 0
        ctx.user_data["state"]        = "wizard_confirm"
        summary = _fmt_wizard_summary(ctx)
        await _edit(
            query,
            f"{summary}\n\n"
            "*الخطوة 5/5* — هل تريد حفظ البوت؟",
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ حفظ",   callback_data="wizard:confirm:yes"),
                    InlineKeyboardButton("❌ إلغاء", callback_data="action:menu"),
                ]
            ]),
        )

    elif data == "wizard:bal:custom":
        ctx.user_data["balance_mode"] = "custom"
        ctx.user_data["state"]        = "wizard_balance_amount"
        await _edit(
            query,
            "*الخطوة 4/5* — أرسل المبلغ بـ USDT (مثال: `500`):",
            _kb_cancel(),
        )

    # ── Wizard: confirm & save ─────────────────────────────────────────────────
    elif data == "wizard:confirm:yes":
        await _wizard_save(query, ctx)

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
        mode     = mode_map.get(cfg.get("rebalance", {}).get("mode", ""), "—")
        assets   = cfg.get("portfolio", {}).get("assets", [])
        asset_lines = "\n".join(
            f"  • `{a['symbol']}` — `{a['allocation_pct']}%`" for a in assets
        )
        dev = (
            cfg.get("rebalance", {})
               .get("proportional", {})
               .get("min_deviation_to_execute_pct", "—")
        )
        status_icon = "🟢 شغالة" if running else "⚫ موقوفة"
        text = (
            f"📋 *{name}*\n\n"
            f"الحالة: {status_icon}\n"
            f"الوضع: `{mode}`\n"
            f"الانحراف: `{dev}%`\n\n"
            f"*الأصول:*\n{asset_lines}"
        )
        await _edit(query, text, _kb_portfolio_detail(pid, running))

    # ── Portfolio actions ──────────────────────────────────────────────────────
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
            cfg    = _get_portfolio_fn(pid)
            assets = cfg.get("portfolio", {}).get("assets", []) if cfg else []
            if not assets:
                await query.answer("لا توجد عملات في المحفظة.", show_alert=True)
                return
            await _edit(
                query,
                "🟢 *شراء — اختر نوع الشراء:*",
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("💰 شراء عملة محددة",   callback_data=f"paction:buy_pick:{pid}"),
                        InlineKeyboardButton("🟢 شراء المحفظة كلها", callback_data=f"paction:buy_all:{pid}"),
                    ],
                    [InlineKeyboardButton("❌ إلغاء", callback_data=f"portfolio:{pid}")],
                ]),
            )

        elif action == "buy_pick":
            cfg    = _get_portfolio_fn(pid)
            assets = cfg.get("portfolio", {}).get("assets", []) if cfg else []
            if not assets:
                await query.answer("لا توجد عملات في المحفظة.", show_alert=True)
                return
            await _edit(
                query,
                "🟢 *شراء عملة — اختر العملة:*",
                _kb_asset_pick(assets, "buy", pid),
            )

        elif action == "buy_all":
            cfg    = _get_portfolio_fn(pid)
            assets = cfg.get("portfolio", {}).get("assets", []) if cfg else []
            sym_list = "\n".join(f"  • `{a['symbol']}` — `{a['allocation_pct']}%`" for a in assets)
            await _edit(
                query,
                f"🟢 *تأكيد شراء المحفظة كلها*\n\n"
                f"سيتم شراء جميع العملات حسب النسب:\n{sym_list}\n\n"
                "هل أنت متأكد؟",
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ تأكيد الشراء الكامل", callback_data=f"confirm:buy_all:{pid}"),
                        InlineKeyboardButton("❌ إلغاء",                callback_data=f"portfolio:{pid}"),
                    ]
                ]),
            )

        elif action == "sell":
            cfg    = _get_portfolio_fn(pid)
            assets = cfg.get("portfolio", {}).get("assets", []) if cfg else []
            if not assets:
                await query.answer("لا توجد عملات في المحفظة.", show_alert=True)
                return
            await _edit(
                query,
                "🔴 *بيع — اختر نوع البيع:*",
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("💰 بيع عملة محددة", callback_data=f"paction:sell_pick:{pid}"),
                        InlineKeyboardButton("🔴 بيع المحفظة كلها", callback_data=f"paction:sell_all:{pid}"),
                    ],
                    [InlineKeyboardButton("❌ إلغاء", callback_data=f"portfolio:{pid}")],
                ]),
            )

        elif action == "sell_pick":
            cfg    = _get_portfolio_fn(pid)
            assets = cfg.get("portfolio", {}).get("assets", []) if cfg else []
            if not assets:
                await query.answer("لا توجد عملات في المحفظة.", show_alert=True)
                return
            await _edit(
                query,
                "🔴 *بيع عملة — اختر العملة:*",
                _kb_asset_pick(assets, "sell", pid),
            )

        elif action == "sell_all":
            cfg    = _get_portfolio_fn(pid)
            assets = cfg.get("portfolio", {}).get("assets", []) if cfg else []
            if not assets:
                await query.answer("لا توجد عملات في المحفظة.", show_alert=True)
                return
            sym_list = "\n".join(f"  • `{a['symbol']}`" for a in assets)
            await _edit(
                query,
                f"⚠️ *تأكيد بيع المحفظة كلها*\n\n"
                f"سيتم بيع جميع العملات:\n{sym_list}\n\n"
                "هل أنت متأكد؟",
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ تأكيد البيع الكامل", callback_data=f"confirm:sell_all:{pid}"),
                        InlineKeyboardButton("❌ إلغاء",               callback_data=f"portfolio:{pid}"),
                    ]
                ]),
            )

        elif action == "remove":
            cfg    = _get_portfolio_fn(pid)
            assets = cfg.get("portfolio", {}).get("assets", []) if cfg else []
            if not assets:
                await query.answer("لا توجد عملات في المحفظة.", show_alert=True)
                return
            await _edit(
                query,
                "🗑️ *حذف عملة — اختر العملة التي تريد حذفها:*",
                _kb_asset_pick(assets, "remove", pid),
            )

        elif action == "replace":
            cfg    = _get_portfolio_fn(pid)
            assets = cfg.get("portfolio", {}).get("assets", []) if cfg else []
            if not assets:
                await query.answer("لا توجد عملات في المحفظة.", show_alert=True)
                return
            await _edit(
                query,
                "🔁 *استبدال عملة — اختر العملة التي تريد استبدالها:*",
                _kb_asset_pick(assets, "replace", pid),
            )

        elif action == "balance":
            await _edit(query, "⏳ جاري جلب الرصيد...", _kb_back("action:portfolios"))
            text = _fmt_portfolio_balance(pid)
            await _edit(query, text, _kb_portfolio_detail(pid, _is_running_fn(pid)))

    # ── Asset picker result ────────────────────────────────────────────────────
    # callback_data = "asset:{action}:{pid}:{sym}"
    elif data.startswith("asset:"):
        _, act, pid_str, sym = data.split(":", 3)
        pid = int(pid_str)

        if act == "buy":
            ctx.user_data["state"]      = "await_buy_amount"
            ctx.user_data["trade_pid"]  = pid
            ctx.user_data["trade_sym"]  = sym
            await _edit(
                query,
                f"🟢 *شراء `{sym}`*\n\nأرسل المبلغ بـ USDT:\nمثال: `50`",
                _kb_back(f"paction:buy:{pid}"),
            )

        elif act == "sell":
            ctx.user_data["state"]      = "await_sell_amount"
            ctx.user_data["trade_pid"]  = pid
            ctx.user_data["trade_sym"]  = sym
            await _edit(
                query,
                f"🔴 *بيع `{sym}`*\n\nأرسل الكمية:\nمثال: `0.001`",
                _kb_back(f"paction:sell:{pid}"),
            )

        elif act == "remove":
            ctx.user_data["state"]         = "confirm_remove"
            ctx.user_data["trade_pid"]     = pid
            ctx.user_data["trade_sym"]     = sym
            await _edit(
                query,
                f"🗑️ هل تريد حذف `{sym}` من المحفظة؟\n\n"
                "⚠️ سيتم إعادة توزيع النسب تلقائياً على باقي العملات.",
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ تأكيد الحذف", callback_data=f"confirm:remove:{pid}:{sym}"),
                        InlineKeyboardButton("❌ إلغاء",        callback_data=f"portfolio:{pid}"),
                    ]
                ]),
            )

        elif act == "replace":
            ctx.user_data["state"]         = "await_replace_new"
            ctx.user_data["trade_pid"]     = pid
            ctx.user_data["trade_sym"]     = sym
            await _edit(
                query,
                f"🔁 *استبدال `{sym}`*\n\nأرسل رمز العملة الجديدة:\nمثال: `ADA`",
                _kb_back(f"paction:replace:{pid}"),
            )

    # ── Confirm sell all ───────────────────────────────────────────────────────
    elif data.startswith("confirm:sell_all:"):
        pid = int(data.split(":")[2])
        cfg = _get_portfolio_fn(pid)
        if not cfg:
            await query.answer("المحفظة غير موجودة.", show_alert=True)
            return
        assets = cfg.get("portfolio", {}).get("assets", [])
        await _edit(query, "⏳ *جاري بيع المحفظة كلها...*", _kb_back(f"portfolio:{pid}"))
        results, errors = [], []
        try:
            balances = _get_balances_fn()
        except Exception as e:
            await _edit(query, f"❌ فشل جلب الأرصدة: `{e}`", _kb_portfolio_detail(pid, _is_running_fn(pid)))
            return
        for a in assets:
            sym = a["symbol"].upper()
            if sym == "USDT":
                continue
            bal = balances.get(sym, 0.0)
            if bal <= 0:
                continue
            try:
                res = _sell_fn(f"{sym}USDT", bal)
                results.append(f"🔴 `{sym}` — Order ID: `{res.get('orderId', '—')}`")
            except Exception as e:
                errors.append(f"❌ `{sym}`: `{e}`")
        lines = ["✅ *تم بيع المحفظة:*\n"] + results
        if errors:
            lines += ["\n⚠️ *أخطاء:*"] + errors
        if not results and not errors:
            lines = ["ℹ️ لا توجد أرصدة للبيع."]
        await _edit(query, "\n".join(lines), _kb_portfolio_detail(pid, _is_running_fn(pid)))

    # ── Confirm buy all ────────────────────────────────────────────────────────
    elif data.startswith("confirm:buy_all:"):
        pid = int(data.split(":")[2])
        cfg = _get_portfolio_fn(pid)
        if not cfg:
            await query.answer("المحفظة غير موجودة.", show_alert=True)
            return
        await _edit(query, "⏳ *جاري شراء المحفظة كلها...*", _kb_back(f"portfolio:{pid}"))
        try:
            cfg["buy_enabled"] = True
            result = _rebalance_fn(pid)
            trades = [r for r in result if r.get("action") == "BUY"]
            if trades:
                lines = ["✅ *تم الشراء:*\n"]
                for r in trades:
                    lines.append(f"🟢 `{r['symbol']}` — `{r.get('diff_usdt', 0):.2f} USDT`")
            else:
                lines = ["ℹ️ لا توجد عملات تحتاج شراء حالياً."]
        except Exception as e:
            lines = [f"❌ فشل الشراء: `{e}`"]
        await _edit(query, "\n".join(lines), _kb_portfolio_detail(pid, _is_running_fn(pid)))

    # ── Confirm remove ─────────────────────────────────────────────────────────
    elif data.startswith("confirm:remove:"):
        _, _, pid_str, sym = data.split(":", 3)
        pid = int(pid_str)
        cfg = _get_portfolio_fn(pid)
        if not cfg:
            await query.answer("المحفظة غير موجودة.", show_alert=True)
            return
        assets = cfg.get("portfolio", {}).get("assets", [])
        assets = [a for a in assets if a["symbol"].upper() != sym.upper()]
        if not assets:
            await _edit(query, "⚠️ لا يمكن حذف العملة الوحيدة في المحفظة.", _kb_portfolio_detail(pid, _is_running_fn(pid)))
            return
        # Redistribute allocations equally among remaining assets
        pct = round(100 / len(assets), 4)
        for a in assets:
            a["allocation_pct"] = pct
        diff = round(100 - sum(a["allocation_pct"] for a in assets), 4)
        assets[-1]["allocation_pct"] = round(assets[-1]["allocation_pct"] + diff, 4)
        cfg["portfolio"]["assets"] = assets
        try:
            _update_portfolio_fn(pid, cfg)
            asset_lines = "\n".join(f"  • `{a['symbol']}` — `{a['allocation_pct']}%`" for a in assets)
            await _edit(
                query,
                f"✅ *تم حذف `{sym}` وإعادة توزيع النسب:*\n\n{asset_lines}",
                _kb_portfolio_detail(pid, _is_running_fn(pid)),
            )
        except Exception as e:
            await _edit(query, f"❌ فشل الحذف: `{e}`", _kb_portfolio_detail(pid, _is_running_fn(pid)))

# ── Wizard save helper ─────────────────────────────────────────────────────────
async def _wizard_save(query, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ud       = ctx.user_data
    bot_name = ud.get("new_bot_name", "بوت جديد")
    syms     = ud.get("new_bot_symbols", [])
    mode     = ud.get("alloc_mode", "equal")
    dev      = ud.get("deviation_pct", 3.0)
    bal_mode = ud.get("balance_mode", "all")
    amount   = ud.get("balance_usdt", 0)

    if not syms:
        await _edit(query, "⚠️ لا توجد عملات.", _kb_cancel())
        return

    # Build assets list
    if mode == "equal":
        pct = round(100 / len(syms), 4)
        assets = [{"symbol": s, "allocation_pct": pct} for s in syms]
        # Adjust last to ensure sum == 100
        diff = 100 - sum(a["allocation_pct"] for a in assets)
        assets[-1]["allocation_pct"] = round(assets[-1]["allocation_pct"] + diff, 4)
    else:
        assets = ud.get("new_bot_assets", [])

    cfg = {
        "bot": {"name": bot_name},
        "portfolio": {
            "assets": assets,
            "total_usdt": amount,
            "initial_value_usdt": 0,
            "allocation_mode": "equal" if mode == "equal" else "manual",
        },
        "rebalance": {
            "mode": "proportional",
            "proportional": {
                "threshold_pct": dev,
                "check_interval_minutes": 5,
                "min_deviation_to_execute_pct": dev,
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
        bal_str = "💯 كل الرصيد" if bal_mode == "all" else f"💵 `{amount} USDT`"
        await _edit(
            query,
            f"✅ *تم إنشاء البوت بنجاح!*\n\n"
            f"الاسم: *{bot_name}*\n"
            f"ID: `{pid}`\n"
            f"الانحراف: `{dev}%`\n"
            f"الرصيد: {bal_str}\n\n"
            f"*الأصول:*\n{asset_lines}\n\n"
            "اذهب للمحافظ لتشغيله.",
            _kb_main(),
        )
    except Exception as e:
        await _edit(query, f"❌ فشل الحفظ: `{e}`", _kb_main())

    ctx.user_data.clear()


# ── Message handler (wizard + trade steps) ────────────────────────────────────
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return await _deny(update)

    state = ctx.user_data.get("state", "")
    text  = (update.message.text or "").strip()

    # ── Wizard step 1: bot name ────────────────────────────────────────────────
    if state == "wizard_name":
        if not text:
            await _reply(update, "⚠️ أرسل اسماً صحيحاً.", _kb_cancel())
            return
        ctx.user_data["new_bot_name"] = text
        ctx.user_data["state"]        = "wizard_symbols"
        await _reply(
            update,
            f"✅ الاسم: *{text}*\n\n"
            "*الخطوة 2/5* — أرسل العملات بدون نسب:\n"
            "`BTC ETH BNB SOL`\n\n"
            "_يمكنك إرسالها في رسالة واحدة أو عدة رسائل — أرسل /done عند الانتهاء_",
            _kb_cancel(),
        )

    # ── Wizard step 2: symbols ─────────────────────────────────────────────────
    elif state == "wizard_symbols":
        syms: list = ctx.user_data.setdefault("new_bot_symbols", [])
        existing   = {s.upper() for s in syms}
        added, skipped = [], []

        for token in text.replace(",", " ").upper().split():
            sym = token.strip()
            if not sym:
                continue
            if sym in existing:
                skipped.append(sym)
            elif len(syms) >= 20:
                skipped.append(f"{sym} (الحد 20)")
            else:
                syms.append(sym)
                existing.add(sym)
                added.append(sym)

        ctx.user_data["new_bot_symbols"] = syms
        sym_str = "  ".join(f"`{s}`" for s in syms)
        lines   = [f"📋 *العملات ({len(syms)}/20):*\n{sym_str}"]
        if skipped:
            lines.append(f"\n⚠️ تجاهلت: {' '.join(skipped)}")
        lines.append("\nأضف المزيد أو أرسل /done للمتابعة.")
        await _reply(update, "\n".join(lines), _kb_cancel())

    # ── Wizard step 3a: manual allocation ─────────────────────────────────────
    elif state == "wizard_manual_alloc":
        syms  = ctx.user_data.get("new_bot_symbols", [])
        parts = text.replace(",", " ").split()
        if len(parts) != len(syms):
            await _reply(
                update,
                f"⚠️ أرسل {len(syms)} أرقام بالترتيب.\n"
                f"العملات: {' '.join(syms)}\n"
                "مثال: `40 30 20 10`",
                _kb_cancel(),
            )
            return
        try:
            pcts = [float(p) for p in parts]
        except ValueError:
            await _reply(update, "⚠️ أرقام غير صحيحة.", _kb_cancel())
            return
        if any(p <= 0 for p in pcts):
            await _reply(update, "⚠️ كل نسبة يجب أن تكون أكبر من 0.", _kb_cancel())
            return
        total = sum(pcts)
        if abs(total - 100) > 0.01:
            await _reply(update, f"⚠️ المجموع `{total:.1f}%` — يجب أن يساوي 100%.", _kb_cancel())
            return
        assets = [{"symbol": s, "allocation_pct": p} for s, p in zip(syms, pcts)]
        ctx.user_data["new_bot_assets"] = assets
        ctx.user_data["state"]          = "wizard_deviation"
        lines = ["✅ *التوزيع:*\n"]
        for a in assets:
            lines.append(f"  • `{a['symbol']}` — `{a['allocation_pct']}%`")
        lines.append("\n*الخطوة 3/5* — اختر نسبة الانحراف:")
        await _reply(update, "\n".join(lines), _kb_deviation())

    # ── Wizard step 3b: custom deviation ──────────────────────────────────────
    elif state == "wizard_deviation_custom":
        try:
            dev = float(text)
            assert 0 < dev <= 50
        except Exception:
            await _reply(update, "⚠️ أرسل رقماً بين 0.1 و 50.", _kb_cancel())
            return
        ctx.user_data["deviation_pct"] = dev
        ctx.user_data["state"]         = "wizard_balance"
        await _reply(
            update,
            f"✅ الانحراف: `{dev}%`\n\n"
            "*الخطوة 4/5* — كيف تريد تحديد رأس المال؟",
            _kb_balance_mode(),
        )

    # ── Wizard step 4: custom balance amount ──────────────────────────────────
    elif state == "wizard_balance_amount":
        try:
            amount = float(text)
            assert amount > 0
        except Exception:
            await _reply(update, "⚠️ أرسل مبلغاً صحيحاً (مثال: `500`).", _kb_cancel())
            return
        ctx.user_data["balance_usdt"] = amount
        ctx.user_data["state"]        = "wizard_confirm"
        summary = _fmt_wizard_summary(ctx)
        await _reply(
            update,
            f"{summary}\n\n"
            "*الخطوة 5/5* — هل تريد حفظ البوت؟",
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ حفظ",   callback_data="wizard:confirm:yes"),
                    InlineKeyboardButton("❌ إلغاء", callback_data="action:menu"),
                ]
            ]),
        )

    # ── Trade: buy amount (after symbol chosen via button) ────────────────────
    elif state == "await_buy_amount":
        sym = ctx.user_data.get("trade_sym", "")
        try:
            amt = float(text)
            assert amt > 0
        except Exception:
            await _reply(update, "⚠️ أرسل مبلغاً صحيحاً بـ USDT (مثال: `50`).", _kb_cancel())
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

    # ── Trade: sell amount (after symbol chosen via button) ───────────────────
    elif state == "await_sell_amount":
        sym = ctx.user_data.get("trade_sym", "")
        try:
            amt = float(text)
            assert amt > 0
        except Exception:
            await _reply(update, "⚠️ أرسل كمية صحيحة (مثال: `0.001`).", _kb_cancel())
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

    # ── Replace: new symbol ────────────────────────────────────────────────────
    elif state == "await_replace_new":
        new_sym = text.upper().strip()
        pid     = ctx.user_data.get("trade_pid")
        old_sym = ctx.user_data.get("trade_sym", "")
        if not new_sym.isalpha():
            await _reply(update, "⚠️ أرسل رمز عملة صحيح (مثال: `ADA`).", _kb_cancel())
            return
        cfg = _get_portfolio_fn(pid)
        if not cfg:
            await _reply(update, "❌ المحفظة غير موجودة.", _kb_main())
            ctx.user_data.clear()
            return
        assets = cfg.get("portfolio", {}).get("assets", [])
        existing = [a["symbol"].upper() for a in assets]
        if new_sym in existing:
            await _reply(update, f"⚠️ `{new_sym}` موجودة بالفعل في المحفظة.", _kb_cancel())
            return
        for a in assets:
            if a["symbol"].upper() == old_sym.upper():
                a["symbol"] = new_sym
                break
        cfg["portfolio"]["assets"] = assets
        try:
            _update_portfolio_fn(pid, cfg)
            asset_lines = "\n".join(f"  • `{a['symbol']}` — `{a['allocation_pct']}%`" for a in assets)
            await _reply(
                update,
                f"✅ *تم استبدال `{old_sym}` بـ `{new_sym}`:*\n\n{asset_lines}",
                _kb_main(),
            )
        except Exception as e:
            await _reply(update, f"❌ فشل الاستبدال: `{e}`", _kb_main())
        ctx.user_data.clear()

    else:
        await _reply(update, "اختر من القائمة:", _kb_main())


# ── /done — finalise wizard ────────────────────────────────────────────────────
async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return await _deny(update)

    state = ctx.user_data.get("state", "")

    # From symbols step → move to allocation mode choice
    if state == "wizard_symbols":
        syms = ctx.user_data.get("new_bot_symbols", [])
        if not syms:
            await _reply(update, "⚠️ أضف عملة واحدة على الأقل.", _kb_cancel())
            return
        if len(syms) < 2:
            await _reply(update, "⚠️ أضف عملتين على الأقل.", _kb_cancel())
            return
        sym_str = "  ".join(f"`{s}`" for s in syms)
        ctx.user_data["state"] = "wizard_alloc_mode"
        await _reply(
            update,
            f"✅ العملات: {sym_str}\n\n"
            "*الخطوة 3/5* — كيف تريد توزيع النسب؟",
            _kb_alloc_mode(),
        )

    # From manual alloc or deviation step → nothing pending
    elif state in ("wizard_manual_alloc", "wizard_deviation", "wizard_balance",
                   "wizard_balance_amount", "wizard_confirm"):
        await _reply(update, "⚠️ أكمل الخطوة الحالية أولاً.", _kb_cancel())

    else:
        await _reply(update, "لا يوجد شيء لحفظه.", _kb_main())

# ── Entry point ────────────────────────────────────────────────────────────────
def run_bot(
    start_fn:             Callable,
    stop_fn:              Callable,
    rebalance_fn:         Callable,
    list_portfolios_fn:   Callable,
    is_running_fn:        Callable,
    get_portfolio_fn:     Callable,
    save_portfolio_fn:    Callable,
    buy_fn:               Callable,
    sell_fn:              Callable,
    get_balances_fn:      Callable,
    update_portfolio_fn:  Callable = lambda pid, cfg: None,
    # backward-compat — unused
    get_status_fn:        Callable = lambda: {},
    get_history_fn:       Callable = lambda limit, portfolio_id=1: [],
) -> None:
    global _start_fn, _stop_fn, _rebalance_fn, _list_portfolios
    global _is_running_fn, _get_portfolio_fn, _save_portfolio_fn
    global _update_portfolio_fn, _buy_fn, _sell_fn, _get_balances_fn

    _start_fn             = start_fn
    _stop_fn              = stop_fn
    _rebalance_fn         = rebalance_fn
    _list_portfolios      = list_portfolios_fn
    _is_running_fn        = is_running_fn
    _get_portfolio_fn     = get_portfolio_fn
    _save_portfolio_fn    = save_portfolio_fn
    _update_portfolio_fn  = update_portfolio_fn
    _buy_fn               = buy_fn
    _sell_fn              = sell_fn
    _get_balances_fn      = get_balances_fn

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
