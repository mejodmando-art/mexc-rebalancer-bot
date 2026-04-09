"""
FastAPI backend for the MEXC Rebalancer web dashboard.
Shares the same database and MEXC client as the Telegram bot.
"""

import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Add project root to path so bot modules are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bot.database import db
from bot.mexc_client import MexcClient
from bot.rebalancer import calculate_trades

app = FastAPI(title="MEXC Rebalancer Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auth ───────────────────────────────────────────────────────────────────────

WEB_SECRET = os.environ.get("WEB_SECRET", "mexc-dashboard-secret")

# Simple token-based auth: the user sets WEB_SECRET in .env
# and passes it as Authorization: Bearer <secret>
def require_auth(authorization: Optional[str] = Header(None)):
    if not authorization or authorization != f"Bearer {WEB_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_user_id() -> int:
    """Return the first allowed user ID from config."""
    from bot.config import config
    if config.allowed_user_ids:
        return config.allowed_user_ids[0]
    raise HTTPException(status_code=400, detail="ALLOWED_USER_IDS not configured")


async def _get_client(user_id: int) -> MexcClient:
    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        raise HTTPException(status_code=400, detail="MEXC API keys not configured")
    return MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])


# ── Models ─────────────────────────────────────────────────────────────────────

class ApiKeysPayload(BaseModel):
    api_key: str
    secret_key: str

class AllocationItem(BaseModel):
    symbol: str
    target_percentage: float

class AllocationsPayload(BaseModel):
    allocations: list[AllocationItem]

class ThresholdPayload(BaseModel):
    threshold: float

class CapitalPayload(BaseModel):
    capital_usdt: float


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@app.get("/api/portfolio")
async def get_portfolio(_: bool = Depends(require_auth)):
    user_id = await _get_user_id()
    client = await _get_client(user_id)
    try:
        portfolio, total_usdt = await asyncio.wait_for(client.get_portfolio(), timeout=20)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="MEXC timeout")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        await client.close()

    portfolio_id = await db.ensure_active_portfolio(user_id)
    portfolio_info = await db.get_portfolio(portfolio_id)
    allocations = await db.get_portfolio_allocations(portfolio_id)
    settings = await db.get_settings(user_id)

    capital = portfolio_info.get("capital_usdt", 0.0) if portfolio_info else 0.0
    effective_total = min(capital, total_usdt) if capital > 0 else total_usdt
    alloc_map = {a["symbol"]: a["target_percentage"] for a in allocations}
    threshold = float(portfolio_info.get("threshold") or settings.get("threshold") or 5.0)

    assets = []
    for sym, data in sorted(portfolio.items(), key=lambda x: x[1]["value_usdt"], reverse=True):
        val = data["value_usdt"]
        pct = (val / effective_total * 100) if effective_total > 0 else 0
        target = alloc_map.get(sym)
        drift = round(pct - target, 2) if target is not None else None
        assets.append({
            "symbol": sym,
            "amount": data["amount"],
            "value_usdt": round(val, 2),
            "price": data.get("price", 0),
            "current_pct": round(pct, 2),
            "target_pct": target,
            "drift_pct": drift,
            "needs_action": abs(drift) >= threshold if drift is not None else False,
        })

    return {
        "total_usdt": round(total_usdt, 2),
        "capital_usdt": round(capital, 2),
        "effective_total": round(effective_total, 2),
        "portfolio_name": portfolio_info.get("name", "محفظتي") if portfolio_info else "محفظتي",
        "threshold": threshold,
        "assets": assets,
    }


@app.get("/api/rebalance/analyze")
async def analyze_rebalance(_: bool = Depends(require_auth)):
    user_id = await _get_user_id()
    client = await _get_client(user_id)
    settings = await db.get_settings(user_id)

    portfolio_id = await db.ensure_active_portfolio(user_id)
    portfolio_info = await db.get_portfolio(portfolio_id)
    allocations = await db.get_portfolio_allocations(portfolio_id)

    if not allocations:
        raise HTTPException(status_code=400, detail="No allocations configured")

    try:
        portfolio, total_usdt = await asyncio.wait_for(client.get_portfolio(), timeout=20)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="MEXC timeout")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        await client.close()

    capital = portfolio_info.get("capital_usdt", 0.0)
    alloc_symbols = {a["symbol"] for a in allocations}
    portfolio_value = sum(portfolio.get(sym, {}).get("value_usdt", 0.0) for sym in alloc_symbols)
    usdt_in_account = portfolio.get("USDT", {}).get("value_usdt", 0.0)

    if capital > 0:
        effective_total = min(capital, portfolio_value + usdt_in_account)
    else:
        effective_total = portfolio_value + usdt_in_account

    if effective_total < 1.0 and total_usdt >= 1.0:
        effective_total = min(capital, total_usdt) if capital > 0 else total_usdt

    threshold = float(portfolio_info.get("threshold") or settings.get("threshold") or 5.0)
    trades, drift_report = calculate_trades(portfolio, effective_total, allocations, threshold)

    total_pct = sum(a["target_percentage"] for a in allocations)

    return {
        "portfolio_name": portfolio_info.get("name", "محفظتي"),
        "total_usdt": round(total_usdt, 2),
        "effective_total": round(effective_total, 2),
        "threshold": threshold,
        "allocations_sum": round(total_pct, 2),
        "drift_report": drift_report,
        "trades": trades,
        "needs_rebalance": len(trades) > 0,
    }


@app.post("/api/rebalance/execute")
async def execute_rebalance(_: bool = Depends(require_auth)):
    user_id = await _get_user_id()
    client = await _get_client(user_id)
    settings = await db.get_settings(user_id)

    portfolio_id = await db.ensure_active_portfolio(user_id)
    portfolio_info = await db.get_portfolio(portfolio_id)
    allocations = await db.get_portfolio_allocations(portfolio_id)

    if not allocations:
        raise HTTPException(status_code=400, detail="No allocations configured")

    try:
        portfolio, total_usdt = await asyncio.wait_for(client.get_portfolio(), timeout=20)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="MEXC timeout")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    capital = portfolio_info.get("capital_usdt", 0.0)
    alloc_symbols = {a["symbol"] for a in allocations}
    portfolio_value = sum(portfolio.get(sym, {}).get("value_usdt", 0.0) for sym in alloc_symbols)
    usdt_in_account = portfolio.get("USDT", {}).get("value_usdt", 0.0)
    effective_total = min(capital, portfolio_value + usdt_in_account) if capital > 0 else portfolio_value + usdt_in_account
    if effective_total < 1.0 and total_usdt >= 1.0:
        effective_total = min(capital, total_usdt) if capital > 0 else total_usdt

    threshold = float(portfolio_info.get("threshold") or settings.get("threshold") or 5.0)
    trades, _ = calculate_trades(portfolio, effective_total, allocations, threshold)

    if not trades:
        return {"message": "Portfolio is balanced", "results": [], "ok": 0, "error": 0}

    try:
        results = await client.execute_rebalance(trades)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        await client.close()

    ok = [r for r in results if r.get("status") == "ok"]
    err = [r for r in results if r.get("status") == "error"]
    total_traded = sum(t["usdt_amount"] for t in trades if any(r["symbol"] == t["symbol"] and r.get("status") == "ok" for r in results))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    summary = f"ويب: {len(ok)} ناجح، {len(err)} خطأ"
    await db.add_history(user_id, now, summary, total_traded, 1 if not err else 0, portfolio_id=portfolio_id)  # type: ignore

    return {
        "results": results,
        "ok": len(ok),
        "error": len(err),
        "total_traded_usdt": round(total_traded, 2),
    }


@app.get("/api/history")
async def get_history(limit: int = 20, _: bool = Depends(require_auth)):
    user_id = await _get_user_id()
    history = await db.get_history(user_id, limit=limit)
    filtered = [h for h in history if not h["summary"].startswith("momentum_loss:")]
    return {"history": filtered}


@app.get("/api/settings")
async def get_settings(_: bool = Depends(require_auth)):
    user_id = await _get_user_id()
    settings = await db.get_settings(user_id) or {}
    portfolio_id = await db.ensure_active_portfolio(user_id)
    portfolio_info = await db.get_portfolio(portfolio_id)
    allocations = await db.get_portfolio_allocations(portfolio_id)

    return {
        "has_api_keys": bool(settings.get("mexc_api_key")),
        "api_key_preview": (settings.get("mexc_api_key") or "")[:8] + "..." if settings.get("mexc_api_key") else None,
        "threshold": settings.get("threshold", 5.0),
        "portfolio_name": portfolio_info.get("name", "محفظتي") if portfolio_info else "محفظتي",
        "capital_usdt": portfolio_info.get("capital_usdt", 0.0) if portfolio_info else 0.0,
        "allocations": allocations,
    }


@app.post("/api/settings/api-keys")
async def save_api_keys(payload: ApiKeysPayload, _: bool = Depends(require_auth)):
    user_id = await _get_user_id()
    # Validate keys first
    client = MexcClient(payload.api_key, payload.secret_key)
    try:
        valid, msg = await client.validate_credentials()
    finally:
        await client.close()
    if not valid:
        raise HTTPException(status_code=400, detail=msg)

    await db.update_settings(user_id, mexc_api_key=payload.api_key, mexc_secret_key=payload.secret_key)
    return {"message": "API keys saved successfully"}


@app.post("/api/settings/threshold")
async def save_threshold(payload: ThresholdPayload, _: bool = Depends(require_auth)):
    user_id = await _get_user_id()
    if not (0.1 <= payload.threshold <= 50):
        raise HTTPException(status_code=400, detail="Threshold must be between 0.1 and 50")
    await db.update_settings(user_id, threshold=payload.threshold)
    return {"message": "Threshold saved"}


@app.post("/api/settings/capital")
async def save_capital(payload: CapitalPayload, _: bool = Depends(require_auth)):
    user_id = await _get_user_id()
    portfolio_id = await db.ensure_active_portfolio(user_id)
    await db.update_portfolio(portfolio_id, capital_usdt=payload.capital_usdt)
    return {"message": "Capital saved"}


@app.post("/api/settings/allocations")
async def save_allocations(payload: AllocationsPayload, _: bool = Depends(require_auth)):
    user_id = await _get_user_id()
    total = sum(a.target_percentage for a in payload.allocations)
    if abs(total - 100) > 1.0:
        raise HTTPException(status_code=400, detail=f"Allocations must sum to 100% (got {total:.1f}%)")

    portfolio_id = await db.ensure_active_portfolio(user_id)
    # Clear existing and re-insert
    await db.clear_portfolio_allocations(portfolio_id)
    for a in payload.allocations:
        await db.set_portfolio_allocation(portfolio_id, user_id, a.symbol.upper(), a.target_percentage)
    return {"message": "Allocations saved"}


@app.get("/api/validate-keys")
async def validate_keys(_: bool = Depends(require_auth)):
    user_id = await _get_user_id()
    settings = await db.get_settings(user_id)
    if not settings or not settings.get("mexc_api_key"):
        return {"valid": False, "message": "No API keys configured"}
    client = MexcClient(settings["mexc_api_key"], settings["mexc_secret_key"])
    try:
        valid, msg = await client.validate_credentials()
    finally:
        await client.close()
    return {"valid": valid, "message": msg}


# ── Startup ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    await db.init()


# ── Serve React frontend ───────────────────────────────────────────────────────

_frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")

if os.path.exists(_frontend_dist):
    # Serve all static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="assets")

    # Serve other static files at root (favicon, icons, etc.)
    for _fname in os.listdir(_frontend_dist):
        _fpath = os.path.join(_frontend_dist, _fname)
        if os.path.isfile(_fpath) and _fname != "index.html":
            _captured = _fname
            @app.get(f"/{_captured}")
            async def _static_file(fname=_captured):
                return FileResponse(os.path.join(_frontend_dist, fname))

    # SPA catch-all — must be last
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(os.path.join(_frontend_dist, "index.html"))
