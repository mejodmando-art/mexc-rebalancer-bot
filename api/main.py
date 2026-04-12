"""
FastAPI backend – REST API for the web dashboard.

Endpoints
---------
GET  /api/status          – portfolio snapshot (live prices)
GET  /api/history         – last N rebalance operations
GET  /api/snapshots       – portfolio value over time (for line chart)
GET  /api/config          – current config (assets, mode, settings)
POST /api/config          – update config
POST /api/rebalance       – trigger manual rebalance
GET  /api/export/csv      – download CSV report
"""

import io
import csv
import os
import sys
import threading
import time
import logging
from datetime import datetime
from typing import Optional

# Support both: running from repo root (Railway) and from api/ subdir
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

log = logging.getLogger("api")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import get_rebalance_history, get_snapshots, init_db, record_snapshot
from mexc_client import MEXCClient
from smart_portfolio import (
    execute_rebalance,
    get_pnl,
    get_portfolio_value,
    load_config,
    save_config,
    validate_allocations,
)

init_db()

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


app = FastAPI(title="MEXC Portfolio Rebalancer API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve Next.js static export
_static_dir = os.path.join(_root, "static")
if os.path.isdir(_static_dir):
    # Serve _next assets (JS/CSS chunks)
    _next_dir = os.path.join(_static_dir, "_next")
    if os.path.isdir(_next_dir):
        app.mount("/_next", StaticFiles(directory=_next_dir), name="nextjs_assets")
    # Serve other static assets
    app.mount("/static_files", StaticFiles(directory=_static_dir), name="static")


@app.get("/", include_in_schema=False)
def serve_dashboard():
    index = os.path.join(_static_dir, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "MEXC Rebalancer API", "docs": "/docs"}


@app.get("/404.html", include_in_schema=False)
def serve_404():
    p = os.path.join(_static_dir, "404.html")
    if os.path.exists(p):
        return FileResponse(p)
    return {"error": "not found"}


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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/status")
def get_status():
    cfg = load_config()
    no_key = not os.environ.get("MEXC_API_KEY")
    # Return config-only snapshot when API keys are missing
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
            })
        return {
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history")
def get_history(limit: int = 10):
    return get_rebalance_history(limit)


@app.get("/api/snapshots")
def get_portfolio_snapshots(limit: int = 90):
    return get_snapshots(limit)


@app.get("/api/config")
def get_config():
    cfg = load_config()
    return cfg


@app.post("/api/config")
def update_config(body: ConfigUpdate):
    cfg = load_config()
    if body.bot_name is not None:
        cfg["bot"]["name"] = body.bot_name
    if body.assets is not None:
        cfg["portfolio"]["assets"] = [a.dict() for a in body.assets]
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


@app.post("/api/rebalance")
def trigger_rebalance():
    cfg = load_config()
    try:
        client = _client()
        details = execute_rebalance(client, cfg)
        return {"ok": True, "details": details}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Bot control endpoints
# ---------------------------------------------------------------------------

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
# Recommended portfolios
# ---------------------------------------------------------------------------

@app.get("/api/recommended")
def get_recommended():
    """Return pre-built portfolio templates (Bitget-style)."""
    return [
        {
            "name": "Top 3 Coins",
            "description": "BTC + ETH + BNB – أكثر العملات استقراراً",
            "assets": [
                {"symbol": "BTC", "allocation_pct": 50},
                {"symbol": "ETH", "allocation_pct": 30},
                {"symbol": "BNB", "allocation_pct": 20},
            ],
        },
        {
            "name": "DeFi Portfolio",
            "description": "عملات DeFi الرائدة",
            "assets": [
                {"symbol": "ETH",  "allocation_pct": 40},
                {"symbol": "SOL",  "allocation_pct": 30},
                {"symbol": "AVAX", "allocation_pct": 30},
            ],
        },
        {
            "name": "Layer 1 Mix",
            "description": "تنويع على شبكات Layer 1",
            "assets": [
                {"symbol": "BTC",  "allocation_pct": 35},
                {"symbol": "ETH",  "allocation_pct": 25},
                {"symbol": "SOL",  "allocation_pct": 20},
                {"symbol": "AVAX", "allocation_pct": 20},
            ],
        },
        {
            "name": "Balanced 5",
            "description": "محفظة متوازنة من 5 عملات",
            "assets": [
                {"symbol": "BTC",  "allocation_pct": 30},
                {"symbol": "ETH",  "allocation_pct": 25},
                {"symbol": "SOL",  "allocation_pct": 20},
                {"symbol": "BNB",  "allocation_pct": 15},
                {"symbol": "AVAX", "allocation_pct": 10},
            ],
        },
    ]
