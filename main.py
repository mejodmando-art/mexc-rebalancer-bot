"""
Entry point — starts the FastAPI app (which also launches the Telegram bot).

    python main.py
    uvicorn api.main:app --host 0.0.0.0 --port $PORT
"""
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

import uvicorn
from api.main import app  # noqa: F401

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=False,
    )
