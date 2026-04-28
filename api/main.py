"""
FastAPI backend — REST API for the MEXC Portfolio Rebalancer.
Telegram bot is started alongside the API via lifespan.
"""

import io
import csv
import os
import sys
import threading
import time
import logging
import uuid
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

log = logging.getLogger("api")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from database import (
    get_rebalance_history, get_snapshots, init_db, record_snapshot,
    save_portfolio, list_portfolios, get_portfolio,
    set_active_portfolio, delete_portfolio, update_portfolio_config,
    set_bot_running, get_running_portfolios,
)
from mexc_client import MEXCClient
from smart_portfolio import (
    execute_rebalance,
    execute_rebalance_equal,
    get_pnl,
    get_portfolio_value,
    is_paper_trading,
    load_config,
    save_config,
    validate_allocations,
)

init_db()

# ── Per-portfolio loop manager ─────────────────────────────────────────────────
_portfolio_loops: dict[int, dict] = {}
_loops_lock = threading.Lock()


def _make_loop(portfolio_id: int, stop_event: threading.Event) -> None:
    from smart_portfolio import (
        execute_rebalance, needs_rebalance_proportional,
        next_run_time, get_portfolio_value, check_sl_tp,
        TIMED_FREQUENCY_MINUTES,
    )
    from database import get_portfolio as db_get_portfolio

    with _loops_lock:
        if portfolio_id in _portfolio_loops:
            _portfolio_loops[portfolio_id]["error"] = None
            _portfolio_loops[portfolio_id]["started_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    try:
        cfg = db_get_portfolio(portfolio_id)
        if cfg is None:
            raise ValueError(f"Portfolio {portfolio_id} not found")
        client = _client()
        mode = cfg["rebalance"]["mode"]
        log.info("Portfolio %d loop started | mode: %s", portfolio_id, mode)
        timed_next_run = None

        while not stop_event.is_set():
            try:
                cfg = db_get_portfolio(portfolio_id)
                if cfg is None:
                    break
                current_mode = cfg["rebalance"]["mode"]

                sl_tp_triggered = check_sl_tp(client, cfg)
                sl_tp_symbols = {t["symbol"] for t in sl_tp_triggered}
                if sl_tp_symbols:
                    for t in sl_tp_triggered:
                        msg = (
                            f"⚠️ *{t['action']}* — `{t['symbol']}`\n"
                            f"دخول: `{t['entry_price']:.4f}` | حالي: `{t['current_price']:.4f}`\n"
                            f"تغيير: `{t['change_pct']:+.2f}%`"
                        )
                        _notify_telegram(msg)

                if current_mode == "proportional":
                    interval = cfg["rebalance"]["proportional"]["check_interval_minutes"] * 60
                    if needs_rebalance_proportional(client, cfg, exclude_symbols=sl_tp_symbols):
                        result = execute_rebalance(client, cfg, exclude_symbols=sl_tp_symbols,
                                                   portfolio_id=portfolio_id)
                        trades = [r for r in result if r.get("action") in ("BUY", "SELL")]
                        if trades:
                            summary = "\n".join(
                                f"{'🟢' if r['action']=='BUY' else '🔴'} `{r['symbol']}` {r['diff_usdt']:+.2f}$"
                                for r in trades
                            )
                            _notify_telegram(f"🔄 *إعادة توازن تلقائية*\n\n{summary}")
                    stop_event.wait(interval)

                elif current_mode == "timed":
                    timed_cfg = cfg["rebalance"]["timed"]
                    frequency = timed_cfg["frequency"]
                    target_hour = timed_cfg.get("hour", 0)
                    if timed_next_run is None:
                        timed_next_run = next_run_time(frequency, target_hour=target_hour)
                    if datetime.utcnow() >= timed_next_run:
                        result = execute_rebalance(client, cfg, exclude_symbols=sl_tp_symbols,
                                                   portfolio_id=portfolio_id)
                        trades = [r for r in result if r.get("action") in ("BUY", "SELL")]
                        if trades:
                            summary = "\n".join(
                                f"{'🟢' if r['action']=='BUY' else '🔴'} `{r['symbol']}` {r['diff_usdt']:+.2f}$"
                                for r in trades
                            )
                            _notify_telegram(f"🔄 *إعادة توازن ({frequency})*\n\n{summary}")
                        timed_next_run = next_run_time(frequency, target_hour=target_hour)
                    short_freq = frequency in TIMED_FREQUENCY_MINUTES and frequency not in ("daily", "weekly", "monthly")
                    stop_event.wait(30 if short_freq else 60)

                else:
                    timed_next_run = None
                    stop_event.wait(60)

            except Exception as e:
                log.error("Portfolio %d loop error: %s", portfolio_id, e)
                stop_event.wait(30)

    except Exception as e:
        with _loops_lock:
            if portfolio_id in _portfolio_loops:
                _portfolio_loops[portfolio_id]["error"] = str(e)
        log.error("Portfolio %d loop crashed: %s", portfolio_id, e)

    log.info("Portfolio %d loop stopped", portfolio_id)


def _is_portfolio_running(portfolio_id: int) -> bool:
    with _loops_lock:
        entry = _portfolio_loops.get(portfolio_id)
    return entry is not None and entry["thread"].is_alive()


def _start_portfolio_loop(portfolio_id: int) -> None:
    with _loops_lock:
        existing = _portfolio_loops.get(portfolio_id)
        if existing is not None and existing["thread"].is_alive():
            return
        stop_ev = threading.Event()
        t = threading.Thread(target=_make_loop, args=(portfolio_id, stop_ev), daemon=True)
        _portfolio_loops[portfolio_id] = {
            "thread": t, "stop": stop_ev,
            "error": None, "started_at": None,
        }
    t.start()
    set_bot_running(portfolio_id, True)


def _stop_portfolio_loop(portfolio_id: int) -> None:
    with _loops_lock:
        entry = _portfolio_loops.get(portfolio_id)
    if entry:
        entry["stop"].set()
        entry["thread"].join(timeout=5)
        with _loops_lock:
            if portfolio_id in _portfolio_loops and not _portfolio_loops[portfolio_id]["thread"].is_alive():
                del _portfolio_loops[portfolio_id]
    set_bot_running(portfolio_id, False)


def _is_running() -> bool:
    return any(_is_portfolio_running(pid) for pid in list(_portfolio_loops.keys()))


# ── Pending rebalance cancel ───────────────────────────────────────────────────
_pending_rebalances: dict[str, dict] = {}
_pending_lock = threading.Lock()


def _run_rebalance_with_cancel(job_id: str, client: MEXCClient, cfg: dict) -> None:
    entry = _pending_rebalances.get(job_id)
    if not entry:
        return
    cancelled = entry["cancel"].wait(timeout=10)
    if cancelled:
        entry["result"] = None
        entry["done"].set()
        return
    try:
        result = execute_rebalance(client, cfg, portfolio_id=1)
        entry["result"] = result
    except Exception as e:
        entry["result"] = [{"error": str(e)}]
    finally:
        entry["done"].set()
        def _cleanup():
            time.sleep(60)
            with _pending_lock:
                _pending_rebalances.pop(job_id, None)
        threading.Thread(target=_cleanup, daemon=True).start()


# ── Telegram notifications ─────────────────────────────────────────────────────
def _notify_telegram(message: str) -> None:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    try:
        import requests as _req
        _req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=5,
        )
    except Exception as e:
        log.warning("Telegram notification failed: %s", e)


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app):
    # Resume portfolio loops
    try:
        running_ids = get_running_portfolios()
        for pid in running_ids:
            try:
                cfg = get_portfolio(pid)
                if cfg is None:
                    set_bot_running(pid, False)
                    continue
                _start_portfolio_loop(pid)
            except Exception as e:
                log.error("Auto-resume failed for portfolio %d: %s", pid, e)
    except Exception as e:
        log.error("Lifespan startup error: %s", e)

    # Start Telegram bot in background thread
    _start_telegram_bot()

    yield

    # Shutdown
    for pid in list(_portfolio_loops.keys()):
        try:
            _stop_portfolio_loop(pid)
        except Exception:
            pass


app = FastAPI(title="MEXC Portfolio Rebalancer API", version="4.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse

class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    _PUBLIC = ("/health", "/docs", "/openapi.json", "/redoc", "/api/status",
               "/api/rebalance/status/", "/api/mexc/status", "/api/db/status")

    def _is_public(self, path: str) -> bool:
        if not path.startswith("/api"):
            return True
        return any(path == p or path.startswith(p) for p in self._PUBLIC)

    async def dispatch(self, request: StarletteRequest, call_next):
        key = os.environ.get("API_AUTH_KEY", "").strip()
        if not key or self._is_public(request.url.path):
            return await call_next(request)
        auth  = request.headers.get("authorization", "")
        x_api = request.headers.get("x-api-key", "")
        provided = auth[7:].strip() if auth.lower().startswith("bearer ") else x_api.strip()
        if not provided or not secrets.compare_digest(provided, key):
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)

app.add_middleware(ApiKeyAuthMiddleware)


def _client() -> MEXCClient:
    return MEXCClient()


# ── Models ─────────────────────────────────────────────────────────────────────
class AssetAlloc(BaseModel):
    symbol: str
    allocation_pct: float

class ConfigUpdate(BaseModel):
    assets: Optional[list[AssetAlloc]] = None
    mode: Optional[str] = None
    threshold_pct: Optional[float] = None
    frequency: Optional[str] = None
    budget_usdt: Optional[float] = None
    bot_name: Optional[str] = None
    paper_trading: Optional[bool] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    allocation_mode: Optional[str] = None

class NotificationConfig(BaseModel):
    telegram_enabled: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

class PortfolioCreate(BaseModel):
    config: dict

class PortfolioRebalanceRequest(BaseModel):
    dry_run: Optional[bool] = False


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/status")
def get_status():
    cfg = load_config()
    no_key = not os.environ.get("MEXC_API_KEY")
    if no_key:
        assets_out = [
            {"symbol": a["symbol"], "balance": 0, "price": 0, "value_usdt": 0,
             "actual_pct": a["allocation_pct"], "target_pct": a["allocation_pct"], "deviation": 0}
            for a in cfg["portfolio"]["assets"]
        ]
        return {"bot_name": cfg["bot"]["name"], "total_usdt": 0, "mode": cfg["rebalance"]["mode"],
                "assets": assets_out, "pnl": {}, "warning": "MEXC API key not set"}
    try:
        client = _client()
        portfolio = get_portfolio_value(client, cfg["portfolio"]["assets"], budget_usdt=None)
        targets = {a["symbol"]: a["allocation_pct"] for a in cfg["portfolio"]["assets"]}
        pnl = get_pnl(cfg, current_usdt=portfolio["total_usdt"])
        assets_out = []
        for r in portfolio["assets"]:
            diff = round(r["actual_pct"] - targets[r["symbol"]], 2)
            assets_out.append({"symbol": r["symbol"], "balance": r["balance"], "price": r["price"],
                                "value_usdt": r["value_usdt"], "actual_pct": round(r["actual_pct"], 2),
                                "target_pct": targets[r["symbol"]], "deviation": diff})
        return {"bot_name": cfg["bot"]["name"], "total_usdt": portfolio["total_usdt"],
                "mode": cfg["rebalance"]["mode"], "assets": assets_out, "pnl": pnl,
                "profit_usdt": pnl.get("pnl_usdt", 0), "profit_pct": pnl.get("pnl_pct", 0)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history")
def get_history(limit: int = 10, portfolio_id: int = 1):
    return get_rebalance_history(limit, portfolio_id=portfolio_id)


@app.get("/api/snapshots")
def get_portfolio_snapshots(limit: int = 90, portfolio_id: int = 1):
    return get_snapshots(limit, portfolio_id=portfolio_id)


@app.get("/api/config")
def get_config():
    return load_config()


@app.post("/api/config")
def update_config(body: ConfigUpdate):
    cfg = load_config()
    if body.assets is not None:
        cfg["portfolio"]["assets"] = [{"symbol": a.symbol, "allocation_pct": a.allocation_pct} for a in body.assets]
    if body.mode is not None:
        cfg["rebalance"]["mode"] = body.mode
    if body.threshold_pct is not None:
        cfg["rebalance"]["proportional"]["threshold_pct"] = body.threshold_pct
    if body.frequency is not None:
        cfg["rebalance"]["timed"]["frequency"] = body.frequency
    if body.budget_usdt is not None:
        cfg["portfolio"]["budget_usdt"] = body.budget_usdt
    if body.bot_name is not None:
        cfg["bot"]["name"] = body.bot_name
    if body.paper_trading is not None:
        cfg["paper_trading"] = body.paper_trading
    if body.stop_loss_pct is not None:
        cfg.setdefault("risk", {})["stop_loss_pct"] = body.stop_loss_pct
    if body.take_profit_pct is not None:
        cfg.setdefault("risk", {})["take_profit_pct"] = body.take_profit_pct
    save_config(cfg)
    return {"ok": True}


@app.get("/api/bot/status")
def bot_status():
    with _loops_lock:
        loops_snapshot = {pid: dict(e) for pid, e in _portfolio_loops.items()}
    running_ids = [pid for pid, e in loops_snapshot.items() if e["thread"].is_alive()]
    return {"running": len(running_ids) > 0, "running_portfolios": running_ids,
            "mode": load_config()["rebalance"]["mode"]}


@app.post("/api/bot/start")
def bot_start():
    cfg = load_config()
    try:
        validate_allocations(cfg["portfolio"]["assets"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    portfolios = list_portfolios()
    active = next((p for p in portfolios if p.get("active")), None)
    if active is None:
        raise HTTPException(status_code=400, detail="لا توجد محفظة نشطة")
    pid = active["id"]
    if _is_portfolio_running(pid):
        return {"ok": False, "message": "البوت شغال بالفعل"}
    _start_portfolio_loop(pid)
    _notify_telegram(f"✅ *البوت بدأ*\nالوضع: `{cfg['rebalance']['mode']}`")
    return {"ok": True, "message": f"البوت بدأ | mode: {cfg['rebalance']['mode']}"}


@app.post("/api/bot/stop")
def bot_stop():
    running = [pid for pid in list(_portfolio_loops.keys()) if _is_portfolio_running(pid)]
    if not running:
        return {"ok": False, "message": "البوت مش شغال"}
    for pid in running:
        _stop_portfolio_loop(pid)
    _notify_telegram("⏹️ *البوت أُوقف*")
    return {"ok": True, "message": "تم إيقاف البوت"}


@app.post("/api/rebalance")
def trigger_rebalance():
    cfg = load_config()
    client = _client()
    job_id = str(uuid.uuid4())[:8]
    cancel_ev = threading.Event()
    done_ev   = threading.Event()
    with _pending_lock:
        _pending_rebalances[job_id] = {"cancel": cancel_ev, "done": done_ev, "result": None}
    t = threading.Thread(target=_run_rebalance_with_cancel, args=(job_id, client, cfg), daemon=True)
    t.start()
    return {"job_id": job_id, "message": "إعادة التوازن ستبدأ خلال 10 ثوانٍ — يمكنك الإلغاء"}


@app.post("/api/rebalance/cancel")
def cancel_rebalance(job_id: str):
    with _pending_lock:
        entry = _pending_rebalances.get(job_id)
    if not entry:
        raise HTTPException(status_code=404, detail="job_id غير موجود أو انتهت مهلته")
    entry["cancel"].set()
    return {"ok": True, "message": "تم الإلغاء"}


@app.get("/api/rebalance/status/{job_id}")
def rebalance_job_status(job_id: str):
    with _pending_lock:
        entry = _pending_rebalances.get(job_id)
    if not entry:
        raise HTTPException(status_code=404, detail="job_id غير موجود")
    if not entry["done"].is_set():
        return {"status": "pending"}
    if entry["result"] is None:
        return {"status": "cancelled"}
    return {"status": "done", "result": entry["result"]}


@app.get("/api/portfolios")
def api_list_portfolios():
    portfolios = list_portfolios()
    for p in portfolios:
        p["running"] = _is_portfolio_running(p["id"])
    return portfolios


@app.post("/api/portfolios")
def api_save_portfolio(body: PortfolioCreate):
    pid = save_portfolio(body.config)
    return {"ok": True, "id": pid}


@app.get("/api/portfolios/{portfolio_id}")
def api_get_portfolio(portfolio_id: int):
    cfg = get_portfolio(portfolio_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="المحفظة غير موجودة")
    return cfg


@app.post("/api/portfolios/{portfolio_id}/activate")
def api_activate_portfolio(portfolio_id: int):
    cfg = get_portfolio(portfolio_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="المحفظة غير موجودة")
    set_active_portfolio(portfolio_id)
    save_config(cfg)
    return {"ok": True}


@app.post("/api/portfolios/{portfolio_id}/start")
def api_start_portfolio(portfolio_id: int):
    cfg = get_portfolio(portfolio_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="المحفظة غير موجودة")
    if _is_portfolio_running(portfolio_id):
        return {"ok": False, "message": "المحفظة شغالة بالفعل"}
    _start_portfolio_loop(portfolio_id)
    _notify_telegram(f"✅ *محفظة {portfolio_id} بدأت*\n`{cfg.get('bot',{}).get('name','')}`")
    return {"ok": True}


@app.post("/api/portfolios/{portfolio_id}/stop")
def api_stop_portfolio(portfolio_id: int):
    _stop_portfolio_loop(portfolio_id)
    _notify_telegram(f"⏹️ *محفظة {portfolio_id} أُوقفت*")
    return {"ok": True}


@app.get("/api/portfolios/{portfolio_id}/status")
def api_portfolio_status(portfolio_id: int):
    cfg = get_portfolio(portfolio_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="المحفظة غير موجودة")
    with _loops_lock:
        entry = _portfolio_loops.get(portfolio_id, {})
    return {"portfolio_id": portfolio_id, "running": _is_portfolio_running(portfolio_id),
            "error": entry.get("error"), "started_at": entry.get("started_at")}


@app.delete("/api/portfolios/{portfolio_id}")
def api_delete_portfolio(portfolio_id: int):
    _stop_portfolio_loop(portfolio_id)
    delete_portfolio(portfolio_id)
    return {"ok": True}


@app.put("/api/portfolios/{portfolio_id}")
def api_update_portfolio(portfolio_id: int, body: PortfolioCreate):
    update_portfolio_config(portfolio_id, body.config)
    return {"ok": True}


@app.post("/api/portfolios/{portfolio_id}/rebalance")
def api_rebalance_portfolio(portfolio_id: int, body: PortfolioRebalanceRequest):
    cfg = get_portfolio(portfolio_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="المحفظة غير موجودة")
    client = _client()
    try:
        result = execute_rebalance(client, cfg, portfolio_id=portfolio_id)
        trades = [r for r in result if r.get("action") in ("BUY", "SELL")]
        if trades:
            summary = "\n".join(
                f"{'🟢' if r['action']=='BUY' else '🔴'} `{r['symbol']}` {r['diff_usdt']:+.2f}$"
                for r in trades
            )
            _notify_telegram(f"🔄 *إعادة توازن يدوية — محفظة {portfolio_id}*\n\n{summary}")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/export/csv")
def export_csv(portfolio_id: int = 1):
    history = get_rebalance_history(1000, portfolio_id=portfolio_id)
    output = io.StringIO()
    if history:
        writer = csv.DictWriter(output, fieldnames=history[0].keys())
        writer.writeheader()
        writer.writerows(history)
    output.seek(0)
    return StreamingResponse(output, media_type="text/csv",
                              headers={"Content-Disposition": "attachment; filename=rebalance_history.csv"})


@app.get("/api/db/status")
def db_status():
    try:
        init_db()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/mexc/status")
def mexc_status():
    try:
        client = _client()
        client.get_price("BTCUSDT")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Telegram bot thread ────────────────────────────────────────────────────────
_tg_thread: Optional[threading.Thread] = None

def _start_telegram_bot() -> None:
    global _tg_thread
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        log.info("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled")
        return
    if _tg_thread and _tg_thread.is_alive():
        return

    def _run():
        try:
            from bot.telegram_bot import run_bot
            run_bot(
                get_status_fn=get_status,
                start_fn=_start_portfolio_loop,
                stop_fn=_stop_portfolio_loop,
                rebalance_fn=lambda pid: api_rebalance_portfolio(pid, PortfolioRebalanceRequest()),
                list_portfolios_fn=list_portfolios,
                is_running_fn=_is_portfolio_running,
                get_history_fn=get_rebalance_history,
                get_portfolio_fn=get_portfolio,
            )
        except Exception as e:
            log.error("Telegram bot crashed: %s", e)

    _tg_thread = threading.Thread(target=_run, daemon=True, name="telegram-bot")
    _tg_thread.start()
    log.info("Telegram bot thread started")
