"""
Grid engine — calculates grid levels and places orders on MEXC.

Given a center price, upper %, lower %, and number of steps:
  - Divides the range into equal price levels
  - Places limit buy orders below center
  - Places limit sell orders above center
  - Each filled buy immediately gets a sell placed one step above it
  - Each filled sell immediately gets a buy placed one step below it

Trailing: when price breaks above upper boundary → shift grid up
          when price breaks below lower boundary → shift grid down
"""

from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


def calculate_grid_levels(
    center_price: float,
    upper_pct: float,
    lower_pct: float,
    steps: int,
) -> Dict[str, Any]:
    """
    Calculate grid price levels.

    Args:
        center_price: current market price
        upper_pct:    % above center (e.g. 10 for 10%)
        lower_pct:    % below center (e.g. 10 for 10%)
        steps:        number of grid levels (split equally above and below)

    Returns:
        {
            "upper":  float,         # upper boundary
            "lower":  float,         # lower boundary
            "levels": [float, ...],  # all price levels sorted ascending
            "step_pct": float,       # % between each level
            "buy_levels":  [float],  # levels below center
            "sell_levels": [float],  # levels above center
        }
    """
    upper = round(center_price * (1 + upper_pct / 100), 8)
    lower = round(center_price * (1 - lower_pct / 100), 8)

    total_range = upper - lower
    step_size   = total_range / steps
    step_pct    = round((step_size / center_price) * 100, 4)

    levels = [round(lower + i * step_size, 8) for i in range(steps + 1)]

    buy_levels  = [l for l in levels if l < center_price]
    sell_levels = [l for l in levels if l > center_price]

    return {
        "upper":       upper,
        "lower":       lower,
        "levels":      levels,
        "step_pct":    step_pct,
        "buy_levels":  buy_levels,
        "sell_levels": sell_levels,
        "center":      center_price,
    }


async def place_grid_orders(
    exchange,
    symbol: str,
    grid: Dict[str, Any],
    order_size_usdt: float,
    initial: bool = False,
) -> Dict[str, Any]:
    """
    Place grid orders on the exchange.

    When initial=True (first-time grid creation):
      - Uses half the total budget for a market buy at current price
      - Splits the remaining half equally across buy and sell limit orders
      - This ensures the bot holds the asset and can profit from both directions

    When initial=False (after a grid shift/reset):
      - Splits the full budget equally across all levels (standard behavior)

    Returns:
        {
            "buy_orders":    [{"price", "qty", "order_id"}, ...],
            "sell_orders":   [{"price", "qty", "order_id"}, ...],
            "market_buy_qty": float,   # qty bought at market (initial only)
            "errors":        [str, ...],
        }
    """
    buy_orders  = []
    sell_orders = []
    errors      = []
    market_buy_qty = 0.0

    buy_levels  = grid["buy_levels"]
    sell_levels = grid["sell_levels"]
    total_levels = len(buy_levels) + len(sell_levels)

    if total_levels == 0:
        return {"buy_orders": [], "sell_orders": [], "market_buy_qty": 0.0, "errors": ["no levels"]}

    if initial:
        # Half budget → market buy at current price
        market_usdt = order_size_usdt / 2.0
        limit_usdt  = order_size_usdt / 2.0
        try:
            mkt_order = await exchange.create_market_buy_order_with_cost(symbol, market_usdt)
            market_buy_qty = float(
                mkt_order.get("filled") or mkt_order.get("amount") or 0
            )
            logger.info(f"Grid: market buy {symbol} ${market_usdt:.2f} → qty={market_buy_qty}")
        except Exception as e:
            errors.append(f"market_buy: {str(e)[:80]}")
            logger.warning(f"Grid: market buy failed {symbol}: {e}")
            # Fall back: use full budget for limit orders
            limit_usdt = order_size_usdt
    else:
        limit_usdt = order_size_usdt

    # Split limit budget equally across all grid levels
    size_per_level = limit_usdt / total_levels

    # Place buy limit orders (ascending — lowest first)
    for price in buy_levels:
        qty = round(size_per_level / price, 8)
        try:
            order = await exchange.create_limit_buy_order(symbol, qty, price)
            buy_orders.append({
                "price":    price,
                "qty":      qty,
                "order_id": order.get("id"),
                "status":   "open",
            })
            logger.info(f"Grid: buy order placed {symbol} @ {price:.6g} qty={qty}")
        except Exception as e:
            errors.append(f"buy@{price:.6g}: {str(e)[:60]}")
            logger.warning(f"Grid: failed buy order {symbol} @ {price}: {e}")

    # Place sell limit orders (ascending)
    for price in sell_levels:
        qty = round(size_per_level / price, 8)
        try:
            order = await exchange.create_limit_sell_order(symbol, qty, price)
            sell_orders.append({
                "price":    price,
                "qty":      qty,
                "order_id": order.get("id"),
                "status":   "open",
            })
            logger.info(f"Grid: sell order placed {symbol} @ {price:.6g} qty={qty}")
        except Exception as e:
            errors.append(f"sell@{price:.6g}: {str(e)[:60]}")
            logger.warning(f"Grid: failed sell order {symbol} @ {price}: {e}")

    return {
        "buy_orders":     buy_orders,
        "sell_orders":    sell_orders,
        "market_buy_qty": market_buy_qty,
        "errors":         errors,
    }


async def cancel_all_grid_orders(exchange, symbol: str, orders: List[Dict]) -> None:
    """Cancel all open grid orders for a symbol."""
    for order in orders:
        order_id = order.get("order_id")
        if not order_id:
            continue
        try:
            await exchange.cancel_order(order_id, symbol)
        except Exception:
            pass  # already filled or cancelled
