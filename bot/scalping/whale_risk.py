"""
Risk management for the Whale Order Flow strategy.

Targets are fast but wide enough to cover fees and slippage:
  T1 = entry + 0.8%   (exit 60% here — quick profit lock)
  T2 = entry + 1.6%   (exit remaining 40% here)
  SL = entry - 0.5%   (tight stop — if whales didn't follow through, exit fast)

R/R = 1:1.6 (0.8% reward vs 0.5% risk at T1)

No trailing stop on this strategy — exits are fixed and fast.
Average hold time: 5 to 20 minutes.
"""

from typing import Dict, Any

_T1_PCT = 0.008   # 0.8%
_T2_PCT = 0.016   # 1.6%
_SL_PCT = 0.005   # 0.5%


def calculate_whale_risk(
    entry_price: float,
    trade_size_usdt: float = 10.0,
) -> Dict[str, Any]:
    """
    Returns:
        {
            "stop_loss":   float,
            "target1":     float,
            "target2":     float,
            "qty":         float,
            "qty_60pct":   float,   # 60% of qty — exit at T1
            "qty_40pct":   float,   # 40% of qty — exit at T2
            "risk_reward": float,
            "valid":       bool,
        }
    """
    if entry_price <= 0 or trade_size_usdt <= 0:
        return _invalid()

    stop_loss = round(entry_price * (1 - _SL_PCT), 8)
    target1   = round(entry_price * (1 + _T1_PCT), 8)
    target2   = round(entry_price * (1 + _T2_PCT), 8)

    qty      = round(trade_size_usdt / entry_price, 8)
    qty_60   = round(qty * 0.6, 8)
    qty_40   = round(qty * 0.4, 8)

    risk   = entry_price - stop_loss
    reward = target1 - entry_price
    rr     = round(reward / risk, 2) if risk > 0 else 0

    return {
        "stop_loss":   stop_loss,
        "target1":     target1,
        "target2":     target2,
        "qty":         qty,
        "qty_60pct":   qty_60,
        "qty_40pct":   qty_40,
        "risk_reward": rr,
        "valid":       True,
    }


def _invalid() -> Dict[str, Any]:
    return {
        "stop_loss":   0.0,
        "target1":     0.0,
        "target2":     0.0,
        "qty":         0.0,
        "qty_60pct":   0.0,
        "qty_40pct":   0.0,
        "risk_reward": 0.0,
        "valid":       False,
    }
