"""
Order Flow analysis — detects a strong CVD shift from negative to positive.

Whales accumulate quietly then trigger a burst of buy orders.
We detect this by splitting recent trades into two halves and
checking if buy pressure increased significantly in the second half.

A "CVD shift" means:
  - First half:  sell pressure dominant (CVD negative or flat)
  - Second half: buy pressure dominant (CVD positive)
  - Delta >= 3x the absolute value of the first-half CVD (strong flip only)

Weak flips (small delta) are market noise and are rejected.
"""

from typing import Dict, Any

# Second-half CVD must be >= 3x the first-half baseline to qualify as strong.
# This filters out random noise and only catches real accumulation bursts.
_STRONG_MULTIPLIER = 3.0


async def get_order_flow(symbol: str, exchange) -> Dict[str, Any]:
    """
    Returns:
        {
            "shifted":    bool,    # True if CVD flipped bullish
            "strong":     bool,    # True if delta >= 3x first-half baseline
            "cvd_first":  float,
            "cvd_second": float,
            "delta":      float,
        }
    """
    try:
        trades = await exchange.fetch_trades(symbol, limit=300)
        if not trades or len(trades) < 60:
            return _empty()

        mid = len(trades) // 2
        first_half  = trades[:mid]
        second_half = trades[mid:]

        cvd_first  = _calc_cvd(first_half)
        cvd_second = _calc_cvd(second_half)
        delta      = cvd_second - cvd_first

        # Basic shift: second half net positive and delta positive
        shifted = (cvd_second > 0) and (delta > 0)

        # Strong shift: delta is at least 3x the first-half baseline magnitude
        baseline = abs(cvd_first) if cvd_first != 0 else abs(cvd_second) * 0.1
        strong   = shifted and (delta >= baseline * _STRONG_MULTIPLIER)

        return {
            "shifted":    shifted,
            "strong":     strong,
            "cvd_first":  round(cvd_first, 4),
            "cvd_second": round(cvd_second, 4),
            "delta":      round(delta, 4),
        }

    except Exception:
        return _empty()


def _calc_cvd(trades: list) -> float:
    cvd = 0.0
    prev_price = float(trades[0]["price"]) if trades else 0.0

    for t in trades:
        price  = float(t["price"])
        amount = float(t["amount"])
        side   = t.get("side")

        if side == "buy":
            cvd += amount
        elif side == "sell":
            cvd -= amount
        else:
            if price >= prev_price:
                cvd += amount
            else:
                cvd -= amount
        prev_price = price

    return cvd


def _empty() -> Dict[str, Any]:
    return {
        "shifted":    False,
        "strong":     False,
        "cvd_first":  0.0,
        "cvd_second": 0.0,
        "delta":      0.0,
    }
