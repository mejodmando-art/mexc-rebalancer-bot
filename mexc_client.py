"""
MEXC Spot API client.
Handles authentication (HMAC-SHA256) and core endpoints needed
for the Smart Portfolio bot.

Auth: API Key + Secret Key only (no passphrase).
Signature: HMAC-SHA256 over the query string, appended as &signature=...
Header: X-MEXC-APIKEY
"""

import hashlib
import hmac
import time
import os
import requests
from typing import Optional
from urllib.parse import urlencode


BASE_URL = "https://api.mexc.com"


class MEXCClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("MEXC_API_KEY", "")
        self.secret_key = secret_key or os.environ.get("MEXC_SECRET_KEY", "")
        self.session = requests.Session()
        self.session.headers.update({
            "X-MEXC-APIKEY": self.api_key,
            "Content-Type": "application/json",
        })

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _timestamp(self) -> str:
        return str(int(time.time() * 1000))

    def _sign(self, params: dict) -> str:
        """Return HMAC-SHA256 hex signature over the URL-encoded params."""
        query = urlencode(params)
        return hmac.new(
            self.secret_key.encode("utf-8"),
            query.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

    def _signed_params(self, params: Optional[dict] = None) -> dict:
        """Merge params with timestamp and append signature."""
        p = dict(params or {})
        p["timestamp"] = self._timestamp()
        p["signature"] = self._sign(p)
        return p

    # ------------------------------------------------------------------
    # HTTP wrappers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: Optional[dict] = None, signed: bool = False) -> dict:
        p = self._signed_params(params) if signed else (params or {})
        resp = self.session.get(BASE_URL + path, params=p, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, params: Optional[dict] = None) -> dict:
        """MEXC signed POST sends params as query string (not JSON body)."""
        p = self._signed_params(params)
        resp = self.session.post(BASE_URL + path, params=p, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str, params: Optional[dict] = None) -> dict:
        p = self._signed_params(params)
        resp = self.session.delete(BASE_URL + path, params=p, timeout=10)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def get_account(self) -> dict:
        """Return full account info including balances."""
        return self._get("/api/v3/account", signed=True)

    def get_spot_assets(self) -> list:
        """Return list of balances with non-zero free or locked amount."""
        data = self.get_account()
        return data.get("balances", [])

    def get_asset_balance(self, symbol: str) -> float:
        """Return free (available) balance for a single asset (e.g. 'BTC')."""
        for a in self.get_spot_assets():
            if a.get("asset", "").upper() == symbol.upper():
                return float(a.get("free", 0))
        return 0.0

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_ticker(self, symbol: str) -> dict:
        """
        symbol: e.g. 'BTCUSDT'
        Returns 24hr ticker dict with 'lastPrice'.
        """
        data = self._get("/api/v3/ticker/24hr", {"symbol": symbol})
        if isinstance(data, list):
            if data:
                return data[0]
            raise ValueError(f"No ticker found for {symbol}")
        return data

    def get_price(self, symbol: str) -> float:
        """Return last traded price for symbol (e.g. 'BTCUSDT')."""
        data = self._get("/api/v3/ticker/price", {"symbol": symbol})
        return float(data.get("price", 0))

    def get_symbol_info(self, symbol: str) -> dict:
        """Return trading rules for a spot symbol."""
        data = self._get("/api/v3/exchangeInfo", {"symbol": symbol})
        symbols = data.get("symbols", [])
        if symbols:
            return symbols[0]
        raise ValueError(f"Symbol info not found for {symbol}")

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def place_market_buy(self, symbol: str, quote_size: float) -> dict:
        """
        Market buy using quote currency (USDT).
        quote_size: amount in USDT to spend.
        MEXC uses quoteOrderQty for market buy by quote amount.
        """
        params = {
            "symbol": symbol,
            "side": "BUY",
            "type": "MARKET",
            "quoteOrderQty": str(round(quote_size, 6)),
        }
        return self._post("/api/v3/order", params)

    def get_step_size(self, symbol: str) -> float:
        """Return the minimum quantity increment (stepSize) for a symbol.

        Falls back to 1e-8 if the info cannot be fetched so callers always
        get a usable value.
        """
        try:
            info = self.get_symbol_info(symbol)
            for f in info.get("filters", []):
                if f.get("filterType") == "LOT_SIZE":
                    return float(f.get("stepSize", 1e-8))
        except Exception:
            pass
        return 1e-8

    def _round_step(self, qty: float, step: float) -> float:
        """Round qty down to the nearest valid step multiple."""
        if step <= 0:
            return round(qty, 8)
        import math
        factor = 1.0 / step
        return math.floor(qty * factor) / factor

    def place_market_sell(self, symbol: str, base_size: float) -> dict:
        """
        Market sell using base currency amount.
        base_size: amount of the base asset to sell.
        Quantity is rounded down to the symbol's stepSize to avoid MEXC
        'Invalid quantity' rejections.
        """
        step = self.get_step_size(symbol)
        qty = self._round_step(base_size, step)
        # Express with enough decimal places to represent the step size.
        decimals = max(0, -int(f"{step:.10f}".rstrip("0").find(".")) + len(f"{step:.10f}".rstrip("0").split(".")[1]))
        qty_str = f"{qty:.{decimals}f}" if decimals > 0 else str(int(qty))
        params = {
            "symbol": symbol,
            "side": "SELL",
            "type": "MARKET",
            "quantity": qty_str,
        }
        return self._post("/api/v3/order", params)

    def get_order(self, symbol: str, order_id: str) -> dict:
        """Fetch order details by orderId."""
        return self._get(
            "/api/v3/order",
            {"symbol": symbol, "orderId": order_id},
            signed=True,
        )
