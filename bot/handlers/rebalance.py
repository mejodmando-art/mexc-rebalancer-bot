import asyncio
import time
from telegram import Update
from telegram.ext import ContextTypes
from bot.database import db
from bot.keyboards import main_menu_kb, rebalance_confirm_kb, rebalance_dry_kb
from bot.mexc_client import MexcClient
from bot.rebalancer import calculate_trades
from datetime import datetime, timezone

# Pending trades expire after 3 minutes — prices may have moved significantly
_PENDING_TTL_SECONDS = 180


async def rebalance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1] if ":" in query.data else "check"
    user_id = update.effective_user.id

    if action == "check":
        await query.edit_message_text("⏳ جاري تحليل المحفظة...")
        settings = await db.get_settings(user_id)
        if not settings or not settings.get("mexc_api_key"):
            await query.edit_message_text(
                "❌ يجب ربط مفاتيح MEXC API أولاً.", reply_markup=main_menu_kb()
            )
            return

        portfolio_id = await db.ensure_active_portfolio(user_id)
        portfolio_info = await db.get_portfolio(portfolio_id)
        allocations = await db.get_portfolio_allocations(portfolio_id)

        if not allocations:
            await query.edit_message_text(
                f"❌ لا يوجد توزيع في محفظة *{portfolio_info.get('name', '')}*.\n"
                "اذهب إلى 🛠 الإعدادات ← إضافة العملات.",
                parse_mode="Markdown",
                reply_markup=main_menu_kb(),
            )
            return

        client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
        try:
            portfolio, total_usdt = await asyncio.wait_for(client.get_portfolio(), timeout=20)
        except asyncio.TimeoutError:
            await query.edit_message_text("❌ انتهت المهلة — MEXC لم يستجب. حاول مجدداً.", reply_markup=main_menu_kb())
            return
        except Exception as e:
            await query.edit_message_text(f"❌ خطأ: {str(e)[:100]}", reply_markup=main_menu_kb())
            return
        finally:
            await client.close()

        capital = portfolio_info.get("capital_usdt", 0.0)

        # Calculate the value of only the coins in this portfolio's allocation.
        # This isolates each portfolio so rebalancing doesn't bleed into coins
        # belonging to other portfolios or grid bots.
        alloc_symbols = {a["symbol"] for a in allocations}
        portfolio_value = sum(
            portfolio.get(sym, {}).get("value_usdt", 0.0)
            for sym in alloc_symbols
        )
        # Also include USDT that belongs to this portfolio's capital budget
        usdt_in_account = portfolio.get("USDT", {}).get("value_usdt", 0.0)

        # Use the portfolio's own coin values + proportional USDT share.
        # If a capital budget is set, cap at that budget; otherwise use the
        # actual value of the portfolio's coins.
        if capital > 0:
            effective_total = min(capital, portfolio_value + usdt_in_account)
        else:
            effective_total = portfolio_value + usdt_in_account

        # Fallback: if portfolio coins have no value yet (all USDT), use total
        if effective_total < 1.0 and total_usdt >= 1.0:
            effective_total = min(capital, total_usdt) if capital > 0 else total_usdt

        # Block execution if the account is essentially empty (< $1)
        if effective_total < 1.0:
            await query.edit_message_text(
                "⚠️ *رصيد غير كافٍ*\n\n"
                f"إجمالي الحساب: `${total_usdt:.2f}`\n\n"
                "يجب أن يكون الرصيد أكبر من $1 لتنفيذ أي عملية توازن.",
                parse_mode="Markdown",
                reply_markup=main_menu_kb(),
            )
            return

        # Validate allocations sum to ~100% before proceeding
        total_pct = sum(a["target_percentage"] for a in allocations)
        if abs(total_pct - 100) > 1.0:
            await query.edit_message_text(
                "⚠️ *التوزيع غير صحيح*\n\n"
                f"مجموع النسب الحالي: `{total_pct:.1f}%`\n"
                "يجب أن يكون المجموع 100% قبل تنفيذ التوازن.\n\n"
                "اذهب إلى 🛠 الإعدادات ← إضافة / تعديل عملة لتصحيح النسب.",
                parse_mode="Markdown",
                reply_markup=main_menu_kb(),
            )
            return

        # Per-portfolio threshold takes priority over the global user setting
        threshold = float(portfolio_info.get("threshold") or settings.get("threshold") or 5.0)
        trades, drift_report = calculate_trades(portfolio, effective_total, allocations, threshold)

        context.user_data["_pending_trades"] = trades
        context.user_data["_pending_portfolio_id"] = portfolio_id
        context.user_data["_pending_total"] = effective_total
        context.user_data["_pending_ts"] = time.monotonic()

        portfolio_name = portfolio_info.get("name", "")
        text = (
            f"⚖️ *تحليل إعادة التوازن*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🗂 *{portfolio_name}*\n"
            f"💰 قيمة المحفظة: `${effective_total:,.2f}`\n"
            f"🏦 إجمالي الحساب: `${total_usdt:,.2f}`\n"
            f"🎯 حد الانحراف: `{threshold}%`\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *تقرير الانحراف*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
        )

        for d in drift_report:
            if d["needs_action"]:
                arrow = "🔴" if d["drift_pct"] > 0 else "🟢"
                action_label = "بيع" if d["drift_pct"] > 0 else "شراء"
                text += (
                    f"{arrow} `{d['symbol']:<6}` "
                    f"`{d['current_pct']:.1f}%` → `{d['target_pct']:.1f}%`  "
                    f"`{d['drift_pct']:+.1f}%` ← {action_label}\n"
                )
            else:
                text += (
                    f"✅ `{d['symbol']:<6}` "
                    f"`{d['current_pct']:.1f}%` → `{d['target_pct']:.1f}%`  "
                    f"`{d['drift_pct']:+.1f}%`\n"
                )

        if not trades:
            text += "\n━━━━━━━━━━━━━━━━━━━━━\n✅ *المحفظة متوازنة — لا حاجة لأي إجراء*"
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=rebalance_dry_kb())
            return

        total_trade = sum(t["usdt_amount"] for t in trades)
        text += f"━━━━━━━━━━━━━━━━━━━━━\n"
        text += f"💡 *الصفقات المطلوبة \\({len(trades)}\\)*\n"
        text += "━━━━━━━━━━━━━━━━━━━━━\n"
        for t in trades:
            emoji = "🔴 بيع" if t["action"] == "sell" else "🟢 شراء"
            text += f"{emoji}  `{t['symbol']}`  `${t['usdt_amount']:.2f}`\n"
        text += f"━━━━━━━━━━━━━━━━━━━━━\n"
        text += f"💵 إجمالي التداول: `${total_trade:.2f}`"

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=rebalance_confirm_kb())

    elif action == "execute":
        trades = context.user_data.get("_pending_trades", [])
        pending_ts = context.user_data.get("_pending_ts", 0)

        if not trades:
            await query.edit_message_text("❌ انتهت الجلسة. أعد التحقق أولاً.", reply_markup=main_menu_kb())
            return

        # Reject stale analysis — prices may have moved significantly
        if time.monotonic() - pending_ts > _PENDING_TTL_SECONDS:
            context.user_data.pop("_pending_trades", None)
            context.user_data.pop("_pending_portfolio_id", None)
            context.user_data.pop("_pending_ts", None)
            await query.edit_message_text(
                "⚠️ *انتهت صلاحية التحليل*\n\n"
                "مرّت أكثر من 3 دقائق منذ آخر تحليل.\n"
                "أسعار السوق تغيّرت — أعد التحقق أولاً.",
                parse_mode="Markdown",
                reply_markup=main_menu_kb(),
            )
            return

        await query.edit_message_text("⏳ جاري تنفيذ الصفقات...")
        settings = await db.get_settings(user_id)

        # Guard: user may have deleted API keys between check and execute
        if not settings or not settings.get("mexc_api_key"):
            await query.edit_message_text(
                "❌ مفاتيح API غير موجودة. أضفها من الإعدادات أولاً.",
                reply_markup=main_menu_kb(),
            )
            return

        client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])

        try:
            results = await client.execute_rebalance(trades)
        except Exception as e:
            await query.edit_message_text(
                f"❌ خطأ أثناء التنفيذ: {str(e)[:100]}", reply_markup=main_menu_kb()
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

        text = "✅ *اكتملت إعادة التوازن*\n"
        text += "━━━━━━━━━━━━━━━━━━━━━\n"
        for r in ok:
            a = "🔴 بيع" if r["action"] == "sell" else "🟢 شراء"
            text += f"{a}  `{r['symbol']}`  `${r.get('usdt', 0):.2f}`  ✅\n"
        for r in err:
            text += f"❌  `{r['symbol']}`: {r.get('reason', 'خطأ')[:50]}\n"
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
        portfolio_id = context.user_data.get("_pending_portfolio_id")
        await db.add_history(user_id, now, summary, total_traded, 1 if not err else 0,
                             portfolio_id=portfolio_id)

        context.user_data.pop("_pending_trades", None)
        context.user_data.pop("_pending_portfolio_id", None)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_kb())



