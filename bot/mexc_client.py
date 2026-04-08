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

    async def wait_for_order(self, order_id: str, symbol: str, timeout: int = 30) -> dict:
        """
        Poll fetch_order until the order is closed (filled).

        Raises immediately on terminal failure statuses (canceled/expired/rejected).
        Raises TimeoutError if the order is not filled within `timeout` seconds.
        Needed because ccxt does not guarantee a synchronous fill on market orders
        for all exchange configurations.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            order = await self.exchange.fetch_order(order_id, symbol)
            status = order.get("status")
            if status == "closed":
                return order
            if status in ("canceled", "expired", "rejected"):
                raise Exception(f"Order {order_id} ended with status: {status}")
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"Order {order_id} not filled after {timeout}s")
            await asyncio.sleep(min(1.0, remaining))

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

                # Wait for confirmed fill before recording success
                order_id = order.get("id")
                filled = float(order.get("filled") or 0)
                if order_id and order.get("status") != "closed":
                    try:
                        confirmed = await self.wait_for_order(order_id, pair)
                        filled = float(confirmed.get("filled") or filled)
                        price = float(confirmed.get("average") or confirmed.get("price") or price)
                    except Exception as wait_err:
                        results.append({"symbol": sym, "action": action, "status": "error",
                                        "reason": str(wait_err)[:100]})
                        continue

                results.append({"symbol": sym, "action": action, "status": "ok",
                                "usdt": usdt_amt, "price": price, "filled": filled,
                                "order_id": order_id})
            except Exception as e:
                results.append({"symbol": sym, "action": action, "status": "error",
                                "reason": str(e)[:100]})
        return results

    async def compute_allocations(self, symbols: list, method: str) -> list:
        """
        احسب النسب المستهدفة لقائمة عملات بثلاث طرق:
          equal  — توزيع متساوٍ
          volume — نسبي حسب حجم التداول 24h من MEXC
          mcap   — نسبي حسب القيمة السوقية (quoteVolume كبديل عملي)

        Returns: [{'symbol': str, 'target_percentage': float}, ...]  مجموعها 100.0
        """
        if not symbols:
            return []

        if method == "equal":
            pct = round(100.0 / len(symbols), 4)
            result = [{"symbol": s, "target_percentage": pct} for s in symbols]
            # تصحيح الفارق العشري على آخر عملة
            diff = round(100.0 - sum(r["target_percentage"] for r in result), 4)
            result[-1]["target_percentage"] = round(result[-1]["target_percentage"] + diff, 4)
            return result

        # volume و mcap: نجلب tickers ونستخدم quoteVolume
        pairs = [f"{s}/{self.quote}" for s in symbols]
        try:
            tickers = await self.exchange.fetch_tickers(pairs)
        except Exception:
            tickers = {}
            for s in symbols:
                try:
                    t = await self.exchange.fetch_ticker(f"{s}/{self.quote}")
                    tickers[f"{s}/{self.quote}"] = t
                except Exception:
                    pass

        weights = {}
        for s in symbols:
            pair = f"{s}/{self.quote}"
            t = tickers.get(pair, {})
            # quoteVolume = حجم التداول بالـ USDT خلال 24 ساعة
            # يُستخدم لكلا الطريقتين (volume و mcap) لأن MEXC لا يوفر market cap مباشرة
            vol = float(t.get("quoteVolume") or t.get("baseVolume") or 0)
            weights[s] = max(vol, 0.0)

        total_w = sum(weights.values())

        if total_w <= 0:
            # fallback: توزيع متساوٍ إذا لم تتوفر بيانات
            return await self.compute_allocations(symbols, "equal")

        result = []
        running = 0.0
        for i, s in enumerate(symbols):
            if i == len(symbols) - 1:
                # آخر عملة تأخذ الباقي لضمان المجموع = 100
                pct = round(100.0 - running, 2)
            else:
                pct = round(weights[s] / total_w * 100, 2)
                running += pct
            result.append({"symbol": s, "target_percentage": pct})

        return result

    async def close(self):
        await self.exchange.close()
