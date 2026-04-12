"""
Bitget Spot API client.
Handles authentication (HMAC-SHA256) and core endpoints needed
for the Smart Portfolio bot.
"""

import hashlib
import hmac
import time
import base64
import json
import os
import requests
from typing import Optional


BASE_URL = "https://api.bitget.com"


class BitgetClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        passphrase: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("BITGET_API_KEY", "")
        self.secret_key = secret_key or os.environ.get("BITGET_SECRET_KEY", "")
        self.passphrase = passphrase or os.environ.get("BITGET_PASSPHRASE", "")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _timestamp(self) -> str:
        return str(int(time.time() * 1000))

    def _sign(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        message = timestamp + method.upper() + request_path + body
        mac = hmac.new(
            self.secret_key.encode("utf-8"),
            message.encode("utf-8"),
            digestmod=hashlib.sha256,
        )
        return base64.b64encode(mac.digest()).decode()

    def _headers(self, method: str, path: str, body: str = "") -> dict:
        ts = self._timestamp()
        return {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": self._sign(ts, method, path, body),
            "ACCESS-TIMESTAMP": ts,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # HTTP wrappers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        query = ""
        if params:
            query = "?" + "&".join(f"{k}={v}" for k, v in params.items())
        full_path = path + query
        headers = self._headers("GET", full_path)
        resp = self.session.get(BASE_URL + full_path, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload)
        headers = self._headers("POST", path, body)
        resp = self.session.post(BASE_URL + path, headers=headers, data=body, timeout=10)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def get_spot_assets(self) -> list:
        """Return list of spot account assets with available balance."""
        data = self._get("/api/v2/spot/account/assets")
        return data.get("data", [])

    def get_asset_balance(self, symbol: str) -> float:
        """Return available balance for a single asset (e.g. 'BTC')."""
        assets = self.get_spot_assets()
        for a in assets:
            if a.get("coin", "").upper() == symbol.upper():
                return float(a.get("available", 0))
        return 0.0

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_ticker(self, symbol: str) -> dict:
        """
        symbol: e.g. 'BTCUSDT'
        Returns ticker dict with 'lastPr' (last price).
        """
        data = self._get("/api/v2/spot/market/tickers", {"symbol": symbol})
        tickers = data.get("data", [])
        if tickers:
            return tickers[0]
        raise ValueError(f"No ticker found for {symbol}")

    def get_price(self, symbol: str) -> float:
        """Return last traded price for symbol (e.g. 'BTCUSDT')."""
        ticker = self.get_ticker(symbol)
        return float(ticker.get("lastPr", 0))

    def get_symbol_info(self, symbol: str) -> dict:
        """Return trading rules for a spot symbol."""
        data = self._get("/api/v2/spot/public/symbols", {"symbol": symbol})
        items = data.get("data", [])
        if items:
            return items[0]
        raise ValueError(f"Symbol info not found for {symbol}")

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def place_market_buy(self, symbol: str, quote_size: float) -> dict:
        """
        Market buy using quote currency (USDT).
        quote_size: amount in USDT to spend.
        """
        payload = {
            "symbol": symbol,
            "side": "buy",
            "orderType": "market",
            "force": "gtc",
            "quoteSize": str(round(quote_size, 6)),
        }
        return self._post("/api/v2/spot/trade/place-order", payload)

    def place_market_sell(self, symbol: str, base_size: float) -> dict:
        """
        Market sell using base currency amount.
        base_size: amount of the base asset to sell.
        """
        payload = {
            "symbol": symbol,
            "side": "sell",
            "orderType": "market",
            "force": "gtc",
            "size": str(round(base_size, 8)),
        }
        return self._post("/api/v2/spot/trade/place-order", payload)

    def get_order(self, symbol: str, order_id: str) -> dict:
        """Fetch order details by orderId."""
        data = self._get(
            "/api/v2/spot/trade/orderInfo",
            {"symbol": symbol, "orderId": order_id},
        )
        return data.get("data", {})
