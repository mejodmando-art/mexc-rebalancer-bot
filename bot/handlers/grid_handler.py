"""
Telegram handler for the Grid Bot.

Conversation flow:
  1. User picks symbol (text input)
  2. Upper % above current price
  3. Lower % below current price
  4. Number of grid steps
  5. Order size in USDT
  6. Take Profit price (optional — skip with /skip)
  7. Stop Loss price   (optional — skip with /skip)
  8. Confirm → place orders
"""

import logging
import asyncio
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)

from bot.database import db
from bot.mexc_client import MexcClient
from bot.grid.engine import calculate_grid_levels, place_grid_orders
from bot.grid.monitor import grid_monitor

logger = logging.getLogger(__name__)

# ── Conversation states ────────────────────────────────────────────────────────
(
    GRID_SYMBOL, GRID_UPPER, GRID_LOWER,
    GRID_STEPS, GRID_SIZE, GRID_TP, GRID_SL, GRID_CONFIRM,
) = range(8)

TEXT = filters.TEXT & ~filters.COMMAND


# ── Menu ───────────────────────────────────────────────────────────────────────

def grid_menu_kb(grids: list) -> InlineKeyboardMarkup:
    buttons = []
    for g in grids:
        buttons.append([InlineKeyboardButton(
            f"📊 {g['symbol']}  ·  {g['steps']} خطوة  ·  ${g['order_size_usdt']:.0f}",
            callback_data=f"grid_detail:{g['id']}"
        )])
    buttons.append([InlineKeyboardButton("➕ شبكة جديدة", callback_data="grid_new")])
    buttons.append([InlineKeyboardButton("◀️ القائمة الرئيسية", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def grid_detail_kb(grid_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 متابعة حية", callback_data=f"grid_live:{grid_id}")],
        [InlineKeyboardButton("🛑 إيقاف الشبكة", callback_data=f"grid_stop:{grid_id}")],
        [InlineKeyboardButton("◀️ رجوع", callback_data="grid:menu")],
    ])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt_grid(g: dict) -> str:
    tp_line = f"🎯 Take Profit: `${g['take_profit']:.6g}`\n" if g.get("take_profit") else ""
    sl_line = f"🛑 Stop Loss:   `${g['stop_loss']:.6g}`\n"  if g.get("stop_loss")   else ""
    return (
        f"📊 *{g['symbol']}*\n\n"
        f"السعر المركزي: `${g['center']:.6g}`\n"
        f"الحد العلوي:   `${g['upper']:.6g}`  (`+{g['upper_pct']}%`)\n"
        f"الحد السفلي:   `${g['lower']:.6g}`  (`-{g['lower_pct']}%`)\n"
        f"عدد الخطوات:  `{g['steps']}`\n"
        f"حجم الشبكة:   `${g['order_size_usdt']:.0f} USDT`\n"
        f"ربح كل خطوة:  `{g['step_pct']:.3f}%`\n"
        f"{tp_line}{sl_line}"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"صفقات منفذة:  `{g.get('total_trades', 0)}`\n"
        f"انتقالات:      `{g.get('shifts', 0)}`"
    )


# ── Menu handlers ──────────────────────────────────────────────────────────────

def _build_grid_chart(all_orders: list, price: float, upper: float, lower: float) -> str:
    """
    Build a vertical price ladder showing each grid level with live price marker.

    Levels sorted top→bottom. Current price injected between levels.
    Each row shows: icon | price bar | price | distance from current price.
    """
    if not all_orders or upper <= lower:
        return ""

    levels      = sorted(all_orders, key=lambda x: x["price"], reverse=True)
    BAR_W       = 8
    price_range = upper - lower if upper > lower else 1
    lines       = []
    price_inserted = False

    for o in levels:
        op   = o["price"]
        side = o["side"]
        st   = o["status"]

        if not price_inserted and price >= op:
            pct = max(0, min(int(((price - lower) / price_range) * BAR_W), BAR_W))
            bar = "█" * pct + "░" * (BAR_W - pct)
            lines.append(f"💲 `│{bar}│` `${price:.6g}` ◀")
            price_inserted = True

        pct   = max(0, min(int(((op - lower) / price_range) * BAR_W), BAR_W))
        bar   = "█" * pct + "░" * (BAR_W - pct)
        dist  = ((op - price) / price) * 100

        if st == "filled":
            icon = "✅"
        elif side == "sell":
            icon = "🔴"
        else:
            icon = "🟢"

        lines.append(f"{icon} `│{bar}│` `${op:.6g}` `{dist:+.2f}%`")

    if not price_inserted:
        pct = max(0, min(int(((price - lower) / price_range) * BAR_W), BAR_W))
        bar = "█" * pct + "░" * (BAR_W - pct)
        lines.append(f"💲 `│{bar}│` `${price:.6g}` ◀")

    return "\n".join(lines)


def _fmt_grid_live(g: dict, price: float) -> str:
    """Build a live grid monitoring screen with visual price ladder and stats."""
    from datetime import datetime, timezone

    symbol   = g["symbol"]
    center   = g["center"]
    upper    = g["upper"]
    lower    = g["lower"]
    step_pct = g.get("step_pct", 0)
    trades   = g.get("total_trades", 0)
    shifts   = g.get("shifts", 0)
    steps    = g.get("steps", 1)
    size_usdt = g.get("order_size_usdt", 0)

    range_total     = upper - lower if upper > lower else 1
    pct_from_center = ((price - center) / center) * 100
    pos_pct         = max(0.0, min(1.0, (price - lower) / range_total))

    # Horizontal position bar (16 chars wide)
    BAR = 16
    filled  = int(pos_pct * BAR)
    pos_bar = "▓" * filled + "░" * (BAR - filled)

    # Zone detection
    if price >= upper * 1.001:
        zone = "🔺 فوق النطاق"
        zone_warn = "\n⚠️ _السعر خرج من النطاق — الشبكة ستنتقل_"
    elif price <= lower * 0.999:
        zone = "🔻 تحت النطاق"
        zone_warn = "\n⚠️ _السعر خرج من النطاق — الشبكة ستنتقل_"
    elif price >= center:
        zone = "🟢 النصف العلوي"
        zone_warn = ""
    else:
        zone = "🔵 النصف السفلي"
        zone_warn = ""

    # TP / SL lines
    tp_line = f"🎯 Take Profit: `${g['take_profit']:.6g}`\n" if g.get("take_profit") else ""
    sl_line = f"🛑 Stop Loss:   `${g['stop_loss']:.6g}`\n"  if g.get("stop_loss")   else ""

    # Collect orders
    buy_orders  = g.get("buy_orders",  [])
    sell_orders = g.get("sell_orders", [])
    all_orders  = []
    for o in buy_orders:
        all_orders.append({"price": o["price"], "side": "buy",  "status": o.get("status", "open")})
    for o in sell_orders:
        all_orders.append({"price": o["price"], "side": "sell", "status": o.get("status", "open")})
    all_orders.sort(key=lambda x: x["price"], reverse=True)

    filled_count = sum(1 for o in all_orders if o["status"] == "filled")
    open_count   = sum(1 for o in all_orders if o["status"] != "filled")
    sell_open    = sum(1 for o in all_orders if o["status"] != "filled" and o["side"] == "sell")
    buy_open     = sum(1 for o in all_orders if o["status"] != "filled" and o["side"] == "buy")

    # Estimated PnL: each completed buy→sell pair earns step_pct on size_per_level
    size_per_level = size_usdt / max(steps, 1)
    completed_pairs = trades // 2 if trades > 0 else 0
    est_pnl = completed_pairs * size_per_level * (step_pct / 100)
    pnl_icon = "🟢" if est_pnl >= 0 else "🔴"

    # Distance to boundaries
    dist_upper = ((upper - price) / price) * 100
    dist_lower = ((price - lower) / price) * 100

    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    header = (
        f"📡 *{symbol}* — متابعة حية\n"
        f"🕐 `{now_str}`\n\n"
        f"╔══════════════════╗\n"
        f"  ⬆️  `${upper:.6g}`  (+{dist_upper:.2f}%)\n"
        f"  `[{pos_bar}]`\n"
        f"  ⬇️  `${lower:.6g}`  (-{dist_lower:.2f}%)\n"
        f"╚══════════════════╝\n\n"
        f"💰 السعر الحالي: `${price:.6g}`\n"
        f"   {zone}  `{pct_from_center:+.2f}%` من المركز{zone_warn}\n"
        f"🎯 المركز: `${center:.6g}`\n"
        f"{tp_line}{sl_line}"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
    )

    # Visual price ladder
    chart = _build_grid_chart(all_orders, price, upper, lower)
    chart_section = (
        f"*📊 سلّم الأسعار:*\n"
        f"🔴 بيع  🟢 شراء  ✅ مُنفَّذ  💲 السعر\n"
        f"{chart}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
    ) if chart else ""

    # Stats panel
    fill_rate = (filled_count / max(len(all_orders), 1)) * 100
    fill_bar_w = 10
    fill_filled = int((fill_rate / 100) * fill_bar_w)
    fill_bar = "█" * fill_filled + "░" * (fill_bar_w - fill_filled)

    stats = (
        f"*📈 إحصائيات الشبكة:*\n"
        f"  🔄 صفقات منفذة: `{trades}`\n"
        f"  🔀 انتقالات: `{shifts}`\n"
        f"  🔴 بيع مفتوح: `{sell_open}`  |  🟢 شراء مفتوح: `{buy_open}`\n"
        f"  ✅ مُنفَّذ: `{filled_count}`  |  نسبة التنفيذ: `[{fill_bar}]` `{fill_rate:.0f}%`\n"
        f"  {pnl_icon} ربح تقديري: `${est_pnl:.4f} USDT`\n"
        f"  📦 حجم الشبكة: `${size_usdt:.0f} USDT`  |  خطوة: `{step_pct:.3f}%`"
    )

    return header + chart_section + stats


async def grid_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    grids = await db.load_user_grids(user_id)
    text = (
        "🔲 *Grid Bot*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"شبكات نشطة: *{len(grids)}*\n"
        "━━━━━━━━━━━━━━━━━━━━━"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=grid_menu_kb(grids))


async def grid_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    grid_id = int(query.data.split(":")[1])
    grid = grid_monitor.active_grids.get(grid_id)
    if not grid:
        await query.edit_message_text("❌ الشبكة مش موجودة.", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ رجوع", callback_data="grid:menu")]
        ]))
        return
    await query.edit_message_text(
        _fmt_grid(grid), parse_mode="Markdown", reply_markup=grid_detail_kb(grid_id)
    )


async def grid_live_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetch current price and show live grid status."""
    query = update.callback_query
    await query.answer("⏳ جاري التحديث...")
    user_id = update.effective_user.id
    grid_id = int(query.data.split(":")[1])

    grid = grid_monitor.active_grids.get(grid_id)
    if not grid or grid.get("user_id") != user_id:
        await query.edit_message_text(
            "❌ الشبكة غير موجودة.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="grid:menu")]])
        )
        return

    settings = await db.get_settings(user_id)
    client   = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    try:
        ticker = await client.exchange.fetch_ticker(grid["symbol"])
        price  = float(ticker.get("last") or 0)
    except Exception as e:
        await query.answer(f"❌ تعذّر جلب السعر: {str(e)[:60]}", show_alert=True)
        return
    finally:
        await client.close()

    if price <= 0:
        await query.answer("❌ السعر غير متاح", show_alert=True)
        return

    await query.edit_message_text(
        _fmt_grid_live(grid, price),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data=f"grid_live:{grid_id}")],
            [InlineKeyboardButton("🛑 إيقاف الشبكة", callback_data=f"grid_stop:{grid_id}")],
            [InlineKeyboardButton("◀️ رجوع", callback_data=f"grid_detail:{grid_id}")],
        ]),
    )


async def grid_stop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    grid_id = int(query.data.split(":")[1])
    grid = grid_monitor.active_grids.get(grid_id)

    if not grid or grid["user_id"] != user_id:
        await query.answer("❌ الشبكة مش موجودة", show_alert=True)
        return

    symbol = grid["symbol"]
    await query.edit_message_text(f"⏳ جاري إيقاف شبكة *{symbol}* وبيع الرصيد...")

    settings = await db.get_settings(user_id)
    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    sell_result = ""
    try:
        from bot.grid.engine import cancel_all_grid_orders

        # 1. Cancel all open limit orders immediately
        all_orders = grid.get("buy_orders", []) + grid.get("sell_orders", [])
        await cancel_all_grid_orders(
            client.exchange, symbol,
            [o for o in all_orders if o["status"] == "open"]
        )

        # 2. Sell the held coin at market price
        base_coin = symbol.split("/")[0]
        try:
            balance = await client.exchange.fetch_balance()
            qty = float(balance.get("free", {}).get(base_coin, 0) or 0)
            if qty > 1e-8:
                await client.exchange.create_market_sell_order(symbol, qty)
                sell_result = f"🔴 بيع `{base_coin}` — `{qty:.6g}` بسعر السوق ✅"
            else:
                sell_result = f"⏭ لا يوجد رصيد `{base_coin}` للبيع"
        except Exception as e:
            sell_result = f"⚠️ تعذّر البيع: {str(e)[:80]}"

    finally:
        await client.close()

    await grid_monitor.remove_grid(grid_id)
    await query.edit_message_text(
        f"✅ *تم إيقاف شبكة {symbol}*\n\n{sell_result}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="grid:menu")]])
    )


# ── Conversation: create new grid ──────────────────────────────────────────────

async def grid_new_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        await query.answer("❌ يجب ربط MEXC API أولاً من الإعدادات", show_alert=True)
        return ConversationHandler.END

    context.user_data.clear()
    await query.edit_message_text(
        "🔲 *شبكة جديدة — الخطوة 1/7*\n\n"
        "أرسل رمز العملة:\n"
        "مثال: `BTC/USDT` أو `ETH/USDT`",
        parse_mode="Markdown",
    )
    return GRID_SYMBOL


async def grid_symbol_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = update.message.text.strip().upper()
    if "/" not in symbol:
        symbol = f"{symbol}/USDT"
    context.user_data["symbol"] = symbol

    await update.message.reply_text(
        f"✅ العملة: `{symbol}`\n\n"
        "🔲 *الخطوة 2/7* — النسبة فوق السعر الحالي:\n"
        "مثال: `10` يعني الشبكة تمتد 10% فوق السعر",
        parse_mode="Markdown",
    )
    return GRID_UPPER


async def grid_upper_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.strip().replace("%", ""))
        if val <= 0 or val > 100:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقم صحيح بين 1 و 100")
        return GRID_UPPER

    context.user_data["upper_pct"] = val
    await update.message.reply_text(
        f"✅ فوق: `{val}%`\n\n"
        "🔲 *الخطوة 3/7* — النسبة تحت السعر الحالي:\n"
        "مثال: `10` يعني الشبكة تمتد 10% تحت السعر",
        parse_mode="Markdown",
    )
    return GRID_LOWER


async def grid_lower_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.strip().replace("%", ""))
        if val <= 0 or val > 100:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقم صحيح بين 1 و 100")
        return GRID_LOWER

    context.user_data["lower_pct"] = val
    await update.message.reply_text(
        f"✅ تحت: `{val}%`\n\n"
        "🔲 *الخطوة 4/7* — عدد خطوات الشبكة:\n"
        "مثال: `10` يعني 10 أوردر شراء + 10 أوردر بيع\n"
        "الحد الأدنى: 2  ·  الحد الأقصى: 50",
        parse_mode="Markdown",
    )
    return GRID_STEPS


async def grid_steps_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = int(update.message.text.strip())
        if val < 2 or val > 50:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقم صحيح بين 2 و 50")
        return GRID_STEPS

    context.user_data["steps"] = val
    await update.message.reply_text(
        f"✅ الخطوات: `{val}`\n\n"
        "🔲 *الخطوة 5/7* — حجم الشبكة الكلي بالـ USDT:\n"
        "مثال: `100` يعني 100 USDT موزعة على كل الأوردرات",
        parse_mode="Markdown",
    )
    return GRID_SIZE


async def grid_size_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.strip())
        if val < 10:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ الحد الأدنى 10 USDT")
        return GRID_SIZE

    context.user_data["order_size_usdt"] = val
    await update.message.reply_text(
        f"✅ الحجم: `${val:.0f} USDT`\n\n"
        "🔲 *الخطوة 6/7* — Take Profit (اختياري):\n"
        "أرسل النسبة المئوية للربح المستهدف\n"
        "مثال: `5` يعني أغلق الشبكة لما السعر يرتفع 5%\n"
        "أو أرسل /skip للتخطي",
        parse_mode="Markdown",
    )
    return GRID_TP


async def grid_tp_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.strip().replace("%", ""))
        if val <= 0 or val > 1000:
            raise ValueError
        context.user_data["take_profit_pct"] = val
    except ValueError:
        await update.message.reply_text("❌ أدخل نسبة صحيحة مثال: `5` أو /skip")
        return GRID_TP

    await update.message.reply_text(
        f"✅ Take Profit: `+{val}%`\n\n"
        "🔲 *الخطوة 7/7* — Stop Loss (اختياري):\n"
        "أرسل النسبة المئوية لوقف الخسارة\n"
        "مثال: `5` يعني أغلق الشبكة لما السعر ينزل 5%\n"
        "أو أرسل /skip للتخطي",
        parse_mode="Markdown",
    )
    return GRID_SL


async def grid_tp_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["take_profit_pct"] = None
    await update.message.reply_text(
        "✅ بدون Take Profit\n\n"
        "🔲 *الخطوة 7/7* — Stop Loss (اختياري):\n"
        "أرسل النسبة المئوية لوقف الخسارة\n"
        "مثال: `5` يعني أغلق الشبكة لما السعر ينزل 5%\n"
        "أو أرسل /skip للتخطي",
        parse_mode="Markdown",
    )
    return GRID_SL


async def grid_sl_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.strip().replace("%", ""))
        if val <= 0 or val > 100:
            raise ValueError
        context.user_data["stop_loss_pct"] = val
    except ValueError:
        await update.message.reply_text("❌ أدخل نسبة صحيحة مثال: `5` أو /skip")
        return GRID_SL

    return await _show_confirmation(update, context)


async def grid_sl_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["stop_loss_pct"] = None
    return await _show_confirmation(update, context)


async def _show_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = context.user_data
    tp_line = f"🎯 Take Profit: `+{d['take_profit_pct']}%`\n" if d.get("take_profit_pct") else "🎯 Take Profit: بدون\n"
    sl_line = f"🛑 Stop Loss:   `-{d['stop_loss_pct']}%`\n"  if d.get("stop_loss_pct")   else "🛑 Stop Loss:   بدون\n"

    text = (
        "📋 *تأكيد إنشاء الشبكة*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"العملة:       `{d['symbol']}`\n"
        f"فوق:          `+{d['upper_pct']}%`\n"
        f"تحت:          `-{d['lower_pct']}%`\n"
        f"الخطوات:      `{d['steps']}`\n"
        f"الحجم:        `${d['order_size_usdt']:.0f} USDT`\n"
        f"{tp_line}{sl_line}"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "هل تريد تأكيد إنشاء الشبكة؟"
    )
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ تأكيد", callback_data="grid_confirm"),
                InlineKeyboardButton("❌ إلغاء", callback_data="grid_cancel"),
            ]
        ]),
    )
    return GRID_CONFIRM


async def grid_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    d = context.user_data

    await query.edit_message_text("⏳ جاري إنشاء الشبكة وتنفيذ الأوردرات...")

    settings = await db.get_settings(user_id)
    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])

    try:
        # Get current price
        ticker = await client.exchange.fetch_ticker(d["symbol"])
        center = float(ticker.get("last") or 0)
        if center <= 0:
            await query.edit_message_text("❌ تعذّر جلب السعر الحالي. حاول مرة أخرى.")
            return ConversationHandler.END

        # ── Balance check ──────────────────────────────────────────────────
        try:
            balance = await client.exchange.fetch_balance()
            usdt_balance = float(balance.get("total", {}).get("USDT", 0) or 0)
        except Exception:
            usdt_balance = 0.0

        if usdt_balance < d["order_size_usdt"]:
            await query.edit_message_text(
                f"❌ *رصيد غير كافٍ*\n\n"
                f"💰 رصيدك الحالي: `${usdt_balance:.2f} USDT`\n"
                f"📦 حجم الشبكة المطلوب: `${d['order_size_usdt']:.0f} USDT`\n\n"
                f"أضف رصيداً أو قلّل حجم الشبكة.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ رجوع", callback_data="grid:menu")
                ]]),
            )
            return ConversationHandler.END

        # ── Calculate TP/SL prices from percentages ────────────────────────
        take_profit = round(center * (1 + d["take_profit_pct"] / 100), 8) if d.get("take_profit_pct") else None
        stop_loss   = round(center * (1 - d["stop_loss_pct"]   / 100), 8) if d.get("stop_loss_pct")   else None

        # Calculate grid
        grid_levels = calculate_grid_levels(
            center_price = center,
            upper_pct    = d["upper_pct"],
            lower_pct    = d["lower_pct"],
            steps        = d["steps"],
        )

        # Place orders — initial=True: market buy half + limit orders for both sides
        result = await place_grid_orders(
            exchange        = client.exchange,
            symbol          = d["symbol"],
            grid            = grid_levels,
            order_size_usdt = d["order_size_usdt"],
            initial         = True,
        )

        # ── If all orders failed → don't save ─────────────────────────────
        buy_count  = len(result["buy_orders"])
        sell_count = len(result["sell_orders"])
        err_count  = len(result["errors"])

        if buy_count == 0 and sell_count == 0:
            err_sample = result["errors"][0] if result["errors"] else "خطأ غير معروف"
            await query.edit_message_text(
                f"❌ *فشل تنفيذ الشبكة*\n\n"
                f"تعذّر وضع أي أوردر.\n"
                f"السبب: `{err_sample}`\n\n"
                f"تأكد من صحة الـ API key وأن الرصيد كافٍ.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ رجوع", callback_data="grid:menu")
                ]]),
            )
            return ConversationHandler.END

        # Save to DB
        tp_pct = d.get("take_profit_pct")
        sl_pct = d.get("stop_loss_pct")
        grid = {
            "user_id":         user_id,
            "symbol":          d["symbol"],
            "center":          center,
            "upper":           grid_levels["upper"],
            "lower":           grid_levels["lower"],
            "upper_pct":       d["upper_pct"],
            "lower_pct":       d["lower_pct"],
            "steps":           d["steps"],
            "step_pct":        grid_levels["step_pct"],
            "order_size_usdt": d["order_size_usdt"],
            "take_profit":     take_profit,
            "stop_loss":       stop_loss,
            "buy_orders":      result["buy_orders"],
            "sell_orders":     result["sell_orders"],
            "total_trades":    0,
            "shifts":          0,
            "mexc_api_key":    settings["mexc_api_key"],
            "mexc_secret_key": settings["mexc_secret_key"],
        }

        grid_id = await db.save_grid(grid)
        grid["id"] = grid_id
        await grid_monitor.add_grid(grid)

        tp_line = f"🎯 Take Profit: `${take_profit:.6g}`  (`+{tp_pct}%`)\n" if take_profit else ""
        sl_line = f"🛑 Stop Loss:   `${stop_loss:.6g}`  (`-{sl_pct}%`)\n"   if stop_loss  else ""
        mkt_qty = result.get("market_buy_qty", 0)
        mkt_line = f"🛒 شراء فوري بالسوق: `{mkt_qty:.6g}` وحدة\n" if mkt_qty > 0 else ""

        await query.edit_message_text(
            f"✅ *الشبكة شغالة!*\n\n"
            f"📌 `{d['symbol']}`\n"
            f"السعر الحالي: `${center:.6g}`\n"
            f"الحد العلوي:  `${grid_levels['upper']:.6g}`\n"
            f"الحد السفلي:  `${grid_levels['lower']:.6g}`\n"
            f"ربح كل خطوة: `{grid_levels['step_pct']:.3f}%`\n"
            f"{tp_line}{sl_line}\n"
            f"{mkt_line}"
            f"أوردرات شراء:  `{buy_count}`\n"
            f"أوردرات بيع:   `{sell_count}`\n"
            + (f"⚠️ أخطاء جزئية: `{err_count}`\n" if err_count else ""),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ القائمة", callback_data="grid:menu")
            ]]),
        )

    except Exception as e:
        logger.error(f"Grid confirm error: {e}")
        await query.edit_message_text(f"❌ خطأ: {str(e)[:100]}")
    finally:
        await client.close()

    context.user_data.clear()
    return ConversationHandler.END


async def grid_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text(
        "❌ تم إلغاء إنشاء الشبكة.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ القائمة", callback_data="grid:menu")
        ]]),
    )
    return ConversationHandler.END


async def grid_cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ تم الإلغاء.")
    return ConversationHandler.END


# ── Monitor job ────────────────────────────────────────────────────────────────

async def run_grid_monitor(app) -> None:
    """Called every 30 seconds by the scheduler."""
    if not grid_monitor.active_grids:
        return

    from bot.mexc_client import MexcClient as _MC
    import ccxt.async_support as ccxt

    def _exchange_factory(api_key, secret):
        return ccxt.mexc({
            "apiKey": api_key,
            "secret": secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })

    await grid_monitor.check_all(_exchange_factory, app.bot)


# ── Conversation handler builder ───────────────────────────────────────────────

def build_grid_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(grid_new_callback, pattern="^grid_new$")],
        states={
            GRID_SYMBOL:  [MessageHandler(TEXT, grid_symbol_input)],
            GRID_UPPER:   [MessageHandler(TEXT, grid_upper_input)],
            GRID_LOWER:   [MessageHandler(TEXT, grid_lower_input)],
            GRID_STEPS:   [MessageHandler(TEXT, grid_steps_input)],
            GRID_SIZE:    [MessageHandler(TEXT, grid_size_input)],
            GRID_TP:      [
                MessageHandler(TEXT, grid_tp_input),
                CommandHandler("skip", grid_tp_skip),
            ],
            GRID_SL:      [
                MessageHandler(TEXT, grid_sl_input),
                CommandHandler("skip", grid_sl_skip),
            ],
            GRID_CONFIRM: [
                CallbackQueryHandler(grid_confirm_callback, pattern="^grid_confirm$"),
                CallbackQueryHandler(grid_cancel_callback,  pattern="^grid_cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", grid_cancel_conv),
            CallbackQueryHandler(grid_cancel_callback, pattern="^grid_cancel$"),
        ],
        conversation_timeout=600,
    )
