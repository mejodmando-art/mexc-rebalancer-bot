import aiosqlite
import asyncio
from bot.config import config

class Database:
    def __init__(self):
        self._path = config.database_path
        self._lock = asyncio.Lock()

    async def init(self):
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    mexc_api_key TEXT,
                    mexc_secret_key TEXT,
                    threshold REAL DEFAULT 5.0,
                    auto_enabled INTEGER DEFAULT 0,
                    auto_interval_hours INTEGER DEFAULT 24,
                    quote_currency TEXT DEFAULT 'USDT',
                    last_rebalance_at TEXT
                )""")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS allocations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    symbol TEXT,
                    target_percentage REAL,
                    UNIQUE(user_id, symbol)
                )""")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rebalance_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    timestamp TEXT,
                    summary TEXT,
                    total_traded_usdt REAL,
                    success INTEGER DEFAULT 1
                )""")
            await conn.commit()

    async def get_settings(self, user_id: int) -> dict:
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM user_settings WHERE user_id=?", (user_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else {}

    async def update_settings(self, user_id: int, **kwargs):
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                "INSERT INTO user_settings(user_id) VALUES(?) ON CONFLICT(user_id) DO NOTHING", (user_id,))
            for k, v in kwargs.items():
                await conn.execute(f"UPDATE user_settings SET {k}=? WHERE user_id=?", (v, user_id))
            await conn.commit()

    async def get_allocations(self, user_id: int) -> list:
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM allocations WHERE user_id=? ORDER BY target_percentage DESC", (user_id,)
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def set_allocation(self, user_id: int, symbol: str, pct: float):
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute("""
                INSERT INTO allocations(user_id, symbol, target_percentage)
                VALUES(?,?,?)
                ON CONFLICT(user_id, symbol) DO UPDATE SET target_percentage=excluded.target_percentage
            """, (user_id, symbol.upper(), pct))
            await conn.commit()

    async def delete_allocation(self, user_id: int, symbol: str):
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute("DELETE FROM allocations WHERE user_id=? AND symbol=?", (user_id, symbol))
            await conn.commit()

    async def clear_allocations(self, user_id: int):
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute("DELETE FROM allocations WHERE user_id=?", (user_id,))
            await conn.commit()

    async def add_history(self, user_id: int, timestamp: str, summary: str, traded: float, success: int = 1):
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute("""
                INSERT INTO rebalance_history(user_id,timestamp,summary,total_traded_usdt,success)
                VALUES(?,?,?,?,?)
            """, (user_id, timestamp, summary, traded, success))
            await conn.commit()

    async def get_history(self, user_id: int, limit: int = 10) -> list:
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("""
                SELECT * FROM rebalance_history WHERE user_id=?
                ORDER BY timestamp DESC LIMIT ?
            """, (user_id, limit)) as cur:
                return [dict(r) for r in await cur.fetchall()]

db = Database()
