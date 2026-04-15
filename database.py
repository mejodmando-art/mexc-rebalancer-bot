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
    # options: force read-committed so every query sees the latest committed data.
    # This prevents stale reads when connections are reused from the pool
    # (critical for Supabase/PgBouncer in transaction-pooling mode on port 6543).
    dsn = _DATABASE_URL
    if "options=" not in (dsn or ""):
        sep = "&" if "?" in (dsn or "") else "?"
        dsn = f"{dsn}{sep}options=-c%20default_transaction_isolation%3Dread%5C%20committed"
    _pg_pool = pg_pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=5,
        dsn=dsn,
        connect_timeout=10,
    )
    log.info("PostgreSQL connection pool created (min=1, max=5)")
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
            # Always rollback any leftover transaction from a previous use of this
            # connection. This is essential with PgBouncer transaction-pooling mode
            # (Supabase port 6543): without it the connection may carry a stale
            # snapshot and return outdated rows.
            try:
                conn.rollback()
            except Exception:
                pass
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
                active      INTEGER NOT NULL DEFAULT 0,
                bot_running INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS grid_bots (
                id           SERIAL PRIMARY KEY,
                ts_created   TEXT    NOT NULL,
                symbol       TEXT    NOT NULL,
                investment   REAL    NOT NULL,
                grid_count   INTEGER NOT NULL DEFAULT 10,
                price_low    REAL    NOT NULL,
                price_high   REAL    NOT NULL,
                status       TEXT    NOT NULL DEFAULT 'running',
                profit       REAL    NOT NULL DEFAULT 0,
                orders_json  TEXT    NOT NULL DEFAULT '[]',
                config_json  TEXT    NOT NULL DEFAULT '{}'
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS grid_orders (
                id           SERIAL PRIMARY KEY,
                grid_bot_id  INTEGER NOT NULL,
                ts           TEXT    NOT NULL,
                order_id     TEXT    NOT NULL DEFAULT '',
                side         TEXT    NOT NULL,
                price        REAL    NOT NULL,
                qty          REAL    NOT NULL,
                status       TEXT    NOT NULL DEFAULT 'open',
                profit       REAL    NOT NULL DEFAULT 0
            )
            """,
        ]
        with _conn() as conn:
            cur = conn.cursor()
            # Safe migration: drop the old user_id column if it exists,
            # never drop the whole table (that would delete all portfolio data).
            cur.execute("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='portfolios' AND column_name='user_id'
                    ) THEN
                        ALTER TABLE portfolios DROP COLUMN IF EXISTS user_id;
                    END IF;
                END$$;
            """)
            for stmt in stmts:
                cur.execute(stmt)
            migrations = [
                "ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS bot_running INTEGER NOT NULL DEFAULT 0",
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
                    active      INTEGER NOT NULL DEFAULT 0,
                    bot_running INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS grid_bots (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_created   TEXT    NOT NULL,
                    symbol       TEXT    NOT NULL,
                    investment   REAL    NOT NULL,
                    grid_count   INTEGER NOT NULL DEFAULT 10,
                    price_low    REAL    NOT NULL,
                    price_high   REAL    NOT NULL,
                    status       TEXT    NOT NULL DEFAULT 'running',
                    profit       REAL    NOT NULL DEFAULT 0,
                    orders_json  TEXT    NOT NULL DEFAULT '[]',
                    config_json  TEXT    NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS grid_orders (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    grid_bot_id  INTEGER NOT NULL,
                    ts           TEXT    NOT NULL,
                    order_id     TEXT    NOT NULL DEFAULT '',
                    side         TEXT    NOT NULL,
                    price        REAL    NOT NULL,
                    qty          REAL    NOT NULL,
                    status       TEXT    NOT NULL DEFAULT 'open',
                    profit       REAL    NOT NULL DEFAULT 0
                );
            """)
        log.info("SQLite tables ready: %s", _SQLITE_PATH)


# ---------------------------------------------------------------------------
# Rebalance history
# ---------------------------------------------------------------------------

def record_rebalance(mode: str, total_usdt: float, details: list, paper: bool = False, portfolio_id: int | None = None) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            pid = portfolio_id if portfolio_id is not None else 1
            cur.execute(
                _q("INSERT INTO rebalance_history (ts, mode, total_usdt, details, paper, portfolio_id) VALUES (?,?,?,?,?,?)"),
                (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), mode, total_usdt, json.dumps(details), int(paper), pid),
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

def record_snapshot(total_usdt: float, assets: list, portfolio_id: int | None = None) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            pid = portfolio_id if portfolio_id is not None else 1
            cur.execute(
                _q("INSERT INTO portfolio_snapshots (ts, total_usdt, assets_json, portfolio_id) VALUES (?,?,?,?)"),
                (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), total_usdt, json.dumps(assets), pid),
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


def set_bot_running(portfolio_id: int, running: bool) -> None:
    """Persist the running state of a portfolio loop so it can be resumed after restart."""
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("UPDATE portfolios SET bot_running=? WHERE id=?"),
                (1 if running else 0, portfolio_id),
            )
    except Exception as e:
        log.error("set_bot_running failed: %s", e)


def get_running_portfolios() -> list[int]:
    """Return IDs of all portfolios that were running before the last restart."""
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM portfolios WHERE bot_running=1")
            rows = cur.fetchall()
        return [r[0] if not isinstance(r, dict) else r["id"] for r in rows]
    except Exception as e:
        log.error("get_running_portfolios failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Grid bots
# ---------------------------------------------------------------------------

def create_grid_bot(symbol: str, investment: float, grid_count: int,
                    price_low: float, price_high: float, config: dict) -> int:
    with _conn() as conn:
        cur = conn.cursor()
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        if _USE_POSTGRES:
            cur.execute(
                "INSERT INTO grid_bots (ts_created,symbol,investment,grid_count,price_low,price_high,status,profit,orders_json,config_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,'running',0,'[]',%s) RETURNING id",
                (ts, symbol, investment, grid_count, price_low, price_high, json.dumps(config)),
            )
            return cur.fetchone()[0]
        else:
            cur.execute(
                "INSERT INTO grid_bots (ts_created,symbol,investment,grid_count,price_low,price_high,status,profit,orders_json,config_json) "
                "VALUES (?,?,?,?,?,?,'running',0,'[]',?)",
                (ts, symbol, investment, grid_count, price_low, price_high, json.dumps(config)),
            )
            return cur.lastrowid


def list_grid_bots() -> list:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM grid_bots ORDER BY id DESC")
            rows = _rows_to_dicts(cur.fetchall(), cur)
        for r in rows:
            try:
                r["config"] = json.loads(r.get("config_json") or "{}")
            except Exception:
                r["config"] = {}
        return rows
    except Exception as e:
        log.error("list_grid_bots failed: %s", e)
        return []


def get_grid_bot(bot_id: int) -> dict | None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("SELECT * FROM grid_bots WHERE id=?"), (bot_id,))
            rows = _rows_to_dicts(cur.fetchall(), cur)
        if rows:
            r = rows[0]
            try:
                r["config"] = json.loads(r.get("config_json") or "{}")
            except Exception:
                r["config"] = {}
            return r
        return None
    except Exception as e:
        log.error("get_grid_bot failed: %s", e)
        return None


def update_grid_bot_status(bot_id: int, status: str) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("UPDATE grid_bots SET status=? WHERE id=?"), (status, bot_id))
    except Exception as e:
        log.error("update_grid_bot_status failed: %s", e)


def update_grid_bot_profit(bot_id: int, profit: float) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("UPDATE grid_bots SET profit=? WHERE id=?"), (profit, bot_id))
    except Exception as e:
        log.error("update_grid_bot_profit failed: %s", e)


def delete_grid_bot(bot_id: int) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("DELETE FROM grid_bots WHERE id=?"), (bot_id,))
            cur.execute(_q("DELETE FROM grid_orders WHERE grid_bot_id=?"), (bot_id,))
    except Exception as e:
        log.error("delete_grid_bot failed: %s", e)


def add_grid_order(bot_id: int, order_id: str, side: str,
                   price: float, qty: float) -> int:
    with _conn() as conn:
        cur = conn.cursor()
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        if _USE_POSTGRES:
            cur.execute(
                "INSERT INTO grid_orders (grid_bot_id,ts,order_id,side,price,qty,status,profit) "
                "VALUES (%s,%s,%s,%s,%s,%s,'open',0) RETURNING id",
                (bot_id, ts, order_id, side, price, qty),
            )
            return cur.fetchone()[0]
        else:
            cur.execute(
                "INSERT INTO grid_orders (grid_bot_id,ts,order_id,side,price,qty,status,profit) "
                "VALUES (?,?,?,?,?,?,'open',0)",
                (bot_id, ts, order_id, side, price, qty),
            )
            return cur.lastrowid


def get_grid_orders(bot_id: int) -> list:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("SELECT * FROM grid_orders WHERE grid_bot_id=? ORDER BY id DESC"), (bot_id,))
            return _rows_to_dicts(cur.fetchall(), cur)
    except Exception as e:
        log.error("get_grid_orders failed: %s", e)
        return []


def update_grid_order(order_id: str, status: str, profit: float = 0) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("UPDATE grid_orders SET status=?, profit=? WHERE order_id=?"),
                (status, profit, order_id),
            )
    except Exception as e:
        log.error("update_grid_order failed: %s", e)
