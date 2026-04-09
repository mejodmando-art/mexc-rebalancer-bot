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


@app.route("/api/grids")
@require_auth
def get_grids():
    """قائمة Grid Bots النشطة."""
    async def _fetch():
        from bot.grid.monitor import grid_monitor
        grids = []
        for gid, g in grid_monitor.active_grids.items():
            grids.append({
                "id":     gid,
                "symbol": g.get("symbol", ""),
                "steps":  g.get("steps", 0),
                "size":   g.get("order_size_usdt", 0),
                "trades": g.get("total_trades", 0),
                "active": g.get("active", False),
            })
        return {"grids": grids}

    try:
        return jsonify(_run(_fetch()))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Static files (webapp/) ────────────────────────────────────────────────────
# Flask serves webapp/ at /webapp/* automatically via static_folder above.
# These routes handle the root and /webapp/ index redirects.

@app.route("/")
@app.route("/webapp/")
@app.route("/webapp")
def webapp_index():
    return send_from_directory(_WEBAPP_DIR, "index.html")
