"""
Smart Portfolio — Bitget-compatible auto-rebalancing bot.

Rebalance modes
---------------
proportional  Rebalance when any coin drifts beyond the configured threshold
              (1 %, 3 %, or 5 %).
timed         Rebalance on a fixed schedule (daily / weekly / monthly),
              regardless of price movement.
unbalanced    No automatic rebalancing; the user intervenes manually.

Other features
--------------
- 2–10 coins per portfolio, allocations must sum to 100 %.
- Equal-distribution helper divides 100 % evenly across all coins.
- Investment amount in USDT; optional sell-at-termination and
  enable-asset-transfer flags.
- Spot only; standard MEXC taker fee (0.1 %) applied to buy orders.
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

import ccxt.async_support as ccxt
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("smart_portfolio")

# ── Constants ──────────────────────────────────────────────────────────────────

CONFIG_PATH = os.environ.get("SP_CONFIG", "smart_portfolio_config.json")
MEXC_API_KEY = os.environ.get("MEXC_API_KEY", "")
MEXC_SECRET_KEY = os.environ.get("MEXC_SECRET_KEY", "")

ALLOWED_THRESHOLDS = [1, 3, 5]          # proportional mode
ALLOWED_INTERVALS = ["daily", "weekly", "monthly"]
MIN_COINS = 2
MAX_COINS = 10
TAKER_FEE = 0.001                        # 0.1 % MEXC spot taker fee
MIN_TRADE_USDT = 1.0

# ── Config loader ──────────────────────────────────────────────────────────────


def load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    _validate_config(cfg)
    return cfg


def _validate_config(cfg: dict) -> None:
    """Raise ValueError for any invalid setting."""
    portfolio = cfg.get("portfolio", {})
    coins: List[dict] = portfolio.get("coins", [])

    if not (MIN_COINS <= len(coins) <= MAX_COINS):
        raise ValueError(
            f"عدد العملات يجب أن يكون بين {MIN_COINS} و{MAX_COINS}، "
            f"الحالي: {len(coins)}"
        )

    total_pct = sum(c["target_percentage"] for c in coins)
    if abs(total_pct - 100.0) > 0.5:
        raise ValueError(
            f"مجموع النسب يجب أن يكون 100%، الحالي: {total_pct:.2f}%"
        )

    mode = cfg.get("rebalance_mode", "")
    if mode not in ("proportional", "timed", "unbalanced"):
        raise ValueError(f"وضع إعادة التوازن غير صحيح: {mode}")

    if mode == "proportional":
        threshold = cfg.get("proportional", {}).get("deviation_threshold_pct")
        if threshold not in ALLOWED_THRESHOLDS:
            raise ValueError(
                f"عتبة الانحراف يجب أن تكون إحدى القيم {ALLOWED_THRESHOLDS}، "
                f"الحالية: {threshold}"
            )

    if mode == "timed":
        interval = cfg.get("timed", {}).get("interval")
        if interval not in ALLOWED_INTERVALS:
            raise ValueError(
                f"الفاصل الزمني يجب أن يكون إحدى القيم {ALLOWED_INTERVALS}، "
                f"الحالي: {interval}"
            )

    investment = cfg.get("investment", {})
    if investment.get("total_usdt", 0) <= 0:
        raise ValueError("مبلغ الاستثمار يجب أن يكون أكبر من صفر")

    if cfg.get("trading", {}).get("futures_enabled", False):
        raise ValueError("هذا النظام يدعم Spot فقط — futures_enabled يجب أن يكون false")


# ── Equal-distribution helper ──────────────────────────────────────────────────


def apply_equal_distribution(coins: List[str]) -> List[dict]:
    """Divide 100 % evenly; last coin absorbs rounding remainder."""
    n = len(coins)
    pct = round(100.0 / n, 4)
    result = [{"symbol": s, "target_percentage": pct} for s in coins]
    diff = round(100.0 - sum(r["target_percentage"] for r in result), 4)
    result[-1]["target_percentage"] = round(result[-1]["target_percentage"] + diff, 4)
    return result


# ── Drift / trade calculation ──────────────────────────────────────────────────


def calculate_trades(
    portfolio: Dict[str, dict],
    total_usdt: float,
    allocations: List[dict],
    threshold_pct: float,
) -> Tuple[List[dict], List[dict]]:
    """
    Returns (trades, drift_report).

    trades       list of {symbol, action, usdt_amount, drift_pct}
    drift_report list of {symbol, current_pct, target_pct, drift_pct, needs_action}
    """
    if total_usdt <= 0 or not allocations:
        return [], []

    alloc_map = {a["symbol"]: a["target_percentage"] for a in allocations}
    drift_report: List[dict] = []
    trades: List[dict] = []

    for sym, target_pct in alloc_map.items():
        current_val = portfolio.get(sym, {}).get("value_usdt", 0.0)
        current_pct = (current_val / total_usdt) * 100
        drift = current_pct - target_pct
        drift_abs = abs(drift)
        needs_action = drift_abs >= threshold_pct

        drift_report.append({
            "symbol": sym,
            "current_pct": round(current_pct, 2),
            "target_pct": target_pct,
            "drift_pct": round(drift, 2),
            "drift_abs": round(drift_abs, 2),
            "needs_action": needs_action,
        })

        if needs_action:
            target_val = (target_pct / 100) * total_usdt
            diff_usdt = abs(target_val - current_val)
            if diff_usdt >= MIN_TRADE_USDT:
                action = "sell" if drift > 0 else "buy"
                # Inflate buy so the post-fee received amount matches the target.
                if action == "buy":
                    diff_usdt = diff_usdt / (1 - TAKER_FEE)
                trades.append({
                    "symbol": sym,
                    "action": action,
                    "usdt_amount": round(diff_usdt, 2),
                    "drift_pct": round(drift, 2),
                })

    drift_report.sort(key=lambda x: x["drift_abs"], reverse=True)
    return trades, drift_report


# ── MEXC exchange wrapper ──────────────────────────────────────────────────────


class SmartPortfolioExchange:
    def __init__(self, api_key: str, secret: str, quote: str = "USDT"):
        self.quote = quote
        self._exchange = ccxt.mexc({
            "apiKey": api_key,
            "secret": secret,
            "enableRateLimit": True,
            "timeout": 15000,
            "options": {"defaultType": "spot"},
        })

    async def get_portfolio(self) -> Tuple[Dict[str, dict], float]:
        """Return ({symbol: {amount, value_usdt, price}}, total_usdt)."""
        balance = await self._exchange.fetch_balance()
        totals = {k: float(v or 0) for k, v in balance["total"].items() if float(v or 0) > 1e-8}

        portfolio: Dict[str, dict] = {}
        total_usdt = 0.0
        holdings: Dict[str, float] = {}

        for sym, amount in totals.items():
            if sym == self.quote:
                portfolio[sym] = {"amount": amount, "value_usdt": amount, "price": 1.0}
                total_usdt += amount
            else:
                holdings[sym] = amount

        if holdings:
            pairs = [f"{s}/{self.quote}" for s in holdings]
            try:
                tickers = await self._exchange.fetch_tickers(pairs)
            except Exception:
                tickers = {}
                for s in holdings:
                    try:
                        t = await self._exchange.fetch_ticker(f"{s}/{self.quote}")
                        tickers[f"{s}/{self.quote}"] = t
                    except Exception:
                        pass

            for sym, amount in holdings.items():
                pair = f"{sym}/{self.quote}"
                ticker = tickers.get(pair, {})
                price = float(ticker.get("last") or ticker.get("close") or 0)
                if price <= 0:
                    continue
                val = amount * price
                if val < 1.0:
                    continue
                portfolio[sym] = {"amount": amount, "value_usdt": val, "price": price}
                total_usdt += val

        return portfolio, total_usdt

    async def execute_trades(self, trades: List[dict]) -> List[dict]:
        """Execute a list of buy/sell trades; return results."""
        if not trades:
            return []

        pairs = [f"{t['symbol']}/{self.quote}" for t in trades]
        try:
            tickers = await self._exchange.fetch_tickers(pairs)
        except Exception:
            tickers = {}

        results = []
        for trade in trades:
            sym = trade["symbol"]
            action = trade["action"]
            usdt_amt = trade["usdt_amount"]
            pair = f"{sym}/{self.quote}"
            try:
                ticker = tickers.get(pair, {})
                price = float(ticker.get("last") or 0)
                if not price:
                    t = await self._exchange.fetch_ticker(pair)
                    price = float(t.get("last") or 0)
                if not price:
                    raise ValueError("تعذّر جلب السعر")

                if action == "sell":
                    qty = usdt_amt / price
                    order = await self._exchange.create_market_sell_order(pair, qty)
                else:
                    order = await self._exchange.create_market_buy_order_with_cost(pair, usdt_amt)

                results.append({
                    "symbol": sym,
                    "action": action,
                    "status": "ok",
                    "usdt": usdt_amt,
                    "order_id": order.get("id"),
                })
            except Exception as e:
                results.append({
                    "symbol": sym,
                    "action": action,
                    "status": "error",
                    "reason": str(e)[:120],
                })

        return results

    async def sell_all_to_usdt(self, allocations: List[dict]) -> List[dict]:
        """
        Sell-at-termination: liquidate every coin in the portfolio to USDT.
        """
        portfolio, _ = await self.get_portfolio()
        trades = []
        for alloc in allocations:
            sym = alloc["symbol"]
            if sym == self.quote:
                continue
            holding = portfolio.get(sym, {})
            val = holding.get("value_usdt", 0.0)
            if val >= MIN_TRADE_USDT:
                trades.append({"symbol": sym, "action": "sell", "usdt_amount": round(val, 2)})

        return await self.execute_trades(trades)

    async def close(self):
        await self._exchange.close()


# ── Rebalance modes ────────────────────────────────────────────────────────────


class SmartPortfolio:
    """
    Orchestrates the three rebalance modes for a single portfolio.

    Usage
    -----
    sp = SmartPortfolio(config)
    await sp.run()          # blocking loop
    await sp.stop()         # graceful shutdown
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.mode: str = cfg["rebalance_mode"]
        self.investment: dict = cfg["investment"]
        self.portfolio_cfg: dict = cfg["portfolio"]
        self.allocations: List[dict] = self._build_allocations()
        self.total_usdt: float = self.investment["total_usdt"]
        self._running = False
        self._exchange: Optional[SmartPortfolioExchange] = None
        self._last_rebalance: Optional[datetime] = None

    # ── Allocation helpers ─────────────────────────────────────────────────────

    def _build_allocations(self) -> List[dict]:
        if self.portfolio_cfg.get("equal_distribution"):
            symbols = [c["symbol"] for c in self.portfolio_cfg["coins"]]
            return apply_equal_distribution(symbols)
        return list(self.portfolio_cfg["coins"])

    def update_allocations(self, new_allocations: List[dict]) -> None:
        """
        Hot-update coin allocations while the bot is running.
        Validates count and sum before applying.
        """
        if not (MIN_COINS <= len(new_allocations) <= MAX_COINS):
            raise ValueError(f"عدد العملات يجب بين {MIN_COINS} و{MAX_COINS}")
        total = sum(a["target_percentage"] for a in new_allocations)
        if abs(total - 100.0) > 0.5:
            raise ValueError(f"مجموع النسب يجب 100%، الحالي: {total:.2f}%")
        self.allocations = new_allocations
        log.info("تم تحديث توزيع العملات: %s", new_allocations)

    # ── Interval helpers ───────────────────────────────────────────────────────

    def _interval_elapsed(self) -> bool:
        """Return True if the timed interval has passed since last rebalance."""
        if self._last_rebalance is None:
            return True
        interval = self.cfg.get("timed", {}).get("interval", "daily")
        now = datetime.now(timezone.utc)
        delta_map = {
            "daily":   timedelta(days=1),
            "weekly":  timedelta(weeks=1),
            "monthly": timedelta(days=30),
        }
        return now - self._last_rebalance >= delta_map[interval]

    # ── Core rebalance logic ───────────────────────────────────────────────────

    async def _fetch_and_rebalance(self) -> dict:
        """
        Fetch live portfolio, compute trades, execute them.
        Returns a summary dict.
        """
        assert self._exchange is not None

        portfolio, account_total = await self._exchange.get_portfolio()

        # Restrict to coins in this portfolio's allocation
        alloc_symbols = {a["symbol"] for a in self.allocations}
        portfolio_slice = {s: d for s, d in portfolio.items() if s in alloc_symbols}
        usdt_balance = portfolio.get(self.portfolio_cfg.get("quote_currency", "USDT"), {}).get("value_usdt", 0.0)

        effective_total = sum(d["value_usdt"] for d in portfolio_slice.values()) + usdt_balance
        if self.total_usdt > 0:
            effective_total = min(self.total_usdt, effective_total)

        if effective_total < MIN_TRADE_USDT:
            return {"status": "skipped", "reason": "رصيد غير كافٍ", "total": effective_total}

        threshold = self.cfg.get("proportional", {}).get("deviation_threshold_pct", 5)
        trades, drift_report = calculate_trades(portfolio_slice, effective_total, self.allocations, threshold)

        if not trades:
            return {"status": "balanced", "drift_report": drift_report, "total": effective_total}

        results = await self._exchange.execute_trades(trades)
        ok = [r for r in results if r["status"] == "ok"]
        err = [r for r in results if r["status"] == "error"]
        traded = sum(t["usdt_amount"] for t in trades if any(r["symbol"] == t["symbol"] and r["status"] == "ok" for r in results))

        self._last_rebalance = datetime.now(timezone.utc)
        return {
            "status": "executed",
            "ok": len(ok),
            "errors": len(err),
            "traded_usdt": round(traded, 2),
            "drift_report": drift_report,
            "results": results,
        }

    # ── Run loop ───────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """
        Main loop.  Behaviour depends on rebalance_mode:

        proportional  — check every 5 minutes; rebalance if drift ≥ threshold.
        timed         — check every minute; rebalance when interval elapses.
        unbalanced    — no automatic action; loop idles until stop() is called.
        """
        api_key = MEXC_API_KEY or os.environ.get("MEXC_API_KEY", "")
        secret = MEXC_SECRET_KEY or os.environ.get("MEXC_SECRET_KEY", "")
        if not api_key or not secret:
            log.error("MEXC_API_KEY و MEXC_SECRET_KEY مطلوبان في متغيرات البيئة")
            return

        self._exchange = SmartPortfolioExchange(api_key, secret, self.portfolio_cfg.get("quote_currency", "USDT"))
        self._running = True

        log.info("Smart Portfolio بدأ — الوضع: %s", self.mode)
        log.info("العملات: %s", [f"{a['symbol']} {a['target_percentage']}%" for a in self.allocations])
        log.info("رأس المال: $%.2f USDT", self.total_usdt)

        try:
            while self._running:
                if self.mode == "proportional":
                    await self._run_proportional_tick()
                    await asyncio.sleep(300)          # check every 5 minutes

                elif self.mode == "timed":
                    await self._run_timed_tick()
                    await asyncio.sleep(60)           # check every minute

                elif self.mode == "unbalanced":
                    # Manual mode — bot is idle; user triggers rebalance externally
                    await asyncio.sleep(60)

        except asyncio.CancelledError:
            pass
        finally:
            await self._shutdown()

    async def _run_proportional_tick(self) -> None:
        """Check drift; rebalance only if any coin exceeds the threshold."""
        try:
            summary = await self._fetch_and_rebalance()
            if summary["status"] == "executed":
                log.info(
                    "إعادة توازن (نسبة): %d ناجح، %d خطأ، $%.2f USDT",
                    summary["ok"], summary["errors"], summary["traded_usdt"],
                )
            elif summary["status"] == "balanced":
                log.debug("المحفظة متوازنة — لا إجراء مطلوب")
            else:
                log.warning("تخطي: %s", summary.get("reason"))
        except Exception as e:
            log.error("خطأ في الوضع النسبي: %s", e)

    async def _run_timed_tick(self) -> None:
        """Rebalance when the configured interval has elapsed."""
        if not self._interval_elapsed():
            return
        try:
            summary = await self._fetch_and_rebalance()
            interval = self.cfg.get("timed", {}).get("interval", "daily")
            log.info(
                "إعادة توازن (%s): %s",
                interval,
                summary.get("status"),
            )
            if summary["status"] == "executed":
                log.info(
                    "  %d ناجح، %d خطأ، $%.2f USDT",
                    summary["ok"], summary["errors"], summary["traded_usdt"],
                )
        except Exception as e:
            log.error("خطأ في الوضع الزمني: %s", e)

    async def manual_rebalance(self) -> dict:
        """
        Trigger a one-shot rebalance in unbalanced mode (or any mode).
        Returns the summary dict from _fetch_and_rebalance.
        """
        if self._exchange is None:
            raise RuntimeError("البوت لم يبدأ بعد — استدعِ run() أولاً")
        log.info("إعادة توازن يدوية مطلوبة")
        return await self._fetch_and_rebalance()

    async def stop(self, sell_at_termination: bool = None) -> None:
        """
        Graceful shutdown.  If sell_at_termination is True (or set in config),
        liquidate all portfolio coins to USDT before closing.
        """
        self._running = False
        sell = sell_at_termination if sell_at_termination is not None else self.investment.get("sell_at_termination", False)

        if sell and self._exchange:
            log.info("بيع عند الإنهاء — تصفية جميع العملات إلى USDT...")
            try:
                results = await self._exchange.sell_all_to_usdt(self.allocations)
                ok = sum(1 for r in results if r["status"] == "ok")
                log.info("تمت التصفية: %d عملة بيعت", ok)
            except Exception as e:
                log.error("خطأ أثناء التصفية: %s", e)

        log.info("Smart Portfolio أوقف")

    async def _shutdown(self) -> None:
        if self._exchange:
            await self._exchange.close()
            self._exchange = None


# ── CLI entry point ────────────────────────────────────────────────────────────


async def _main() -> None:
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else CONFIG_PATH
    log.info("تحميل الإعدادات من: %s", cfg_path)
    cfg = load_config(cfg_path)

    sp = SmartPortfolio(cfg)

    loop = asyncio.get_running_loop()
    import signal

    def _handle_signal():
        log.info("إشارة إيقاف — جاري الإغلاق...")
        asyncio.ensure_future(sp.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    await sp.run()


if __name__ == "__main__":
    asyncio.run(_main())
