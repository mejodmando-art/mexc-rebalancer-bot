import asyncio
import re
import time
import ccxt.async_support as ccxt

# Minimum USD value to include an asset — filters out dust/cents positions
_MIN_VALUE_THRESHOLD = 1.0

# Cache markets for 10 minutes — the list rarely changes and fetch_markets()
# returns thousands of records on every call without caching.
_MARKETS_CACHE: dict = {}          # symbol → min_qty
_MARKETS_CACHE_TS: float = 0.0
_MARKETS_CACHE_TTL: float = 600.0  # seconds
_MARKETS_LOCK = asyncio.Lock()     # prevents thundering-herd on cache refresh

# MEXC sometimes returns network-tagged balances like USDT_ERC20, BTC_BEP20.
# This regex strips the network suffix so balances are merged under the base symbol.
_NETWORK_SUFFIX_RE = re.compile(
    r"_(ERC20|BEP20|TRC20|MATIC|SOL|AVAXC|ARBITRUM|OPTIMISM|BSC|HECO|"
    r"OMNI|LIQUID|NATIVE|SPL|ALGO|XLM|ATOM|DOT|KSM|NEAR|FTM|CRO|ONE|"
    r"CELO|MOVR|GLMR|KLAY|ROSE|EVMOS|ASTR|METIS|BOBA|AURORA|ZKSYNC|"
    r"BASE|LINEA|SCROLL|MANTA|BLAST|OPBNB|ZKFAIR|MERLIN|BEVM|BOB|MODE)$",
    re.IGNORECASE,
)


def _base_symbol(raw: str) -> str:
    """Strip network suffix: 'USDT_ERC20' → 'USDT', 'BTC_BEP20' → 'BTC'."""
    return _NETWORK_SUFFIX_RE.sub("", raw.upper())


def _merge_balances(raw_totals: dict) -> dict:
    """
    Merge network-tagged entries into their base symbol.
    e.g. {'USDT': 10, 'USDT_ERC20': 5, 'USDT_BEP20': 3} → {'USDT': 18}
    """
    merged: dict = {}
    for raw_sym, amount in raw_totals.items():
        amount = float(amount or 0)
        if amount < 1e-8:
            continue
        base = _base_symbol(raw_sym)
        merged[base] = merged.get(base, 0.0) + amount
    return merged


class MexcClient:
    def __init__(self, api_key: str, secret: str, quote: str = "USDT"):
        self.quote = quote
        self.exchange = ccxt.mexc({
            "apiKey": api_key,
            "secret": secret,
            "enableRateLimit": True,
            "timeout": 10000,  # 10s per request
            "options": {"defaultType": "spot"},
        })

    async def validate_credentials(self) -> tuple:
        try:
            await self.exchange.fetch_balance()
            return True, "OK"
        except ccxt.AuthenticationError as e:
            return False, f"مفاتيح خاطئة: {str(e)[:80]}"
        except Exception as e:
            return False, str(e)[:100]

    async def get_portfolio(self) -> tuple:
        """Returns ({symbol: {amount, value_usdt, price}}, total_usdt)"""
        balance = await self.exchange.fetch_balance()
        total_usdt = 0.0
        portfolio = {}
        holdings = {}

        # Merge network-tagged balances before processing
        merged = _merge_balances(balance["total"])

        for sym, amount in merged.items():
            if sym == self.quote:
                portfolio[sym] = {"amount": amount, "value_usdt": amount, "price": 1.0}
                total_usdt += amount
            else:
                holdings[sym] = amount

        if not holdings:
            return portfolio, total_usdt

        pairs = [f"{sym}/{self.quote}" for sym in holdings]

        try:
            tickers = await self.exchange.fetch_tickers(pairs)
        except Exception:
            # Fallback: fetch one by one
            tickers = {}
            for sym in holdings:
                try:
                    t = await self.exchange.fetch_ticker(f"{sym}/{self.quote}")
                    tickers[f"{sym}/{self.quote}"] = t
                except Exception:
                    pass

        for sym, amount in holdings.items():
            pair = f"{sym}/{self.quote}"
            ticker = tickers.get(pair, {})
            price = float(ticker.get("last") or ticker.get("close") or 0)
            if price <= 0:
                continue
            val = amount * price
            if val < _MIN_VALUE_THRESHOLD:
                continue  # skip dust
            portfolio[sym] = {"amount": amount, "value_usdt": val, "price": price}
            total_usdt += val

        return portfolio, total_usdt

    async def execute_rebalance(self, trades: list) -> list:
        if not trades:
            return []

        pairs = [f"{t['symbol']}/{self.quote}" for t in trades]

        try:
            tickers = await self.exchange.fetch_tickers(pairs)
        except Exception:
            tickers = {}

        try:
            global _MARKETS_CACHE, _MARKETS_CACHE_TS
            if time.monotonic() - _MARKETS_CACHE_TS > _MARKETS_CACHE_TTL:
                async with _MARKETS_LOCK:
                    # Re-check inside lock — another coroutine may have refreshed already
                    if time.monotonic() - _MARKETS_CACHE_TS > _MARKETS_CACHE_TTL:
                        markets = await self.exchange.fetch_markets()
                        _MARKETS_CACHE = {
                            m["symbol"]: m.get("limits", {}).get("amount", {}).get("min", 0) or 0
                            for m in markets
                        }
                        _MARKETS_CACHE_TS = time.monotonic()
            min_qty_map = _MARKETS_CACHE
        except Exception:
            min_qty_map = _MARKETS_CACHE or {}

        results = []
        for trade in trades:
            sym = trade["symbol"]
            action = trade["action"]
            usdt_amt = trade["usdt_amount"]
            pair = f"{sym}/{self.quote}"
            try:
                ticker = tickers.get(pair, {})
                price = float(ticker.get("last") or 0)
                if not price:
                    t = await self.exchange.fetch_ticker(pair)
                    price = float(t.get("last") or 0)
                if not price:
                    raise ValueError("تعذّر جلب السعر")

                if action == "sell":
                    qty = usdt_amt / price
                    min_qty = min_qty_map.get(pair, 0)
                    if qty < min_qty:
                        results.append({"symbol": sym, "action": action, "status": "skip",
                                        "reason": f"الكمية أقل من الحد ({min_qty})"})
                        continue
                    order = await self.exchange.create_market_sell_order(pair, qty)
                else:
                    # MEXC Spot market buy requires quoteOrderQty (USDT amount), not base qty
                    order = await self.exchange.create_market_buy_order_with_cost(pair, usdt_amt)

                results.append({"symbol": sym, "action": action, "status": "ok",
                                "usdt": usdt_amt, "price": price, "order_id": order.get("id")})
            except Exception as e:
                results.append({"symbol": sym, "action": action, "status": "error",
                                "reason": str(e)[:100]})
        return results

    async def close(self):
        await self.exchange.close()
