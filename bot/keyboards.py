from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict


# ── القائمة الرئيسية ───────────────────────────────────────────────────────────

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 المحفظة",        callback_data="balance"),
            InlineKeyboardButton("⚖️ إعادة التوازن",  callback_data="rebalance:check"),
        ],
        [
            InlineKeyboardButton("🗂 محافظي",          callback_data="portfolios"),
            InlineKeyboardButton("📋 السجل",           callback_data="history"),
        ],
        [
            InlineKeyboardButton("⚡ Scalping",        callback_data="scalping:menu"),
            InlineKeyboardButton("🐋 Whale",           callback_data="whale:menu"),
            InlineKeyboardButton("🔲 Grid",            callback_data="grid:menu"),
        ],
        [
            InlineKeyboardButton("🚨 بيع طوارئ",       callback_data="emergency:menu"),
            InlineKeyboardButton("⚙️ الإعدادات",       callback_data="menu:settings"),
        ],
    ])


# ── الإعدادات العامة ───────────────────────────────────────────────────────────

def settings_kb(auto_enabled: bool = False) -> InlineKeyboardMarkup:
    auto_label = "🟢 إيقاف التوازن التلقائي" if auto_enabled else "🔴 تفعيل التوازن التلقائي"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 مفاتيح MEXC API",        callback_data="settings:set_api")],
        [
            InlineKeyboardButton("📊 عرض التوزيع",          callback_data="settings:view_allocs"),
            InlineKeyboardButton("✏️ تعديل العملات",        callback_data="settings:add_alloc"),
        ],
        [
            InlineKeyboardButton("🎯 حد الانحراف",          callback_data="settings:set_threshold"),
            InlineKeyboardButton("⏱ فترة التوازن",          callback_data="settings:set_interval"),
        ],
        [InlineKeyboardButton(auto_label,                   callback_data="toggle_auto")],
        [InlineKeyboardButton("◀️ رجوع",                    callback_data="menu:main")],
    ])


def allocs_list_kb(allocations: List[Dict]) -> InlineKeyboardMarkup:
    buttons = []
    for a in allocations:
        buttons.append([
            InlineKeyboardButton(
                f"🗑  {a['symbol']}  ·  {a['target_percentage']:.1f}%",
                callback_data=f"del_alloc:{a['symbol']}",
            )
        ])
    buttons.append([InlineKeyboardButton("🧹 مسح جميع العملات", callback_data="clear_allocs")])
    buttons.append([InlineKeyboardButton("◀️ الإعدادات", callback_data="menu:settings")])
    return InlineKeyboardMarkup(buttons)


# ── إعادة التوازن ──────────────────────────────────────────────────────────────

def rebalance_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تنفيذ الآن", callback_data="rebalance:execute"),
            InlineKeyboardButton("✖️ إلغاء",      callback_data="menu:main"),
        ],
    ])


def rebalance_dry_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ القائمة الرئيسية", callback_data="menu:main")],
    ])


# ── أزرار عامة ────────────────────────────────────────────────────────────────

def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ القائمة الرئيسية", callback_data="menu:main")]
    ])


def back_to_settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ الإعدادات", callback_data="menu:settings")]
    ])


# ── المحافظ ────────────────────────────────────────────────────────────────────

def portfolios_list_kb(portfolios: List[Dict], active_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for p in portfolios:
        active_mark = "✅ " if p['id'] == active_id else ""
        label = f"{active_mark}{p['name']}  ·  ${p['capital_usdt']:,.0f}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"portfolio:{p['id']}")])
    buttons.append([InlineKeyboardButton("➕ محفظة جديدة", callback_data="portfolio_new")])
    buttons.append([InlineKeyboardButton("◀️ رجوع",        callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def portfolio_actions_kb(portfolio_id: int, is_active: bool, auto_enabled: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    if not is_active:
        buttons.append([InlineKeyboardButton("✅ تفعيل هذه المحفظة", callback_data=f"portfolio_switch:{portfolio_id}")])
    buttons.append([
        InlineKeyboardButton("✏️ الاسم",       callback_data=f"portfolio_edit_name:{portfolio_id}"),
        InlineKeyboardButton("💰 رأس المال",   callback_data=f"portfolio_edit_capital:{portfolio_id}"),
    ])
    buttons.append([InlineKeyboardButton("✏️ إضافة / تعديل عملة", callback_data=f"portfolio_edit_allocs:{portfolio_id}")])
    buttons.append([
        InlineKeyboardButton("⏱ فترة التوازن", callback_data=f"portfolio_set_interval:{portfolio_id}"),
        InlineKeyboardButton("🎯 حد الانحراف",  callback_data=f"portfolio_set_threshold:{portfolio_id}"),
    ])
    auto_label = "🟢 إيقاف التوازن التلقائي" if auto_enabled else "🔴 تفعيل التوازن التلقائي"
    buttons.append([InlineKeyboardButton(auto_label, callback_data=f"portfolio_toggle_auto:{portfolio_id}")])
    buttons.append([InlineKeyboardButton("🎯 أهداف الربح ووقف الخسارة", callback_data=f"portfolio_tp_menu:{portfolio_id}")])
    buttons.append([
        InlineKeyboardButton("🔴 بيع الكل",   callback_data=f"portfolio_sell_all:{portfolio_id}"),
        InlineKeyboardButton("📊 بيع بنسبة",  callback_data=f"portfolio_rebalance_sell:{portfolio_id}"),
    ])
    buttons.append([InlineKeyboardButton("🔴 بيع عملة واحدة", callback_data=f"portfolio_sell_one:{portfolio_id}")])
    buttons.append([InlineKeyboardButton("🗑 حذف المحفظة",     callback_data=f"portfolio_delete:{portfolio_id}")])
    buttons.append([InlineKeyboardButton("◀️ رجوع",            callback_data="portfolios")])
    return InlineKeyboardMarkup(buttons)


def portfolio_sell_one_kb(portfolio_id: int, symbols: List[str]) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for sym in symbols:
        row.append(InlineKeyboardButton(sym, callback_data=f"portfolio_sell_coin:{portfolio_id}:{sym}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("◀️ رجوع", callback_data=f"portfolio:{portfolio_id}")])
    return InlineKeyboardMarkup(buttons)


def portfolio_sell_confirm_kb(portfolio_id: int, action: str, symbol: str = "") -> InlineKeyboardMarkup:
    confirm_data = f"portfolio_sell_exec:{portfolio_id}:{action}:{symbol}"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تأكيد البيع", callback_data=confirm_data),
            InlineKeyboardButton("❌ إلغاء",       callback_data=f"portfolio:{portfolio_id}"),
        ]
    ])


def portfolio_delete_confirm_kb(portfolio_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ نعم، احذف", callback_data=f"portfolio_delete_confirm:{portfolio_id}"),
            InlineKeyboardButton("✖️ إلغاء",      callback_data=f"portfolio:{portfolio_id}"),
        ]
    ])


# ── Scalping ───────────────────────────────────────────────────────────────────

def scalping_menu_kb(enabled: bool) -> InlineKeyboardMarkup:
    toggle = "🔴 إيقاف Scalping" if enabled else "🟢 تشغيل Scalping"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle,                    callback_data="scalping:toggle")],
        [InlineKeyboardButton("📊 الصفقات المفتوحة",    callback_data="scalping:open_trades")],
        [InlineKeyboardButton("🔴 بيع صفقة",            callback_data="scalping:sell_pick")],
        [InlineKeyboardButton("⚙️ الإعدادات",           callback_data="scalping:settings")],
        [InlineKeyboardButton("◀️ رجوع",                callback_data="menu:main")],
    ])


def scalping_settings_kb(trade_size: float, max_trades: int,
                          daily_limit: float, trail_pct: float) -> InlineKeyboardMarkup:
    daily_str = f"${daily_limit:.0f}" if daily_limit > 0 else "غير محدد"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💵 حجم الصفقة: ${trade_size:.0f}",      callback_data="scalping:set_size")],
        [InlineKeyboardButton(f"📊 أقصى صفقات: {max_trades}",           callback_data="scalping:set_max_trades")],
        [InlineKeyboardButton(f"🛑 حد الخسارة اليومي: {daily_str}",     callback_data="scalping:set_daily_limit")],
        [InlineKeyboardButton(f"📉 Trailing Stop: {trail_pct:.1f}%",     callback_data="scalping:set_trail_pct")],
        [InlineKeyboardButton("◀️ رجوع",                                 callback_data="scalping:menu")],
    ])


# ── Whale ──────────────────────────────────────────────────────────────────────

def whale_menu_kb(enabled: bool) -> InlineKeyboardMarkup:
    toggle = "🔴 إيقاف Whale" if enabled else "🟢 تشغيل Whale"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle,                    callback_data="whale:toggle")],
        [InlineKeyboardButton("📊 الصفقات المفتوحة",    callback_data="whale:open_trades")],
        [InlineKeyboardButton("🔴 بيع صفقة",            callback_data="whale:sell_pick")],
        [InlineKeyboardButton("⚙️ الإعدادات",           callback_data="whale:settings")],
        [InlineKeyboardButton("◀️ رجوع",                callback_data="menu:main")],
    ])


def whale_settings_kb(trade_size: float, max_trades: int, daily_limit: float) -> InlineKeyboardMarkup:
    daily_str = f"${daily_limit:.0f}" if daily_limit > 0 else "غير محدد"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💵 حجم الصفقة: ${trade_size:.0f}",      callback_data="whale:set_size")],
        [InlineKeyboardButton(f"📊 أقصى صفقات: {max_trades}",           callback_data="whale:set_max_trades")],
        [InlineKeyboardButton(f"🛑 حد الخسارة اليومي: {daily_str}",     callback_data="whale:set_daily_limit")],
        [InlineKeyboardButton("◀️ رجوع",                                 callback_data="whale:menu")],
    ])


# ── Grid ───────────────────────────────────────────────────────────────────────

def grid_menu_kb(grids: list) -> InlineKeyboardMarkup:
    """grids: list of active grid dicts from db."""
    buttons = []
    for g in grids:
        buttons.append([InlineKeyboardButton(
            f"📊 {g['symbol']}  ·  {g['steps']} خطوة  ·  ${g['order_size_usdt']:.0f}",
            callback_data=f"grid_detail:{g['id']}"
        )])
    buttons.append([InlineKeyboardButton("➕ شبكة جديدة", callback_data="grid_new")])
    buttons.append([InlineKeyboardButton("◀️ رجوع",       callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def grid_detail_kb(grid_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 متابعة حية",   callback_data=f"grid_live:{grid_id}")],
        [InlineKeyboardButton("🛑 إيقاف الشبكة", callback_data=f"grid_stop:{grid_id}")],
        [InlineKeyboardButton("◀️ رجوع",         callback_data="grid:menu")],
    ])
