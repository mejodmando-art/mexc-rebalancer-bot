from typing import List, Dict, Tuple

def calculate_trades(
    portfolio: dict,
    total_usdt: float,
    allocations: list,
    threshold: float = 5.0,
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
            if diff_usdt >= 5:  # min $5 trade
                trades.append({
                    "symbol": sym,
                    "action": "sell" if drift > 0 else "buy",
                    "usdt_amount": round(diff_usdt, 2),
                    "drift_pct": round(drift, 2),
                })

    drift_report.sort(key=lambda x: x["drift_abs"], reverse=True)
    return trades, drift_report
