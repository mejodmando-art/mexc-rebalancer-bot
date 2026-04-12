"""
PostgreSQL database layer (Supabase) for rebalance history and portfolio snapshots.

Uses psycopg2 (sync) so it works from both the bot thread and FastAPI.
Connection string is read from DATABASE_URL environment variable.

Falls back to SQLite if DATABASE_URL is not set (local dev without Supabase).
"""

import json
import logging
import os
import sqlite3
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

DATABASE_URL: Optional[str] = os.environ.get("DATABASE_URL", "")


def _use_postgres() -> bool:
    return bool(DATABASE_URL and DATABASE_URL.startswith("postgresql"))


# ---------------------------------------------------------------------------
# PostgreSQL helpers
# ---------------------------------------------------------------------------

def _pg_conn():
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def _pg_init() -> None:
    conn = _pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS rebalance_history (
                    id          SERIAL PRIMARY KEY,
                    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    mode        TEXT        NOT NULL,
                    total_usdt  DOUBLE PRECISION NOT NULL,
                    details     JSONB       NOT NULL,
                    paper       BOOLEAN     NOT NULL DEFAULT FALSE
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id          SERIAL PRIMARY KEY,
                    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    total_usdt  DOUBLE PRECISION NOT NULL,
                    assets_json JSONB       NOT NULL
                );
            """)
        conn.commit()
        log.info("PostgreSQL tables ready (Supabase)")
    finally:
        conn.close()


def _pg_record_rebalance(mode: str, total_usdt: float, details: list, paper: bool) -> None:
    conn = _pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rebalance_history (ts, mode, total_usdt, details, paper) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    mode,
                    total_usdt,
                    json.dumps(details),
                    paper,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _pg_get_rebalance_history(limit: int) -> list:
    conn = _pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, ts::text, mode, total_usdt, details, paper "
                "FROM rebalance_history ORDER BY id DESC LIMIT %s",
                (limit,),
            )
            rows = cur.fetchall()
        result = []
        for r in rows:
            details = r[4]
            if isinstance(details, str):
                details = json.loads(details)
            result.append({
                "id":         r[0],
                "ts":         r[1],
                "mode":       r[2],
                "total_usdt": r[3],
                "details":    details,
                "paper":      r[5],
            })
        return result
    finally:
        conn.close()


def _pg_record_snapshot(total_usdt: float, assets: list) -> None:
    conn = _pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO portfolio_snapshots (ts, total_usdt, assets_json) VALUES (%s, %s, %s)",
                (
                    datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    total_usdt,
                    json.dumps(assets),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _pg_get_snapshots(limit: int) -> list:
    conn = _pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ts::text, total_usdt FROM portfolio_snapshots "
                "ORDER BY id DESC LIMIT %s",
                (limit,),
            )
            rows = cur.fetchall()
        return [{"ts": r[0], "total_usdt": r[1]} for r in reversed(rows)]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# SQLite fallback (local dev without Supabase)
# ---------------------------------------------------------------------------

_SQLITE_PATH = os.path.join(os.path.dirname(__file__), "portfolio.db")


def _sq_conn() -> sqlite3.Connection:
    c = sqlite3.connect(_SQLITE_PATH)
    c.row_factory = sqlite3.Row
    return c


def _sq_init() -> None:
    with _sq_conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS rebalance_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT    NOT NULL,
                mode        TEXT    NOT NULL,
                total_usdt  REAL    NOT NULL,
                details     TEXT    NOT NULL,
                paper       INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT    NOT NULL,
                total_usdt  REAL    NOT NULL,
                assets_json TEXT    NOT NULL
            );
        """)
    log.info("SQLite tables ready (local fallback)")


def _sq_record_rebalance(mode: str, total_usdt: float, details: list, paper: bool) -> None:
    with _sq_conn() as c:
        c.execute(
            "INSERT INTO rebalance_history (ts, mode, total_usdt, details, paper) VALUES (?,?,?,?,?)",
            (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), mode, total_usdt, json.dumps(details), int(paper)),
        )


def _sq_get_rebalance_history(limit: int) -> list:
    with _sq_conn() as c:
        rows = c.execute(
            "SELECT * FROM rebalance_history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["details"] = json.loads(d["details"])
        result.append(d)
    return result


def _sq_record_snapshot(total_usdt: float, assets: list) -> None:
    with _sq_conn() as c:
        c.execute(
            "INSERT INTO portfolio_snapshots (ts, total_usdt, assets_json) VALUES (?,?,?)",
            (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), total_usdt, json.dumps(assets)),
        )


def _sq_get_snapshots(limit: int) -> list:
    with _sq_conn() as c:
        rows = c.execute(
            "SELECT ts, total_usdt FROM portfolio_snapshots ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


# ---------------------------------------------------------------------------
# Public API – same interface regardless of backend
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create tables if they don't exist. Called once at startup."""
    if _use_postgres():
        _pg_init()
    else:
        _sq_init()


def record_rebalance(
    mode: str,
    total_usdt: float,
    details: list,
    paper: bool = False,
) -> None:
    try:
        if _use_postgres():
            _pg_record_rebalance(mode, total_usdt, details, paper)
        else:
            _sq_record_rebalance(mode, total_usdt, details, paper)
    except Exception as e:
        log.error("record_rebalance failed: %s", e)


def get_rebalance_history(limit: int = 10) -> list:
    try:
        if _use_postgres():
            return _pg_get_rebalance_history(limit)
        return _sq_get_rebalance_history(limit)
    except Exception as e:
        log.error("get_rebalance_history failed: %s", e)
        return []


def record_snapshot(total_usdt: float, assets: list) -> None:
    try:
        if _use_postgres():
            _pg_record_snapshot(total_usdt, assets)
        else:
            _sq_record_snapshot(total_usdt, assets)
    except Exception as e:
        log.error("record_snapshot failed: %s", e)


def get_snapshots(limit: int = 90) -> list:
    try:
        if _use_postgres():
            return _pg_get_snapshots(limit)
        return _sq_get_snapshots(limit)
    except Exception as e:
        log.error("get_snapshots failed: %s", e)
        return []
