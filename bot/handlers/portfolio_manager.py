import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bot.database import db
from bot.keyboards import (
    portfolios_list_kb, portfolio_actions_kb,
    portfolio_delete_confirm_kb, main_menu_kb,
    portfolio_sell_one_kb, portfolio_sell_confirm_kb,
)

async def _portfolio_kb(portfolio_id: int, user_id: int) -> InlineKeyboardMarkup:
    """جلب بيانات المحفظة وبناء keyboard الشاشة الكاملة."""
    p      = await db.get_portfolio(portfolio_id)
    allocs = await db.get_portfolio_allocations(portfolio_id)
    active_id = await db.get_active_portfolio_id(user_id)
    if not p:
        return main_menu_kb()
    return portfolio_actions_kb(
        portfolio_id=portfolio_id,
        is_active=(p["id"] == active_id),
        auto_enabled=bool(p.get("auto_enabled")),
        allocations=allocs,
        capital_usdt=float(p.get("capital_usdt") or 0.0),
        threshold=float(p.get("threshold") or 5.0),
        auto_interval=int(p.get("auto_interval_hours") or 24),
    )


# Conversation states
CREATE_NAME, CREATE_CAPITAL, EDIT_NAME, EDIT_CAPITAL = range(30, 34)
PORTFOLIO_SET_THRESHOLD, PORTFOLIO_SET_INTERVAL = range(34, 36)
# Take-profit / stop-loss wizard states (existing portfolio)
TP_TP1_TYPE, TP_TP1_VALUE, TP_TP1_SELL, TP_TP2_TYPE, TP_TP2_VALUE, TP_TP2_SELL, TP_SL_TYPE, TP_SL_VALUE = range(36, 44)
# Create-portfolio wizard TP/SL states
CREATE_TP1_TYPE, CREATE_TP1_VALUE, CREATE_TP2_VALUE, CREATE_SL_VALUE = range(44, 48)



async def portfolios_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    portfolios = await db.get_portfolios(user_id)
    active_id = await db.ensure_active_portfolio(user_id)

    if not portfolios:
        portfolios = await db.get_portfolios(user_id)

    if not portfolios:
        text = (
            "🗂️ *محافظي*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "لا يوجد محافظ بعد.\n"
            "اضغط ➕ لإنشاء محفظتك الأولى!"
        )
    else:
        total_capital = sum(p["capital_usdt"] for p in portfolios)
        text = (
            f"🗂️ *محافظي*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊  المحافظ:    *{len(portfolios)}*\n"
            f"💰  رأس المال:  *${total_capital:,.0f} USDT*\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )

    await query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=portfolios_list_kb(portfolios, active_id)
    )


async def portfolio_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    active_id = await db.get_active_portfolio_id(user_id)
    allocs    = await db.get_portfolio_allocations(portfolio_id)
    total_pct = sum(a["target_percentage"] for a in allocs)

    threshold = float(p.get("threshold") or 5.0)
    interval  = int(p.get("auto_interval_hours") or 24)
    auto_on   = bool(p.get("auto_enabled"))
    capital   = float(p.get("capital_usdt") or 0.0)
    is_active = p["id"] == active_id

    active_badge = "✅ *نشطة*" if is_active else "⭕ غير نشطة"

    # ── جلب الرصيد الحي من MEXC ──────────────────────────────────────────────
    total_usdt = None
    settings = await db.get_settings(user_id)
    if settings and settings.get("mexc_api_key"):
        try:
            from bot.mexc_client import MexcClient
            client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
            _, total_usdt = await asyncio.wait_for(client.get_portfolio(), timeout=10)
            await client.close()
        except Exception:
            total_usdt = None

    # ── بناء نص الرسالة ───────────────────────────────────────────────────────
    lines = [f"📁 *{p['name']}*  {active_badge}", "━━━━━━━━━━━━━━━━━━━━━"]
    if total_usdt is not None:
        lines.append(f"🏦  الحساب:    `${total_usdt:,.2f} USDT`")
    if capital > 0:
        lines.append(f"💼  المحفظة:   `${capital:,.2f} USDT`")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    if allocs:
        pct_warn = f"  ⚠️ `{total_pct:.1f}%`" if abs(total_pct - 100) > 1 else ""
        lines.append(f"🪙  *{len(allocs)} عملة*{pct_warn}")
    else:
        lines.append("🪙  لا توجد عملات — اضغط *تعديل العملات*")
    text = "\n".join(lines)

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=portfolio_actions_kb(
            portfolio_id=portfolio_id,
            is_active=is_active,
            auto_enabled=auto_on,
            allocations=allocs,
            capital_usdt=capital,
            threshold=threshold,
            auto_interval=interval,
        )
    )


async def portfolio_rebalance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعادة التوازن مباشرة من داخل شاشة المحفظة."""
    from bot.mexc_client import MexcClient
    from bot.rebalancer import calculate_trades
    from bot.keyboards import rebalance_confirm_kb, back_to_main_kb
    import time as _time

    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    await query.edit_message_text("⏳ جاري تحليل المحفظة...")

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.edit_message_text(
            "❌ يجب ربط مفاتيح MEXC API أولاً.",
            reply_markup=back_to_main_kb()
        )
        return

    allocations = await db.get_portfolio_allocations(portfolio_id)
    if not allocations:
        await query.edit_message_text(
            f"❌ لا يوجد توزيع في محفظة *{p.get('name', '')}*.\n"
            "اذهب إلى 🪙 إضافة / تعديل عملات.",
            parse_mode="Markdown",
            reply_markup=await _portfolio_kb(portfolio_id, user_id)
        )
        return

    total_pct = sum(a["target_percentage"] for a in allocations)
    if abs(total_pct - 100) > 1.0:
        await query.edit_message_text(
            f"⚠️ *التوزيع غير صحيح*\n\n"
            f"المجموع الحالي: `{total_pct:.1f}%` — يجب أن يكون 100%",
            parse_mode="Markdown",
            reply_markup=await _portfolio_kb(portfolio_id, user_id)
        )
        return

    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    try:
        full_portfolio, total_usdt = await asyncio.wait_for(client.get_portfolio(), timeout=20)
    except asyncio.TimeoutError:
        await query.edit_message_text("❌ انتهت المهلة — MEXC لم يستجب.", reply_markup=back_to_main_kb())
        return
    except Exception as e:
        await query.edit_message_text(f"❌ خطأ: {str(e)[:100]}", reply_markup=back_to_main_kb())
        return
    finally:
        await client.close()

    capital = float(p.get("capital_usdt") or 0)
    alloc_symbols = {a["symbol"] for a in allocations}

    # فلترة العملات لهذه المحفظة فقط — يمنع تداخل المحافظ المتعددة
    portfolio = {sym: data for sym, data in full_portfolio.items() if sym in alloc_symbols}

    # رأس المال المحدد هو الأساس — لا نستخدم إجمالي الحساب
    if capital > 0:
        effective_total = capital
    else:
        effective_total = sum(d.get("value_usdt", 0.0) for d in portfolio.values())
        if effective_total < 1.0:
            effective_total = total_usdt

    threshold = float(p.get("threshold") or settings.get("threshold") or 5.0)
    trades, drift_report = calculate_trades(portfolio, effective_total, allocations, threshold)

    context.user_data["_pending_trades"]       = trades
    context.user_data["_pending_portfolio_id"] = portfolio_id
    context.user_data["_pending_total"]        = effective_total
    context.user_data["_pending_ts"]           = _time.monotonic()

    text = (
        f"⚖️ *إعادة التوازن — {p.get('name', '')}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 قيمة المحفظة: `${effective_total:,.2f}`\n"
        f"🎯 حد الانحراف: `{threshold}%`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
    )
    for d in drift_report:
        if d["needs_action"]:
            arrow = "🔴" if d["drift_pct"] > 0 else "🟢"
            action_label = "بيع" if d["drift_pct"] > 0 else "شراء"
            text += f"{arrow} `{d['symbol']:<6}` `{d['current_pct']:.1f}%`→`{d['target_pct']:.1f}%` `{d['drift_pct']:+.1f}%` ← {action_label}\n"
        else:
            text += f"✅ `{d['symbol']:<6}` `{d['current_pct']:.1f}%`→`{d['target_pct']:.1f}%` `{d['drift_pct']:+.1f}%`\n"

    if not trades:
        text += "\n━━━━━━━━━━━━━━━━━━━━━\n✅ *المحفظة متوازنة*"
        from bot.keyboards import rebalance_dry_kb
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=rebalance_dry_kb())
        return

    total_trade = sum(t["usdt_amount"] for t in trades)
    text += f"━━━━━━━━━━━━━━━━━━━━━\n💡 *{len(trades)} صفقة مطلوبة*\n"
    for t in trades:
        emoji = "🔴 بيع" if t["action"] == "sell" else "🟢 شراء"
        text += f"{emoji}  `{t['symbol']}`  `${t['usdt_amount']:.2f}`\n"
    text += f"━━━━━━━━━━━━━━━━━━━━━\n💵 الإجمالي: `${total_trade:.2f}`"

    await query.edit_message_text(text, parse_mode="Markdown",
                                   reply_markup=rebalance_confirm_kb(portfolio_id))


async def portfolio_rebalance_exec_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنفيذ صفقات إعادة التوازن المحفوظة في user_data."""
    from bot.mexc_client import MexcClient
    from datetime import datetime, timezone
    import time as _time

    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    trades     = context.user_data.get("_pending_trades", [])
    pending_id = context.user_data.get("_pending_portfolio_id")
    pending_ts = context.user_data.get("_pending_ts", 0)

    # التحقق من أن التحليل يخص نفس المحفظة
    if not trades or pending_id != portfolio_id:
        await query.edit_message_text(
            "❌ انتهت الجلسة أو المحفظة تغيّرت. أعد التحليل أولاً.",
            reply_markup=await _portfolio_kb(portfolio_id, user_id)
        )
        return

    # رفض التحليل القديم (أكثر من 3 دقائق)
    if _time.monotonic() - pending_ts > 180:
        context.user_data.pop("_pending_trades", None)
        context.user_data.pop("_pending_portfolio_id", None)
        context.user_data.pop("_pending_ts", None)
        await query.edit_message_text(
            "⚠️ *انتهت صلاحية التحليل*\n\n"
            "مرّت أكثر من 3 دقائق — أسعار السوق تغيّرت.\n"
            "أعد الضغط على 🔄 إعادة التوازن.",
            parse_mode="Markdown",
            reply_markup=await _portfolio_kb(portfolio_id, user_id)
        )
        return

    await query.edit_message_text("⏳ جاري تنفيذ الصفقات...")

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.edit_message_text(
            "❌ مفاتيح API غير موجودة.",
            reply_markup=await _portfolio_kb(portfolio_id, user_id)
        )
        return

    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    try:
        results = await client.execute_rebalance(trades)
    except Exception as e:
        await query.edit_message_text(
            f"❌ خطأ أثناء التنفيذ: {str(e)[:120]}",
            reply_markup=await _portfolio_kb(portfolio_id, user_id)
        )
        return
    finally:
        await client.close()

    ok   = [r for r in results if r.get("status") == "ok"]
    err  = [r for r in results if r.get("status") == "error"]
    skip = [r for r in results if r.get("status") == "skip"]
    total_traded = sum(
        t["usdt_amount"] for t in trades
        if any(r["symbol"] == t["symbol"] and r.get("status") == "ok" for r in results)
    )

    text = "✅ *اكتملت إعادة التوازن*\n━━━━━━━━━━━━━━━━━━━━━\n"
    for r in ok:
        a = "🔴 بيع" if r["action"] == "sell" else "🟢 شراء"
        text += f"{a}  `{r['symbol']}`  `${r.get('usdt', 0):.2f}`  ✅\n"
    for r in err:
        text += f"❌  `{r['symbol']}`: {r.get('reason', 'خطأ')[:60]}\n"
    for r in skip:
        text += f"⏭  `{r['symbol']}`: {r.get('reason', 'تم التخطي')}\n"
    text += "━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📊 ناجح: *{len(ok)}*"
    if err:
        text += f"  ❌ خطأ: *{len(err)}*"
    if skip:
        text += f"  ⏭ تخطي: *{len(skip)}*"
    text += f"\n💵 الإجمالي: `${total_traded:.2f}`"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    summary = f"يدوي: {len(ok)} ناجح، {len(err)} خطأ"
    await db.add_history(user_id, now, summary, total_traded, 1 if not err else 0,
                         portfolio_id=portfolio_id)

    context.user_data.pop("_pending_trades", None)
    context.user_data.pop("_pending_portfolio_id", None)
    context.user_data.pop("_pending_ts", None)

    await query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=await _portfolio_kb(portfolio_id, user_id)
    )


async def switch_portfolio_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    await db.set_active_portfolio(user_id, portfolio_id)

    portfolios = await db.get_portfolios(user_id)
    text = f"✅ *تم تفعيل المحفظة: {p['name']}*\n\nكل العمليات ستُطبَّق على هذه المحفظة الآن.\n\n"
    text += "📁 *محافظك:*\n"
    for port in portfolios:
        mark = "✅" if port["id"] == portfolio_id else "•"
        text += f"{mark} *{port['name']}* — ${port['capital_usdt']:,.0f}\n"

    await query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=portfolios_list_kb(portfolios, portfolio_id)
    )


async def portfolio_balance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عرض الرصيد الكلي للمحفظة — سطر واحد لكل عملة.
    callback_data = pf_balance:<portfolio_id>
    """
    from bot.mexc_client import MexcClient

    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    allocs  = await db.get_portfolio_allocations(portfolio_id)
    capital = float(p.get("capital_usdt") or 0.0)

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.edit_message_text(
            "❌ يجب ربط مفاتيح MEXC API أولاً.",
            reply_markup=await _portfolio_kb(portfolio_id, user_id),
        )
        return

    await query.edit_message_text("⏳ جاري جلب الأرصدة...")

    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    try:
        portfolio_data, total_account = await asyncio.wait_for(
            client.get_portfolio(), timeout=15
        )
    except asyncio.TimeoutError:
        await query.edit_message_text(
            "❌ انتهت المهلة — MEXC لم يستجب.",
            reply_markup=await _portfolio_kb(portfolio_id, user_id),
        )
        return
    except Exception as e:
        await query.edit_message_text(
            f"❌ خطأ: {str(e)[:100]}",
            reply_markup=await _portfolio_kb(portfolio_id, user_id),
        )
        return
    finally:
        await client.close()

    alloc_symbols = {a["symbol"] for a in allocs}
    portfolio_value = sum(
        portfolio_data.get(sym, {}).get("value_usdt", 0.0)
        for sym in alloc_symbols
    )

    pnl     = portfolio_value - capital if capital > 0 else None
    pnl_pct = (pnl / capital * 100)     if pnl is not None else None

    # ── هيدر الملخص ──────────────────────────────────────────────────────────
    pnl_sign = "+" if pnl is not None and pnl >= 0 else ""
    pnl_icon = "📈" if pnl is not None and pnl >= 0 else "📉"

    lines = [f"📊 *{p['name']}*", ""]
    lines.append(f"🏦  الحساب الكلي    `${total_account:,.2f}`")
    lines.append(f"💼  قيمة المحفظة   `${portfolio_value:,.2f}`")
    if capital > 0:
        lines.append(f"🎯  رأس المال       `${capital:,.2f}`")
    if pnl is not None:
        lines.append(f"{pnl_icon}  ر / خ            `{pnl_sign}${abs(pnl):,.2f}  ({pnl_sign}{pnl_pct:.1f}%)`")
    lines.append("")

    # ── العملات — 3 في كل صف ─────────────────────────────────────────────────
    # كل خلية: SYM \n $val  (بدون أي تفاصيل زيادة)
    sorted_coins = sorted(
        alloc_symbols,
        key=lambda s: portfolio_data.get(s, {}).get("value_usdt", 0.0),
        reverse=True,
    )

    # نبني صفوف من 3 عملات — كل صف سطر واحد بـ monospace
    # تنسيق كل خلية: "SYM $X.XX" بعرض ثابت 12 حرف
    CELL = 13
    row_cells = []
    for sym in sorted_coins:
        val = portfolio_data.get(sym, {}).get("value_usdt", 0.0)
        cell = f"{sym:<6} ${val:>5.2f}"   # مثال: "BTC    $4.97"
        row_cells.append(cell)

    # اجمع كل 3 في سطر
    for i in range(0, len(row_cells), 3):
        chunk = row_cells[i:i+3]
        # افصل بـ │ وحاذِ
        row = "  │  ".join(f"{c:<{CELL}}" for c in chunk)
        lines.append(f"`{row}`")

    lines.append("")
    lines.append("_آخر تحديث: الآن_")

    back_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 تحديث", callback_data=f"pf_balance:{portfolio_id}"),
        InlineKeyboardButton("◀️ رجوع",  callback_data=f"portfolio:{portfolio_id}"),
    ]])

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=back_kb,
    )


async def delete_portfolio_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    portfolios = await db.get_portfolios(user_id)
    if len(portfolios) <= 1:
        await query.answer("❌ لا يمكن حذف المحفظة الوحيدة", show_alert=True)
        return

    await query.edit_message_text(
        f"⚠️ *تأكيد الحذف*\n\nهل أنت متأكد من حذف محفظة *{p['name']}*؟\n"
        f"💰 رأس المال: ${p['capital_usdt']:,.0f}\n\n"
        "سيتم حذف جميع التوزيعات المرتبطة بها بشكل نهائي.",
        parse_mode="Markdown",
        reply_markup=portfolio_delete_confirm_kb(portfolio_id)
    )


async def delete_portfolio_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    portfolios = await db.get_portfolios(user_id)
    if len(portfolios) <= 1:
        await query.answer("❌ لا يمكن حذف المحفظة الوحيدة", show_alert=True)
        return

    active_id = await db.get_active_portfolio_id(user_id)
    await db.delete_portfolio(portfolio_id)

    if active_id == portfolio_id:
        remaining = await db.get_portfolios(user_id)
        if remaining:
            await db.set_active_portfolio(user_id, remaining[0]["id"])

    remaining = await db.get_portfolios(user_id)
    new_active = await db.get_active_portfolio_id(user_id)
    text = f"✅ *تم حذف المحفظة: {p['name']}*\n\n📁 *محافظك المتبقية:*\n"
    for port in remaining:
        mark = "✅" if port["id"] == new_active else "•"
        text += f"{mark} *{port['name']}* — ${port['capital_usdt']:,.0f}\n"

    await query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=portfolios_list_kb(remaining, new_active)
    )


# ── Create Portfolio Conversation ──────────────────────────────────────────────

async def create_portfolio_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    # Try to fetch real balance from MEXC
    settings = await db.get_settings(user_id)
    real_balance = None
    if settings and settings.get("mexc_api_key"):
        await query.edit_message_text("⏳ جاري جلب رصيدك من MEXC...")
        try:
            from bot.mexc_client import MexcClient
            client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
            try:
                _, total_usdt = await asyncio.wait_for(client.get_portfolio(), timeout=15)
                real_balance = total_usdt
            finally:
                await client.close()
        except Exception:
            real_balance = None

    context.user_data["_real_balance"] = real_balance

    if real_balance is not None:
        balance_text = f"💰 رصيدك الحالي في MEXC: *${real_balance:,.2f} USDT*\n\n"
        use_full_btn = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"✅ استخدام كامل الرصيد (${real_balance:,.2f})", callback_data="portfolio_capital:full")],
            [InlineKeyboardButton("✏️ تحديد مبلغ مخصص", callback_data="portfolio_capital:custom")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")],
        ])
        await query.edit_message_text(
            f"📁 *إنشاء محفظة جديدة*\n\n{balance_text}"
            "اختر رأس المال لهذه المحفظة:",
            parse_mode="Markdown",
            reply_markup=use_full_btn,
        )
    else:
        await query.edit_message_text(
            "📁 *إنشاء محفظة جديدة*\n\n"
            "⚠️ لم يتم ربط MEXC API بعد أو تعذّر جلب الرصيد.\n\n"
            "أدخل *اسم المحفظة*:\n"
            "مثال: محفظة المضاربة / محفظة طويلة المدى\n\n/cancel للإلغاء",
            parse_mode="Markdown",
        )
    return CREATE_NAME


async def create_portfolio_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle capital choice buttons (full/custom) that arrive as callback queries
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        choice = query.data.split(":")[1]
        real_balance = context.user_data.get("_real_balance")

        if choice == "full" and real_balance is not None:
            context.user_data["_new_portfolio_capital"] = real_balance
        # For "custom", fall through to ask for name first

        await query.edit_message_text(
            "📁 أدخل *اسم المحفظة*:\n"
            "مثال: محفظة المضاربة / محفظة طويلة المدى\n\n/cancel للإلغاء",
            parse_mode="Markdown",
        )
        return CREATE_NAME

    name = update.message.text.strip()
    if len(name) < 2 or len(name) > 50:
        await update.message.reply_text("❌ الاسم يجب بين 2 و 50 حرف. أعد المحاولة:")
        return CREATE_NAME

    context.user_data["_new_portfolio_name"] = name

    # If capital already chosen (full balance), go to TP/SL step
    if "_new_portfolio_capital" in context.user_data:
        capital = context.user_data["_new_portfolio_capital"]
        await update.message.reply_text(
            f"✅ رأس المال: *${capital:,.2f} USDT*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🎯 *هدف الربح الأول (Take Profit 1)*\n\n"
            "اختر نوع الهدف:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 نسبة مئوية (%)", callback_data="create_tp_type:pct")],
                [InlineKeyboardButton("💵 مبلغ USDT",       callback_data="create_tp_type:usdt")],
                [InlineKeyboardButton("⏭ تخطي الأهداف",    callback_data="create_tp_type:skip")],
            ]),
        )
        return CREATE_TP1_TYPE

    real_balance = context.user_data.get("_real_balance")
    balance_hint = f"\n💡 رصيدك الحالي: ${real_balance:,.2f}" if real_balance else ""
    await update.message.reply_text(
        f"✅ الاسم: *{name}*\n\n💰 أدخل *رأس المال بالـ USDT*:{balance_hint}\n"
        "مثال: `1000` أو `5000.50`\n\n/cancel للإلغاء",
        parse_mode="Markdown",
    )
    return CREATE_CAPITAL


async def create_portfolio_capital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        capital = float(update.message.text.strip().replace(",", ""))
        if capital < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً صحيحاً أكبر من أو يساوي 0:")
        return CREATE_CAPITAL

    context.user_data["_new_portfolio_capital"] = capital
    context.user_data.pop("_real_balance", None)

    # Ask about Take Profit
    await update.message.reply_text(
        f"✅ رأس المال: *${capital:,.2f} USDT*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🎯 *هدف الربح الأول (Take Profit 1)*\n\n"
        "اختر نوع الهدف:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 نسبة مئوية (%)", callback_data="create_tp_type:pct")],
            [InlineKeyboardButton("💵 مبلغ USDT",       callback_data="create_tp_type:usdt")],
            [InlineKeyboardButton("⏭ تخطي الأهداف",    callback_data="create_tp_type:skip")],
        ]),
    )
    return CREATE_TP1_TYPE


async def create_tp1_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data.split(":")[1]

    if choice == "skip":
        # Save portfolio without TP/SL
        await _finalize_portfolio_creation(update, context, tp1_type=None, tp1_value=0,
                                           tp2_value=0, sl_value=0)
        return ConversationHandler.END

    context.user_data["_create_tp1_type"] = choice
    type_label = "نسبة مئوية (%)" if choice == "pct" else "مبلغ USDT"
    example    = "مثال: `10` تعني +10%" if choice == "pct" else "مثال: `500` تعني $500 ربح"

    await query.edit_message_text(
        f"🎯 *هدف الربح الأول — {type_label}*\n\n"
        f"أدخل قيمة الهدف الأول:\n{example}\n\n"
        "أرسل `0` لتخطي هذا الهدف.\n\n/cancel للإلغاء",
        parse_mode="Markdown",
    )
    return CREATE_TP1_VALUE


async def create_tp1_value_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.strip())
        if val < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً أكبر من أو يساوي 0:")
        return CREATE_TP1_VALUE

    context.user_data["_create_tp1_value"] = val

    # Ask TP2
    tp1_type = context.user_data.get("_create_tp1_type", "pct")
    type_label = "نسبة مئوية (%)" if tp1_type == "pct" else "مبلغ USDT"
    example    = "مثال: `20` تعني +20%" if tp1_type == "pct" else "مثال: `1000` تعني $1000 ربح"

    await update.message.reply_text(
        f"✅ هدف 1: `{val:.2f}{'%' if tp1_type == 'pct' else ' USDT'}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 *هدف الربح الثاني (Take Profit 2)*\n\n"
        f"أدخل قيمة الهدف الثاني ({type_label}):\n{example}\n\n"
        "أرسل `0` لتخطي هذا الهدف.\n\n/cancel للإلغاء",
        parse_mode="Markdown",
    )
    return CREATE_TP2_VALUE


async def create_tp2_value_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.strip())
        if val < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً أكبر من أو يساوي 0:")
        return CREATE_TP2_VALUE

    context.user_data["_create_tp2_value"] = val
    tp1_type = context.user_data.get("_create_tp1_type", "pct")
    type_label = "نسبة مئوية (%)" if tp1_type == "pct" else "مبلغ USDT"
    example    = "مثال: `5` تعني -5% خسارة" if tp1_type == "pct" else "مثال: `200` تعني -$200 خسارة"

    await update.message.reply_text(
        f"✅ هدف 2: `{val:.2f}{'%' if tp1_type == 'pct' else ' USDT'}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛑 *وقف الخسارة (Stop Loss)*\n\n"
        f"أدخل حد الخسارة ({type_label}):\n{example}\n\n"
        "عند الوصول لهذا الحد، يتم بيع المحفظة تلقائياً وإيقاف التوازن.\n\n"
        "أرسل `0` لتخطي وقف الخسارة.\n\n/cancel للإلغاء",
        parse_mode="Markdown",
    )
    return CREATE_SL_VALUE


async def create_sl_value_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.strip())
        if val < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً أكبر من أو يساوي 0:")
        return CREATE_SL_VALUE

    context.user_data["_create_sl_value"] = val
    tp1_type  = context.user_data.get("_create_tp1_type", "pct")
    tp1_value = context.user_data.get("_create_tp1_value", 0)
    tp2_value = context.user_data.get("_create_tp2_value", 0)

    await _finalize_portfolio_creation(
        update, context,
        tp1_type=tp1_type, tp1_value=tp1_value,
        tp2_value=tp2_value, sl_value=val,
    )
    return ConversationHandler.END


async def _finalize_portfolio_creation(update, context, tp1_type, tp1_value, tp2_value, sl_value):
    """Create the portfolio in DB with all settings and show confirmation."""
    user_id = update.effective_user.id if update.effective_user else None
    name    = context.user_data.pop("_new_portfolio_name", "محفظة جديدة")
    capital = context.user_data.pop("_new_portfolio_capital", 0.0)
    context.user_data.pop("_create_tp1_type",  None)
    context.user_data.pop("_create_tp1_value", None)
    context.user_data.pop("_create_tp2_value", None)
    context.user_data.pop("_create_sl_value",  None)

    portfolio_id = await db.create_portfolio(user_id, name, capital)

    # Save TP/SL if provided
    if tp1_type and tp1_value > 0:
        await db.update_portfolio(
            portfolio_id,
            tp_enabled=1,
            tp_entry_value=capital,
            tp1_type=tp1_type,
            tp1_value=tp1_value,
            tp1_sell_pct=50.0,
            tp2_type=tp1_type,
            tp2_value=tp2_value,
            tp2_sell_pct=100.0,
            sl_type=tp1_type,
            sl_value=sl_value,
        )

    portfolios = await db.get_portfolios(user_id)
    active_id  = await db.get_active_portfolio_id(user_id)

    # Build summary
    suffix = "%" if tp1_type == "pct" else " USDT"
    tp1_line = f"🎯 هدف 1: `{tp1_value:.2f}{suffix}`" if tp1_value > 0 else "🎯 هدف 1: غير محدد"
    tp2_line = f"🏆 هدف 2: `{tp2_value:.2f}{suffix}`" if tp2_value > 0 else "🏆 هدف 2: غير محدد"
    sl_line  = f"🛑 وقف الخسارة: `{sl_value:.2f}{suffix}`" if sl_value > 0 else "🛑 وقف الخسارة: غير محدد"

    msg = update.message if hasattr(update, "message") and update.message else None
    text = (
        f"✅ *تم إنشاء المحفظة!*\n\n"
        f"📁 *{name}*\n"
        f"💰 رأس المال: *${capital:,.2f} USDT*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{tp1_line}\n"
        f"{tp2_line}\n"
        f"{sl_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        "يمكنك تعديل هذه الإعدادات لاحقاً من تفاصيل المحفظة."
    )

    if msg:
        await msg.reply_text(text, parse_mode="Markdown",
                             reply_markup=portfolios_list_kb(portfolios, active_id))
    else:
        # Fallback for callback_query path
        await update.callback_query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=portfolios_list_kb(portfolios, active_id)
        )


# ── Edit Portfolio Name Conversation ───────────────────────────────────────────

async def edit_portfolio_name_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    portfolio_id = int(query.data.split(":")[1])
    p = await db.get_portfolio(portfolio_id)
    context.user_data["_edit_portfolio_id"] = portfolio_id
    await query.edit_message_text(
        f"✏️ *تعديل اسم المحفظة*\n\nالاسم الحالي: *{p['name']}*\n\nأدخل الاسم الجديد:\n\n/cancel للإلغاء",
        parse_mode="Markdown",
    )
    return EDIT_NAME


async def edit_portfolio_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 2 or len(name) > 50:
        await update.message.reply_text("❌ الاسم يجب بين 2 و 50 حرف:")
        return EDIT_NAME

    portfolio_id = context.user_data.pop("_edit_portfolio_id", None)
    if not portfolio_id:
        await update.message.reply_text("❌ انتهت الجلسة.", reply_markup=main_menu_kb())
        return ConversationHandler.END

    await db.update_portfolio(portfolio_id, name=name)
    user_id = update.effective_user.id
    portfolios = await db.get_portfolios(user_id)
    active_id = await db.get_active_portfolio_id(user_id)
    await update.message.reply_text(
        f"✅ *تم تعديل الاسم إلى: {name}*",
        parse_mode="Markdown",
        reply_markup=portfolios_list_kb(portfolios, active_id),
    )
    return ConversationHandler.END


# ── Edit Portfolio Capital Conversation ────────────────────────────────────────

async def edit_portfolio_capital_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    portfolio_id = int(query.data.split(":")[1])
    p = await db.get_portfolio(portfolio_id)
    context.user_data["_edit_portfolio_id"] = portfolio_id
    await query.edit_message_text(
        f"💰 *تعديل رأس المال*\n\nالمحفظة: *{p['name']}*\n"
        f"رأس المال الحالي: *${p['capital_usdt']:,.2f} USDT*\n\n"
        "أدخل رأس المال الجديد بالـ USDT:\n\n/cancel للإلغاء",
        parse_mode="Markdown",
    )
    return EDIT_CAPITAL


async def cancel_portfolio_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ تم الإلغاء.", reply_markup=main_menu_kb())
    else:
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=main_menu_kb())
    return ConversationHandler.END


# ── Edit Capital with Real Execution ──────────────────────────────────────────

async def edit_portfolio_capital_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Override: after saving new capital, buy/sell to match the new allocation."""
    try:
        new_capital = float(update.message.text.strip().replace(",", ""))
        if new_capital < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً صحيحاً:")
        return EDIT_CAPITAL

    portfolio_id = context.user_data.pop("_edit_portfolio_id", None)
    if not portfolio_id:
        await update.message.reply_text("❌ انتهت الجلسة.", reply_markup=main_menu_kb())
        return ConversationHandler.END

    user_id = update.effective_user.id
    p = await db.get_portfolio(portfolio_id)
    old_capital = p["capital_usdt"]
    diff = new_capital - old_capital

    # Save new capital first
    await db.update_portfolio(portfolio_id, capital_usdt=new_capital)

    if abs(diff) < 1.0:
        # No meaningful change — just update DB
        portfolios = await db.get_portfolios(user_id)
        active_id = await db.get_active_portfolio_id(user_id)
        await update.message.reply_text(
            f"✅ *تم تعديل رأس المال إلى: ${new_capital:,.2f} USDT*\n"
            "_(لا يوجد فرق كافٍ لتنفيذ صفقات)_",
            parse_mode="Markdown",
            reply_markup=portfolios_list_kb(portfolios, active_id),
        )
        return ConversationHandler.END

    # Try to execute real trades based on the capital difference
    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        portfolios = await db.get_portfolios(user_id)
        active_id = await db.get_active_portfolio_id(user_id)
        await update.message.reply_text(
            f"✅ *تم تعديل رأس المال إلى: ${new_capital:,.2f} USDT*\n"
            "⚠️ لم يتم ربط MEXC API — لم تُنفَّذ صفقات.",
            parse_mode="Markdown",
            reply_markup=portfolios_list_kb(portfolios, active_id),
        )
        return ConversationHandler.END

    allocs = await db.get_portfolio_allocations(portfolio_id)
    if not allocs:
        portfolios = await db.get_portfolios(user_id)
        active_id = await db.get_active_portfolio_id(user_id)
        await update.message.reply_text(
            f"✅ *تم تعديل رأس المال إلى: ${new_capital:,.2f} USDT*\n"
            "⚠️ لا يوجد توزيع عملات — لم تُنفَّذ صفقات.",
            parse_mode="Markdown",
            reply_markup=portfolios_list_kb(portfolios, active_id),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"⏳ جاري تنفيذ الصفقات بناءً على الفرق `${diff:+,.2f} USDT`..."
    )

    from bot.mexc_client import MexcClient
    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    results = []
    try:
        if diff > 0:
            # Capital increased → buy each coin proportionally
            for a in allocs:
                sym = a["symbol"]
                pct = a["target_percentage"] / 100.0
                usdt_to_buy = diff * pct
                if usdt_to_buy < 1.0:
                    continue
                pair = f"{sym}/USDT"
                try:
                    await client.exchange.create_market_buy_order_with_cost(pair, usdt_to_buy)
                    results.append(f"🟢 شراء `{sym}` — `${usdt_to_buy:.2f}` ✅")
                except Exception as e:
                    results.append(f"❌ شراء `{sym}`: {str(e)[:60]}")
        else:
            # Capital decreased → sell each coin proportionally
            abs_diff = abs(diff)
            for a in allocs:
                sym = a["symbol"]
                pct = a["target_percentage"] / 100.0
                usdt_to_sell = abs_diff * pct
                if usdt_to_sell < 1.0:
                    continue
                pair = f"{sym}/USDT"
                try:
                    ticker = await client.exchange.fetch_ticker(pair)
                    price = float(ticker.get("last") or 0)
                    if price <= 0:
                        results.append(f"❌ بيع `{sym}`: تعذّر جلب السعر")
                        continue
                    qty = usdt_to_sell / price
                    await client.exchange.create_market_sell_order(pair, qty)
                    results.append(f"🔴 بيع `{sym}` — `${usdt_to_sell:.2f}` ✅")
                except Exception as e:
                    results.append(f"❌ بيع `{sym}`: {str(e)[:60]}")
    finally:
        await client.close()

    action_text = "زيادة" if diff > 0 else "تخفيض"
    result_text = "\n".join(results) if results else "لم تُنفَّذ أي صفقة"
    portfolios = await db.get_portfolios(user_id)
    active_id = await db.get_active_portfolio_id(user_id)
    await update.message.reply_text(
        f"✅ *تم {action_text} رأس المال إلى: ${new_capital:,.2f} USDT*\n\n"
        f"*الصفقات المنفذة:*\n{result_text}",
        parse_mode="Markdown",
        reply_markup=portfolios_list_kb(portfolios, active_id),
    )
    return ConversationHandler.END


# ── Portfolio Sell Operations ──────────────────────────────────────────────────

async def portfolio_sell_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show confirmation to sell ALL coins in the portfolio at market price."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    allocs = await db.get_portfolio_allocations(portfolio_id)
    coins = [a["symbol"] for a in allocs]
    coins_text = "، ".join(coins) if coins else "لا يوجد عملات"

    await query.edit_message_text(
        f"⚠️ *تأكيد بيع الكل*\n\n"
        f"المحفظة: *{p['name']}*\n"
        f"العملات: `{coins_text}`\n\n"
        "سيتم بيع جميع العملات بسعر السوق الحالي فوراً.",
        parse_mode="Markdown",
        reply_markup=portfolio_sell_confirm_kb(portfolio_id, "all"),
    )


async def portfolio_sell_one_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show list of coins to pick one for selling."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    allocs = await db.get_portfolio_allocations(portfolio_id)
    if not allocs:
        await query.answer("❌ لا يوجد عملات في هذه المحفظة", show_alert=True)
        return

    symbols = [a["symbol"] for a in allocs]
    await query.edit_message_text(
        f"🔴 *بيع عملة واحدة*\n\nاختر العملة التي تريد بيعها من محفظة *{p['name']}*:",
        parse_mode="Markdown",
        reply_markup=portfolio_sell_one_kb(portfolio_id, symbols),
    )


async def portfolio_sell_coin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show confirmation for selling a specific coin."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    portfolio_id = int(parts[1])
    symbol = parts[2]

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    await query.edit_message_text(
        f"⚠️ *تأكيد بيع {symbol}*\n\n"
        f"المحفظة: *{p['name']}*\n\n"
        f"سيتم بيع كامل رصيد `{symbol}` بسعر السوق الحالي.",
        parse_mode="Markdown",
        reply_markup=portfolio_sell_confirm_kb(portfolio_id, "one", symbol),
    )


async def portfolio_rebalance_sell_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show confirmation to sell proportionally (rebalance sell)."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    allocs = await db.get_portfolio_allocations(portfolio_id)
    coins_text = "، ".join(a["symbol"] for a in allocs) if allocs else "لا يوجد"

    await query.edit_message_text(
        f"⚠️ *تأكيد استبدال بنسبة*\n\n"
        f"المحفظة: *{p['name']}*\n"
        f"العملات: `{coins_text}`\n\n"
        "سيتم بيع كل عملة بنسبتها المخصصة من رأس المال الحالي وتحويلها إلى USDT.",
        parse_mode="Markdown",
        reply_markup=portfolio_sell_confirm_kb(portfolio_id, "proportional"),
    )


async def portfolio_sell_exec_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute the sell operation."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    portfolio_id = int(parts[1])
    action = parts[2]
    symbol = parts[3] if len(parts) > 3 else ""

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.answer("❌ يجب ربط MEXC API أولاً", show_alert=True)
        return

    await query.edit_message_text("⏳ جاري تنفيذ البيع...")

    from bot.mexc_client import MexcClient
    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    results = []

    try:
        balance = await client.exchange.fetch_balance()
        allocs = await db.get_portfolio_allocations(portfolio_id)

        if action == "all":
            # Sell all coins in the portfolio
            for a in allocs:
                sym = a["symbol"]
                qty = float(balance.get("free", {}).get(sym, 0) or 0)
                if qty < 1e-8:
                    results.append(f"⏭ `{sym}`: رصيد صفر")
                    continue
                pair = f"{sym}/USDT"
                try:
                    await client.exchange.create_market_sell_order(pair, qty)
                    results.append(f"🔴 بيع `{sym}` — `{qty:.6g}` ✅")
                except Exception as e:
                    results.append(f"❌ `{sym}`: {str(e)[:60]}")

        elif action == "one" and symbol:
            # Sell a single coin
            qty = float(balance.get("free", {}).get(symbol, 0) or 0)
            if qty < 1e-8:
                results.append(f"⏭ `{symbol}`: رصيد صفر")
            else:
                pair = f"{symbol}/USDT"
                try:
                    await client.exchange.create_market_sell_order(pair, qty)
                    results.append(f"🔴 بيع `{symbol}` — `{qty:.6g}` ✅")
                except Exception as e:
                    results.append(f"❌ `{symbol}`: {str(e)[:60]}")

        elif action == "proportional":
            # Sell each coin proportionally based on its target allocation
            capital = p["capital_usdt"]
            for a in allocs:
                sym = a["symbol"]
                pct = a["target_percentage"] / 100.0
                usdt_target = capital * pct
                pair = f"{sym}/USDT"
                try:
                    ticker = await client.exchange.fetch_ticker(pair)
                    price = float(ticker.get("last") or 0)
                    if price <= 0:
                        results.append(f"❌ `{sym}`: تعذّر جلب السعر")
                        continue
                    qty = usdt_target / price
                    free_qty = float(balance.get("free", {}).get(sym, 0) or 0)
                    qty = min(qty, free_qty)
                    if qty < 1e-8:
                        results.append(f"⏭ `{sym}`: رصيد غير كافٍ")
                        continue
                    await client.exchange.create_market_sell_order(pair, qty)
                    results.append(f"🔴 بيع `{sym}` — `${usdt_target:.2f}` ✅")
                except Exception as e:
                    results.append(f"❌ `{sym}`: {str(e)[:60]}")

    finally:
        await client.close()

    result_text = "\n".join(results) if results else "لم تُنفَّذ أي صفقة"
    await query.edit_message_text(
        f"✅ *اكتملت عملية البيع*\n\n{result_text}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ رجوع للمحفظة", callback_data=f"portfolio:{portfolio_id}")]
        ]),
    )


# ── Per-portfolio: Edit Allocations ───────────────────────────────────────────

async def portfolio_edit_allocs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شاشة إضافة / حذف عملات المحفظة مباشرة."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    # تفعيل المحفظة حتى يعمل alloc flow عليها
    await db.set_active_portfolio(user_id, portfolio_id)

    allocs = await db.get_portfolio_allocations(portfolio_id)
    existing = "  ·  ".join(f"`{a['symbol']}`" for a in allocs) if allocs else "لا يوجد"
    total_pct = sum(a["target_percentage"] for a in allocs)
    pct_line = f"📌 المجموع: `{total_pct:.1f}%`" + (" ✅" if abs(total_pct - 100) < 1 else " ⚠️ يجب 100%")

    # حفظ portfolio_id في user_data حتى يعرف alloc flow أين يحفظ
    context.user_data["_alloc_portfolio_id"] = portfolio_id

    await query.edit_message_text(
        f"🪙 *إضافة / تعديل عملات*\n"
        f"📁 المحفظة: *{p['name']}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"الحالية: {existing}\n"
        f"{pct_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"أرسل رموز العملات مفصولة بمسافة:\n"
        f"`BTC ETH SOL ADA XRP`\n\n"
        f"أو بالنسب مباشرة:\n"
        f"`BTC=40 ETH=30 SOL=30`\n\n"
        f"✖️ /cancel للإلغاء",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑  عرض وحذف عملة", callback_data=f"pf_alloc_list:{portfolio_id}")],
            [InlineKeyboardButton("🧹  مسح جميع العملات", callback_data=f"pf_alloc_clear:{portfolio_id}")],
            [InlineKeyboardButton("◀️  رجوع للمحفظة",    callback_data=f"portfolio:{portfolio_id}")],
        ]),
    )
    return


# ── Per-portfolio: Set Threshold ───────────────────────────────────────────────

async def portfolio_set_threshold_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    context.user_data["_portfolio_settings_id"] = portfolio_id
    current = p.get("threshold") or 5.0
    await query.edit_message_text(
        f"🎯 *حد الانحراف — {p['name']}*\n\n"
        f"الحالي: `{current}%`\n\n"
        "أدخل النسبة المئوية (مثال: `5` تعني 5%).\n"
        "النطاق المسموح: `1` إلى `50`.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data=f"portfolio:{portfolio_id}")]
        ]),
    )
    return PORTFOLIO_SET_THRESHOLD


async def portfolio_set_threshold_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    portfolio_id = context.user_data.pop("_portfolio_settings_id", None)
    if not portfolio_id:
        await update.message.reply_text("❌ انتهت الجلسة.", reply_markup=main_menu_kb())
        return ConversationHandler.END

    try:
        val = float(update.message.text.strip().replace("%", ""))
        if not (1.0 <= val <= 50.0):
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً بين 1 و 50:")
        context.user_data["_portfolio_settings_id"] = portfolio_id
        return PORTFOLIO_SET_THRESHOLD

    await db.update_portfolio(portfolio_id, threshold=val)
    p = await db.get_portfolio(portfolio_id)
    await update.message.reply_text(
        f"✅ *تم تعديل حد الانحراف إلى {val}%*\n\nالمحفظة: *{p['name']}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ رجوع للمحفظة", callback_data=f"portfolio:{portfolio_id}")]
        ]),
    )
    return ConversationHandler.END


# ── Per-portfolio: Set Interval ────────────────────────────────────────────────

async def portfolio_set_interval_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    context.user_data["_portfolio_settings_id"] = portfolio_id
    current = p.get("auto_interval_hours") or 24
    await query.edit_message_text(
        f"⏱ *فترة التوازن التلقائي — {p['name']}*\n\n"
        f"الحالية: كل `{current}` ساعة\n\n"
        "أدخل عدد الساعات (مثال: `24` = يومياً، `168` = أسبوعياً).\n"
        "النطاق المسموح: `1` إلى `720`.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data=f"portfolio:{portfolio_id}")]
        ]),
    )
    return PORTFOLIO_SET_INTERVAL


async def portfolio_set_interval_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    portfolio_id = context.user_data.pop("_portfolio_settings_id", None)
    if not portfolio_id:
        await update.message.reply_text("❌ انتهت الجلسة.", reply_markup=main_menu_kb())
        return ConversationHandler.END

    try:
        val = int(float(update.message.text.strip()))
        if not (1 <= val <= 720):
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً بين 1 و 720:")
        context.user_data["_portfolio_settings_id"] = portfolio_id
        return PORTFOLIO_SET_INTERVAL

    await db.update_portfolio(portfolio_id, auto_interval_hours=val)
    p = await db.get_portfolio(portfolio_id)
    await update.message.reply_text(
        f"✅ *تم تعديل فترة التوازن إلى كل {val} ساعة*\n\nالمحفظة: *{p['name']}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ رجوع للمحفظة", callback_data=f"portfolio:{portfolio_id}")]
        ]),
    )
    return ConversationHandler.END


# ── Per-portfolio: Alloc List / Delete / Clear ────────────────────────────────

async def pf_alloc_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة العملات مع زر حذف لكل منها."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    allocs = await db.get_portfolio_allocations(portfolio_id)
    if not allocs:
        await query.answer("لا توجد عملات", show_alert=True)
        return

    capital = float(p.get("capital_usdt") or 0.0)
    buttons = []
    for a in allocs:
        val = capital * a["target_percentage"] / 100 if capital > 0 else 0
        val_str = f"  ${val:,.1f}" if val > 0 else ""
        buttons.append([InlineKeyboardButton(
            f"🗑  {a['symbol']}  ·  {a['target_percentage']:.1f}%{val_str}",
            callback_data=f"pf_alloc_del:{portfolio_id}:{a['symbol']}"
        )])
    buttons.append([InlineKeyboardButton("◀️  رجوع", callback_data=f"portfolio_edit_allocs:{portfolio_id}")])

    total_pct = sum(a["target_percentage"] for a in allocs)
    await query.edit_message_text(
        f"🗑 *حذف عملة — {p['name']}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"اضغط على العملة لحذفها:\n"
        f"المجموع: `{total_pct:.1f}%`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def pf_alloc_del_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف عملة واحدة من المحفظة."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    portfolio_id = int(parts[1])
    symbol = parts[2]

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    await db.delete_portfolio_allocation(portfolio_id, symbol)
    await query.answer(f"✅ تم حذف {symbol}", show_alert=False)

    # أعد عرض القائمة بعد الحذف
    allocs = await db.get_portfolio_allocations(portfolio_id)
    if not allocs:
        await query.edit_message_text(
            f"✅ تم حذف {symbol}\n\nلا توجد عملات متبقية.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ رجوع للمحفظة", callback_data=f"portfolio:{portfolio_id}")
            ]])
        )
        return

    capital = float(p.get("capital_usdt") or 0.0)
    buttons = []
    for a in allocs:
        val = capital * a["target_percentage"] / 100 if capital > 0 else 0
        val_str = f"  ${val:,.1f}" if val > 0 else ""
        buttons.append([InlineKeyboardButton(
            f"🗑  {a['symbol']}  ·  {a['target_percentage']:.1f}%{val_str}",
            callback_data=f"pf_alloc_del:{portfolio_id}:{a['symbol']}"
        )])
    buttons.append([InlineKeyboardButton("◀️  رجوع", callback_data=f"portfolio_edit_allocs:{portfolio_id}")])

    total_pct = sum(a["target_percentage"] for a in allocs)
    await query.edit_message_text(
        f"✅ تم حذف `{symbol}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"المجموع الحالي: `{total_pct:.1f}%`\n"
        f"اضغط على عملة لحذفها:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def pf_alloc_clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مسح جميع عملات المحفظة بعد تأكيد."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    # تأكيد أول مرة
    if query.data.startswith("pf_alloc_clear:") and not query.data.startswith("pf_alloc_clear_confirm:"):
        await query.edit_message_text(
            f"⚠️ *هل تريد مسح جميع عملات {p['name']}؟*\n\nلا يمكن التراجع.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⚠️ نعم، امسح الكل", callback_data=f"pf_alloc_clear_confirm:{portfolio_id}"),
                    InlineKeyboardButton("✖️ إلغاء",           callback_data=f"portfolio_edit_allocs:{portfolio_id}"),
                ]
            ])
        )
        return

    await db.clear_portfolio_allocations(portfolio_id)
    kb = await _portfolio_kb(portfolio_id, user_id)
    await query.edit_message_text(
        f"✅ *تم مسح جميع العملات*\n📁 *{p['name']}*\n\n"
        f"💰 *{'${:,.1f} USD'.format(float(p.get('capital_usdt') or 0))}*          "
        f"💰 *{'${:,.1f} USD'.format(float(p.get('capital_usdt') or 0))}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 *العملات \\(0\\)*",
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def pf_alloc_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    استقبال رموز العملات المكتوبة وحفظها في المحفظة النشطة.
    يُستدعى من _text_router في main.py عند وجود _alloc_portfolio_id في user_data.
    """
    user_id = update.effective_user.id
    portfolio_id = context.user_data.get("_alloc_portfolio_id")
    if not portfolio_id:
        return

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        context.user_data.pop("_alloc_portfolio_id", None)
        return

    text = update.message.text.strip().upper()
    MAX_COINS = 20

    # تنسيق BTC=40 ETH=30 ...
    if "=" in text:
        pairs_raw = text.replace("\n", " ").split()
        parsed = []
        errors = []
        for item in pairs_raw:
            if "=" in item:
                sym, _, pct_str = item.partition("=")
                sym = sym.strip()
                try:
                    pct = float(pct_str.strip())
                    if pct <= 0:
                        raise ValueError
                    parsed.append((sym, pct))
                except ValueError:
                    errors.append(item)
            else:
                errors.append(item)

        if not parsed:
            await update.message.reply_text(
                "❌ تنسيق خاطئ.\nمثال: `BTC=40 ETH=30 SOL=30`",
                parse_mode="Markdown"
            )
            return

        total = sum(p for _, p in parsed)
        if abs(total - 100) > 1:
            await update.message.reply_text(
                f"⚠️ مجموع النسب `{total:.1f}%` — يجب أن يكون 100%.\n"
                f"مثال: `BTC=40 ETH=30 SOL=30`",
                parse_mode="Markdown"
            )
            return

        for sym, pct in parsed:
            await db.set_portfolio_allocation(portfolio_id, user_id, sym, pct)

        context.user_data.pop("_alloc_portfolio_id", None)
        allocs = await db.get_portfolio_allocations(portfolio_id)
        kb = await _portfolio_kb(portfolio_id, user_id)
        err_txt = f"\n⚠️ تجاهلت: `{'  '.join(errors)}`" if errors else ""
        await update.message.reply_text(
            f"✅ *تم حفظ {len(parsed)} عملة*{err_txt}\n"
            f"📁 *{p['name']}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 *العملات \\({len(allocs)}\\)*",
            parse_mode="Markdown",
            reply_markup=kb,
        )
        return

    # تنسيق BTC ETH SOL ... (بدون نسب — توزيع متساوٍ)
    symbols = [s.strip() for s in text.replace(",", " ").split() if s.strip().isalpha()]
    if not symbols:
        await update.message.reply_text(
            "❌ أرسل رموز العملات:\n`BTC ETH SOL`\nأو بالنسب:\n`BTC=40 ETH=30 SOL=30`",
            parse_mode="Markdown"
        )
        return

    existing = await db.get_portfolio_allocations(portfolio_id)
    existing_syms = {a["symbol"] for a in existing}
    new_syms = [s for s in symbols if s not in existing_syms]

    if len(existing_syms) + len(new_syms) > MAX_COINS:
        await update.message.reply_text(f"❌ الحد الأقصى {MAX_COINS} عملة.")
        return

    # توزيع متساوٍ على الجميع (القديم + الجديد)
    all_syms = list(existing_syms) + new_syms
    pct = round(100.0 / len(all_syms), 2)
    diff = round(100.0 - pct * len(all_syms), 2)

    await db.clear_portfolio_allocations(portfolio_id)
    for i, sym in enumerate(all_syms):
        p_val = pct + (diff if i == len(all_syms) - 1 else 0)
        await db.set_portfolio_allocation(portfolio_id, user_id, sym, round(p_val, 2))

    context.user_data.pop("_alloc_portfolio_id", None)
    allocs = await db.get_portfolio_allocations(portfolio_id)
    kb = await _portfolio_kb(portfolio_id, user_id)
    await update.message.reply_text(
        f"✅ *تم إضافة {len(new_syms)} عملة — توزيع متساوٍ {pct}%*\n"
        f"📁 *{p['name']}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 *العملات \\({len(allocs)}\\)*",
        parse_mode="Markdown",
        reply_markup=kb,
    )


# ── Per-portfolio: Toggle Auto Rebalance ──────────────────────────────────────

async def portfolio_toggle_auto_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    new_state = 0 if p.get("auto_enabled") else 1
    await db.update_portfolio(portfolio_id, auto_enabled=new_state)
    p = await db.get_portfolio(portfolio_id)

    interval  = p.get("auto_interval_hours") or 24
    threshold = p.get("threshold") or 5.0
    auto_on   = bool(p.get("auto_enabled"))
    allocs    = await db.get_portfolio_allocations(portfolio_id)
    active_id = await db.get_active_portfolio_id(user_id)
    active_badge = "✅ نشطة" if p["id"] == active_id else "⭕ غير نشطة"
    auto_line = f"🟢 تلقائي كل {interval}س" if auto_on else "🔴 التوازن التلقائي معطل"

    lines = [f"📁 *{p['name']}*  {active_badge}", "━━━━━━━━━━━━━━━━━━━━━"]
    if p.get("capital_usdt", 0) > 0:
        lines.append(f"💼  المحفظة:   `${p['capital_usdt']:,.2f} USDT`")
    lines.append(f"🎯  الانحراف:  `{threshold}%`")
    lines.append(f"⏱  الفترة:    `{interval} ساعة`")
    lines.append(auto_line)
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    if allocs:
        lines.append(f"🪙  *{len(allocs)} عملة*")
    text = "\n".join(lines)

    await query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=await _portfolio_kb(portfolio_id, user_id)
    )


# ── Portfolio TP/SL Menu ───────────────────────────────────────────────────────

async def portfolio_tp_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    tp_enabled = bool(p.get("tp_enabled"))
    tp1_type   = p.get("tp1_type", "pct")
    tp1_value  = float(p.get("tp1_value") or 0)
    tp2_value  = float(p.get("tp2_value") or 0)
    sl_value   = float(p.get("sl_value") or 0)
    suffix     = "%" if tp1_type == "pct" else " USDT"

    tp1_line = f"`{tp1_value:.2f}{suffix}`" if tp1_value > 0 else "_غير محدد_"
    tp2_line = f"`{tp2_value:.2f}{suffix}`" if tp2_value > 0 else "_غير محدد_"
    sl_line  = f"`{sl_value:.2f}{suffix}`"  if sl_value  > 0 else "_غير محدد_"
    status   = "🟢 مفعّل" if tp_enabled else "🔴 معطّل"

    text = (
        f"🎯 *أهداف الربح ووقف الخسارة*\n"
        f"📁 *{p['name']}*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"الحالة: {status}\n"
        f"🎯 هدف 1 (بيع 50%): {tp1_line}\n"
        f"🏆 هدف 2 (بيع 100%): {tp2_line}\n"
        f"🛑 وقف الخسارة: {sl_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )

    buttons = []
    if tp_enabled:
        buttons.append([InlineKeyboardButton("🔴 تعطيل الأهداف", callback_data=f"portfolio_tp_deactivate:{portfolio_id}")])
    else:
        buttons.append([InlineKeyboardButton("🟢 تفعيل الأهداف", callback_data=f"portfolio_tp_activate:{portfolio_id}")])
    buttons.append([InlineKeyboardButton("✏️ تعديل الأهداف", callback_data=f"portfolio_tp_setup:{portfolio_id}")])
    buttons.append([InlineKeyboardButton("◀️ رجوع", callback_data=f"portfolio:{portfolio_id}")])

    await query.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


async def portfolio_tp_activate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])
    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return
    await db.update_portfolio(portfolio_id, tp_enabled=1, tp_entry_value=p["capital_usdt"])
    await query.answer("✅ تم تفعيل الأهداف")
    query.data = f"portfolio_tp_menu:{portfolio_id}"
    await portfolio_tp_menu_callback(update, context)


async def portfolio_tp_deactivate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])
    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return
    await db.update_portfolio(portfolio_id, tp_enabled=0)
    await query.answer("✅ تم تعطيل الأهداف")
    query.data = f"portfolio_tp_menu:{portfolio_id}"
    await portfolio_tp_menu_callback(update, context)


# ── TP/SL Setup Wizard ────────────────────────────────────────────────────────

async def portfolio_tp_setup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    portfolio_id = int(query.data.split(":")[1])
    context.user_data["_tp_portfolio_id"] = portfolio_id
    context.user_data["_tp_step"] = "tp1_type"
    await query.edit_message_text(
        "🎯 *إعداد أهداف الربح ووقف الخسارة*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "*هدف الربح الأول (TP1)*\n\nاختر نوع الهدف:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 نسبة مئوية (%)", callback_data="tp_type:pct")],
            [InlineKeyboardButton("💵 مبلغ USDT",       callback_data="tp_type:usdt")],
            [InlineKeyboardButton("⏭ تخطي",            callback_data="tp_type:skip")],
        ]),
    )
    return TP_TP1_TYPE


async def tp_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data.split(":")[1]
    step   = context.user_data.get("_tp_step", "tp1_type")

    if choice == "skip":
        if step == "tp1_type":
            context.user_data.update({"_tp1_type": "pct", "_tp1_value": 0, "_tp_step": "tp2_type"})
            await query.edit_message_text(
                "🏆 *هدف الربح الثاني (TP2)*\n\nاختر نوع الهدف:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 نسبة مئوية (%)", callback_data="tp_type:pct")],
                    [InlineKeyboardButton("💵 مبلغ USDT",       callback_data="tp_type:usdt")],
                    [InlineKeyboardButton("⏭ تخطي",            callback_data="tp_type:skip")],
                ]),
            )
            return TP_TP2_TYPE
        elif step == "tp2_type":
            context.user_data.update({"_tp2_value": 0, "_tp_step": "sl_type"})
            await query.edit_message_text(
                "🛑 *وقف الخسارة (Stop Loss)*\n\nاختر نوع الوقف:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 نسبة مئوية (%)", callback_data="tp_type:pct")],
                    [InlineKeyboardButton("💵 مبلغ USDT",       callback_data="tp_type:usdt")],
                    [InlineKeyboardButton("⏭ تخطي",            callback_data="tp_type:skip")],
                ]),
            )
            return TP_SL_TYPE
        else:
            await _save_tp_sl(update, context, sl_value=0)
            return ConversationHandler.END

    context.user_data["_tp_type"] = choice
    type_label = "نسبة مئوية (%)" if choice == "pct" else "مبلغ USDT"

    if step == "tp1_type":
        context.user_data["_tp_step"] = "tp1_value"
        example = "مثال: `10` = +10%" if choice == "pct" else "مثال: `500` = $500 ربح"
        await query.edit_message_text(
            f"🎯 *هدف 1 — {type_label}*\n\nأدخل القيمة:\n{example}\n\n/cancel للإلغاء",
            parse_mode="Markdown",
        )
        return TP_TP1_VALUE
    elif step == "tp2_type":
        context.user_data["_tp_step"] = "tp2_value"
        example = "مثال: `20` = +20%" if choice == "pct" else "مثال: `1000` = $1000 ربح"
        await query.edit_message_text(
            f"🏆 *هدف 2 — {type_label}*\n\nأدخل القيمة:\n{example}\n\n/cancel للإلغاء",
            parse_mode="Markdown",
        )
        return TP_TP2_VALUE
    else:
        context.user_data["_tp_step"] = "sl_value"
        example = "مثال: `5` = -5% خسارة" if choice == "pct" else "مثال: `200` = -$200 خسارة"
        await query.edit_message_text(
            f"🛑 *وقف الخسارة — {type_label}*\n\nأدخل القيمة:\n{example}\n\n/cancel للإلغاء",
            parse_mode="Markdown",
        )
        return TP_SL_VALUE


async def tp1_value_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.strip())
        if val < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً أكبر من أو يساوي 0:")
        return TP_TP1_VALUE
    context.user_data["_tp1_value"] = val
    context.user_data["_tp1_type"]  = context.user_data.get("_tp_type", "pct")
    context.user_data["_tp_step"]   = "tp1_sell"
    await update.message.reply_text(
        f"✅ هدف 1: `{val:.2f}`\n\n"
        "أدخل نسبة البيع عند هدف 1 (%):\n"
        "مثال: `50` تعني بيع 50% من المحفظة\n\n/cancel للإلغاء",
        parse_mode="Markdown",
    )
    return TP_TP1_SELL


async def tp1_sell_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.strip())
        if not (1 <= val <= 100):
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل نسبة بين 1 و 100:")
        return TP_TP1_SELL
    context.user_data["_tp1_sell"] = val
    context.user_data["_tp_step"]  = "tp2_type"
    await update.message.reply_text(
        f"✅ بيع عند هدف 1: `{val:.0f}%`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🏆 *هدف الربح الثاني (TP2)*\n\nاختر نوع الهدف:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 نسبة مئوية (%)", callback_data="tp_type:pct")],
            [InlineKeyboardButton("💵 مبلغ USDT",       callback_data="tp_type:usdt")],
            [InlineKeyboardButton("⏭ تخطي",            callback_data="tp_type:skip")],
        ]),
    )
    return TP_TP2_TYPE


async def tp2_value_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.strip())
        if val < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً أكبر من أو يساوي 0:")
        return TP_TP2_VALUE
    context.user_data["_tp2_value"] = val
    context.user_data["_tp_step"]   = "tp2_sell"
    await update.message.reply_text(
        f"✅ هدف 2: `{val:.2f}`\n\n"
        "أدخل نسبة البيع عند هدف 2 (%):\n"
        "مثال: `100` تعني بيع كامل المحفظة\n\n/cancel للإلغاء",
        parse_mode="Markdown",
    )
    return TP_TP2_SELL


async def tp2_sell_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.strip())
        if not (1 <= val <= 100):
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل نسبة بين 1 و 100:")
        return TP_TP2_SELL
    context.user_data["_tp2_sell"] = val
    context.user_data["_tp_step"]  = "sl_type"
    await update.message.reply_text(
        f"✅ بيع عند هدف 2: `{val:.0f}%`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🛑 *وقف الخسارة (Stop Loss)*\n\nاختر نوع الوقف:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 نسبة مئوية (%)", callback_data="tp_type:pct")],
            [InlineKeyboardButton("💵 مبلغ USDT",       callback_data="tp_type:usdt")],
            [InlineKeyboardButton("⏭ تخطي",            callback_data="tp_type:skip")],
        ]),
    )
    return TP_SL_TYPE


async def sl_value_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.strip())
        if val < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً أكبر من أو يساوي 0:")
        return TP_SL_VALUE
    await _save_tp_sl(update, context, sl_value=val)
    return ConversationHandler.END


async def _save_tp_sl(update, context, sl_value: float):
    portfolio_id = context.user_data.pop("_tp_portfolio_id", None)
    tp1_type  = context.user_data.pop("_tp1_type",  "pct")
    tp1_value = context.user_data.pop("_tp1_value", 0)
    tp1_sell  = context.user_data.pop("_tp1_sell",  50.0)
    tp2_value = context.user_data.pop("_tp2_value", 0)
    tp2_sell  = context.user_data.pop("_tp2_sell",  100.0)
    context.user_data.pop("_tp_step", None)
    context.user_data.pop("_tp_type", None)

    if not portfolio_id:
        if update.message:
            await update.message.reply_text("❌ انتهت الجلسة.", reply_markup=main_menu_kb())
        return

    p = await db.get_portfolio(portfolio_id)
    await db.update_portfolio(
        portfolio_id,
        tp_enabled=1 if (tp1_value > 0 or tp2_value > 0 or sl_value > 0) else 0,
        tp_entry_value=p["capital_usdt"],
        tp1_type=tp1_type, tp1_value=tp1_value, tp1_sell_pct=tp1_sell,
        tp2_type=tp1_type, tp2_value=tp2_value, tp2_sell_pct=tp2_sell,
        sl_type=tp1_type,  sl_value=sl_value,
    )

    suffix   = "%" if tp1_type == "pct" else " USDT"
    tp1_line = f"🎯 هدف 1: `{tp1_value:.2f}{suffix}` (بيع `{tp1_sell:.0f}%`)" if tp1_value > 0 else "🎯 هدف 1: غير محدد"
    tp2_line = f"🏆 هدف 2: `{tp2_value:.2f}{suffix}` (بيع `{tp2_sell:.0f}%`)" if tp2_value > 0 else "🏆 هدف 2: غير محدد"
    sl_line  = f"🛑 وقف الخسارة: `{sl_value:.2f}{suffix}`" if sl_value > 0 else "🛑 وقف الخسارة: غير محدد"

    text = (
        f"✅ *تم حفظ الأهداف*\n\n📁 *{p['name']}*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{tp1_line}\n{tp2_line}\n{sl_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ رجوع للمحفظة", callback_data=f"portfolio:{portfolio_id}")
    ]])
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
