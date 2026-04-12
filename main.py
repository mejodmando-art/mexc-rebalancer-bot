"""
Entry point – starts the web API (FastAPI) which also launches the Telegram bot.

Usage
-----
    uvicorn api.main:app --host 0.0.0.0 --port 8000

Environment variables
---------------------
    MEXC_API_KEY         – MEXC Spot API key
    MEXC_SECRET_KEY      – MEXC Spot API secret
    TELEGRAM_BOT_TOKEN   – BotFather token (optional; enables Telegram mode)
    TELEGRAM_CHAT_ID     – Restrict Telegram access to one user ID (optional)
    DISCORD_WEBHOOK_URL  – Discord webhook for trade notifications (optional)
"""

import os
import sys

# Support running as: python main.py (from repo root)
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

import uvicorn
from api.main import app  # noqa: F401 – imported so uvicorn can reference it

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=False,
    )
