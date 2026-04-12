import logging
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bot.database import db
from bot.mexc_client import MexcClient
from bot.rebalancer import calculate_trades

logger = logging.getLogger(__name__)


async def auto_rebalance_job(app):
    """Run rebalance for each portfolio that has auto_enabled=1 and whose interval has elapsed."""
    portfolios = await db.get_all_portfolios_with_auto()
    now = datetime.now(timezone.utc)

    for row in portfolios:
        portfolio_id   = row["id"]
        user_id        = row["user_id"]
        interval_hours = int(row.get("auto_interval_hours") or 24)
        last_str       = row.get("last_rebalance_at")

        try:
            if last_str:
                try:
                    last_dt = datetime.fromisoformat(last_str.replace(" UTC", "+00:00"))
                    if now - last_dt < timedelta(hours=interval_hours):
                        continue  # interval not elapsed yet
                except Exception:
                    pass  # parse failure → run anyway

            await _do_rebalance(app, user_id, portfolio_id=portfolio_id, auto=True)

        except Exception as e:
            logger.error(f"Auto rebalance error portfolio={portfolio_id} user={user_id}: {e}")


async def _do_rebalance(app, user_id: int, portfolio_id: int = None, auto: bool = False):
    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        return

    if not portfolio_id:
        portfolio_id = await db.get_active_portfolio_id(user_id)
    if not portfolio_id:
        portfolio_id = await db.ensure_active_portfolio(user_id)

    allocations = await db.get_portfolio_allocations(portfolio_id)
    if not allocations:
        return

    portfolio_info = await db.get_portfolio(portfolio_id)

    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    try:
        full_portfolio, total_usdt = await client.get_portfolio()

        # فلترة العملات لهذه المحفظة فقط — يمنع تداخل المحافظ المتعددة
        alloc_symbols = {a["symbol"] for a in allocations}
        portfolio = {sym: data for sym, data in full_portfolio.items() if sym in alloc_symbols}

        # Per-portfolio threshold takes priority over the global user setting
        threshold = float(portfolio_info.get("threshold") or settings.get("threshold") or 5.0)

        # رأس المال المحدد للمحفظة هو الأساس — لا نستخدم إجمالي الحساب
        capital = portfolio_info.get("capital_usdt", 0.0) if portfolio_info else 0.0
        if capital > 0:
            effective_total = capital
        else:
            # إذا لم يُحدد رأس مال، استخدم قيمة عملات المحفظة فقط
            effective_total = sum(d.get("value_usdt", 0.0) for d in portfolio.values())
            if effective_total < 1.0:
                effective_total = total_usdt

        # Skip if account is essentially empty — notify the user so they know
        if effective_total < 1.0:
            try:
                await app.bot.send_message(
                    user_id,
                    "⚠️ *توازن تلقائي — رصيد غير كافٍ*\n\n"
                    f"إجمالي الحساب: `${total_usdt:.2f}`\n"
                    "يجب أن يكون الرصيد أكبر من $1 لتنفيذ التوازن التلقائي.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
            return

        # Skip if allocations don't sum to ~100%
        total_pct = sum(a["target_percentage"] for a in allocations)
        if abs(total_pct - 100) > 1.0:
            logger.warning(f"User {user_id}: allocations sum to {total_pct:.1f}%, skipping rebalance")
            return

        trades, _ = calculate_trades(portfolio, effective_total, allocations, threshold)

        if not trades:
            return

        results = await client.execute_rebalance(trades)

        # Update timestamp AFTER execution so a crash mid-trade doesn't silently
        # skip the next scheduled cycle.
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        await db.update_portfolio(portfolio_id, last_rebalance_at=now_str)
        ok  = sum(1 for r in results if r.get("status") == "ok")
        err = sum(1 for r in results if r.get("status") == "error")
        traded = sum(
            t["usdt_amount"] for t in trades
            if any(r["symbol"] == t["symbol"] and r.get("status") == "ok" for r in results)
        )

        summary = f"{'تلقائي' if auto else 'يدوي'}: {ok} ناجح، {err} خطأ"
        # portfolio_id was already fetched above — reuse it instead of querying again
        await db.add_history(user_id, now_str, summary, traded,
                             1 if err == 0 else 0, portfolio_id=portfolio_id)

        label = "🤖 توازن تلقائي" if auto else "⚖️ إعادة التوازن"
        lines = [
            f"{label}",
            "━━━━━━━━━━━━━━━━━━━━━",
            f"✅ ناجح: *{ok}* صفقة",
        ]
        if err:
            lines.append(f"❌ خطأ: *{err}*")
        lines.append(f"💵 إجمالي: `${traded:.2f}`")
        lines.append(f"🕐 `{now_str}`")
        await app.bot.send_message(user_id, "\n".join(lines), parse_mode="Markdown")
    finally:
        await client.close()


async def smart_portfolio_job(app):
    """
    Smart Portfolio scheduler — runs every 5 minutes.

    proportional  Rebalance when drift >= deviation_threshold_pct.
    timed         Rebalance when the configured interval (daily/weekly/monthly) has elapsed.
    unbalanced    No automatic action.
    """
    from smart_portfolio import SmartPortfolioExchange, calculate_trades

    rows = await db.get_all_running_smart_portfolios()
    now  = datetime.now(timezone.utc)

    INTERVAL_DELTA = {
        "daily":   timedelta(days=1),
        "weekly":  timedelta(weeks=1),
        "monthly": timedelta(days=30),
    }

    for row in rows:
        user_id = row["user_id"]
        mode    = row.get("rebalance_mode", "unbalanced")

        if mode == "unbalanced":
            continue  # manual only

        try:
            # ── Timed: check if interval elapsed ──────────────────────────────
            if mode == "timed":
                interval  = row.get("timed_interval", "weekly")
                last_str  = row.get("last_rebalance_at")
                delta     = INTERVAL_DELTA.get(interval, timedelta(weeks=1))
                if last_str:
                    try:
                        last_dt = datetime.fromisoformat(last_str.replace(" UTC", "+00:00"))
                        if now - last_dt < delta:
                            continue
                    except Exception:
                        pass  # parse failure → run anyway

            # ── Proportional: always fetch; skip if within threshold ───────────
            settings = await db.get_settings(user_id)
            if not settings or not settings.get("mexc_api_key"):
                continue

            coins = await db.get_sp_coins(user_id)
            if len(coins) < 2:
                continue

            total_pct = sum(c["target_percentage"] for c in coins)
            if abs(total_pct - 100) > 0.5:
                continue

            client = SmartPortfolioExchange(
                settings["mexc_api_key"], settings["mexc_secret_key"]
            )
            try:
                portfolio, _ = await client.get_portfolio()
            except Exception as e:
                logger.error("SP fetch error user=%s: %s", user_id, e)
                await client.close()
                continue

            capital = float(row.get("capital_usdt") or 0)
            alloc_symbols   = {c["symbol"] for c in coins}
            portfolio_slice = {s: d for s, d in portfolio.items() if s in alloc_symbols}
            usdt_val        = portfolio.get("USDT", {}).get("value_usdt", 0.0)
            effective       = sum(d["value_usdt"] for d in portfolio_slice.values()) + usdt_val
            if capital > 0:
                effective = min(capital, effective)

            if effective < 1.0:
                await client.close()
                continue

            threshold = float(row.get("deviation_threshold_pct") or 5)
            trades, _ = calculate_trades(portfolio_slice, effective, coins, threshold)

            if not trades:
                await client.close()
                continue

            results  = await client.execute_trades(trades)
            await client.close()

            ok  = sum(1 for r in results if r["status"] == "ok")
            err = sum(1 for r in results if r["status"] == "error")
            traded = sum(
                t["usdt_amount"] for t in trades
                if any(r["symbol"] == t["symbol"] and r["status"] == "ok" for r in results)
            )

            now_str = now.strftime("%Y-%m-%d %H:%M UTC")
            await db.update_smart_portfolio(user_id, last_rebalance_at=now_str)
            await db.add_sp_history(
                user_id, now_str,
                f"تلقائي ({mode}): {ok} ناجح، {err} خطأ",
                traded, 1 if err == 0 else 0,
            )

            mode_label = "📊 نسبة" if mode == "proportional" else "⏰ زمني"
            lines = [
                f"🤖 *Smart Portfolio — {mode_label}*",
                "━━━━━━━━━━━━━━━━━━━━━",
                f"✅ ناجح: *{ok}* صفقة",
            ]
            if err:
                lines.append(f"❌ خطأ: *{err}*")
            lines.append(f"💵 إجمالي: `${traded:.2f}`")
            lines.append(f"🕐 `{now_str}`")
            try:
                await app.bot.send_message(user_id, "\n".join(lines), parse_mode="Markdown")
            except Exception:
                pass

        except Exception as e:
            logger.error("SP job error user=%s: %s", user_id, e)


async def start_scheduler(app) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    # Check every hour; each user's own interval is respected inside the job
    scheduler.add_job(
        auto_rebalance_job,
        trigger="interval",
        hours=1,
        args=[app],
        id="auto_rebalance",
        replace_existing=True,
    )
    # Smart Portfolio: proportional checks every 5 min, timed checks every 5 min
    scheduler.add_job(
        smart_portfolio_job,
        trigger="interval",
        minutes=5,
        args=[app],
        id="smart_portfolio",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started")
    return scheduler
