from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict

# ── Coin logo emoji map ────────────────────────────────────────────────────────
# Maps well-known symbols to a distinctive emoji that visually represents the coin.
# Falls back to 🔹 for unknown symbols.
_COIN_EMOJI: Dict[str, str] = {
    "BTC":     "🟠",  # Bitcoin — orange
    "ETH":     "🔷",  # Ethereum — blue diamond
    "BNB":     "🟡",  # BNB — yellow
    "SOL":     "🟣",  # Solana — purple
    "XRP":     "🔵",  # XRP — blue
    "ADA":     "🔵",  # Cardano — blue
    "DOGE":    "🐶",  # Dogecoin
    "TRX":     "🔴",  # TRON — red
    "AVAX":    "🔺",  # Avalanche — red triangle
    "LINK":    "🔗",  # Chainlink
    "DOT":     "⚪",  # Polkadot
    "MATIC":   "🟣",  # Polygon — purple
    "POL":     "🟣",  # Polygon (new ticker)
    "LTC":     "⚫",  # Litecoin — grey
    "UNI":     "🦄",  # Uniswap
    "ATOM":    "⚛️",  # Cosmos
    "ICP":     "♾️",  # Internet Computer
    "NEAR":    "🟩",  # NEAR Protocol — green
    "ARB":     "🔵",  # Arbitrum — blue
    "OP":      "🔴",  # Optimism — red
    "FET":     "🤖",  # Fetch.ai
    "WLD":     "🌍",  # Worldcoin
    "SUI":     "🔵",  # Sui — blue
    "APT":     "⬛",  # Aptos
    "INJ":     "🔵",  # Injective
    "TIA":     "🌌",  # Celestia
    "VIRTUAL": "🟦",  # Virtual Protocol
    "CFX":     "🟠",  # Conflux
    "TAO":     "🧠",  # Bittensor
    "AITECH":  "🤖",  # Solidus AI Tech
    "AIA":     "💎",  # AIA Chain
    "COAI":    "🤖",  # CoAI
    "USDT":    "💵",  # Tether
    "USDC":    "💵",  # USD Coin
    "BUSD":    "💵",  # BUSD
}


def coin_emoji(symbol: str) -> str:
    """Return a distinctive emoji for a coin symbol, falling back to 🔹."""
    return _COIN_EMOJI.get(symbol.upper(), "🔹")


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


def auto_alloc_methods_kb(portfolio_id: int) -> InlineKeyboardMarkup:
    """أزرار اختيار طريقة التوزيع التلقائي."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "⚖️  توزيع متساوٍ",
            callback_data=f"auto_alloc:equal:{portfolio_id}"
        )],
        [InlineKeyboardButton(
            "📊  حسب حجم التداول (Volume)",
            callback_data=f"auto_alloc:volume:{portfolio_id}"
        )],
        [InlineKeyboardButton(
            "📈  حسب القيمة السوقية (Market Cap)",
            callback_data=f"auto_alloc:mcap:{portfolio_id}"
        )],
        [InlineKeyboardButton("◀️  رجوع", callback_data=f"portfolio:{portfolio_id}")],
    ])


def auto_alloc_confirm_kb(portfolio_id: int, method: str) -> InlineKeyboardMarkup:
    """تأكيد تطبيق التوزيع المحسوب."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅  تطبيق النسب",
                callback_data=f"auto_alloc_apply:{method}:{portfolio_id}"
            ),
            InlineKeyboardButton(
                "✖️  إلغاء",
                callback_data=f"portfolio:{portfolio_id}"
            ),
        ]
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


import os as _os
WEBAPP_URL = _os.environ.get("WEBAPP_URL", "").strip().rstrip("/") + "/"
if WEBAPP_URL == "/":
    # fallback: بناء الرابط من WEBHOOK_URL إذا لم يُحدَّد WEBAPP_URL صراحةً
    _base = _os.environ.get("WEBHOOK_URL", "").strip().rstrip("/")
    WEBAPP_URL = f"{_base}/webapp/" if _base else "https://example.com/webapp/"


def portfolio_actions_kb(
    portfolio_id: int,
    is_active: bool,
    auto_enabled: bool = False,
    allocations: List[Dict] = None,
    capital_usdt: float = 0.0,
    threshold: float = 5.0,
    auto_interval: int = 24,
) -> InlineKeyboardMarkup:
    from telegram import WebAppInfo
    buttons = []

    # ── زر فتح الواجهة الجديدة ──
    buttons.append([InlineKeyboardButton(
        "🌐  فتح الواجهة المرئية",
        web_app=WebAppInfo(url=WEBAPP_URL)
    )])

    # ── تفعيل المحفظة إذا لم تكن نشطة ──
    if not is_active:
        buttons.append([InlineKeyboardButton(
            "✅  تفعيل هذه المحفظة",
            callback_data=f"portfolio_switch:{portfolio_id}"
        )])

    # ── فولدر العملات (زر واحد يفتح القائمة) ──
    coin_count = len(allocations) if allocations else 0
    coins_label = f"🪙  العملات  ({coin_count})" if coin_count else "🪙  لا توجد عملات"
    buttons.append([
        InlineKeyboardButton(coins_label, callback_data=f"pf_alloc_list:{portfolio_id}"),
    ])

    # ── الإجراءات الرئيسية (نص عرض الشاشة) ──
    buttons.append([
        InlineKeyboardButton("🔄  إعادة التوازن", callback_data=f"pf_rebalance:{portfolio_id}"),
        InlineKeyboardButton("📊  الرصيد الحي",   callback_data=f"pf_balance:{portfolio_id}"),
    ])

    # ── إدارة العملات + توزيع ذكي ──
    buttons.append([
        InlineKeyboardButton("✏️  تعديل العملات", callback_data=f"portfolio_edit_allocs:{portfolio_id}"),
        InlineKeyboardButton("🤖  توزيع ذكي",     callback_data=f"auto_alloc_menu:{portfolio_id}"),
    ])

    # ── Grid Bot ──
    buttons.append([
        InlineKeyboardButton("🔲  Grid Bot", callback_data="grid:menu"),
    ])

    # ── رأس المال ──
    buttons.append([
        InlineKeyboardButton("💰  رأس المال", callback_data=f"portfolio_edit_capital:{portfolio_id}"),
    ])

    # ── بيع ──
    buttons.append([
        InlineKeyboardButton("🔴  بيع الكل",  callback_data=f"portfolio_sell_all:{portfolio_id}"),
        InlineKeyboardButton("🗑  بيع عملة",  callback_data=f"portfolio_sell_one:{portfolio_id}"),
    ])

    # ── حذف المحفظة ──
    buttons.append([
        InlineKeyboardButton("🗑  حذف المحفظة", callback_data=f"portfolio_delete:{portfolio_id}"),
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
