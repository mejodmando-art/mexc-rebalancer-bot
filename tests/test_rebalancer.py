import unittest
from bot.rebalancer import calculate_trades, MEXC_TAKER_FEE, MIN_TRADE_USDT


def _portfolio(sym, value_usdt):
    """Helper: build a single-asset portfolio dict."""
    return {sym: {"value_usdt": value_usdt, "amount": 1.0, "price": value_usdt}}


class TestCalculateTrades(unittest.TestCase):

    def test_no_trades_when_within_threshold(self):
        """Drift below threshold produces no trades."""
        portfolio = _portfolio("BTC", 51.0)
        allocations = [{"symbol": "BTC", "target_percentage": 50.0}]
        trades, report = calculate_trades(portfolio, 100.0, allocations, threshold=5.0)
        self.assertEqual(trades, [])
        self.assertEqual(len(report), 1)
        self.assertFalse(report[0]["needs_action"])

    def test_buy_trade_generated(self):
        """Underweight asset beyond threshold generates a buy trade."""
        portfolio = _portfolio("ETH", 30.0)
        allocations = [{"symbol": "ETH", "target_percentage": 50.0}]
        trades, _ = calculate_trades(portfolio, 100.0, allocations, threshold=5.0)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["action"], "buy")
        self.assertEqual(trades[0]["symbol"], "ETH")

    def test_sell_trade_generated(self):
        """Overweight asset beyond threshold generates a sell trade."""
        portfolio = _portfolio("BNB", 70.0)
        allocations = [{"symbol": "BNB", "target_percentage": 50.0}]
        trades, _ = calculate_trades(portfolio, 100.0, allocations, threshold=5.0)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["action"], "sell")
        self.assertEqual(trades[0]["symbol"], "BNB")

    def test_fee_inflates_buy_amount(self):
        """Buy usdt_amount is inflated by 1/(1-MEXC_TAKER_FEE) vs raw diff."""
        portfolio = _portfolio("SOL", 30.0)
        allocations = [{"symbol": "SOL", "target_percentage": 50.0}]
        trades, _ = calculate_trades(portfolio, 100.0, allocations, threshold=5.0)
        self.assertEqual(len(trades), 1)
        raw_diff = 50.0 - 30.0  # 20 USDT
        expected = round(raw_diff / (1 - MEXC_TAKER_FEE), 2)
        self.assertAlmostEqual(trades[0]["usdt_amount"], expected, places=2)
        self.assertGreater(trades[0]["usdt_amount"], raw_diff)

    def test_sell_amount_not_inflated(self):
        """Sell usdt_amount equals the raw diff (no fee inflation)."""
        portfolio = _portfolio("ADA", 70.0)
        allocations = [{"symbol": "ADA", "target_percentage": 50.0}]
        trades, _ = calculate_trades(portfolio, 100.0, allocations, threshold=5.0)
        self.assertEqual(len(trades), 1)
        raw_diff = 70.0 - 50.0  # 20 USDT
        self.assertAlmostEqual(trades[0]["usdt_amount"], round(raw_diff, 2), places=2)

    def test_empty_portfolio(self):
        """Empty portfolio with allocations produces buy trades (0 current value)."""
        portfolio = {}
        allocations = [{"symbol": "BTC", "target_percentage": 100.0}]
        trades, report = calculate_trades(portfolio, 100.0, allocations, threshold=5.0)
        # BTC has 0% current, target 100% → drift = -100% → buy
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["action"], "buy")

    def test_below_min_trade_usdt(self):
        """Drift exceeds threshold but diff < MIN_TRADE_USDT → trade skipped."""
        # total=100, target=50%, current=44% → diff=6 USDT but we set min_trade=10
        portfolio = _portfolio("XRP", 44.0)
        allocations = [{"symbol": "XRP", "target_percentage": 50.0}]
        trades, report = calculate_trades(
            portfolio, 100.0, allocations, threshold=5.0, min_trade_usdt=10.0
        )
        self.assertEqual(trades, [])
        self.assertTrue(report[0]["needs_action"])  # drift detected but trade skipped


if __name__ == "__main__":
    unittest.main()
