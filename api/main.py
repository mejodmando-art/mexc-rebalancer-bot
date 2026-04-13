"""
FastAPI backend – REST API for the web dashboard.

Endpoints
---------
GET  /api/status              – portfolio snapshot (live prices)
GET  /api/history             – last N rebalance operations
GET  /api/snapshots           – portfolio value over time (for line chart)
GET  /api/config              – current config (assets, mode, settings)
POST /api/config              – update config (assets, allocations, mode…)
POST /api/rebalance           – trigger manual rebalance (returns job_id)
POST /api/rebalance/cancel    – cancel a pending rebalance within 10 s
GET  /api/export/csv          – download CSV report
GET  /api/export/excel        – download Excel report
GET  /api/bot/status          – rebalancer loop status
POST /api/bot/start           – start rebalancer loop
POST /api/bot/stop            – stop rebalancer loop
GET  /api/notifications/config – Discord / Telegram notification settings
POST /api/notifications/config – update notification settings
"""

import asyncio
import io
import csv
import os
import sys
import threading
import time
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

log = logging.getLogger("api")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import (
    get_rebalance_history, get_snapshots, init_db, record_snapshot,
    save_portfolio, list_portfolios, get_portfolio,
    set_active_portfolio, delete_portfolio, update_portfolio_config,
)
from mexc_client import MEXCClient
from smart_portfolio import (
    execute_rebalance,
    execute_rebalance_equal,
    get_pnl,
    get_portfolio_value,
    load_config,
    save_config,
    validate_allocations,
)

init_db()

# ---------------------------------------------------------------------------
# Telegram bot – runs as asyncio background task inside FastAPI event loop
# ---------------------------------------------------------------------------

async def _run_telegram_async() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        log.info("TELEGRAM_BOT_TOKEN not set – Telegram bot disabled")
        return
    try:
        from telegram import Update
        from telegram.ext import Application
        import telegram_bot as _tg_module
        from telegram_bot import (
            button_handler, cmd_export, cmd_help,
            cmd_history, cmd_rebalance, cmd_start, cmd_stats,
            cmd_status, cmd_stop, settings_cancel, settings_start,
            settings_assets_count, settings_asset_symbol, settings_asset_pct,
            settings_equal_alloc, settings_usdt, settings_mode,
            settings_threshold, settings_frequency, settings_sell_term,
            settings_asset_transfer, settings_paper_mode,
            ST_ASSETS_COUNT, ST_ASSET_SYMBOL, ST_ASSET_PCT, ST_EQUAL_ALLOC,
            ST_USDT_AMOUNT, ST_REBALANCE_MODE, ST_THRESHOLD, ST_FREQUENCY,
            ST_SELL_TERM, ST_ASSET_TRANSFER, ST_PAPER_MODE,
        )
        from telegram.ext import (
            CallbackQueryHandler, CommandHandler,
            ConversationHandler, MessageHandler, filters,
        )

        async def _api_post_init(app: Application) -> None:
            """Store app reference in telegram_bot module for button callbacks.
            The rebalancer loop is managed separately via /api/bot/start."""
            _tg_module._app_ref = app

        tg_app = (
            Application.builder()
            .token(token)
            .post_init(_api_post_init)
            .build()
        )

        settings_conv = ConversationHandler(
            entry_points=[
                CommandHandler("settings", settings_start),
                CallbackQueryHandler(settings_start, pattern="^settings$"),
            ],
            states={
                ST_ASSETS_COUNT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_assets_count)],
                ST_ASSET_SYMBOL:   [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_asset_symbol)],
                ST_ASSET_PCT:      [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, settings_asset_pct),
                    CallbackQueryHandler(settings_equal_alloc, pattern="^equal_alloc$"),
                ],
                ST_EQUAL_ALLOC:    [CallbackQueryHandler(settings_equal_alloc, pattern="^equal_alloc$")],
                ST_USDT_AMOUNT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_usdt)],
                ST_REBALANCE_MODE: [CallbackQueryHandler(settings_mode, pattern="^mode_")],
                ST_THRESHOLD:      [CallbackQueryHandler(settings_threshold, pattern="^thr_")],
                ST_FREQUENCY:      [CallbackQueryHandler(settings_frequency, pattern="^freq_")],
                ST_SELL_TERM:      [CallbackQueryHandler(settings_sell_term, pattern="^sell_")],
                ST_ASSET_TRANSFER: [CallbackQueryHandler(settings_asset_transfer, pattern="^transfer_")],
                ST_PAPER_MODE:     [CallbackQueryHandler(settings_paper_mode, pattern="^paper_")],
            },
            fallbacks=[CommandHandler("cancel", settings_cancel)],
            allow_reentry=True,
        )

        tg_app.add_handler(settings_conv)
        tg_app.add_handler(CommandHandler("start",     cmd_start))
        tg_app.add_handler(CommandHandler("status",    cmd_status))
        tg_app.add_handler(CommandHandler("rebalance", cmd_rebalance))
        tg_app.add_handler(CommandHandler("history",   cmd_history))
        tg_app.add_handler(CommandHandler("stats",     cmd_stats))
        tg_app.add_handler(CommandHandler("export",    cmd_export))
        tg_app.add_handler(CommandHandler("stop",      cmd_stop))
        tg_app.add_handler(CommandHandler("help",      cmd_help))
        tg_app.add_handler(CallbackQueryHandler(button_handler))

        async with tg_app:
            await tg_app.start()
            log.info("Telegram bot polling started")
            await tg_app.updater.start_polling(drop_pending_updates=True)
            # Keep running until the FastAPI lifespan cancels this task
            await asyncio.Event().wait()

    except Exception as e:
        log.error("Telegram bot error: %s", e)


# ---------------------------------------------------------------------------
# Rebalancer loop manager
# ---------------------------------------------------------------------------
_loop_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_loop_error: Optional[str] = None
_loop_started_at: Optional[str] = None


def _rebalancer_loop() -> None:
    global _loop_error, _loop_started_at
    _loop_error = None
    _loop_started_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    try:
        from smart_portfolio import (
            execute_rebalance, needs_rebalance_proportional,
            next_run_time, load_config,
        )
        cfg = load_config()
        client = _client()
        mode = cfg["rebalance"]["mode"]
        log.info("Rebalancer loop started | mode: %s", mode)

        if mode == "proportional":
            interval = cfg["rebalance"]["proportional"]["check_interval_minutes"] * 60
            while not _stop_event.is_set():
                try:
                    cfg = load_config()
                    if needs_rebalance_proportional(client, cfg):
                        execute_rebalance(client, cfg)
                except Exception as e:
                    log.error("Loop iteration error: %s", e)
                _stop_event.wait(interval)

        elif mode == "timed":
            timed_cfg = cfg["rebalance"]["timed"]
            frequency = timed_cfg["frequency"]
            target_hour = timed_cfg.get("hour", 0)
            next_run = next_run_time(frequency, target_hour=target_hour)
            while not _stop_event.is_set():
                try:
                    if datetime.utcnow() >= next_run:
                        cfg = load_config()
                        execute_rebalance(client, cfg)
                        frequency = cfg["rebalance"]["timed"]["frequency"]
                        target_hour = cfg["rebalance"]["timed"].get("hour", 0)
                        next_run = next_run_time(frequency, target_hour=target_hour)
                except Exception as e:
                    log.error("Loop iteration error: %s", e)
                _stop_event.wait(60)

        elif mode == "unbalanced":
            _stop_event.wait()

    except Exception as e:
        _loop_error = str(e)
        log.error("Rebalancer loop crashed: %s", e)

    log.info("Rebalancer loop stopped")


def _is_running() -> bool:
    return _loop_thread is not None and _loop_thread.is_alive()


# ---------------------------------------------------------------------------
# Pending rebalance cancel window (10 seconds)
# ---------------------------------------------------------------------------
# Maps job_id -> {"cancel": threading.Event, "done": threading.Event, "result": list | None}
_pending_rebalances: dict[str, dict] = {}
_pending_lock = threading.Lock()


def _run_rebalance_with_cancel(job_id: str, client: MEXCClient, cfg: dict) -> None:
    """Execute rebalance after a 10-second cancel window."""
    entry = _pending_rebalances.get(job_id)
    if not entry:
        return
    cancelled = entry["cancel"].wait(timeout=10)
    if cancelled:
        entry["result"] = None
        entry["done"].set()
        log.info("Rebalance %s cancelled by user", job_id)
        return
    try:
        result = execute_rebalance(client, cfg)
        entry["result"] = result
    except Exception as e:
        entry["result"] = [{"error": str(e)}]
        log.error("Rebalance %s failed: %s", job_id, e)
    finally:
        entry["done"].set()
        # Clean up after 60 s
        def _cleanup():
            time.sleep(60)
            with _pending_lock:
                _pending_rebalances.pop(job_id, None)
        threading.Thread(target=_cleanup, daemon=True).start()


# ---------------------------------------------------------------------------
# Discord notifications
# ---------------------------------------------------------------------------

def _send_discord(webhook_url: str, message: str) -> None:
    """Fire-and-forget Discord webhook notification."""
    try:
        import requests as _req
        _req.post(webhook_url, json={"content": message}, timeout=5)
    except Exception as e:
        log.warning("Discord notification failed: %s", e)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(_run_telegram_async())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="MEXC Portfolio Rebalancer API", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_static_dir = os.path.join(_root, "static")
_next_dir = os.path.join(_static_dir, "_next")
if os.path.isdir(_next_dir):
    app.mount("/_next", StaticFiles(directory=_next_dir), name="nextjs_assets")


@app.get("/", include_in_schema=False)
def serve_dashboard():
    index = os.path.join(_static_dir, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "MEXC Rebalancer API", "docs": "/docs"}


def _client() -> MEXCClient:
    return MEXCClient()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class AssetAlloc(BaseModel):
    symbol: str
    allocation_pct: float


class ConfigUpdate(BaseModel):
    bot_name: Optional[str] = None
    assets: Optional[list[AssetAlloc]] = None
    total_usdt: Optional[float] = None
    rebalance_mode: Optional[str] = None
    threshold_pct: Optional[int] = None
    frequency: Optional[str] = None
    timed_hour: Optional[int] = None
    sell_at_termination: Optional[bool] = None
    enable_asset_transfer: Optional[bool] = None
    paper_trading: Optional[bool] = None


class NotificationConfig(BaseModel):
    discord_webhook_url: Optional[str] = None
    discord_enabled: Optional[bool] = None
    telegram_enabled: Optional[bool] = None


# ---------------------------------------------------------------------------
# Routes – Status & portfolio
# ---------------------------------------------------------------------------

@app.get("/api/status")
def get_status():
    cfg = load_config()
    no_key = not os.environ.get("MEXC_API_KEY")
    if no_key:
        assets_out = [
            {
                "symbol": a["symbol"],
                "balance": 0,
                "price": 0,
                "value_usdt": 0,
                "actual_pct": a["allocation_pct"],
                "target_pct": a["allocation_pct"],
                "deviation": 0,
            }
            for a in cfg["portfolio"]["assets"]
        ]
        return {
            "bot_name": cfg["bot"]["name"],
            "total_usdt": cfg["portfolio"].get("total_usdt", 0),
            "mode": cfg["rebalance"]["mode"],
            "paper_trading": cfg.get("paper_trading", False),
            "last_rebalance": cfg.get("last_rebalance"),
            "assets": assets_out,
            "pnl": {"initial_usdt": 0, "current_usdt": 0, "pnl_usdt": 0, "pnl_pct": 0},
            "warning": "MEXC_API_KEY not set – showing config only",
            "rebalance_config": {
                "threshold_pct": cfg["rebalance"]["proportional"]["threshold_pct"],
                "frequency": cfg["rebalance"]["timed"]["frequency"],
            },
        }
    try:
        client = _client()
        portfolio = get_portfolio_value(client, cfg["portfolio"]["assets"])
        targets = {a["symbol"]: a["allocation_pct"] for a in cfg["portfolio"]["assets"]}
        pnl = get_pnl(cfg)
        assets_out = []
        for r in portfolio["assets"]:
            assets_out.append({
                "symbol": r["symbol"],
                "balance": r["balance"],
                "price": r["price"],
                "value_usdt": r["value_usdt"],
                "actual_pct": round(r["actual_pct"], 2),
                "target_pct": targets[r["symbol"]],
                "deviation": round(r["actual_pct"] - targets[r["symbol"]], 2),
                "error": r.get("error"),
            })
        invalid = portfolio.get("invalid_symbols", [])
        response = {
            "bot_name": cfg["bot"]["name"],
            "total_usdt": portfolio["total_usdt"],
            "mode": cfg["rebalance"]["mode"],
            "paper_trading": cfg.get("paper_trading", False),
            "last_rebalance": cfg.get("last_rebalance"),
            "assets": assets_out,
            "pnl": pnl,
            "rebalance_config": {
                "threshold_pct": cfg["rebalance"]["proportional"]["threshold_pct"],
                "frequency": cfg["rebalance"]["timed"]["frequency"],
            },
        }
        if invalid:
            response["warning"] = f"رموز غير موجودة على MEXC: {', '.join(invalid)} — تحقق من الإعدادات"
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history")
def get_history(limit: int = 10):
    return get_rebalance_history(limit)


@app.get("/api/snapshots")
def get_portfolio_snapshots(limit: int = 90):
    return get_snapshots(limit)


# ---------------------------------------------------------------------------
# Routes – Config
# ---------------------------------------------------------------------------

@app.get("/api/config")
def get_config():
    return load_config()


@app.post("/api/config")
def update_config(body: ConfigUpdate):
    cfg = load_config()
    if body.bot_name is not None:
        cfg["bot"]["name"] = body.bot_name
    if body.assets is not None:
        symbols = [a.symbol.strip().upper() for a in body.assets]
        if len(symbols) != len(set(symbols)):
            raise HTTPException(status_code=400, detail="لا يمكن تكرار رموز العملات")
        # Validate symbols exist on MEXC (only when API key is set)
        if os.environ.get("MEXC_API_KEY"):
            try:
                client = _client()
                invalid = []
                for sym in symbols:
                    if sym == "USDT":
                        continue
                    try:
                        price = client.get_price(f"{sym}USDT")
                        if price <= 0:
                            invalid.append(sym)
                    except Exception:
                        invalid.append(sym)
                if invalid:
                    raise HTTPException(
                        status_code=400,
                        detail=f"الرموز التالية غير موجودة على MEXC: {', '.join(invalid)}"
                    )
            except HTTPException:
                raise
            except Exception:
                pass  # If validation itself fails, allow save
        cfg["portfolio"]["assets"] = [
            {"symbol": s, "allocation_pct": a.allocation_pct}
            for s, a in zip(symbols, body.assets)
        ]
    if body.total_usdt is not None:
        cfg["portfolio"]["total_usdt"] = body.total_usdt
        if "initial_value_usdt" not in cfg["portfolio"]:
            cfg["portfolio"]["initial_value_usdt"] = body.total_usdt
    if body.rebalance_mode is not None:
        cfg["rebalance"]["mode"] = body.rebalance_mode
    if body.threshold_pct is not None:
        cfg["rebalance"]["proportional"]["threshold_pct"] = body.threshold_pct
    if body.frequency is not None:
        cfg["rebalance"]["timed"]["frequency"] = body.frequency
    if body.timed_hour is not None:
        cfg["rebalance"]["timed"]["hour"] = max(0, min(23, body.timed_hour))
    if body.sell_at_termination is not None:
        cfg["termination"]["sell_at_termination"] = body.sell_at_termination
    if body.enable_asset_transfer is not None:
        cfg["asset_transfer"]["enable_asset_transfer"] = body.enable_asset_transfer
    if body.paper_trading is not None:
        cfg["paper_trading"] = body.paper_trading
    try:
        validate_allocations(cfg["portfolio"]["assets"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    save_config(cfg)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Routes – Rebalance (with 10-second cancel window)
# ---------------------------------------------------------------------------

@app.post("/api/rebalance")
def trigger_rebalance():
    """
    Starts a rebalance with a 10-second cancel window.
    Returns a job_id that can be passed to /api/rebalance/cancel.
    """
    cfg = load_config()
    try:
        client = _client()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    job_id = str(uuid.uuid4())
    entry = {
        "cancel": threading.Event(),
        "done": threading.Event(),
        "result": None,
    }
    with _pending_lock:
        _pending_rebalances[job_id] = entry

    t = threading.Thread(
        target=_run_rebalance_with_cancel,
        args=(job_id, client, cfg),
        daemon=True,
    )
    t.start()

    return {"ok": True, "job_id": job_id, "cancel_window_seconds": 10}


@app.post("/api/rebalance/cancel")
def cancel_rebalance(job_id: str):
    """Cancel a pending rebalance within the 10-second window."""
    with _pending_lock:
        entry = _pending_rebalances.get(job_id)
    if not entry:
        raise HTTPException(status_code=404, detail="لم يتم العثور على العملية أو انتهت مهلة الإلغاء")
    if entry["done"].is_set():
        raise HTTPException(status_code=409, detail="تم تنفيذ العملية بالفعل ولا يمكن إلغاؤها")
    entry["cancel"].set()
    return {"ok": True, "message": "تم إلغاء عملية Rebalance"}


@app.get("/api/rebalance/status/{job_id}")
def rebalance_job_status(job_id: str):
    """Poll the status of a rebalance job."""
    with _pending_lock:
        entry = _pending_rebalances.get(job_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Job not found")
    cancelled = entry["cancel"].is_set()
    done = entry["done"].is_set()
    return {
        "job_id": job_id,
        "cancelled": cancelled,
        "done": done,
        "result": entry.get("result") if done else None,
    }


# ---------------------------------------------------------------------------
# Routes – Notifications
# ---------------------------------------------------------------------------

@app.get("/api/notifications/config")
def get_notification_config():
    cfg = load_config()
    notif = cfg.get("notifications", {})
    return {
        "discord_enabled": notif.get("discord_enabled", False),
        "discord_webhook_url": notif.get("discord_webhook_url", ""),
        "telegram_enabled": notif.get("telegram_enabled", bool(os.environ.get("TELEGRAM_BOT_TOKEN"))),
    }


@app.post("/api/notifications/config")
def update_notification_config(body: NotificationConfig):
    cfg = load_config()
    if "notifications" not in cfg:
        cfg["notifications"] = {}
    if body.discord_webhook_url is not None:
        cfg["notifications"]["discord_webhook_url"] = body.discord_webhook_url
    if body.discord_enabled is not None:
        cfg["notifications"]["discord_enabled"] = body.discord_enabled
    if body.telegram_enabled is not None:
        cfg["notifications"]["telegram_enabled"] = body.telegram_enabled
    save_config(cfg)
    return {"ok": True}


@app.post("/api/notifications/test")
def test_discord_notification():
    cfg = load_config()
    notif = cfg.get("notifications", {})
    webhook = notif.get("discord_webhook_url", "")
    if not webhook:
        raise HTTPException(status_code=400, detail="Discord webhook URL غير مضبوط")
    _send_discord(webhook, "✅ اختبار إشعار Discord من MEXC Smart Portfolio Bot")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Routes – Export
# ---------------------------------------------------------------------------

@app.get("/api/export/csv")
def export_csv():
    rows = get_rebalance_history(500)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp", "mode", "total_usdt", "paper",
                "symbol", "target_pct", "actual_pct",
                "deviation", "diff_usdt", "action"])
    for r in rows:
        for d in r["details"]:
            w.writerow([
                r["ts"], r["mode"], r["total_usdt"], bool(r["paper"]),
                d["symbol"], d["target_pct"], d["actual_pct"],
                d["deviation"], d["diff_usdt"], d["action"],
            ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=rebalance_history.csv"},
    )


@app.get("/api/export/excel")
def export_excel():
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl غير مثبت")

    rows = get_rebalance_history(500)
    wb = openpyxl.Workbook()

    # ── Sheet 1: Rebalance History ──────────────────────────────────────────
    ws = wb.active
    ws.title = "سجل العمليات"

    headers = ["الوقت", "الوضع", "الإجمالي (USDT)", "تجريبي",
               "العملة", "الهدف%", "الحالي%", "الفرق%", "الفرق (USDT)", "الإجراء"]
    header_fill = PatternFill("solid", fgColor="1F2937")
    header_font = Font(bold=True, color="F0B90B")

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    row_num = 2
    for r in rows:
        for d in r["details"]:
            action = d.get("action", "")
            ws.cell(row=row_num, column=1, value=r["ts"])
            ws.cell(row=row_num, column=2, value=r["mode"])
            ws.cell(row=row_num, column=3, value=round(r["total_usdt"], 2))
            ws.cell(row=row_num, column=4, value="نعم" if r["paper"] else "لا")
            ws.cell(row=row_num, column=5, value=d.get("symbol", ""))
            ws.cell(row=row_num, column=6, value=d.get("target_pct", 0))
            ws.cell(row=row_num, column=7, value=d.get("actual_pct", 0))
            ws.cell(row=row_num, column=8, value=d.get("deviation", 0))
            ws.cell(row=row_num, column=9, value=d.get("diff_usdt", 0))
            action_cell = ws.cell(row=row_num, column=10, value=action)
            if action == "BUY":
                action_cell.font = Font(color="10B981", bold=True)
            elif action == "SELL":
                action_cell.font = Font(color="EF4444", bold=True)
            row_num += 1

    for col in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 18

    # ── Sheet 2: Portfolio Snapshots ────────────────────────────────────────
    ws2 = wb.create_sheet("أداء المحفظة")
    ws2.cell(row=1, column=1, value="الوقت").font = header_font
    ws2.cell(row=1, column=2, value="الإجمالي (USDT)").font = header_font
    for i, snap in enumerate(get_snapshots(500), 2):
        ws2.cell(row=i, column=1, value=snap["ts"])
        ws2.cell(row=i, column=2, value=round(snap["total_usdt"], 2))

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"portfolio_report_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# Routes – Health & bot control
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/bot/status")
def bot_status():
    return {
        "running": _is_running(),
        "started_at": _loop_started_at,
        "error": _loop_error,
        "mode": load_config()["rebalance"]["mode"],
    }


@app.post("/api/bot/start")
def bot_start():
    global _loop_thread
    if _is_running():
        return {"ok": False, "message": "البوت شغال بالفعل"}
    cfg = load_config()
    try:
        validate_allocations(cfg["portfolio"]["assets"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _stop_event.clear()
    _loop_thread = threading.Thread(target=_rebalancer_loop, daemon=True)
    _loop_thread.start()
    return {"ok": True, "message": f"البوت بدأ | mode: {cfg['rebalance']['mode']}"}


@app.post("/api/bot/stop")
def bot_stop():
    if not _is_running():
        return {"ok": False, "message": "البوت مش شغال"}
    _stop_event.set()
    return {"ok": True, "message": "تم إيقاف البوت"}


# ---------------------------------------------------------------------------
# Routes – Multi-portfolio management
# ---------------------------------------------------------------------------

class PortfolioCreate(BaseModel):
    config: dict


@app.get("/api/portfolios")
def api_list_portfolios():
    """List all saved portfolios."""
    return list_portfolios()


@app.post("/api/portfolios")
def api_save_portfolio(body: PortfolioCreate):
    """Save current config as a new named portfolio."""
    cfg = body.config
    try:
        validate_allocations(cfg["portfolio"]["assets"])
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    name = cfg.get("bot", {}).get("name", "Portfolio")
    try:
        pid = save_portfolio(name, cfg)
    except Exception as e:
        log.error("save_portfolio exception: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"فشل حفظ المحفظة: {e}")
    if pid < 0:
        raise HTTPException(status_code=500, detail="فشل حفظ المحفظة: خطأ في قاعدة البيانات")
    return {"ok": True, "id": pid}


@app.get("/api/db/status")
def db_status():
    """Diagnostic endpoint — returns DB backend and connection health."""
    import database as _db
    try:
        count = len(_db.list_portfolios())
        return {"backend": _db._BACKEND, "ok": True, "portfolio_count": count}
    except Exception as e:
        return {"backend": _db._BACKEND, "ok": False, "error": str(e)}


@app.get("/api/portfolios/{portfolio_id}")
def api_get_portfolio(portfolio_id: int):
    cfg = get_portfolio(portfolio_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="المحفظة غير موجودة")
    return cfg


@app.post("/api/portfolios/{portfolio_id}/activate")
def api_activate_portfolio(portfolio_id: int):
    """Load a saved portfolio into config.json and make it active."""
    cfg = get_portfolio(portfolio_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="المحفظة غير موجودة")
    try:
        validate_allocations(cfg["portfolio"]["assets"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Stop running loop before switching
    if _is_running():
        _stop_event.set()
    save_config(cfg)
    set_active_portfolio(portfolio_id)
    return {"ok": True, "message": f"تم تفعيل المحفظة: {cfg['bot']['name']}"}


@app.delete("/api/portfolios/{portfolio_id}")
def api_delete_portfolio(portfolio_id: int):
    delete_portfolio(portfolio_id)
    return {"ok": True}


@app.put("/api/portfolios/{portfolio_id}")
def api_update_portfolio(portfolio_id: int, body: PortfolioCreate):
    """Update a saved portfolio's config without activating it."""
    cfg = body.config
    try:
        validate_allocations(cfg["portfolio"]["assets"])
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    existing = get_portfolio(portfolio_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="المحفظة غير موجودة")
    update_portfolio_config(portfolio_id, cfg)
    return {"ok": True}


class PortfolioRebalanceRequest(BaseModel):
    rebalance_type: str = "market_value"  # "market_value" | "equal"


@app.post("/api/portfolios/{portfolio_id}/rebalance")
def api_rebalance_portfolio(portfolio_id: int, body: PortfolioRebalanceRequest):
    """
    Trigger a rebalance for a specific portfolio.

    rebalance_type:
      - "market_value": restore configured allocation_pct targets (default)
      - "equal": redistribute equally across all assets regardless of targets
    """
    cfg = get_portfolio(portfolio_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="المحفظة غير موجودة")
    try:
        client = _client()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    job_id = str(uuid.uuid4())
    entry: dict = {"cancel": threading.Event(), "done": threading.Event(), "result": None}
    with _pending_lock:
        _pending_rebalances[job_id] = entry

    def _run() -> None:
        cancel_ev: threading.Event = entry["cancel"]
        cancel_ev.wait(10)
        if cancel_ev.is_set():
            entry["done"].set()
            return
        try:
            if body.rebalance_type == "equal":
                result = execute_rebalance_equal(client, cfg)
            else:
                result = execute_rebalance(client, cfg)
            entry["result"] = result
        except Exception as exc:
            log.error("Portfolio rebalance failed (id=%s): %s", portfolio_id, exc)
            entry["result"] = [{"error": str(exc)}]
        finally:
            entry["done"].set()

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "job_id": job_id, "cancel_window_seconds": 10}
