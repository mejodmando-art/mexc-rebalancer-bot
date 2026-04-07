"""
Cumulative Volume Delta (CVD) calculation using recent trades.

Uses the `side` field returned by MEXC for each trade (buy/sell).
Falls back to price-direction comparison if `side` is unavailable.
CVD = cumulative sum of (buy_vol - sell_vol)

Uses 200 trades instead of 500 — enough signal for short-term whale
detection while being faster to fetch and more relevant to current price action.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


async def get_cvd(symbol: str, exchange) -> Dict[str, Any]:
    """
    Returns:
        {
            "cvd":   float,              # positive = buy pressure, negative = sell pressure
            "trend": "up"|"down"|"neutral"
        }
    """
    try:
        # 200 recent trades — faster API call, still captures current whale activity
        trades = await exchange.fetch_trades(symbol, limit=200)
        if not trades or len(trades) < 10:
            return {"cvd": 0.0, "trend": "neutral"}

        cvd = 0.0
        prev_price = float(trades[0]["price"])

        for t in trades[1:]:
            price  = float(t["price"])
            amount = float(t["amount"])
            side   = t.get("side")  # "buy" or "sell" from exchange

            if side == "buy":
                cvd += amount
            elif side == "sell":
                cvd -= amount
            else:
                # Fallback: infer direction from price movement
                if price >= prev_price:
                    cvd += amount
                else:
                    cvd -= amount

            prev_price = price

        if cvd > 0:
            trend = "up"
        elif cvd < 0:
            trend = "down"
        else:
            trend = "neutral"

        return {"cvd": round(cvd, 6), "trend": trend}

    except Exception as e:
        logger.debug(f"CVD: {symbol} failed: {e}")
        return {"cvd": 0.0, "trend": "neutral"}
