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
_BACKEND = "postgresql" if _USE_POSTGRES else "sqlite"

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
    """
    PostgreSQL connection context manager with retry logic on connection errors.

    The retry loop only covers *connection acquisition* — the yield happens
    exactly once, outside the loop.  This prevents the RuntimeError that occurs
    when a @contextmanager generator tries to yield a second time after catching
    an exception thrown by the caller's with-block.
    """
    global _pg_pool
    last_err = None
    conn = None
    pool = None

    # --- Acquire a connection with retries ---
    for attempt in range(_MAX_RETRIES):
        try:
            pool = _get_pg_pool()
            conn = pool.getconn()
            # Always rollback any leftover transaction from a previous use of
            # this connection.  Critical for PgBouncer transaction-pooling mode
            # (Supabase port 6543) so the connection doesn't carry a stale
            # snapshot and return outdated rows.
            try:
                conn.rollback()
            except Exception:
                pass
            conn.autocommit = False
            break  # connection acquired successfully
        except Exception as e:
            last_err = e
            if conn is not None:
                try:
                    if pool:
                        pool.putconn(conn, close=True)
                except Exception:
                    pass
                conn = None
            # Reset pool so the next attempt creates fresh connections
            _pg_pool = None
            pool = None
            log.warning("PostgreSQL connection error (attempt %d/%d): %s", attempt + 1, _MAX_RETRIES, e)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY * (attempt + 1))
    else:
        # All retries exhausted — raise the last connection error
        raise last_err

    # --- Single yield outside the retry loop ---
    try:
        yield conn
        conn.commit()
        if pool:
            pool.putconn(conn)
        else:
            conn.close()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            if pool:
                pool.putconn(conn, close=True)
            else:
                conn.close()
        except Exception:
            pass
        _pg_pool = None
        raise


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
            """
            CREATE TABLE IF NOT EXISTS grid_bots (
                id              SERIAL PRIMARY KEY,
                ts_created      TEXT    NOT NULL,
                symbol          TEXT    NOT NULL,
                investment      REAL    NOT NULL,
                grid_count      INTEGER NOT NULL DEFAULT 10,
                price_low       REAL    NOT NULL,
                price_high      REAL    NOT NULL,
                status          TEXT    NOT NULL DEFAULT 'running',
                profit          REAL    NOT NULL DEFAULT 0,
                orders_json     TEXT    NOT NULL DEFAULT '[]',
                config_json     TEXT    NOT NULL DEFAULT '{}',
                mode            TEXT    NOT NULL DEFAULT 'normal',
                avg_buy_price   REAL    NOT NULL DEFAULT 0,
                base_qty        REAL    NOT NULL DEFAULT 0,
                unrealized_pnl  REAL    NOT NULL DEFAULT 0,
                realised_profit REAL    NOT NULL DEFAULT 0
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
                "ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS bot_running INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE grid_bots ADD COLUMN IF NOT EXISTS should_run INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE grid_bots ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'normal'",
                "ALTER TABLE grid_bots ADD COLUMN IF NOT EXISTS avg_buy_price REAL NOT NULL DEFAULT 0",
                "ALTER TABLE grid_bots ADD COLUMN IF NOT EXISTS base_qty REAL NOT NULL DEFAULT 0",
                "ALTER TABLE grid_bots ADD COLUMN IF NOT EXISTS unrealized_pnl REAL NOT NULL DEFAULT 0",
                "ALTER TABLE grid_bots ADD COLUMN IF NOT EXISTS realised_profit REAL NOT NULL DEFAULT 0",
                "ALTER TABLE grid_bots ADD COLUMN IF NOT EXISTS shift_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE grid_bots ADD COLUMN IF NOT EXISTS initial_range_pct REAL NOT NULL DEFAULT 5.0",
                "ALTER TABLE grid_bots ADD COLUMN IF NOT EXISTS lower_pct REAL NOT NULL DEFAULT 5.0",
                "ALTER TABLE grid_bots ADD COLUMN IF NOT EXISTS upper_pct REAL NOT NULL DEFAULT 5.0",
                "ALTER TABLE grid_bots ADD COLUMN IF NOT EXISTS expand_direction TEXT NOT NULL DEFAULT 'both'",
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
                CREATE TABLE IF NOT EXISTS grid_bots (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_created      TEXT    NOT NULL,
                    symbol          TEXT    NOT NULL,
                    investment      REAL    NOT NULL,
                    grid_count      INTEGER NOT NULL DEFAULT 10,
                    price_low       REAL    NOT NULL,
                    price_high      REAL    NOT NULL,
                    status          TEXT    NOT NULL DEFAULT 'running',
                    profit          REAL    NOT NULL DEFAULT 0,
                    orders_json     TEXT    NOT NULL DEFAULT '[]',
                    config_json     TEXT    NOT NULL DEFAULT '{}',
                    mode            TEXT    NOT NULL DEFAULT 'normal',
                    avg_buy_price   REAL    NOT NULL DEFAULT 0,
                    base_qty        REAL    NOT NULL DEFAULT 0,
                    unrealized_pnl  REAL    NOT NULL DEFAULT 0,
                    realised_profit REAL    NOT NULL DEFAULT 0
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
        # SQLite doesn't support IF NOT EXISTS in ALTER TABLE, so we try/except
        try:
            with _conn() as conn:
                conn.execute("ALTER TABLE portfolios ADD COLUMN bot_running INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass  # column already exists
        try:
            with _conn() as conn:
                conn.execute("ALTER TABLE grid_bots ADD COLUMN should_run INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            with _conn() as conn:
                conn.execute("ALTER TABLE grid_bots ADD COLUMN mode TEXT NOT NULL DEFAULT 'normal'")
        except Exception:
            pass
        try:
            with _conn() as conn:
                conn.execute("ALTER TABLE grid_bots ADD COLUMN avg_buy_price REAL NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            with _conn() as conn:
                conn.execute("ALTER TABLE grid_bots ADD COLUMN base_qty REAL NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            with _conn() as conn:
                conn.execute("ALTER TABLE grid_bots ADD COLUMN unrealized_pnl REAL NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            with _conn() as conn:
                conn.execute("ALTER TABLE grid_bots ADD COLUMN realised_profit REAL NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            with _conn() as conn:
                conn.execute("ALTER TABLE grid_bots ADD COLUMN shift_count INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            with _conn() as conn:
                conn.execute("ALTER TABLE grid_bots ADD COLUMN initial_range_pct REAL NOT NULL DEFAULT 5.0")
        except Exception:
            pass
        try:
            with _conn() as conn:
                conn.execute("ALTER TABLE grid_bots ADD COLUMN lower_pct REAL NOT NULL DEFAULT 5.0")
        except Exception:
            pass
        try:
            with _conn() as conn:
                conn.execute("ALTER TABLE grid_bots ADD COLUMN upper_pct REAL NOT NULL DEFAULT 5.0")
        except Exception:
            pass
        try:
            with _conn() as conn:
                conn.execute("ALTER TABLE grid_bots ADD COLUMN expand_direction TEXT NOT NULL DEFAULT 'both'")
        except Exception:
            pass
        log.info("SQLite tables ready: %s", _SQLITE_PATH)


# ---------------------------------------------------------------------------
# Rebalance history
# ---------------------------------------------------------------------------

def record_rebalance(mode: str, total_usdt: float, details: list,
                     paper: bool = False, portfolio_id: int = 1) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("INSERT INTO rebalance_history (ts, mode, total_usdt, details, paper, portfolio_id) VALUES (?,?,?,?,?,?)"),
                (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), mode, total_usdt, json.dumps(details), int(paper), portfolio_id),
            )
    except Exception as e:
        log.error("record_rebalance failed: %s", e)


def get_rebalance_history(limit: int = 10, portfolio_id: int = 1) -> list:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("SELECT * FROM rebalance_history WHERE portfolio_id=? ORDER BY id DESC LIMIT ?"),
                (portfolio_id, limit),
            )
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

def record_snapshot(total_usdt: float, assets: list, portfolio_id: int = 1) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("INSERT INTO portfolio_snapshots (ts, total_usdt, assets_json, portfolio_id) VALUES (?,?,?,?)"),
                (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), total_usdt, json.dumps(assets), portfolio_id),
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


# ---------------------------------------------------------------------------
# Grid bots
# ---------------------------------------------------------------------------

def create_grid_bot(symbol: str, investment: float, grid_count: int,
                    price_low: float, price_high: float, config: dict,
                    mode: str = "normal") -> int:
    with _conn() as conn:
        cur = conn.cursor()
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        if _USE_POSTGRES:
            cur.execute(
                "INSERT INTO grid_bots "
                "(ts_created,symbol,investment,grid_count,price_low,price_high,status,profit,orders_json,config_json,mode) "
                "VALUES (%s,%s,%s,%s,%s,%s,'running',0,'[]',%s,%s) RETURNING id",
                (ts, symbol, investment, grid_count, price_low, price_high, json.dumps(config), mode),
            )
            return cur.fetchone()[0]
        else:
            cur.execute(
                "INSERT INTO grid_bots "
                "(ts_created,symbol,investment,grid_count,price_low,price_high,status,profit,orders_json,config_json,mode) "
                "VALUES (?,?,?,?,?,?,'running',0,'[]',?,?)",
                (ts, symbol, investment, grid_count, price_low, price_high, json.dumps(config), mode),
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


def update_grid_bot_position(bot_id: int, avg_buy_price: float,
                              base_qty: float, unrealized_pnl: float,
                              realised_profit: float | None = None) -> None:
    """Update position tracking: average buy price, held base qty, unrealized P&L.
    Also updates realised_profit and the combined profit column."""
    try:
        with _conn() as conn:
            cur = conn.cursor()
            if realised_profit is not None:
                total = round(realised_profit + unrealized_pnl, 4)
                cur.execute(
                    _q("UPDATE grid_bots SET avg_buy_price=?, base_qty=?, unrealized_pnl=?, realised_profit=?, profit=? WHERE id=?"),
                    (avg_buy_price, base_qty, unrealized_pnl, realised_profit, total, bot_id),
                )
            else:
                cur.execute(
                    _q("UPDATE grid_bots SET avg_buy_price=?, base_qty=?, unrealized_pnl=? WHERE id=?"),
                    (avg_buy_price, base_qty, unrealized_pnl, bot_id),
                )
    except Exception as e:
        log.error("update_grid_bot_position failed: %s", e)


def update_grid_bot_range(bot_id: int, price_low: float, price_high: float,
                           grid_count: int) -> None:
    """Update grid range after dynamic re-adjustment."""
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("UPDATE grid_bots SET price_low=?, price_high=?, grid_count=? WHERE id=?"),
                (price_low, price_high, grid_count, bot_id),
            )
    except Exception as e:
        log.error("update_grid_bot_range failed: %s", e)


def increment_grid_shift_count(bot_id: int) -> int:
    """Increment shift_count and return the new value."""
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("UPDATE grid_bots SET shift_count = shift_count + 1 WHERE id=?"), (bot_id,))
            cur.execute(_q("SELECT shift_count FROM grid_bots WHERE id=?"), (bot_id,))
            row = cur.fetchone()
            return int(row[0] if _USE_POSTGRES else row["shift_count"])
    except Exception as e:
        log.error("increment_grid_shift_count failed: %s", e)
        return 1


def get_grid_shift_info(bot_id: int) -> tuple[int, float]:
    """Return (shift_count, initial_range_pct) for a bot."""
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("SELECT shift_count, initial_range_pct FROM grid_bots WHERE id=?"), (bot_id,))
            row = cur.fetchone()
            if row:
                if _USE_POSTGRES:
                    return int(row[0]), float(row[1])
                return int(row["shift_count"]), float(row["initial_range_pct"])
    except Exception as e:
        log.error("get_grid_shift_info failed: %s", e)
    return 0, 5.0


def set_grid_range_pcts(bot_id: int, lower_pct: float, upper_pct: float) -> None:
    """Store the user-defined lower/upper % range for a bot."""
    try:
        with _conn() as conn:
            conn.cursor().execute(
                _q("UPDATE grid_bots SET lower_pct=?, upper_pct=? WHERE id=?"),
                (lower_pct, upper_pct, bot_id),
            )
    except Exception as e:
        log.error("set_grid_range_pcts failed: %s", e)


def get_grid_range_pcts(bot_id: int) -> tuple[float, float]:
    """Return (lower_pct, upper_pct) for a bot."""
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("SELECT lower_pct, upper_pct FROM grid_bots WHERE id=?"), (bot_id,))
            row = cur.fetchone()
            if row:
                if _USE_POSTGRES:
                    return float(row[0]), float(row[1])
                return float(row["lower_pct"]), float(row["upper_pct"])
    except Exception as e:
        log.error("get_grid_range_pcts failed: %s", e)
    return 5.0, 5.0


def set_grid_expand_direction(bot_id: int, direction: str) -> None:
    """Store expand direction: 'both' | 'lower' | 'upper'."""
    try:
        with _conn() as conn:
            conn.cursor().execute(
                _q("UPDATE grid_bots SET expand_direction=? WHERE id=?"),
                (direction, bot_id),
            )
    except Exception as e:
        log.error("set_grid_expand_direction failed: %s", e)


def get_grid_expand_direction(bot_id: int) -> str:
    """Return expand_direction for a bot ('both' | 'lower' | 'upper')."""
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("SELECT expand_direction FROM grid_bots WHERE id=?"), (bot_id,))
            row = cur.fetchone()
            if row:
                return str(row[0] if _USE_POSTGRES else row["expand_direction"])
    except Exception as e:
        log.error("get_grid_expand_direction failed: %s", e)
    return "both"


def set_grid_initial_range_pct(bot_id: int, pct: float) -> None:
    """Store the initial range % so expansions can double it each time."""
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("UPDATE grid_bots SET initial_range_pct=? WHERE id=?"), (pct, bot_id))
    except Exception as e:
        log.error("set_grid_initial_range_pct failed: %s", e)


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


# ---------------------------------------------------------------------------
# Bot running state (persisted across restarts)
# ---------------------------------------------------------------------------

def set_bot_running(portfolio_id: int, running: bool) -> None:
    """Mark a portfolio's bot loop as running or stopped in the database."""
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
    """Return the IDs of all portfolios whose bot_running flag is set."""
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM portfolios WHERE bot_running=1")
            rows = cur.fetchall()
        if _USE_POSTGRES:
            return [row[0] for row in rows]
        return [row["id"] for row in rows]
    except Exception as e:
        log.error("get_running_portfolios failed: %s", e)
        return []


def set_grid_bot_should_run(bot_id: int, should_run: bool) -> None:
    """Persist the user's intent to keep this grid bot running across restarts."""
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("UPDATE grid_bots SET should_run=? WHERE id=?"),
                (1 if should_run else 0, bot_id),
            )
    except Exception as e:
        log.error("set_grid_bot_should_run failed: %s", e)


def get_should_run_grid_bots() -> list[int]:
    """Return IDs of grid bots that should be auto-resumed on startup."""
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM grid_bots WHERE should_run=1")
            rows = cur.fetchall()
        if _USE_POSTGRES:
            return [row[0] for row in rows]
        return [row["id"] for row in rows]
    except Exception as e:
        log.error("get_should_run_grid_bots failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# OB Scanner — schema migration
# ---------------------------------------------------------------------------

def _init_ob_scanner_tables() -> None:
    """Create ob_scanners and ob_trades tables if they don't exist."""
    if _USE_POSTGRES:
        stmts = [
            """
            CREATE TABLE IF NOT EXISTS ob_scanners (
                id              SERIAL PRIMARY KEY,
                ts_created      TEXT    NOT NULL,
                symbol          TEXT    NOT NULL,
                timeframe       TEXT    NOT NULL DEFAULT '15m',
                entry_usdt      REAL    NOT NULL DEFAULT 15.0,
                tp1_pct         REAL    NOT NULL DEFAULT 5.0,
                tp2_pct         REAL    NOT NULL DEFAULT 5.0,
                status          TEXT    NOT NULL DEFAULT 'scanning',
                should_run      INTEGER NOT NULL DEFAULT 1,
                entry_price     REAL    NOT NULL DEFAULT 0,
                base_qty        REAL    NOT NULL DEFAULT 0,
                tp1_hit         INTEGER NOT NULL DEFAULT 0,
                realised_pnl    REAL    NOT NULL DEFAULT 0,
                conditions_json TEXT    NOT NULL DEFAULT '{}'
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ob_trades (
                id          SERIAL PRIMARY KEY,
                scanner_id  INTEGER NOT NULL,
                ts          TEXT    NOT NULL,
                side        TEXT    NOT NULL,
                price       REAL    NOT NULL,
                qty         REAL    NOT NULL,
                usdt_value  REAL    NOT NULL DEFAULT 0,
                pnl         REAL    NOT NULL DEFAULT 0,
                label       TEXT    NOT NULL DEFAULT ''
            )
            """,
        ]
        with _conn() as conn:
            cur = conn.cursor()
            for stmt in stmts:
                cur.execute(stmt)
    else:
        with _conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS ob_scanners (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_created      TEXT    NOT NULL,
                    symbol          TEXT    NOT NULL,
                    timeframe       TEXT    NOT NULL DEFAULT '15m',
                    entry_usdt      REAL    NOT NULL DEFAULT 15.0,
                    tp1_pct         REAL    NOT NULL DEFAULT 5.0,
                    tp2_pct         REAL    NOT NULL DEFAULT 5.0,
                    status          TEXT    NOT NULL DEFAULT 'scanning',
                    should_run      INTEGER NOT NULL DEFAULT 1,
                    entry_price     REAL    NOT NULL DEFAULT 0,
                    base_qty        REAL    NOT NULL DEFAULT 0,
                    tp1_hit         INTEGER NOT NULL DEFAULT 0,
                    realised_pnl    REAL    NOT NULL DEFAULT 0,
                    conditions_json TEXT    NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS ob_trades (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    scanner_id  INTEGER NOT NULL,
                    ts          TEXT    NOT NULL,
                    side        TEXT    NOT NULL,
                    price       REAL    NOT NULL,
                    qty         REAL    NOT NULL,
                    usdt_value  REAL    NOT NULL DEFAULT 0,
                    pnl         REAL    NOT NULL DEFAULT 0,
                    label       TEXT    NOT NULL DEFAULT ''
                );
            """)


# ---------------------------------------------------------------------------
# OB Scanner — CRUD
# ---------------------------------------------------------------------------

def create_ob_scanner(symbol: str, timeframe: str = "15m",
                       entry_usdt: float = 15.0,
                       tp1_pct: float = 5.0,
                       tp2_pct: float = 5.0) -> int:
    _init_ob_scanner_tables()
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        cur = conn.cursor()
        if _USE_POSTGRES:
            cur.execute(
                "INSERT INTO ob_scanners (ts_created,symbol,timeframe,entry_usdt,tp1_pct,tp2_pct) "
                "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                (ts, symbol.upper(), timeframe, entry_usdt, tp1_pct, tp2_pct),
            )
            return cur.fetchone()[0]
        else:
            cur.execute(
                "INSERT INTO ob_scanners (ts_created,symbol,timeframe,entry_usdt,tp1_pct,tp2_pct) "
                "VALUES (?,?,?,?,?,?)",
                (ts, symbol.upper(), timeframe, entry_usdt, tp1_pct, tp2_pct),
            )
            return cur.lastrowid


def list_ob_scanners() -> list:
    _init_ob_scanner_tables()
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM ob_scanners ORDER BY id DESC")
            rows = _rows_to_dicts(cur.fetchall(), cur)
        for r in rows:
            try:
                r["conditions"] = json.loads(r.get("conditions_json") or "{}")
            except Exception:
                r["conditions"] = {}
        return rows
    except Exception as e:
        log.error("list_ob_scanners failed: %s", e)
        return []


def get_ob_scanner(scanner_id: int) -> dict | None:
    _init_ob_scanner_tables()
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("SELECT * FROM ob_scanners WHERE id=?"), (scanner_id,))
            rows = _rows_to_dicts(cur.fetchall(), cur)
        if rows:
            r = rows[0]
            try:
                r["conditions"] = json.loads(r.get("conditions_json") or "{}")
            except Exception:
                r["conditions"] = {}
            return r
        return None
    except Exception as e:
        log.error("get_ob_scanner failed: %s", e)
        return None


def update_ob_scanner_status(scanner_id: int, status: str) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("UPDATE ob_scanners SET status=? WHERE id=?"), (status, scanner_id))
    except Exception as e:
        log.error("update_ob_scanner_status failed: %s", e)


def update_ob_position(scanner_id: int, entry_price: float, base_qty: float,
                        tp1_hit: bool, realised_pnl: float,
                        conditions: dict | None = None) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cj = json.dumps(conditions) if conditions is not None else None
            if cj is not None:
                cur.execute(
                    _q("UPDATE ob_scanners SET entry_price=?,base_qty=?,tp1_hit=?,realised_pnl=?,conditions_json=? WHERE id=?"),
                    (entry_price, base_qty, int(tp1_hit), realised_pnl, cj, scanner_id),
                )
            else:
                cur.execute(
                    _q("UPDATE ob_scanners SET entry_price=?,base_qty=?,tp1_hit=?,realised_pnl=? WHERE id=?"),
                    (entry_price, base_qty, int(tp1_hit), realised_pnl, scanner_id),
                )
    except Exception as e:
        log.error("update_ob_position failed: %s", e)


def record_ob_trade(scanner_id: int, side: str, price: float,
                     qty: float, usdt_value: float,
                     pnl: float = 0.0, label: str = "") -> None:
    try:
        _init_ob_scanner_tables()
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("INSERT INTO ob_trades (scanner_id,ts,side,price,qty,usdt_value,pnl,label) VALUES (?,?,?,?,?,?,?,?)"),
                (scanner_id, ts, side, price, qty, usdt_value, pnl, label),
            )
    except Exception as e:
        log.error("record_ob_trade failed: %s", e)


def get_ob_trades(scanner_id: int) -> list:
    _init_ob_scanner_tables()
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("SELECT * FROM ob_trades WHERE scanner_id=? ORDER BY id DESC"), (scanner_id,))
            return _rows_to_dicts(cur.fetchall(), cur)
    except Exception as e:
        log.error("get_ob_trades failed: %s", e)
        return []


def set_ob_should_run(scanner_id: int, should_run: bool) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("UPDATE ob_scanners SET should_run=? WHERE id=?"),
                        (1 if should_run else 0, scanner_id))
    except Exception as e:
        log.error("set_ob_should_run failed: %s", e)


def get_should_run_ob_scanners() -> list[int]:
    """Return IDs of OB scanners that should auto-resume on startup."""
    _init_ob_scanner_tables()
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM ob_scanners WHERE should_run=1 AND status != 'deleted'")
            rows = cur.fetchall()
        if _USE_POSTGRES:
            return [row[0] for row in rows]
        return [row["id"] for row in rows]
    except Exception as e:
        log.error("get_should_run_ob_scanners failed: %s", e)
        return []


def delete_ob_scanner(scanner_id: int) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("DELETE FROM ob_scanners WHERE id=?"), (scanner_id,))
            cur.execute(_q("DELETE FROM ob_trades WHERE scanner_id=?"), (scanner_id,))
    except Exception as e:
        log.error("delete_ob_scanner failed: %s", e)


# ---------------------------------------------------------------------------
# OB Detector — schema + CRUD
# ---------------------------------------------------------------------------

def _init_ob_detector_tables() -> None:
    """Create ob_detectors and ob_detector_trades tables if they don't exist."""
    if _USE_POSTGRES:
        stmts = [
            """
            CREATE TABLE IF NOT EXISTS ob_detectors (
                id              SERIAL PRIMARY KEY,
                ts_created      TEXT    NOT NULL,
                symbol          TEXT    NOT NULL DEFAULT 'MARKET',
                timeframe       TEXT    NOT NULL DEFAULT '5m',
                entry_usdt      REAL    NOT NULL DEFAULT 15.0,
                tp1_pct         REAL    NOT NULL DEFAULT 1.0,
                tp2_pct         REAL    NOT NULL DEFAULT 2.0,
                use_stop_loss   INTEGER NOT NULL DEFAULT 1,
                status          TEXT    NOT NULL DEFAULT 'stopped',
                should_run      INTEGER NOT NULL DEFAULT 0,
                entry_price     REAL    NOT NULL DEFAULT 0,
                sl_price        REAL    NOT NULL DEFAULT 0,
                base_qty        REAL    NOT NULL DEFAULT 0,
                tp1_hit         INTEGER NOT NULL DEFAULT 0,
                realised_pnl    REAL    NOT NULL DEFAULT 0,
                conditions_json TEXT    NOT NULL DEFAULT '{}'
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ob_detector_trades (
                id          SERIAL PRIMARY KEY,
                detector_id INTEGER NOT NULL,
                ts          TEXT    NOT NULL,
                side        TEXT    NOT NULL,
                price       REAL    NOT NULL,
                qty         REAL    NOT NULL,
                usdt_value  REAL    NOT NULL DEFAULT 0,
                pnl         REAL    NOT NULL DEFAULT 0,
                label       TEXT    NOT NULL DEFAULT ''
            )
            """,
        ]
        with _conn() as conn:
            cur = conn.cursor()
            for stmt in stmts:
                cur.execute(stmt)
    else:
        with _conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS ob_detectors (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_created      TEXT    NOT NULL,
                    symbol          TEXT    NOT NULL DEFAULT 'MARKET',
                    timeframe       TEXT    NOT NULL DEFAULT '5m',
                    entry_usdt      REAL    NOT NULL DEFAULT 15.0,
                    tp1_pct         REAL    NOT NULL DEFAULT 1.0,
                    tp2_pct         REAL    NOT NULL DEFAULT 2.0,
                    use_stop_loss   INTEGER NOT NULL DEFAULT 1,
                    status          TEXT    NOT NULL DEFAULT 'stopped',
                    should_run      INTEGER NOT NULL DEFAULT 0,
                    entry_price     REAL    NOT NULL DEFAULT 0,
                    sl_price        REAL    NOT NULL DEFAULT 0,
                    base_qty        REAL    NOT NULL DEFAULT 0,
                    tp1_hit         INTEGER NOT NULL DEFAULT 0,
                    realised_pnl    REAL    NOT NULL DEFAULT 0,
                    conditions_json TEXT    NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS ob_detector_trades (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    detector_id INTEGER NOT NULL,
                    ts          TEXT    NOT NULL,
                    side        TEXT    NOT NULL,
                    price       REAL    NOT NULL,
                    qty         REAL    NOT NULL,
                    usdt_value  REAL    NOT NULL DEFAULT 0,
                    pnl         REAL    NOT NULL DEFAULT 0,
                    label       TEXT    NOT NULL DEFAULT ''
                );
            """)


def create_ob_detector(
    timeframe:     str   = "5m",
    entry_usdt:    float = 15.0,
    tp1_pct:       float = 1.0,
    tp2_pct:       float = 2.0,
    use_stop_loss: bool  = True,
) -> int:
    """Insert a new OB detector row and return its id."""
    _init_ob_detector_tables()
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q(
                    "INSERT INTO ob_detectors "
                    "(ts_created,symbol,timeframe,entry_usdt,tp1_pct,tp2_pct,use_stop_loss) "
                    "VALUES (?,?,?,?,?,?,?)"
                ),
                (ts, "MARKET", timeframe, entry_usdt, tp1_pct, tp2_pct, int(use_stop_loss)),
            )
            if _USE_POSTGRES:
                cur.execute("SELECT lastval()")
            else:
                cur.execute("SELECT last_insert_rowid()")
            return cur.fetchone()[0]
    except Exception as e:
        log.error("create_ob_detector failed: %s", e)
        return -1


def list_ob_detectors() -> list:
    _init_ob_detector_tables()
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM ob_detectors ORDER BY id DESC")
            return _rows_to_dicts(cur.fetchall(), cur)
    except Exception as e:
        log.error("list_ob_detectors failed: %s", e)
        return []


def get_ob_detector(detector_id: int) -> dict | None:
    _init_ob_detector_tables()
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("SELECT * FROM ob_detectors WHERE id=?"), (detector_id,))
            rows = _rows_to_dicts(cur.fetchall(), cur)
            if not rows:
                return None
            row = rows[0]
            try:
                row["conditions"] = json.loads(row.get("conditions_json") or "{}")
            except Exception:
                row["conditions"] = {}
            return row
    except Exception as e:
        log.error("get_ob_detector failed: %s", e)
        return None


def update_ob_detector_status(detector_id: int, status: str) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("UPDATE ob_detectors SET status=? WHERE id=?"),
                (status, detector_id),
            )
    except Exception as e:
        log.error("update_ob_detector_status failed: %s", e)


def update_ob_detector_position(
    detector_id: int,
    entry_price: float,
    base_qty:    float,
    tp1_hit:     bool,
    realised_pnl: float,
    conditions:  dict | None = None,
    sl_price:    float = 0.0,
    symbol:      str   = "",
) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            if conditions is not None:
                cj = json.dumps(conditions)
                if symbol:
                    cur.execute(
                        _q(
                            "UPDATE ob_detectors "
                            "SET entry_price=?,base_qty=?,tp1_hit=?,realised_pnl=?,"
                            "conditions_json=?,sl_price=?,symbol=? WHERE id=?"
                        ),
                        (entry_price, base_qty, int(tp1_hit), realised_pnl,
                         cj, sl_price, symbol, detector_id),
                    )
                else:
                    cur.execute(
                        _q(
                            "UPDATE ob_detectors "
                            "SET entry_price=?,base_qty=?,tp1_hit=?,realised_pnl=?,"
                            "conditions_json=?,sl_price=? WHERE id=?"
                        ),
                        (entry_price, base_qty, int(tp1_hit), realised_pnl,
                         cj, sl_price, detector_id),
                    )
            else:
                cur.execute(
                    _q(
                        "UPDATE ob_detectors "
                        "SET entry_price=?,base_qty=?,tp1_hit=?,realised_pnl=? WHERE id=?"
                    ),
                    (entry_price, base_qty, int(tp1_hit), realised_pnl, detector_id),
                )
    except Exception as e:
        log.error("update_ob_detector_position failed: %s", e)


def record_ob_detector_trade(
    detector_id: int,
    side:        str,
    price:       float,
    qty:         float,
    usdt_value:  float,
    pnl:         float = 0.0,
    label:       str   = "",
) -> None:
    try:
        _init_ob_detector_tables()
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q(
                    "INSERT INTO ob_detector_trades "
                    "(detector_id,ts,side,price,qty,usdt_value,pnl,label) "
                    "VALUES (?,?,?,?,?,?,?,?)"
                ),
                (detector_id, ts, side, price, qty, usdt_value, pnl, label),
            )
    except Exception as e:
        log.error("record_ob_detector_trade failed: %s", e)


def get_ob_detector_trades(detector_id: int) -> list:
    _init_ob_detector_tables()
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("SELECT * FROM ob_detector_trades WHERE detector_id=? ORDER BY id DESC"),
                (detector_id,),
            )
            return _rows_to_dicts(cur.fetchall(), cur)
    except Exception as e:
        log.error("get_ob_detector_trades failed: %s", e)
        return []


def set_ob_detector_should_run(detector_id: int, should_run: bool) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                _q("UPDATE ob_detectors SET should_run=? WHERE id=?"),
                (int(should_run), detector_id),
            )
    except Exception as e:
        log.error("set_ob_detector_should_run failed: %s", e)


def get_should_run_ob_detectors() -> list[int]:
    _init_ob_detector_tables()
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM ob_detectors WHERE should_run=1 AND status != 'deleted'"
            )
            return [r[0] for r in cur.fetchall()]
    except Exception as e:
        log.error("get_should_run_ob_detectors failed: %s", e)
        return []


def delete_ob_detector(detector_id: int) -> None:
    try:
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(_q("DELETE FROM ob_detectors WHERE id=?"), (detector_id,))
            cur.execute(
                _q("DELETE FROM ob_detector_trades WHERE detector_id=?"), (detector_id,)
            )
    except Exception as e:
        log.error("delete_ob_detector failed: %s", e)
