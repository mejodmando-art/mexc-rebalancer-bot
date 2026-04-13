"""
Database layer — PostgreSQL (Supabase) when DATABASE_URL is set, SQLite otherwise.

All public functions have identical signatures regardless of backend so the
rest of the codebase never needs to know which engine is active.
"""

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

log = logging.getLogger(__name__)

_DATABASE_URL: str | None = os.environ.get("DATABASE_URL")
_SQLITE_PATH = os.path.join(os.path.dirname(__file__), "portfolio.db")

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _try_postgres() -> bool:
    """Return True if psycopg2 is available and DATABASE_URL connects."""
    if not _DATABASE_URL:
        log.info("DATABASE_URL not set — using SQLite")
        return False
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        log.warning("psycopg2 not installed — falling back to SQLite")
        return False
    try:
        conn = psycopg2.connect(_DATABASE_URL)
        conn.close()
        log.info("PostgreSQL connection OK (Supabase)")
        return True
    except Exception as e:
        log.warning("PostgreSQL connection failed (%s: %s) — falling back to SQLite", type(e).__name__, e)
        return False


_USE_POSTGRES = _try_postgres()

if _USE_POSTGRES:
    import psycopg2

    @contextmanager
    def _conn() -> Generator:
        """Yield a psycopg2 connection; commit on success, rollback on error."""
        conn = psycopg2.connect(_DATABASE_URL)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    _BACKEND = "postgresql"

else:
    @contextmanager
    def _conn() -> Generator:
        """Yield a sqlite3 connection."""
        conn = sqlite3.connect(_SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    _BACKEND = "sqlite"


def _q(sql: str) -> str:
    """Replace '?' with '%s' for PostgreSQL."""
    if _BACKEND == "postgresql":
        return sql.replace("?", "%s")
    return sql


def _rows_to_dicts(rows, cursor=None) -> list[dict]:
    """Normalise rows from either backend into plain dicts."""
    if _BACKEND == "postgresql":
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in rows]
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create tables if they don't exist. Called once at startup."""
    if _BACKEND == "postgresql":
        stmts = [
            """
            CREATE TABLE IF NOT EXISTS rebalance_history (
                id           SERIAL PRIMARY KEY,
                ts           TEXT    NOT NULL,
                mode         TEXT    NOT NULL,
                total_usdt   REAL    NOT NULL,
                details      TEXT    NOT NULL,
                paper        INTEGER NOT NULL DEFAULT 0,
                portfolio_id INTEGER NOT NULL DEFAULT 1
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id           SERIAL PRIMARY KEY,
                ts           TEXT    NOT NULL,
                total_usdt   REAL    NOT NULL,
                assets_json  TEXT    NOT NULL,
                portfolio_id INTEGER NOT NULL DEFAULT 1
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS portfolios (
                id          SERIAL PRIMARY KEY,
                ts_created  TEXT    NOT NULL,
                name        TEXT    NOT NULL,
                config_json TEXT    NOT NULL,
                active      INTEGER NOT NULL DEFAULT 0
            )
            """,
        ]
        with _conn() as conn:
            cur = conn.cursor()
            for stmt in stmts:
                cur.execute(stmt)
            # Migration: add missing columns to existing tables
            migrations = [
                "ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS ts_created TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS config_json TEXT NOT NULL DEFAULT '{}'",
                "ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS active INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE rebalance_history ADD COLUMN IF NOT EXISTS portfolio_id INTEGER NOT NULL DEFAULT 1",
                "ALTER TABLE rebalance_history ADD COLUMN IF NOT EXISTS paper INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE portfolio_snapshots ADD COLUMN IF NOT EXISTS portfolio_id INTEGER NOT NULL DEFAULT 1",
            ]
            for m in migrations:
                try:
                    cur.execute(m)
                except Exception as e:
                    log.debug("Migration skipped (%s): %s", m[:50], e)
        log.info("PostgreSQL tables ready (Supabase)")
    else:
        with _conn() as conn:
            conn.executescript("""
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


# ---------------------------------------------------------------------------
# Rebalance history
# ---------------------------------------------------------------------------

def record_rebalance(
    mode: str,
    total_usdt: float,
    details: list,
    paper: bool = False,
) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("INSERT INTO rebalance_history (ts, mode, total_usdt, details, paper) VALUES (?,?,?,?,?)"),
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
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("SELECT * FROM rebalance_history ORDER BY id DESC LIMIT ?"),
                (limit,),
            )
            rows = _rows_to_dicts(cur.fetchall(), cur)
        for d in rows:
            d["details"] = json.loads(d["details"])
        return rows
    except Exception as e:
        log.error("get_rebalance_history failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Portfolio snapshots
# ---------------------------------------------------------------------------

def record_snapshot(total_usdt: float, assets: list) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("INSERT INTO portfolio_snapshots (ts, total_usdt, assets_json) VALUES (?,?,?)"),
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
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("SELECT ts, total_usdt FROM portfolio_snapshots WHERE portfolio_id=? ORDER BY id DESC LIMIT ?"),
                (portfolio_id, limit),
            )
            rows = _rows_to_dicts(cur.fetchall(), cur)
        return list(reversed(rows))
    except Exception as e:
        log.error("get_snapshots failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Multi-portfolio management
# ---------------------------------------------------------------------------

def save_portfolio(name: str, config: dict) -> int:
    """Save a new portfolio. Returns its new id. Raises on failure."""
    with _conn() as conn:
        cur = conn.cursor()
        if _BACKEND == "postgresql":
            cur.execute(
                "INSERT INTO portfolios (ts_created, name, config_json, active) VALUES (%s,%s,%s,0) RETURNING id",
                (
                    datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    name,
                    json.dumps(config),
                ),
            )
            return cur.fetchone()[0]
        else:
            cur.execute(
                "INSERT INTO portfolios (ts_created, name, config_json, active) VALUES (?,?,?,0)",
                (
                    datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    name,
                    json.dumps(config),
                ),
            )
            return cur.lastrowid


def list_portfolios() -> list:
    """Return all saved portfolios with summary fields."""
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, name, ts_created, active, config_json FROM portfolios ORDER BY id DESC"
            )
            rows = _rows_to_dicts(cur.fetchall(), cur)
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
                "assets": [
                    {"symbol": a["symbol"], "allocation_pct": a["allocation_pct"]}
                    for a in assets
                ],
                "paper_trading": cfg.get("paper_trading", False),
            })
        return result
    except Exception as e:
        log.error("list_portfolios failed: %s", e)
        return []


def get_portfolio(portfolio_id: int) -> dict | None:
    """Return full config of a saved portfolio."""
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("SELECT config_json FROM portfolios WHERE id=?"),
                (portfolio_id,),
            )
            row = cur.fetchone()
        if row:
            val = row[0] if _BACKEND == "postgresql" else row["config_json"]
            return json.loads(val)
        return None
    except Exception as e:
        log.error("get_portfolio failed: %s", e)
        return None


def set_active_portfolio(portfolio_id: int) -> None:
    """Mark one portfolio as active, clear others."""
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE portfolios SET active=0")
            cur.execute(
                _q("UPDATE portfolios SET active=1 WHERE id=?"),
                (portfolio_id,),
            )
    except Exception as e:
        log.error("set_active_portfolio failed: %s", e)


def delete_portfolio(portfolio_id: int) -> None:
    """Delete a portfolio and its associated history."""
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("DELETE FROM portfolios WHERE id=?"), (portfolio_id,))
            cur.execute(_q("DELETE FROM rebalance_history WHERE portfolio_id=?"), (portfolio_id,))
            cur.execute(_q("DELETE FROM portfolio_snapshots WHERE portfolio_id=?"), (portfolio_id,))
    except Exception as e:
        log.error("delete_portfolio failed: %s", e)


def update_portfolio_config(portfolio_id: int, config: dict) -> None:
    """Update the stored config of an existing portfolio."""
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("UPDATE portfolios SET config_json=? WHERE id=?"),
                (json.dumps(config), portfolio_id),
            )
    except Exception as e:
        log.error("update_portfolio_config failed: %s", e)
