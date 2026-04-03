import os
from dataclasses import dataclass, field
from typing import List

@dataclass
class Config:
    telegram_token: str = field(default_factory=lambda: os.environ["TELEGRAM_BOT_TOKEN"])
    allowed_user_ids: List[int] = field(default_factory=lambda: [
        int(i) for i in os.environ.get("ALLOWED_USER_IDS", "").split(",") if i.strip()
    ])
    database_path: str = field(default_factory=lambda: os.environ.get("DATABASE_PATH", "bot.db"))
    quote_currency: str = field(default_factory=lambda: os.environ.get("QUOTE_CURRENCY", "USDT"))

config = Config()
