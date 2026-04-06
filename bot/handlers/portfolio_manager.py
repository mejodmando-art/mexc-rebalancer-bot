import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bot.database import db
from bot.keyboards import (
    portfolios_list_kb, portfolio_actions_kb,
    portfolio_delete_confirm_kb, main_menu_kb, back_to_main_kb,
    portfolio_sell_one_kb, portfolio_sell_confirm_kb,
)

# Conversation states
CREATE_NAME, CREATE_CAPITAL, EDIT_NAME, EDIT_CAPITAL = range(30, 34)
PORTFOLIO_SET_THRESHOLD, PORTFOLIO_SET_INTERVAL = range(34, 36)
# Take-profit / stop-loss wizard states
TP_TP1_TYPE, TP_TP1_VALUE, TP_TP1_SELL, TP_TP2_TYPE, TP_TP2_VALUE, TP_TP2_SELL, TP_SL_TYPE, TP_SL_VALUE = range(36, 44)


async def portfolios_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    portfolios = await db.get_portfolios(user_id)
    active_id = await db.ensure_active_portfolio(user_id)

    if not portfolios:
        portfolios = await db.get_portfolios(user_id)

    text = "📁 *محافظك*\n\n"
    if not portfolios:
        text += "لا يوجد محافظ بعد. أنشئ محفظتك الأولى!"
    else:
        for p in portfolios:
            mark = "✅ نشطة" if p["id"] == active_id else ""
            text += f"• *{p['name']}* — ${p['capital_usdt']:,.0f} USDT {mark}\n"

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
    allocs = await db.get_portfolio_allocations(portfolio_id)
    total_pct = sum(a["target_percentage"] for a in allocs)

    threshold = p.get("threshold") or 5.0
    interval  = p.get("auto_interval_hours") or 24
    auto_on   = bool(p.get("auto_enabled"))
    auto_line = f"🟢 تلقائي كل {interval}س" if auto_on else "🔴 التوازن التلقائي معطل"

    text = (
        f"📁 *{p['name']}*\n\n"
        f"💰 رأس المال: *${p['capital_usdt']:,.2f} USDT*\n"
        f"🪙 عدد العملات: *{len(allocs)}*\n"
        f"📊 مجموع التوزيع: *{total_pct:.1f}%*\n"
        f"🎯 حد الانحراف: *{threshold}%*\n"
        f"{auto_line}\n"
        f"{'✅ المحفظة النشطة الآن' if p['id'] == active_id else '⭕ غير نشطة'}\n"
    )
    if allocs:
        text += "\n*التوزيع:*\n"
        for a in allocs[:8]:
            text += f"• `{a['symbol']:6}` {a['target_percentage']:.1f}%\n"
        if len(allocs) > 8:
            text += f"_... و {len(allocs)-8} عملات أخرى_\n"

    await query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=portfolio_actions_kb(portfolio_id, p["id"] == active_id, bool(p.get("auto_enabled")))
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

    # If capital already chosen (full balance), skip capital input step
    if "_new_portfolio_capital" in context.user_data:
        capital = context.user_data.pop("_new_portfolio_capital")
        user_id = update.effective_user.id
        await db.create_portfolio(user_id, name, capital)
        portfolios = await db.get_portfolios(user_id)
        active_id = await db.get_active_portfolio_id(user_id)
        await update.message.reply_text(
            f"✅ *تم إنشاء المحفظة!*\n\n📁 *{name}*\n💰 رأس المال: *${capital:,.2f} USDT*",
            parse_mode="Markdown",
            reply_markup=portfolios_list_kb(portfolios, active_id),
        )
        return ConversationHandler.END

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

    name = context.user_data.pop("_new_portfolio_name", "محفظة جديدة")
    context.user_data.pop("_real_balance", None)
    user_id = update.effective_user.id

    await db.create_portfolio(user_id, name, capital)
    portfolios = await db.get_portfolios(user_id)
    active_id = await db.get_active_portfolio_id(user_id)

    await update.message.reply_text(
        f"✅ *تم إنشاء المحفظة!*\n\n📁 *{name}*\n💰 رأس المال: *${capital:,.2f} USDT*\n\n"
        "يمكنك تفعيلها من قائمة المحافظ وإضافة عملات لها من الإعدادات.",
        parse_mode="Markdown",
        reply_markup=portfolios_list_kb(portfolios, active_id),
    )
    return ConversationHandler.END


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
                    order = await client.exchange.create_market_buy_order_with_cost(pair, usdt_to_buy)
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
                    order = await client.exchange.create_market_sell_order(pair, qty)
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
    """Redirect to the global alloc settings flow but scoped to this portfolio."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    portfolio_id = int(query.data.split(":")[1])

    p = await db.get_portfolio(portfolio_id)
    if not p or p["user_id"] != user_id:
        await query.answer("❌ محفظة غير موجودة", show_alert=True)
        return

    # Make this portfolio active so the alloc flow targets it
    await db.set_active_portfolio(user_id, portfolio_id)
    await query.edit_message_text(
        f"✏️ *تعديل عملات محفظة: {p['name']}*\n\n"
        "استخدم الإعدادات ← إضافة / تعديل عملة لتعديل التوزيع.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings:view")],
            [InlineKeyboardButton("◀️ رجوع للمحفظة", callback_data=f"portfolio:{portfolio_id}")],
        ]),
    )


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
    auto_line = f"🟢 تلقائي كل {interval}س" if auto_on else "🔴 التوازن التلقائي معطل"

    allocs    = await db.get_portfolio_allocations(portfolio_id)
    total_pct = sum(a["target_percentage"] for a in allocs)
    active_id = await db.get_active_portfolio_id(user_id)

    text = (
        f"📁 *{p['name']}*\n\n"
        f"💰 رأس المال: *${p['capital_usdt']:,.2f} USDT*\n"
        f"🪙 عدد العملات: *{len(allocs)}*\n"
        f"📊 مجموع التوزيع: *{total_pct:.1f}%*\n"
        f"🎯 حد الانحراف: *{threshold}%*\n"
        f"{auto_line}\n"
        f"{'✅ المحفظة النشطة الآن' if p['id'] == active_id else '⭕ غير نشطة'}\n"
    )
    if allocs:
        text += "\n*التوزيع:*\n"
        for a in allocs[:8]:
            text += f"• `{a['symbol']:6}` {a['target_percentage']:.1f}%\n"
        if len(allocs) > 8:
            text += f"_... و {len(allocs)-8} عملات أخرى_\n"

    await query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=portfolio_actions_kb(portfolio_id, p["id"] == active_id, bool(p.get("auto_enabled")))
    )

