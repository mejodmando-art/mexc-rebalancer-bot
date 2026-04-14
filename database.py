"""
Database layer — PostgreSQL (Railway) when DATABASE_URL is set, SQLite otherwise.

PostgreSQL uses a persistent connection pool (psycopg2.pool.ThreadedConnectionPool)
so every query reuses an existing connection instead of opening a new one.
Transient errors (dropped connections, Railway restarts) are retried automatically.
"""

import json
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

log = logging.getLogger(__name__)

_DATABASE_URL: str | None = os.environ.get("DATABASE_URL")
_SQLITE_PATH = os.path.join(os.path.dirname(__file__), "portfolio.db")

# ---------------------------------------------------------------------------
# PostgreSQL connection pool
# ---------------------------------------------------------------------------

_pg_pool = None  # ThreadedConnectionPool, initialised lazily


def _get_pg_pool():
    """Return (or create) the shared PostgreSQL connection pool."""
    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool
    from psycopg2 import pool as pg_pool
    _pg_pool = pg_pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=10,
        dsn=_DATABASE_URL,
        connect_timeout=10,
    )
    log.info("PostgreSQL connection pool created (min=1, max=10)")
    return _pg_pool


def _try_postgres() -> bool:
    if not _DATABASE_URL:
        log.info("DATABASE_URL not set — using SQLite")
        return False
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        log.warning("psycopg2 not installed — falling back to SQLite")
        return False
    try:
        _get_pg_pool()
        return True
    except Exception as e:
        log.warning("PostgreSQL unavailable (%s) — falling back to SQLite", e)
        return False


_USE_POSTGRES = _try_postgres()

# ---------------------------------------------------------------------------
# Connection context managers
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_RETRY_DELAY = 0.5  # seconds


@contextmanager
def _conn() -> Generator:
    if _USE_POSTGRES:
        with _pg_conn() as conn:
            yield conn
    else:
        with _sqlite_conn() as conn:
            yield conn


@contextmanager
def _pg_conn() -> Generator:
    global _pg_pool
    last_err = None
    for attempt in range(_MAX_RETRIES):
        conn = None
        try:
            pool = _get_pg_pool()
            conn = pool.getconn()
            conn.autocommit = False
            yield conn
            conn.commit()
            pool.putconn(conn)
            return
        except Exception as e:
            last_err = e
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
                try:
                    if _pg_pool:
                        _pg_pool.putconn(conn, close=True)
                except Exception:
                    pass
            # Reset pool so next attempt creates fresh connections
            _pg_pool = None
            log.warning("PostgreSQL error (attempt %d/%d): %s", attempt + 1, _MAX_RETRIES, e)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY * (attempt + 1))
    raise last_err


@contextmanager
def _sqlite_conn() -> Generator:
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _q(sql: str) -> str:
    if _USE_POSTGRES:
        return sql.replace("?", "%s")
    return sql


def _rows_to_dicts(rows, cursor=None) -> list[dict]:
    if _USE_POSTGRES:
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in rows]
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db() -> None:
    if _USE_POSTGRES:
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
            cur.execute("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='portfolios' AND column_name='user_id'
                    ) THEN
                        DROP TABLE IF EXISTS portfolios CASCADE;
                    END IF;
                END$$;
            """)
            for stmt in stmts:
                cur.execute(stmt)
            migrations = [
                "ALTER TABLE rebalance_history ADD COLUMN IF NOT EXISTS ts TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE rebalance_history ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE rebalance_history ADD COLUMN IF NOT EXISTS total_usdt REAL NOT NULL DEFAULT 0",
                "ALTER TABLE rebalance_history ADD COLUMN IF NOT EXISTS details TEXT NOT NULL DEFAULT '[]'",
                "ALTER TABLE rebalance_history ADD COLUMN IF NOT EXISTS paper INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE rebalance_history ADD COLUMN IF NOT EXISTS portfolio_id INTEGER NOT NULL DEFAULT 1",
                "ALTER TABLE portfolio_snapshots ADD COLUMN IF NOT EXISTS ts TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE portfolio_snapshots ADD COLUMN IF NOT EXISTS total_usdt REAL NOT NULL DEFAULT 0",
                "ALTER TABLE portfolio_snapshots ADD COLUMN IF NOT EXISTS assets_json TEXT NOT NULL DEFAULT '[]'",
                "ALTER TABLE portfolio_snapshots ADD COLUMN IF NOT EXISTS portfolio_id INTEGER NOT NULL DEFAULT 1",
            ]
            for m in migrations:
                try:
                    cur.execute(m)
                except Exception as e:
                    log.debug("Migration skipped: %s", e)
        log.info("PostgreSQL tables ready (Railway)")
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

def record_rebalance(mode: str, total_usdt: float, details: list, paper: bool = False) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("INSERT INTO rebalance_history (ts, mode, total_usdt, details, paper) VALUES (?,?,?,?,?)"),
                (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), mode, total_usdt, json.dumps(details), int(paper)),
            )
    except Exception as e:
        log.error("record_rebalance failed: %s", e)


def get_rebalance_history(limit: int = 10) -> list:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("SELECT * FROM rebalance_history ORDER BY id DESC LIMIT ?"), (limit,))
            rows = _rows_to_dicts(cur.fetchall(), cur)
        for d in rows:
            raw = d.get("details") or "[]"
            try:
                d["details"] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                d["details"] = []
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
                (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), total_usdt, json.dumps(assets)),
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
    with _conn() as conn:
        cur = conn.cursor()
        if _USE_POSTGRES:
            cur.execute(
                "INSERT INTO portfolios (ts_created, name, config_json, active) VALUES (%s,%s,%s,0) RETURNING id",
                (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), name, json.dumps(config)),
            )
            return cur.fetchone()[0]
        else:
            cur.execute(
                "INSERT INTO portfolios (ts_created, name, config_json, active) VALUES (?,?,?,0)",
                (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), name, json.dumps(config)),
            )
            return cur.lastrowid


def list_portfolios() -> list:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, name, ts_created, active, config_json FROM portfolios ORDER BY id DESC")
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
                "assets": [{"symbol": a["symbol"], "allocation_pct": a["allocation_pct"]} for a in assets],
                "paper_trading": cfg.get("paper_trading", False),
            })
        return result
    except Exception as e:
        log.error("list_portfolios failed: %s", e)
        return []


def get_portfolio(portfolio_id: int) -> dict | None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("SELECT config_json FROM portfolios WHERE id=?"), (portfolio_id,))
            row = cur.fetchone()
        if row:
            val = row[0] if _USE_POSTGRES else row["config_json"]
            return json.loads(val)
        return None
    except Exception as e:
        log.error("get_portfolio failed: %s", e)
        return None


def set_active_portfolio(portfolio_id: int) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE portfolios SET active=0")
            cur.execute(_q("UPDATE portfolios SET active=1 WHERE id=?"), (portfolio_id,))
    except Exception as e:
        log.error("set_active_portfolio failed: %s", e)


def delete_portfolio(portfolio_id: int) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("DELETE FROM portfolios WHERE id=?"), (portfolio_id,))
            cur.execute(_q("DELETE FROM rebalance_history WHERE portfolio_id=?"), (portfolio_id,))
            cur.execute(_q("DELETE FROM portfolio_snapshots WHERE portfolio_id=?"), (portfolio_id,))
    except Exception as e:
        log.error("delete_portfolio failed: %s", e)


def update_portfolio_config(portfolio_id: int, config: dict) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("UPDATE portfolios SET config_json=? WHERE id=?"),
                (json.dumps(config), portfolio_id),
            )
    except Exception as e:
        log.error("update_portfolio_config failed: %s", e)
