"""
SQLite database layer for rebalance history, portfolio snapshots, and P&L.
Uses SQLAlchemy Core (sync) so it works from both the bot thread and FastAPI.
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "portfolio.db")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    """Create tables if they don't exist."""
    with _conn() as c:
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


# ---------------------------------------------------------------------------
# Rebalance history
# ---------------------------------------------------------------------------

def record_rebalance(
    mode: str,
    total_usdt: float,
    details: list,
    paper: bool = False,
) -> None:
    """
    details: list of dicts with keys symbol, target_pct, actual_pct,
             deviation, diff_usdt, action (BUY/SELL/SKIP).
    """
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


def get_rebalance_history(limit: int = 10) -> list:
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


# ---------------------------------------------------------------------------
# Portfolio snapshots (for performance chart)
# ---------------------------------------------------------------------------

def record_snapshot(total_usdt: float, assets: list) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO portfolio_snapshots (ts, total_usdt, assets_json) VALUES (?,?,?)",
            (
                datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                total_usdt,
                json.dumps(assets),
            ),
        )


def get_snapshots(limit: int = 90) -> list:
    with _conn() as c:
        rows = c.execute(
            "SELECT ts, total_usdt FROM portfolio_snapshots ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]
