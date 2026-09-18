import unittest

from app.services.ipo.features import (
    FEATURE_WEIGHTS,
    calculate_pricing_discipline_score,
    calculate_relative_valuation_score,
    compute_derived_features,
)


class IpoFeaturesTests(unittest.TestCase):
    def test_weights_sum_to_exactly_100(self):
        total_weight = sum(FEATURE_WEIGHTS.values())
        self.assertEqual(total_weight, 100)

    def test_pricing_discipline_boundaries(self):
        # At or below band high: 100
        self.assertEqual(calculate_pricing_discipline_score(20000, 20000), 100.0)
        self.assertEqual(calculate_pricing_discipline_score(18000, 20000), 100.0)

        # +5%: 75
        self.assertEqual(calculate_pricing_discipline_score(21000, 20000), 75.0)

        # +10%: 50
        self.assertEqual(calculate_pricing_discipline_score(22000, 20000), 50.0)

        # +15%: 25
        self.assertEqual(calculate_pricing_discipline_score(23000, 20000), 25.0)

        # +20%: 0
        self.assertEqual(calculate_pricing_discipline_score(24000, 20000), 0.0)

        # Above +20%: clamped to 0
        self.assertEqual(calculate_pricing_discipline_score(30000, 20000), 0.0)

        # None inputs
        self.assertIsNone(calculate_pricing_discipline_score(None, 20000))
        self.assertIsNone(calculate_pricing_discipline_score(20000, None))

    def test_relative_valuation_breakpoints_and_interpolation(self):
        # Breakpoints
        self.assertEqual(calculate_relative_valuation_score(0.70), 100.0)
        self.assertEqual(calculate_relative_valuation_score(0.80), 100.0)
        self.assertEqual(calculate_relative_valuation_score(1.00), 70.0)
        self.assertEqual(calculate_relative_valuation_score(1.20), 30.0)
        self.assertEqual(calculate_relative_valuation_score(1.40), 0.0)
        self.assertEqual(calculate_relative_valuation_score(1.60), 0.0)

        # Midpoints interpolation
        self.assertEqual(calculate_relative_valuation_score(0.90), 85.0)
        self.assertEqual(calculate_relative_valuation_score(1.10), 50.0)
        self.assertEqual(calculate_relative_valuation_score(1.30), 15.0)

        # None inputs
        self.assertIsNone(calculate_relative_valuation_score(None))
        self.assertIsNone(calculate_relative_valuation_score(0.0))

    def test_derived_features_computation(self):
        ipo = {
            "final_offer_price": 21000.0,
            "offer_band_high": 20000.0,
            "post_offer_shares": 10000000,
            "features": {
                "tradable_share_ratio": {"value": 25.0, "status": "ok"},
            },
        }
        derived = compute_derived_features(ipo)

        # pricing_discipline: 21000 vs 20000 (+5%) -> 75.0
        self.assertEqual(derived["pricing_discipline"]["status"], "ok")
        self.assertEqual(derived["pricing_discipline"]["value"], 75.0)

        # tradable_market_cap_krw: (25% of 10M) * 21000 = 2.5M * 21000 = 52,500,000,000 KRW
        self.assertEqual(derived["tradable_market_cap_krw"]["status"], "ok")
        self.assertEqual(derived["tradable_market_cap_krw"]["value"], 52500000000.0)


if __name__ == "__main__":
    unittest.main()
