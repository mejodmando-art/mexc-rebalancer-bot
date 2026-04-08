from typing import List, Dict, Tuple

# Minimum trade size in USDT — MEXC minimum is $1.
MIN_TRADE_USDT = 1.0

# MEXC spot taker fee. Buy orders are inflated by 1/(1-fee) so the
# post-fee received amount matches the target allocation value.
MEXC_TAKER_FEE = 0.001


def calculate_trades(
    portfolio: dict,
    total_usdt: float,
    allocations: list,
    threshold: float = 5.0,
    min_trade_usdt: float = MIN_TRADE_USDT,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Returns (trades_needed, drift_report)
    trades_needed: [{'symbol', 'action', 'usdt_amount', 'drift_pct'}]
    drift_report:  [{'symbol', 'current_pct', 'target_pct', 'drift_pct', 'needs_action'}]
    """
    if total_usdt <= 0 or not allocations:
        return [], []

    alloc_map = {a["symbol"]: a["target_percentage"] for a in allocations}
    drift_report = []
    trades = []

    for sym, target_pct in alloc_map.items():
        current_val = portfolio.get(sym, {}).get("value_usdt", 0.0)
        current_pct = (current_val / total_usdt) * 100

        drift = current_pct - target_pct
        drift_abs = abs(drift)
        needs_action = drift_abs >= threshold

        drift_report.append({
            "symbol": sym,
            "current_pct": round(current_pct, 2),
            "target_pct": target_pct,
            "drift_pct": round(drift, 2),
            "drift_abs": round(drift_abs, 2),
            "needs_action": needs_action,
        })

        if needs_action:
            target_val = (target_pct / 100) * total_usdt
            diff_usdt = abs(target_val - current_val)
            if diff_usdt >= min_trade_usdt:
                action = "sell" if drift > 0 else "buy"
                # Inflate buy amount so the post-fee received value matches
                # the target. Sell amount is left as-is; the fee reduces USDT
                # received, which is reflected in the next portfolio snapshot.
                if action == "buy":
                    diff_usdt = diff_usdt / (1 - MEXC_TAKER_FEE)
                trades.append({
                    "symbol": sym,
                    "action": action,
                    "usdt_amount": round(diff_usdt, 2),
                    "drift_pct": round(drift, 2),
                })

    drift_report.sort(key=lambda x: x["drift_abs"], reverse=True)
    return trades, drift_report
