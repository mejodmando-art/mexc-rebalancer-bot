import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _require(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        print(f"[FATAL] Missing environment variable: {key}", flush=True)
        sys.exit(1)
    return val


class Config:
    telegram_token: str = _require("TELEGRAM_BOT_TOKEN")
    allowed_user_ids: list = [
        int(i.strip())
        for i in os.environ.get("ALLOWED_USER_IDS", "").split(",")
        if i.strip().isdigit()
    ]
    database_url: str = os.environ.get("DATABASE_URL", "").strip()
    database_path: str = os.environ.get("DATABASE_PATH", "bot.db").strip()
    quote_currency: str = os.environ.get("QUOTE_CURRENCY", "USDT").strip()

    def __init__(self):
        if not self.allowed_user_ids:
            print(
                "[WARN] ALLOWED_USER_IDS not set — bot responds to ANY user. "
                "Set this variable to restrict access.",
                flush=True,
            )

        # Ensure SQLite directory exists
        db_dir = os.path.dirname(self.database_path)
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
            except Exception as e:
                print(f"[WARN] Could not create {db_dir}: {e} — using bot.db", flush=True)
                self.database_path = "bot.db"

        backend = "PostgreSQL" if self.database_url else f"SQLite ({self.database_path})"
        print(f"[INFO] DB: {backend} | Users: {self.allowed_user_ids}", flush=True)


config = Config()
