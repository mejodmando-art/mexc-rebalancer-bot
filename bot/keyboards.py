from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 رصيد المحفظة",   callback_data="balance"),
            InlineKeyboardButton("⚖️ إعادة التوازن",  callback_data="rebalance:check"),
        ],
        [
            InlineKeyboardButton("⚡ Scalping",        callback_data="scalping:menu"),
            InlineKeyboardButton("🐋 Whale Strategy",  callback_data="whale:menu"),
        ],
        [
            InlineKeyboardButton("🔲 Grid Bot",        callback_data="grid:menu"),
            InlineKeyboardButton("🗂 محافظي",          callback_data="portfolios"),
        ],
        [
            InlineKeyboardButton("🚨 بيع طوارئ",       callback_data="emergency:menu"),
            InlineKeyboardButton("📋 السجل",           callback_data="history"),
        ],
        [
            InlineKeyboardButton("⚙️ الإعدادات",       callback_data="menu:settings"),
            InlineKeyboardButton("❓ كيف يعمل البوت",  callback_data="menu:info"),
        ],
    ])


def settings_kb(auto_enabled: bool = False) -> InlineKeyboardMarkup:
    auto_label = "🟢 إيقاف التوازن التلقائي" if auto_enabled else "🔴 تفعيل التوازن التلقائي"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 مفاتيح MEXC API",        callback_data="settings:set_api")],
        [InlineKeyboardButton("📊 عرض التوزيع الحالي",     callback_data="settings:view_allocs")],
        [InlineKeyboardButton("✏️ إضافة / تعديل عملة",    callback_data="settings:add_alloc")],
        [
            InlineKeyboardButton("🎯 حد الانحراف",         callback_data="settings:set_threshold"),
            InlineKeyboardButton("⏱ فترة التوازن",         callback_data="settings:set_interval"),
        ],
        [InlineKeyboardButton(auto_label,                  callback_data="toggle_auto")],
        [InlineKeyboardButton("◀️ رجوع",                   callback_data="menu:main")],
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


def rebalance_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تنفيذ الآن", callback_data="rebalance:execute"),
            InlineKeyboardButton("✖️ إلغاء", callback_data="menu:main"),
        ],
    ])


def rebalance_dry_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ القائمة الرئيسية", callback_data="menu:main")],
    ])


def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ القائمة الرئيسية", callback_data="menu:main")]
    ])


def back_to_settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ الإعدادات", callback_data="menu:settings")]
    ])


# ── Portfolio Keyboards ────────────────────────────────────────────────────────

def portfolios_list_kb(portfolios: List[Dict], active_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for p in portfolios:
        active_mark = "✅ " if p['id'] == active_id else ""
        label = f"{active_mark}{p['name']}  ·  ${p['capital_usdt']:,.0f}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"portfolio:{p['id']}")])
    buttons.append([InlineKeyboardButton("➕ محفظة جديدة",  callback_data="portfolio_new")])
    buttons.append([InlineKeyboardButton("◀️ رجوع",         callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def portfolio_actions_kb(portfolio_id: int, is_active: bool) -> InlineKeyboardMarkup:
    buttons = []
    if not is_active:
        buttons.append([InlineKeyboardButton("✅ تفعيل هذه المحفظة", callback_data=f"portfolio_switch:{portfolio_id}")])
    buttons.append([
        InlineKeyboardButton("✏️ تعديل الاسم",  callback_data=f"portfolio_edit_name:{portfolio_id}"),
        InlineKeyboardButton("💰 رأس المال",     callback_data=f"portfolio_edit_capital:{portfolio_id}"),
    ])
    buttons.append([
        InlineKeyboardButton("🔴 بيع الكل",     callback_data=f"portfolio_sell_all:{portfolio_id}"),
        InlineKeyboardButton("📊 بيع بنسبة",    callback_data=f"portfolio_rebalance_sell:{portfolio_id}"),
    ])
    buttons.append([InlineKeyboardButton("🔴 بيع عملة واحدة", callback_data=f"portfolio_sell_one:{portfolio_id}")])
    buttons.append([InlineKeyboardButton("🗑 حذف المحفظة",     callback_data=f"portfolio_delete:{portfolio_id}")])
    buttons.append([InlineKeyboardButton("◀️ رجوع",            callback_data="portfolios")])
    return InlineKeyboardMarkup(buttons)


def portfolio_sell_one_kb(portfolio_id: int, symbols: List[str]) -> InlineKeyboardMarkup:
    """Keyboard to pick a single coin to sell from a portfolio."""
    buttons = []
    row = []
    for i, sym in enumerate(symbols):
        row.append(InlineKeyboardButton(sym, callback_data=f"portfolio_sell_coin:{portfolio_id}:{sym}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("◀️ رجوع", callback_data=f"portfolio:{portfolio_id}")])
    return InlineKeyboardMarkup(buttons)


def portfolio_sell_confirm_kb(portfolio_id: int, action: str, symbol: str = "") -> InlineKeyboardMarkup:
    """Confirm/cancel sell action."""
    confirm_data = f"portfolio_sell_exec:{portfolio_id}:{action}:{symbol}"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تأكيد البيع", callback_data=confirm_data),
            InlineKeyboardButton("❌ إلغاء", callback_data=f"portfolio:{portfolio_id}"),
        ]
    ])


def portfolio_delete_confirm_kb(portfolio_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ نعم، احذف", callback_data=f"portfolio_delete_confirm:{portfolio_id}"),
            InlineKeyboardButton("✖️ إلغاء", callback_data=f"portfolio:{portfolio_id}"),
        ]
    ])
