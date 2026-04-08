from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict


# ── القائمة الرئيسية ───────────────────────────────────────────────────────────

def main_menu_kb() -> InlineKeyboardMarkup:
    """
    الواجهة الرئيسية = شاشة المحفظة النشطة مباشرة.
    هذا الـ keyboard يُستخدم فقط كـ fallback عند عدم وجود محفظة نشطة.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗂️  فتح المحفظة",  callback_data="home")],
        [InlineKeyboardButton("🔑  إعدادات API",   callback_data="menu:settings")],
    ])


# ── الإعدادات العامة ───────────────────────────────────────────────────────────

def settings_kb(auto_enabled: bool = False) -> InlineKeyboardMarkup:
    """إعدادات عامة — API keys فقط. إعدادات إعادة التوازن داخل شاشة المحفظة."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 مفاتيح MEXC API", callback_data="settings:set_api")],
        [InlineKeyboardButton("◀️ رجوع",             callback_data="menu:main")],
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

def rebalance_confirm_kb(portfolio_id: int = 0) -> InlineKeyboardMarkup:
    """
    زر التأكيد لإعادة التوازن.
    إذا أُعطي portfolio_id يُرسل pf_rebalance_exec:{id} (المسار الصحيح).
    وإلا يُرسل rebalance:execute للتوافق مع الكود القديم.
    """
    if portfolio_id:
        exec_data = f"pf_rebalance_exec:{portfolio_id}"
        cancel_data = f"portfolio:{portfolio_id}"
    else:
        exec_data = "rebalance:execute"
        cancel_data = "menu:main"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تنفيذ الآن", callback_data=exec_data),
            InlineKeyboardButton("✖️ إلغاء",      callback_data=cancel_data),
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
    """كل محفظة زر كامل العرض بأيقونة ملونة."""
    buttons = []
    icons = ["🟦", "🟩", "🟨", "🟧", "🟪", "🟥"]
    for i, p in enumerate(portfolios):
        icon = "✅" if p["id"] == active_id else icons[i % len(icons)]
        capital = f"${p['capital_usdt']:,.0f}" if p["capital_usdt"] > 0 else "بدون رأس مال"
        label = f"{icon}  {p['name']}  ·  {capital} USDT"
        buttons.append([InlineKeyboardButton(label, callback_data=f"portfolio:{p['id']}")])
    buttons.append([InlineKeyboardButton("➕  إنشاء محفظة جديدة", callback_data="portfolio_new")])
    buttons.append([InlineKeyboardButton("🔑  مفاتيح MEXC API",   callback_data="settings:set_api")])
    buttons.append([InlineKeyboardButton("◀️  رجوع",              callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def portfolio_actions_kb(
    portfolio_id: int,
    is_active: bool,
    auto_enabled: bool = False,
    allocations: List[Dict] = None,
    capital_usdt: float = 0.0,
    threshold: float = 5.0,
    auto_interval: int = 24,
) -> InlineKeyboardMarkup:
    """
    شاشة المحفظة الكاملة:
    - معلومات رأس المال + حد الانحراف في أزرار عرض
    - كل عملة = زر خارجي يعرض: 🪙 SYM  XX%  $YY.Y
    - زر إعادة التوازن بارز في المنتصف
    - باقي أزرار الإدارة في الأسفل
    """
    buttons = []

    # ── تفعيل المحفظة إذا لم تكن نشطة ──
    if not is_active:
        buttons.append([InlineKeyboardButton(
            "✅  تفعيل هذه المحفظة",
            callback_data=f"portfolio_switch:{portfolio_id}"
        )])

    # ── معلومات رأس المال وحد الانحراف (صف واحد للعرض) ──
    auto_icon = "🟢" if auto_enabled else "🔴"
    buttons.append([
        InlineKeyboardButton(f"🎯 حد الانحراف: {threshold:.0f}%",
                             callback_data=f"portfolio_set_threshold:{portfolio_id}"),
        InlineKeyboardButton(f"{auto_icon} تلقائي: {'شغّال' if auto_enabled else 'معطّل'}",
                             callback_data=f"portfolio_toggle_auto:{portfolio_id}"),
    ])

    # ── العملات كأزرار خارجية (عمودان) ──
    if allocations:
        coin_buttons = []
        for a in allocations:
            sym = a["symbol"]
            pct = a["target_percentage"]
            val = capital_usdt * pct / 100 if capital_usdt > 0 else 0.0
            val_str = f"${val:,.1f}" if val > 0 else f"{pct:.0f}%"
            label = f"🪙 {sym}   {pct:.0f}%   {val_str}"
            coin_buttons.append(
                InlineKeyboardButton(label, callback_data=f"portfolio_edit_allocs:{portfolio_id}")
            )

        # عمودان متساويان
        for i in range(0, len(coin_buttons), 2):
            row = coin_buttons[i:i + 2]
            buttons.append(row)

    # ── زر إعادة التوازن بارز (عرض كامل) ──
    buttons.append([InlineKeyboardButton(
        "🔄  إعادة التوازن الآن",
        callback_data=f"pf_rebalance:{portfolio_id}"
    )])

    # ── Momentum + Grid ──
    buttons.append([
        InlineKeyboardButton("⚡ Momentum\nاستراتيجية زخم",   callback_data="momentum:menu"),
        InlineKeyboardButton("🔲 Grid Bot\nأوامر تلقائية",    callback_data="grid:menu"),
    ])

    # ── رأس المال + تعديل عملات ──
    buttons.append([
        InlineKeyboardButton("💰  رأس المال",              callback_data=f"portfolio_edit_capital:{portfolio_id}"),
        InlineKeyboardButton("🎯  تعديل العملات",          callback_data=f"portfolio_edit_allocs:{portfolio_id}"),
    ])

    # ── بيع الكل + أهداف الربح ──
    buttons.append([
        InlineKeyboardButton("🔴  بيع الكل",               callback_data=f"portfolio_sell_all:{portfolio_id}"),
        InlineKeyboardButton("🏆  أهداف الربح / وقف الخسارة", callback_data=f"portfolio_tp_menu:{portfolio_id}"),
    ])

    # ── عملة واحدة + بيع عملة واحدة ──
    buttons.append([
        InlineKeyboardButton("🪙  إضافة عملة",             callback_data=f"portfolio_edit_allocs:{portfolio_id}"),
        InlineKeyboardButton("🗑  بيع عملة واحدة",         callback_data=f"portfolio_sell_one:{portfolio_id}"),
    ])

    # ── إعدادات متقدمة + حذف + رجوع ──
    buttons.append([
        InlineKeyboardButton("✏️  الاسم",        callback_data=f"portfolio_edit_name:{portfolio_id}"),
        InlineKeyboardButton("⏱  فترة التوازن", callback_data=f"portfolio_set_interval:{portfolio_id}"),
    ])
    buttons.append([
        InlineKeyboardButton("🗑  حذف المحفظة", callback_data=f"portfolio_delete:{portfolio_id}"),
        InlineKeyboardButton("◀️  رجوع",         callback_data="portfolios"),
    ])

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


# ── Grid ───────────────────────────────────────────────────────────────────────

def grid_menu_kb(grids: list) -> InlineKeyboardMarkup:
    """كل شبكة زر كامل العرض بأيقونة ملونة."""
    buttons = []
    icons = ["🟦", "🟩", "🟨", "🟧", "🟪", "🟥"]
    for i, g in enumerate(grids):
        icon = icons[i % len(icons)]
        trades = g.get("total_trades", 0)
        label = f"{icon}  {g['symbol']}  ·  {g['steps']} خطوة  ·  ${g['order_size_usdt']:.0f}  ·  🔄{trades}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"grid_detail:{g['id']}")])
    buttons.append([InlineKeyboardButton("➕  شبكة جديدة", callback_data="grid_new")])
    buttons.append([InlineKeyboardButton("◀️  رجوع",       callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def grid_detail_kb(grid_id: int) -> InlineKeyboardMarkup:
    """شاشة تفاصيل الشبكة — أزرار مربعة متساوية."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📡  متابعة حية",        callback_data=f"grid_live:{grid_id}")],
        [
            InlineKeyboardButton("🎯  تعديل TP/SL",    callback_data=f"grid_edit_tpsl:{grid_id}"),
            InlineKeyboardButton("📐  تعديل السلّم",   callback_data=f"grid_edit_range:{grid_id}"),
        ],
        [
            InlineKeyboardButton("➕  إضافة رصيد",     callback_data=f"grid_add_funds:{grid_id}"),
            InlineKeyboardButton("➖  سحب رصيد",       callback_data=f"grid_remove_funds:{grid_id}"),
        ],
        [InlineKeyboardButton("🛑  حذف الشبكة",        callback_data=f"grid_stop:{grid_id}")],
        [InlineKeyboardButton("◀️  رجوع",              callback_data="grid:menu")],
    ])


# ── Momentum ───────────────────────────────────────────────────────────────────

def momentum_menu_kb(enabled: bool, trade_size: float = 20.0,
                     max_trades: int = 3, daily_loss: float = 0.0) -> InlineKeyboardMarkup:
    """شاشة Momentum الرئيسية — كل الإعدادات في مكان واحد."""
    toggle = "🔴  إيقاف Momentum" if enabled else "🟢  تشغيل Momentum"
    loss_str = f"${daily_loss:.0f}" if daily_loss > 0 else "غير محدد"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle, callback_data="momentum:toggle")],
        [InlineKeyboardButton("📊  الصفقات المفتوحة",     callback_data="momentum:trades")],
        [InlineKeyboardButton("🔴  إغلاق صفقة يدوياً",   callback_data="momentum:sell_pick")],
        # ── الإعدادات مربعة متساوية ──
        [
            InlineKeyboardButton(f"💵  الحجم: ${trade_size:.0f}", callback_data="momentum:set_size"),
            InlineKeyboardButton(f"📊  أقصى: {max_trades} صفقة", callback_data="momentum:set_max"),
        ],
        [InlineKeyboardButton(f"🛑  حد الخسارة اليومي: {loss_str}", callback_data="momentum:set_loss")],
        [InlineKeyboardButton("◀️  رجوع", callback_data="menu:main")],
    ])


def momentum_settings_kb(trade_size: float, max_trades: int, daily_loss: float) -> InlineKeyboardMarkup:
    """للتوافق مع الكود القديم — يُعيد نفس momentum_menu_kb."""
    return momentum_menu_kb(True, trade_size, max_trades, daily_loss)
