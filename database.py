"""
SQLite database layer for rebalance history and portfolio snapshots.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime

log = logging.getLogger(__name__)

_SQLITE_PATH = os.path.join(os.path.dirname(__file__), "portfolio.db")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_SQLITE_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    """Create tables if they don't exist. Called once at startup."""
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS rebalance_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ts           TEXT    NOT NULL,
                mode         TEXT    NOT NULL,
                total_usdt   REAL    NOT NULL,
                details      TEXT    NOT NULL,
                paper        INTEGER NOT NULL DEFAULT 0,
                portfolio_id INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ts           TEXT    NOT NULL,
                total_usdt   REAL    NOT NULL,
                assets_json  TEXT    NOT NULL,
                portfolio_id INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS portfolios (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_created  TEXT    NOT NULL,
                name        TEXT    NOT NULL,
                config_json TEXT    NOT NULL,
                active      INTEGER NOT NULL DEFAULT 0
            );
        """)
    log.info("SQLite tables ready: %s", _SQLITE_PATH)


def record_rebalance(
    mode: str,
    total_usdt: float,
    details: list,
    paper: bool = False,
) -> None:
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO rebalance_history (ts, mode, total_usdt, details, paper) VALUES (?,?,?,?,?)",
                (
                    datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    mode,
                    total_usdt,
                    json.dumps(details),
                    int(paper),
                ),
            )
    except Exception as e:
        log.error("record_rebalance failed: %s", e)


def get_rebalance_history(limit: int = 10) -> list:
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT * FROM rebalance_history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["details"] = json.loads(d["details"])
            result.append(d)
        return result
    except Exception as e:
        log.error("get_rebalance_history failed: %s", e)
        return []


def record_snapshot(total_usdt: float, assets: list) -> None:
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO portfolio_snapshots (ts, total_usdt, assets_json) VALUES (?,?,?)",
                (
                    datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    total_usdt,
                    json.dumps(assets),
                ),
            )
    except Exception as e:
        log.error("record_snapshot failed: %s", e)


def get_snapshots(limit: int = 90, portfolio_id: int = 1) -> list:
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT ts, total_usdt FROM portfolio_snapshots WHERE portfolio_id=? ORDER BY id DESC LIMIT ?",
                (portfolio_id, limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]
    except Exception as e:
        log.error("get_snapshots failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Multi-portfolio management
# ---------------------------------------------------------------------------

def save_portfolio(name: str, config: dict) -> int:
    """Save a new portfolio. Returns its new id."""
    try:
        with _conn() as c:
            cur = c.execute(
                "INSERT INTO portfolios (ts_created, name, config_json, active) VALUES (?,?,?,0)",
                (
                    datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    name,
                    json.dumps(config),
                ),
            )
            return cur.lastrowid
    except Exception as e:
        log.error("save_portfolio failed: %s", e)
        return -1


def list_portfolios() -> list:
    """Return all saved portfolios (id, name, ts_created, active, summary)."""
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT id, name, ts_created, active, config_json FROM portfolios ORDER BY id DESC"
            ).fetchall()
        result = []
        for r in rows:
            cfg = json.loads(r["config_json"])
            assets = cfg.get("portfolio", {}).get("assets", [])
            result.append({
                "id": r["id"],
                "name": r["name"],
                "ts_created": r["ts_created"],
                "active": bool(r["active"]),
                "mode": cfg.get("rebalance", {}).get("mode", "—"),
                "total_usdt": cfg.get("portfolio", {}).get("total_usdt", 0),
                "assets": [{"symbol": a["symbol"], "allocation_pct": a["allocation_pct"]} for a in assets],
                "paper_trading": cfg.get("paper_trading", False),
            })
        return result
    except Exception as e:
        log.error("list_portfolios failed: %s", e)
        return []


def get_portfolio(portfolio_id: int) -> dict | None:
    """Return full config of a saved portfolio."""
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT config_json FROM portfolios WHERE id=?", (portfolio_id,)
            ).fetchone()
        if row:
            return json.loads(row["config_json"])
        return None
    except Exception as e:
        log.error("get_portfolio failed: %s", e)
        return None


def set_active_portfolio(portfolio_id: int) -> None:
    """Mark one portfolio as active, clear others."""
    try:
        with _conn() as c:
            c.execute("UPDATE portfolios SET active=0")
            c.execute("UPDATE portfolios SET active=1 WHERE id=?", (portfolio_id,))
    except Exception as e:
        log.error("set_active_portfolio failed: %s", e)


def delete_portfolio(portfolio_id: int) -> None:
    """Delete a saved portfolio and its history."""
    try:
        with _conn() as c:
            c.execute("DELETE FROM portfolios WHERE id=?", (portfolio_id,))
            c.execute("DELETE FROM rebalance_history WHERE portfolio_id=?", (portfolio_id,))
            c.execute("DELETE FROM portfolio_snapshots WHERE portfolio_id=?", (portfolio_id,))
    except Exception as e:
        log.error("delete_portfolio failed: %s", e)


def update_portfolio_config(portfolio_id: int, config: dict) -> None:
    """Update the stored config of an existing portfolio."""
    try:
        with _conn() as c:
            c.execute(
                "UPDATE portfolios SET config_json=? WHERE id=?",
                (json.dumps(config), portfolio_id),
            )
    except Exception as e:
        log.error("update_portfolio_config failed: %s", e)
