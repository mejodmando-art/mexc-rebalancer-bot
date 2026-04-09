"""
Flask API server — يعمل جنب البوت ويخدم الـ Web App.

Endpoints:
  GET  /api/portfolio          → رصيد المحفظة النشطة من MEXC
  GET  /api/portfolio/allocs   → توزيع العملات المستهدف
  POST /api/rebalance/preview  → حساب الصفقات المطلوبة (بدون تنفيذ)
  POST /api/rebalance/execute  → تنفيذ إعادة التوازن
  POST /api/sell_all           → بيع كل العملات
  GET  /api/grids              → قائمة Grid Bots
  GET  /api/health             → health check

الأمان: كل طلب يحتاج header  X-API-Key  يساوي WEB_APP_SECRET من .env
"""

import asyncio
import os
import time
import logging
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory

from bot.database import db
from bot.config import config
from bot.rebalancer import calculate_trades

logger = logging.getLogger(__name__)

_WEBAPP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "webapp")
app = Flask(__name__, static_folder=_WEBAPP_DIR, static_url_path="/webapp")

# ── Secret key للحماية ────────────────────────────────────────────────────────
_WEB_SECRET = os.environ.get("WEB_APP_SECRET", "").strip()

# ── CORS للـ Web App ──────────────────────────────────────────────────────────
@app.after_request
def _cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

@app.route("/", defaults={"path": ""}, methods=["OPTIONS"])
@app.route("/<path:path>", methods=["OPTIONS"])
def _preflight(path):
    return "", 204


# ── Auth decorator ────────────────────────────────────────────────────────────
def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if _WEB_SECRET:
            key = request.headers.get("X-API-Key", "")
            if key != _WEB_SECRET:
                return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


# ── Helper: run async in the bot's event loop ─────────────────────────────────
_bot_loop: asyncio.AbstractEventLoop | None = None

def set_bot_loop(loop: asyncio.AbstractEventLoop):
    global _bot_loop
    _bot_loop = loop

def _run(coro):
    """تشغيل coroutine في event loop البوت من thread Flask."""
    if _bot_loop is None:
        raise RuntimeError("Bot event loop not set")
    future = asyncio.run_coroutine_threadsafe(coro, _bot_loop)
    return future.result(timeout=30)


# ── Helper: جلب user_id الوحيد المسموح له ────────────────────────────────────
def _get_user_id() -> int:
    """
    Private mode: نستخدم أول user_id في ALLOWED_USER_IDS.
    لو مش موجود نرجع 0 (سيفشل لاحقاً بشكل واضح).
    """
    if config.allowed_user_ids:
        return config.allowed_user_ids[0]
    return 0


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "ts": int(time.time())})


@app.route("/api/config")
def get_config():
    """
    يعطي الـ Web App مفتاح الـ API عند التحميل.
    الصفحة على نفس الخادم فالمفتاح يُعاد دائماً.
    """
    return jsonify({"api_key": _WEB_SECRET})


@app.route("/api/portfolio")
@require_auth
def get_portfolio():
    """رصيد المحفظة النشطة من MEXC + بيانات التوزيع."""
    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "no allowed user configured"}), 500

    async def _fetch():
        portfolio_id = await db.ensure_active_portfolio(user_id)
        p = await db.get_portfolio(portfolio_id) if portfolio_id else None
        if not p:
            return {"error": "no active portfolio"}

        allocs   = await db.get_portfolio_allocations(portfolio_id)
        capital  = float(p.get("capital_usdt") or 0.0)
        settings = await db.get_settings(user_id)

        live_data = {}
        total_account = 0.0
        if settings and settings.get("mexc_api_key"):
            from bot.mexc_client import MexcClient
            client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
            try:
                live_data, total_account = await asyncio.wait_for(
                    client.get_portfolio(), timeout=15
                )
            except Exception as e:
                logger.warning("MEXC fetch error: %s", e)
            finally:
                await client.close()

        alloc_map = {a["symbol"]: a["target_percentage"] for a in allocs}
        effective = capital if capital > 0 else total_account

        coins = []
        for sym, data in sorted(live_data.items(), key=lambda x: x[1]["value_usdt"], reverse=True):
            val = data["value_usdt"]
            pct = (val / effective * 100) if effective > 0 else 0
            coins.append({
                "symbol":  sym,
                "value":   round(val, 2),
                "pct":     round(pct, 2),
                "target":  alloc_map.get(sym),
                "drift":   round(pct - alloc_map[sym], 2) if sym in alloc_map else None,
            })

        return {
            "portfolio_id":    portfolio_id,
            "name":            p["name"],
            "capital":         capital,
            "total_account":   round(total_account, 2),
            "coin_count":      len(allocs),
            "coins":           coins,
        }

    try:
        result = _run(_fetch())
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        logger.exception("get_portfolio error")
        return jsonify({"error": str(e)}), 500


@app.route("/api/portfolio/allocs")
@require_auth
def get_allocs():
    """قائمة العملات المستهدفة مع نسبها."""
    user_id = _get_user_id()

    async def _fetch():
        portfolio_id = await db.ensure_active_portfolio(user_id)
        if not portfolio_id:
            return {"error": "no active portfolio"}
        allocs = await db.get_portfolio_allocations(portfolio_id)
        return {"allocs": [{"symbol": a["symbol"], "target": a["target_percentage"]} for a in allocs]}

    try:
        return jsonify(_run(_fetch()))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/rebalance/preview", methods=["POST"])
@require_auth
def rebalance_preview():
    """حساب الصفقات المطلوبة بدون تنفيذ."""
    user_id = _get_user_id()

    async def _calc():
        portfolio_id = await db.ensure_active_portfolio(user_id)
        p = await db.get_portfolio(portfolio_id) if portfolio_id else None
        if not p:
            return {"error": "no active portfolio"}

        allocs   = await db.get_portfolio_allocations(portfolio_id)
        capital  = float(p.get("capital_usdt") or 0.0)
        threshold = float(p.get("threshold") or 5.0)
        settings = await db.get_settings(user_id)

        if not settings or not settings.get("mexc_api_key"):
            return {"error": "MEXC API keys not configured"}
        if not allocs:
            return {"error": "no allocations set"}

        from bot.mexc_client import MexcClient
        client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
        try:
            full_portfolio, total_account = await asyncio.wait_for(
                client.get_portfolio(), timeout=15
            )
        except Exception as e:
            return {"error": f"MEXC error: {e}"}
        finally:
            await client.close()

        alloc_symbols = {a["symbol"] for a in allocs}
        portfolio = {s: d for s, d in full_portfolio.items() if s in alloc_symbols}
        effective = capital if capital > 0 else sum(d["value_usdt"] for d in portfolio.values()) or total_account

        trades, drift = calculate_trades(portfolio, effective, allocs, threshold)

        return {
            "portfolio_id": portfolio_id,
            "total":        round(effective, 2),
            "threshold":    threshold,
            "trades":       trades,
            "drift":        drift,
            "ts":           int(time.time()),
        }

    try:
        result = _run(_calc())
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        logger.exception("rebalance_preview error")
        return jsonify({"error": str(e)}), 500


@app.route("/api/rebalance/execute", methods=["POST"])
@require_auth
def rebalance_execute():
    """تنفيذ إعادة التوازن — يحسب ثم ينفذ مباشرة."""
    user_id = _get_user_id()
    body    = request.get_json(silent=True) or {}
    # يقبل trades مرسلة من الـ preview أو يحسبها من جديد
    trades_in = body.get("trades")

    async def _exec():
        portfolio_id = await db.ensure_active_portfolio(user_id)
        p = await db.get_portfolio(portfolio_id) if portfolio_id else None
        if not p:
            return {"error": "no active portfolio"}

        settings = await db.get_settings(user_id)
        if not settings or not settings.get("mexc_api_key"):
            return {"error": "MEXC API keys not configured"}

        trades = trades_in
        if not trades:
            # احسب من جديد
            allocs    = await db.get_portfolio_allocations(portfolio_id)
            capital   = float(p.get("capital_usdt") or 0.0)
            threshold = float(p.get("threshold") or 5.0)
            from bot.mexc_client import MexcClient
            client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
            try:
                full_portfolio, total_account = await asyncio.wait_for(
                    client.get_portfolio(), timeout=15
                )
            except Exception as e:
                return {"error": f"MEXC error: {e}"}
            finally:
                await client.close()
            alloc_symbols = {a["symbol"] for a in allocs}
            portfolio = {s: d for s, d in full_portfolio.items() if s in alloc_symbols}
            effective = capital if capital > 0 else sum(d["value_usdt"] for d in portfolio.values()) or total_account
            trades, _ = calculate_trades(portfolio, effective, allocs, threshold)

        if not trades:
            return {"message": "المحفظة متوازنة بالفعل", "results": []}

        from bot.mexc_client import MexcClient
        client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
        try:
            results = await client.execute_rebalance(trades)
        except Exception as e:
            return {"error": f"execution error: {e}"}
        finally:
            await client.close()

        ok   = [r for r in results if r.get("status") == "ok"]
        err  = [r for r in results if r.get("status") == "error"]
        total_traded = sum(
            t["usdt_amount"] for t in trades
            if any(r["symbol"] == t["symbol"] and r.get("status") == "ok" for r in results)
        )

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        summary = f"Web App: {len(ok)} ناجح، {len(err)} خطأ"
        await db.add_history(user_id, now, summary, total_traded,
                             1 if not err else 0, portfolio_id=portfolio_id)

        return {
            "results":      results,
            "ok_count":     len(ok),
            "error_count":  len(err),
            "total_traded": round(total_traded, 2),
        }

    try:
        result = _run(_exec())
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        logger.exception("rebalance_execute error")
        return jsonify({"error": str(e)}), 500


@app.route("/api/sell_all", methods=["POST"])
@require_auth
def sell_all():
    """بيع كل عملات المحفظة النشطة."""
    user_id = _get_user_id()

    async def _sell():
        portfolio_id = await db.ensure_active_portfolio(user_id)
        p = await db.get_portfolio(portfolio_id) if portfolio_id else None
        if not p:
            return {"error": "no active portfolio"}

        settings = await db.get_settings(user_id)
        if not settings or not settings.get("mexc_api_key"):
            return {"error": "MEXC API keys not configured"}

        allocs = await db.get_portfolio_allocations(portfolio_id)
        if not allocs:
            return {"error": "no coins in portfolio"}

        from bot.mexc_client import MexcClient
        client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
        try:
            full_portfolio, _ = await asyncio.wait_for(
                client.get_portfolio(), timeout=15
            )
        except Exception as e:
            return {"error": f"MEXC error: {e}"}

        alloc_symbols = {a["symbol"] for a in allocs}
        trades = [
            {"symbol": sym, "action": "sell", "usdt_amount": round(data["value_usdt"], 2)}
            for sym, data in full_portfolio.items()
            if sym in alloc_symbols and sym != "USDT" and data["value_usdt"] >= 1.0
        ]

        if not trades:
            await client.close()
            return {"message": "لا توجد عملات للبيع", "results": []}

        try:
            results = await client.execute_rebalance(trades)
        except Exception as e:
            return {"error": f"execution error: {e}"}
        finally:
            await client.close()

        ok  = [r for r in results if r.get("status") == "ok"]
        err = [r for r in results if r.get("status") == "error"]
        return {"results": results, "ok_count": len(ok), "error_count": len(err)}

    try:
        result = _run(_sell())
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        logger.exception("sell_all error")
        return jsonify({"error": str(e)}), 500


@app.route("/api/history")
@require_auth
def get_history():
    """آخر 20 عملية إعادة توازن."""
    user_id = _get_user_id()

    async def _fetch():
        rows = await db.get_history(user_id, limit=20)
        return {"history": [dict(r) for r in rows]}

    try:
        return jsonify(_run(_fetch()))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/grids")
@require_auth
def get_grids():
    """قائمة Grid Bots النشطة مع تفاصيلها."""
    async def _fetch():
        from bot.grid.monitor import grid_monitor
        grids = []
        for gid, g in grid_monitor.active_grids.items():
            grids.append({
                "id":          gid,
                "symbol":      g.get("symbol", ""),
                "center":      g.get("center", 0),
                "upper":       g.get("upper", 0),
                "lower":       g.get("lower", 0),
                "upper_pct":   g.get("upper_pct", 0),
                "lower_pct":   g.get("lower_pct", 0),
                "steps":       g.get("steps", 0),
                "step_pct":    round(g.get("step_pct", 0), 4),
                "size":        g.get("order_size_usdt", 0),
                "take_profit": g.get("take_profit"),
                "stop_loss":   g.get("stop_loss"),
                "trades":      g.get("total_trades", 0),
                "shifts":      g.get("shifts", 0),
                "active":      g.get("active", True),
            })
        return {"grids": grids}

    try:
        return jsonify(_run(_fetch()))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/grids/<int:grid_id>/stop", methods=["POST"])
@require_auth
def stop_grid(grid_id):
    """إيقاف شبكة وإلغاء أوامرها."""
    user_id = _get_user_id()

    async def _stop():
        from bot.grid.monitor import grid_monitor
        g = grid_monitor.active_grids.get(grid_id)
        if not g:
            return {"error": "الشبكة غير موجودة"}
        if g.get("user_id") and g["user_id"] != user_id:
            return {"error": "غير مصرح"}

        settings = await db.get_settings(user_id)
        if not settings or not settings.get("mexc_api_key"):
            return {"error": "MEXC API غير مربوط"}

        from bot.mexc_client import MexcClient
        client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
        cancelled = 0
        errors = []
        try:
            all_orders = g.get("buy_orders", []) + g.get("sell_orders", [])
            for o in all_orders:
                oid = o.get("id") or o.get("order_id")
                if not oid or o.get("status") == "filled":
                    continue
                try:
                    await client.exchange.cancel_order(oid, g["symbol"])
                    cancelled += 1
                except Exception as e:
                    errors.append(str(e)[:60])
        finally:
            await client.close()

        await grid_monitor.remove_grid(grid_id)
        await db.delete_grid(grid_id)
        return {"ok": True, "cancelled": cancelled, "errors": errors}

    try:
        result = _run(_stop())
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/grids/create", methods=["POST"])
@require_auth
def create_grid():
    """إنشاء شبكة جديدة من الواجهة المرئية."""
    user_id = _get_user_id()
    body = request.get_json(silent=True) or {}

    required = ["symbol", "upper_pct", "lower_pct", "steps", "size"]
    for f in required:
        if f not in body:
            return jsonify({"error": f"حقل مطلوب: {f}"}), 400

    async def _create():
        settings = await db.get_settings(user_id)
        if not settings or not settings.get("mexc_api_key"):
            return {"error": "MEXC API غير مربوط"}

        from bot.mexc_client import MexcClient
        from bot.grid.engine import calculate_grid_levels, place_grid_orders
        from bot.grid.monitor import grid_monitor

        symbol     = body["symbol"].upper().replace("/", "").replace("-", "") + (
            "" if body["symbol"].upper().endswith("USDT") else "/USDT"
        )
        upper_pct  = float(body["upper_pct"])
        lower_pct  = float(body["lower_pct"])
        steps      = int(body["steps"])
        size       = float(body["size"])
        tp_pct     = float(body["take_profit_pct"]) if body.get("take_profit_pct") else None
        sl_pct     = float(body["stop_loss_pct"])   if body.get("stop_loss_pct")   else None

        if not (1 <= upper_pct <= 100): return {"error": "upper_pct يجب بين 1 و 100"}
        if not (1 <= lower_pct <= 100): return {"error": "lower_pct يجب بين 1 و 100"}
        if not (2 <= steps <= 50):      return {"error": "steps يجب بين 2 و 50"}
        if size < 5:                    return {"error": "الحجم الأدنى 5 USDT"}

        client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
        try:
            ticker = await asyncio.wait_for(
                client.exchange.fetch_ticker(symbol), timeout=10
            )
            center = float(ticker.get("last") or 0)
            if center <= 0:
                return {"error": "تعذّر جلب السعر الحالي"}

            balance = await client.exchange.fetch_balance()
            usdt_bal = float(balance.get("total", {}).get("USDT", 0) or 0)
            if usdt_bal < size:
                return {"error": f"رصيد غير كافٍ — متاح: ${usdt_bal:.2f}"}

            take_profit = round(center * (1 + tp_pct / 100), 8) if tp_pct else None
            stop_loss   = round(center * (1 - sl_pct / 100), 8) if sl_pct else None

            grid_levels = calculate_grid_levels(
                center_price=center,
                upper_pct=upper_pct,
                lower_pct=lower_pct,
                steps=steps,
            )
            result = await place_grid_orders(
                exchange=client.exchange,
                symbol=symbol,
                grid=grid_levels,
                order_size_usdt=size,
                initial=True,
            )

            if not result["buy_orders"] and not result["sell_orders"]:
                err = result["errors"][0] if result["errors"] else "خطأ غير معروف"
                return {"error": f"فشل تنفيذ الشبكة: {err}"}

            grid = {
                "user_id":         user_id,
                "symbol":          symbol,
                "center":          center,
                "upper":           grid_levels["upper"],
                "lower":           grid_levels["lower"],
                "upper_pct":       upper_pct,
                "lower_pct":       lower_pct,
                "steps":           steps,
                "step_pct":        grid_levels["step_pct"],
                "order_size_usdt": size,
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

            return {
                "ok":      True,
                "grid_id": grid_id,
                "symbol":  symbol,
                "center":  center,
                "upper":   grid_levels["upper"],
                "lower":   grid_levels["lower"],
                "step_pct": round(grid_levels["step_pct"], 4),
                "buys":    len(result["buy_orders"]),
                "sells":   len(result["sell_orders"]),
                "errors":  len(result["errors"]),
            }
        finally:
            await client.close()

    try:
        result = _run(_create())
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        logger.exception("create_grid error")
        return jsonify({"error": str(e)}), 500


# ── Static files (webapp/) ────────────────────────────────────────────────────
# Flask serves webapp/ at /webapp/* automatically via static_folder above.
# These routes handle the root and /webapp/ index redirects.

@app.route("/")
@app.route("/webapp/")
@app.route("/webapp")
def webapp_index():
    return send_from_directory(_WEBAPP_DIR, "index.html")
