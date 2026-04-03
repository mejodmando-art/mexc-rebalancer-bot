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
                    last_rebalance_at TEXT,
                    active_portfolio_id INTEGER
                )""")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS portfolios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    capital_usdt REAL DEFAULT 0.0,
                    created_at TEXT DEFAULT (datetime('now'))
                )""")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS allocations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    portfolio_id INTEGER,
                    symbol TEXT,
                    target_percentage REAL,
                    UNIQUE(portfolio_id, symbol)
                )""")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rebalance_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    portfolio_id INTEGER,
                    timestamp TEXT,
                    summary TEXT,
                    total_traded_usdt REAL,
                    success INTEGER DEFAULT 1
                )""")
            await conn.commit()

            # Migration: add new columns to existing tables
            migrations = [
                "ALTER TABLE user_settings ADD COLUMN active_portfolio_id INTEGER",
                "ALTER TABLE allocations ADD COLUMN portfolio_id INTEGER",
                "ALTER TABLE rebalance_history ADD COLUMN portfolio_id INTEGER",
            ]
            for sql in migrations:
                try:
                    await conn.execute(sql)
                    await conn.commit()
                except Exception:
                    pass

    # ── Portfolio CRUD ─────────────────────────────────────────────────────────

    async def create_portfolio(self, user_id: int, name: str, capital_usdt: float = 0.0) -> int:
        async with aiosqlite.connect(self._path) as conn:
            cur = await conn.execute(
                "INSERT INTO portfolios(user_id, name, capital_usdt) VALUES(?,?,?)",
                (user_id, name, capital_usdt),
            )
            portfolio_id = cur.lastrowid
            await conn.commit()
            return portfolio_id

    async def get_portfolios(self, user_id: int) -> list:
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM portfolios WHERE user_id=? ORDER BY id", (user_id,)
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def get_portfolio(self, portfolio_id: int) -> dict:
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM portfolios WHERE id=?", (portfolio_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else {}

    async def update_portfolio(self, portfolio_id: int, **kwargs):
        async with aiosqlite.connect(self._path) as conn:
            for k, v in kwargs.items():
                await conn.execute(
                    f"UPDATE portfolios SET {k}=? WHERE id=?", (v, portfolio_id)
                )
            await conn.commit()

    async def delete_portfolio(self, portfolio_id: int):
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute("DELETE FROM allocations WHERE portfolio_id=?", (portfolio_id,))
            await conn.execute("DELETE FROM portfolios WHERE id=?", (portfolio_id,))
            await conn.commit()

    async def get_active_portfolio_id(self, user_id: int):
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT active_portfolio_id FROM user_settings WHERE user_id=?", (user_id,)
            ) as cur:
                row = await cur.fetchone()
                if row and row["active_portfolio_id"]:
                    return row["active_portfolio_id"]
                return None

    async def set_active_portfolio(self, user_id: int, portfolio_id: int):
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                "INSERT INTO user_settings(user_id, active_portfolio_id) VALUES(?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET active_portfolio_id=?",
                (user_id, portfolio_id, portfolio_id),
            )
            await conn.commit()

    async def ensure_active_portfolio(self, user_id: int) -> int:
        """Returns active portfolio_id, creating a default one if needed."""
        portfolio_id = await self.get_active_portfolio_id(user_id)
        if portfolio_id:
            p = await self.get_portfolio(portfolio_id)
            if p:
                return portfolio_id

        portfolios = await self.get_portfolios(user_id)
        if portfolios:
            portfolio_id = portfolios[0]["id"]
        else:
            portfolio_id = await self.create_portfolio(user_id, "المحفظة الرئيسية", 0.0)
            await self._migrate_old_allocations(user_id, portfolio_id)

        await self.set_active_portfolio(user_id, portfolio_id)
        return portfolio_id

    async def _migrate_old_allocations(self, user_id: int, portfolio_id: int):
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                "UPDATE allocations SET portfolio_id=? WHERE user_id=? AND portfolio_id IS NULL",
                (portfolio_id, user_id),
            )
            await conn.commit()

    # ── Portfolio Allocations ──────────────────────────────────────────────────

    async def get_portfolio_allocations(self, portfolio_id: int) -> list:
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM allocations WHERE portfolio_id=? ORDER BY target_percentage DESC",
                (portfolio_id,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def set_portfolio_allocation(self, portfolio_id: int, user_id: int, symbol: str, pct: float):
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                """INSERT INTO allocations(portfolio_id, user_id, symbol, target_percentage)
                   VALUES(?,?,?,?)
                   ON CONFLICT(portfolio_id, symbol)
                   DO UPDATE SET target_percentage=excluded.target_percentage""",
                (portfolio_id, user_id, symbol.upper(), pct),
            )
            await conn.commit()

    async def delete_portfolio_allocation(self, portfolio_id: int, symbol: str):
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                "DELETE FROM allocations WHERE portfolio_id=? AND symbol=?", (portfolio_id, symbol)
            )
            await conn.commit()

    async def clear_portfolio_allocations(self, portfolio_id: int):
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute("DELETE FROM allocations WHERE portfolio_id=?", (portfolio_id,))
            await conn.commit()

    # ── Backward-compatible wrappers (route to active portfolio) ───────────────

    async def get_allocations(self, user_id: int) -> list:
        portfolio_id = await self.ensure_active_portfolio(user_id)
        return await self.get_portfolio_allocations(portfolio_id)

    async def set_allocation(self, user_id: int, symbol: str, pct: float):
        portfolio_id = await self.ensure_active_portfolio(user_id)
        await self.set_portfolio_allocation(portfolio_id, user_id, symbol, pct)

    async def delete_allocation(self, user_id: int, symbol: str):
        portfolio_id = await self.get_active_portfolio_id(user_id)
        if portfolio_id:
            await self.delete_portfolio_allocation(portfolio_id, symbol)

    async def clear_allocations(self, user_id: int):
        portfolio_id = await self.get_active_portfolio_id(user_id)
        if portfolio_id:
            await self.clear_portfolio_allocations(portfolio_id)

    # ── User Settings ──────────────────────────────────────────────────────────

    async def get_settings(self, user_id: int) -> dict:
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM user_settings WHERE user_id=?", (user_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else {}

    async def update_settings(self, user_id: int, **kwargs):
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                "INSERT INTO user_settings(user_id) VALUES(?) ON CONFLICT(user_id) DO NOTHING",
                (user_id,),
            )
            for k, v in kwargs.items():
                await conn.execute(
                    f"UPDATE user_settings SET {k}=? WHERE user_id=?", (v, user_id)
                )
            await conn.commit()

    # ── History ────────────────────────────────────────────────────────────────

    async def add_history(self, user_id: int, timestamp: str, summary: str,
                          traded: float, success: int = 1, portfolio_id: int = None):
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                """INSERT INTO rebalance_history
                   (user_id, portfolio_id, timestamp, summary, total_traded_usdt, success)
                   VALUES(?,?,?,?,?,?)""",
                (user_id, portfolio_id, timestamp, summary, traded, success),
            )
            await conn.commit()

    async def get_history(self, user_id: int, limit: int = 10) -> list:
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                """SELECT rh.*, p.name as portfolio_name
                   FROM rebalance_history rh
                   LEFT JOIN portfolios p ON rh.portfolio_id = p.id
                   WHERE rh.user_id=? ORDER BY rh.id DESC LIMIT ?""",
                (user_id, limit),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def get_all_users_with_auto(self) -> list:
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT user_id FROM user_settings WHERE auto_enabled=1"
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]


db = Database()
