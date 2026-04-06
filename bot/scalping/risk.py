"""
Risk management: calculates stop loss, T1, T2 targets, and position size.

Rules:
  stop_loss = sweep_low * 0.997       (0.3% below the sweep wick)
  target1   = entry + risk * 1.5      (1.5R — sell 50% here, lock partial profit)
  target2   = entry + risk * 3.0      (3R  — sell remaining 50% here)

  After T1 is hit the trailing stop tightens to protect profit.
  After T2 is hit the full position is closed.
"""

from typing import Dict, Any

_STOP_PCT     = 0.003   # 0.3% below sweep low
_T1_R         = 1.5     # target1 = entry + 1.5 × risk (50% exit)
_T2_R         = 3.0     # target2 = entry + 3.0 × risk (remaining 50% exit)
_MAX_RISK_PCT = 0.02    # SL must not be more than 2% below entry
_MIN_RISK_PCT = 0.003   # SL must not be less than 0.3% below entry


def calculate_risk(
    entry_price: float,
    sweep_low: float,
    liquidity_high: float,   # kept for API compatibility
    trade_size_usdt: float = 10.0,
) -> Dict[str, Any]:
    """
    Returns:
        {
            "stop_loss":     float,
            "target1":       float,   # 1.5R — sell 50%
            "target2":       float,   # 3.0R — sell remaining 50%
            "qty":           float,
            "qty_half":      float,
            "risk_reward":   float,
            "valid":         bool,
        }
    """
    if entry_price <= 0 or sweep_low <= 0:
        return _invalid()

    stop_loss = round(sweep_low * (1 - _STOP_PCT), 8)
    risk      = entry_price - stop_loss

    if risk <= 0:
        return _invalid()

    # Reject if SL is too far (> 2%) or too tight (< 0.3%) from entry
    risk_pct = risk / entry_price
    if risk_pct > _MAX_RISK_PCT or risk_pct < _MIN_RISK_PCT:
        return _invalid()

    target1 = round(entry_price + risk * _T1_R, 8)
    target2 = round(entry_price + risk * _T2_R, 8)

    qty      = round(trade_size_usdt / entry_price, 8)
    qty_half = round(qty / 2, 8)

    rr = round(_T2_R, 2)

    return {
        "stop_loss":   stop_loss,
        "target1":     target1,
        "target2":     target2,
        "qty":         qty,
        "qty_half":    qty_half,
        "risk_reward": rr,
        "valid":       True,
    }


def _invalid() -> Dict[str, Any]:
    return {
        "stop_loss":   0.0,
        "target1":     0.0,
        "target2":     0.0,
        "qty":         0.0,
        "qty_half":    0.0,
        "risk_reward": 0.0,
        "valid":       False,
    }
