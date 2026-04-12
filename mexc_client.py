"""
MEXC Spot API client.
Handles authentication (HMAC-SHA256) and core endpoints needed
for the Smart Portfolio bot.

Docs: https://mexcdevelop.github.io/apidocs/spot_v3_en/
"""

import hashlib
import hmac
import time
import json
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
            "Content-Type": "application/json",
            "X-MEXC-APIKEY": self.api_key,
        })

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _timestamp(self) -> str:
        return str(int(time.time() * 1000))

    def _sign(self, params: dict) -> str:
        query = urlencode(params)
        return hmac.new(
            self.secret_key.encode("utf-8"),
            query.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

    def _signed_params(self, params: Optional[dict] = None) -> dict:
        p = params or {}
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

    def get_asset_balance(self, symbol: str) -> float:
        """Return free (available) balance for a single asset (e.g. 'BTC')."""
        account = self.get_account()
        for b in account.get("balances", []):
            if b.get("asset", "").upper() == symbol.upper():
                return float(b.get("free", 0))
        return 0.0

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_ticker(self, symbol: str) -> dict:
        """
        symbol: e.g. 'BTCUSDT'
        Returns ticker dict with 'lastPrice'.
        """
        data = self._get("/api/v3/ticker/price", {"symbol": symbol})
        return data

    def get_price(self, symbol: str) -> float:
        """Return last traded price for symbol (e.g. 'BTCUSDT')."""
        ticker = self.get_ticker(symbol)
        return float(ticker.get("price", 0))

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
        """
        params = {
            "symbol": symbol,
            "side": "BUY",
            "type": "MARKET",
            "quoteOrderQty": str(round(quote_size, 6)),
        }
        return self._post("/api/v3/order", params)

    def place_market_sell(self, symbol: str, base_size: float) -> dict:
        """
        Market sell using base currency amount.
        base_size: amount of the base asset to sell.
        """
        params = {
            "symbol": symbol,
            "side": "SELL",
            "type": "MARKET",
            "quantity": str(round(base_size, 8)),
        }
        return self._post("/api/v3/order", params)

    def get_order(self, symbol: str, order_id: str) -> dict:
        """Fetch order details by orderId."""
        return self._get(
            "/api/v3/order",
            {"symbol": symbol, "orderId": order_id},
            signed=True,
        )
