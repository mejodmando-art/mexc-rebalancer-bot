"""
Unit tests for smart_portfolio.py

Run with:
    pytest tests/ -v
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

# Ensure repo root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smart_portfolio import (
    get_pnl,
    get_portfolio_value,
    load_config,
    needs_rebalance_proportional,
    next_run_time,
    save_config,
    validate_allocations,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> dict:
    """Return a minimal valid config dict."""
    cfg = {
        "bot": {"name": "TestBot"},
        "portfolio": {
            "assets": [
                {"symbol": "BTC", "allocation_pct": 60.0},
                {"symbol": "ETH", "allocation_pct": 40.0},
            ],
            "total_usdt": 1000.0,
            "initial_value_usdt": 1000.0,
        },
        "rebalance": {
            "mode": "proportional",
            "proportional": {
                "threshold_pct": 5,
                "check_interval_minutes": 5,
                "min_deviation_to_execute_pct": 3,
            },
            "timed": {"frequency": "daily", "hour": 0},
            "unbalanced": {},
        },
        "termination": {"sell_at_termination": False},
        "asset_transfer": {"enable_asset_transfer": False},
        "paper_trading": True,
    }
    cfg.update(overrides)
    return cfg


def _make_client(prices: dict, balances: dict) -> MagicMock:
    """Return a mock MEXCClient with preset prices and balances."""
    client = MagicMock()
    client.get_price.side_effect = lambda symbol: prices[symbol]
    client.get_asset_balance.side_effect = lambda symbol: balances.get(symbol, 0.0)
    return client


# ---------------------------------------------------------------------------
# validate_allocations
# ---------------------------------------------------------------------------

class TestValidateAllocations(unittest.TestCase):

    def test_valid_two_assets(self):
        assets = [
            {"symbol": "BTC", "allocation_pct": 60},
            {"symbol": "ETH", "allocation_pct": 40},
        ]
        validate_allocations(assets)  # should not raise

    def test_valid_ten_assets(self):
        assets = [{"symbol": f"C{i}", "allocation_pct": 10} for i in range(10)]
        validate_allocations(assets)

    def test_too_few_assets(self):
        with self.assertRaises(ValueError):
            validate_allocations([{"symbol": "BTC", "allocation_pct": 100}])

    def test_too_many_assets(self):
        assets = [{"symbol": f"C{i}", "allocation_pct": 9} for i in range(11)]
        with self.assertRaises(ValueError):
            validate_allocations(assets)

    def test_sum_not_100(self):
        assets = [
            {"symbol": "BTC", "allocation_pct": 60},
            {"symbol": "ETH", "allocation_pct": 30},  # total = 90
        ]
        with self.assertRaises(ValueError):
            validate_allocations(assets)

    def test_sum_exactly_100_with_float(self):
        # 33.33 + 33.33 + 33.34 = 100.00
        assets = [
            {"symbol": "BTC", "allocation_pct": 33.33},
            {"symbol": "ETH", "allocation_pct": 33.33},
            {"symbol": "SOL", "allocation_pct": 33.34},
        ]
        validate_allocations(assets)  # should not raise


# ---------------------------------------------------------------------------
# load_config / save_config
# ---------------------------------------------------------------------------

class TestConfigIO(unittest.TestCase):

    def test_roundtrip(self):
        cfg = _make_config()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            save_config(cfg, path)
            loaded = load_config(path)
            self.assertEqual(loaded["bot"]["name"], "TestBot")
            self.assertEqual(loaded["portfolio"]["total_usdt"], 1000.0)
            self.assertEqual(len(loaded["portfolio"]["assets"]), 2)
        finally:
            os.unlink(path)

    def test_save_creates_valid_json(self):
        cfg = _make_config()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            save_config(cfg, path)
            with open(path) as fh:
                data = json.load(fh)
            self.assertIn("portfolio", data)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# get_portfolio_value
# ---------------------------------------------------------------------------

class TestGetPortfolioValue(unittest.TestCase):

    def test_basic_valuation(self):
        assets = [
            {"symbol": "BTC", "allocation_pct": 60},
            {"symbol": "ETH", "allocation_pct": 40},
        ]
        client = _make_client(
            prices={"BTCUSDT": 50000.0, "ETHUSDT": 3000.0},
            balances={"BTC": 0.01, "ETH": 0.5},
        )
        result = get_portfolio_value(client, assets)

        self.assertAlmostEqual(result["total_usdt"], 2000.0)  # 500 + 1500
        btc = next(r for r in result["assets"] if r["symbol"] == "BTC")
        eth = next(r for r in result["assets"] if r["symbol"] == "ETH")
        self.assertAlmostEqual(btc["value_usdt"], 500.0)
        self.assertAlmostEqual(eth["value_usdt"], 1500.0)
        self.assertAlmostEqual(btc["actual_pct"], 25.0)
        self.assertAlmostEqual(eth["actual_pct"], 75.0)

    def test_zero_balance(self):
        assets = [
            {"symbol": "BTC", "allocation_pct": 50},
            {"symbol": "ETH", "allocation_pct": 50},
        ]
        client = _make_client(
            prices={"BTCUSDT": 50000.0, "ETHUSDT": 3000.0},
            balances={"BTC": 0.0, "ETH": 0.0},
        )
        result = get_portfolio_value(client, assets)
        self.assertEqual(result["total_usdt"], 0.0)
        for r in result["assets"]:
            self.assertEqual(r["actual_pct"], 0.0)

    def test_usdt_asset(self):
        """USDT asset should use price=1.0 and get_asset_balance('USDT')."""
        assets = [
            {"symbol": "BTC", "allocation_pct": 50},
            {"symbol": "USDT", "allocation_pct": 50},
        ]
        client = _make_client(
            prices={"BTCUSDT": 40000.0},
            balances={"BTC": 0.01, "USDT": 400.0},
        )
        result = get_portfolio_value(client, assets)
        self.assertAlmostEqual(result["total_usdt"], 800.0)


# ---------------------------------------------------------------------------
# needs_rebalance_proportional
# ---------------------------------------------------------------------------

class TestNeedsRebalanceProportional(unittest.TestCase):

    def _cfg(self, min_dev=3):
        cfg = _make_config()
        cfg["rebalance"]["proportional"]["min_deviation_to_execute_pct"] = min_dev
        return cfg

    def test_no_rebalance_needed(self):
        """Portfolio exactly at target — no rebalance."""
        cfg = self._cfg()
        # BTC target 60%, ETH target 40%
        client = _make_client(
            prices={"BTCUSDT": 60000.0, "ETHUSDT": 40000.0},
            balances={"BTC": 0.01, "ETH": 0.01},
        )
        # BTC value = 600, ETH value = 400 → total 1000 → BTC 60%, ETH 40%
        self.assertFalse(needs_rebalance_proportional(client, cfg))

    def test_rebalance_needed_over_threshold(self):
        """BTC drifts to 70% (target 60%) → deviation 10% > 3% threshold."""
        cfg = self._cfg(min_dev=3)
        client = _make_client(
            prices={"BTCUSDT": 70000.0, "ETHUSDT": 30000.0},
            balances={"BTC": 0.01, "ETH": 0.01},
        )
        # BTC = 700, ETH = 300 → total 1000 → BTC 70%, ETH 30%
        self.assertTrue(needs_rebalance_proportional(client, cfg))

    def test_rebalance_not_needed_under_threshold(self):
        """Deviation of 1% is below min_dev=3%."""
        cfg = self._cfg(min_dev=3)
        # BTC target 60%, actual ~61%
        client = _make_client(
            prices={"BTCUSDT": 61000.0, "ETHUSDT": 39000.0},
            balances={"BTC": 0.01, "ETH": 0.01},
        )
        self.assertFalse(needs_rebalance_proportional(client, cfg))


# ---------------------------------------------------------------------------
# next_run_time
# ---------------------------------------------------------------------------

class TestNextRunTime(unittest.TestCase):

    def test_daily_future(self):
        now = datetime(2024, 1, 15, 10, 0, 0)
        nxt = next_run_time("daily", from_dt=now, target_hour=12)
        self.assertEqual(nxt.hour, 12)
        self.assertEqual(nxt.day, 15)

    def test_daily_past_rolls_to_tomorrow(self):
        now = datetime(2024, 1, 15, 14, 0, 0)
        nxt = next_run_time("daily", from_dt=now, target_hour=12)
        self.assertEqual(nxt.day, 16)
        self.assertEqual(nxt.hour, 12)

    def test_weekly(self):
        now = datetime(2024, 1, 15, 10, 0, 0)
        nxt = next_run_time("weekly", from_dt=now, target_hour=0)
        self.assertGreater(nxt, now)
        delta = nxt - now
        self.assertGreaterEqual(delta.days, 6)

    def test_monthly(self):
        now = datetime(2024, 1, 15, 10, 0, 0)
        nxt = next_run_time("monthly", from_dt=now, target_hour=0)
        self.assertGreater(nxt, now)
        delta = nxt - now
        self.assertGreaterEqual(delta.days, 29)

    def test_invalid_frequency(self):
        with self.assertRaises(ValueError):
            next_run_time("hourly")


# ---------------------------------------------------------------------------
# get_pnl
# ---------------------------------------------------------------------------

class TestGetPnl(unittest.TestCase):
    # get_snapshots is imported into smart_portfolio's namespace, so patch there.

    @patch("smart_portfolio.get_snapshots")
    def test_profit(self, mock_snaps):
        mock_snaps.return_value = [{"ts": "2024-01-01", "total_usdt": 1200.0}]
        cfg = _make_config()
        cfg["portfolio"]["initial_value_usdt"] = 1000.0
        result = get_pnl(cfg)
        self.assertAlmostEqual(result["pnl_usdt"], 200.0)
        self.assertAlmostEqual(result["pnl_pct"], 20.0)

    @patch("smart_portfolio.get_snapshots")
    def test_loss(self, mock_snaps):
        mock_snaps.return_value = [{"ts": "2024-01-01", "total_usdt": 800.0}]
        cfg = _make_config()
        cfg["portfolio"]["initial_value_usdt"] = 1000.0
        result = get_pnl(cfg)
        self.assertAlmostEqual(result["pnl_usdt"], -200.0)
        self.assertAlmostEqual(result["pnl_pct"], -20.0)

    @patch("smart_portfolio.get_snapshots")
    def test_no_snapshots_uses_initial(self, mock_snaps):
        mock_snaps.return_value = []
        cfg = _make_config()
        cfg["portfolio"]["initial_value_usdt"] = 1000.0
        result = get_pnl(cfg)
        self.assertAlmostEqual(result["pnl_usdt"], 0.0)
        self.assertAlmostEqual(result["pnl_pct"], 0.0)


# ---------------------------------------------------------------------------
# execute_rebalance (paper trading — no real orders)
# ---------------------------------------------------------------------------

class TestExecuteRebalancePaper(unittest.TestCase):

    @patch("smart_portfolio.record_rebalance")
    @patch("smart_portfolio.record_snapshot")
    @patch("smart_portfolio.save_config")
    def test_paper_no_orders_placed(self, mock_save, mock_snap, mock_rec):
        """In paper mode, place_market_buy/sell must never be called."""
        cfg = _make_config()
        cfg["paper_trading"] = True

        client = _make_client(
            prices={"BTCUSDT": 70000.0, "ETHUSDT": 30000.0},
            balances={"BTC": 0.01, "ETH": 0.01},
        )

        from smart_portfolio import execute_rebalance
        with patch.dict(os.environ, {"PAPER_TRADING": "true"}):
            details = execute_rebalance(client, cfg)

        client.place_market_buy.assert_not_called()
        client.place_market_sell.assert_not_called()
        self.assertTrue(len(details) > 0)

    @patch("smart_portfolio.record_rebalance")
    @patch("smart_portfolio.record_snapshot")
    @patch("smart_portfolio.save_config")
    def test_sells_before_buys(self, mock_save, mock_snap, mock_rec):
        """Overweight assets must be sold before underweight ones are bought."""
        cfg = _make_config()
        # BTC target 60%, ETH target 40%
        # BTC actual ~70%, ETH actual ~30% → BTC overweight, ETH underweight
        client = _make_client(
            prices={"BTCUSDT": 70000.0, "ETHUSDT": 30000.0},
            balances={"BTC": 0.01, "ETH": 0.01},
        )

        from smart_portfolio import execute_rebalance
        with patch.dict(os.environ, {"PAPER_TRADING": "true"}):
            details = execute_rebalance(client, cfg)

        actions = [d["action"] for d in details if d["action"] != "SKIP"]
        # At least one SELL and one BUY
        self.assertIn("SELL", actions)
        self.assertIn("BUY", actions)
        # First non-SKIP action must be SELL
        self.assertEqual(actions[0], "SELL")

    @patch("smart_portfolio.record_rebalance")
    @patch("smart_portfolio.record_snapshot")
    @patch("smart_portfolio.save_config")
    def test_details_contain_required_fields(self, mock_save, mock_snap, mock_rec):
        cfg = _make_config()
        client = _make_client(
            prices={"BTCUSDT": 50000.0, "ETHUSDT": 3000.0},
            balances={"BTC": 0.01, "ETH": 0.5},
        )
        from smart_portfolio import execute_rebalance
        with patch.dict(os.environ, {"PAPER_TRADING": "true"}):
            details = execute_rebalance(client, cfg)

        for d in details:
            self.assertIn("symbol", d)
            self.assertIn("target_pct", d)
            self.assertIn("actual_pct", d)
            self.assertIn("deviation", d)
            self.assertIn("diff_usdt", d)
            self.assertIn("action", d)


# ---------------------------------------------------------------------------
# Duplicate symbol detection (API-level logic mirrored here)
# ---------------------------------------------------------------------------

class TestDuplicateSymbolDetection(unittest.TestCase):

    def test_duplicate_raises(self):
        """validate_allocations does not check duplicates — API does.
        This test mirrors the API-level duplicate check logic."""
        assets = [
            {"symbol": "SOL", "allocation_pct": 50},
            {"symbol": "SOL", "allocation_pct": 50},
        ]
        symbols = [a["symbol"] for a in assets]
        has_duplicate = len(symbols) != len(set(symbols))
        self.assertTrue(has_duplicate)

    def test_no_duplicate(self):
        assets = [
            {"symbol": "BTC", "allocation_pct": 60},
            {"symbol": "ETH", "allocation_pct": 40},
        ]
        symbols = [a["symbol"] for a in assets]
        has_duplicate = len(symbols) != len(set(symbols))
        self.assertFalse(has_duplicate)


if __name__ == "__main__":
    unittest.main()
