import unittest

from app.services.ipo.score import calculate_wealth_ipo_score, determine_grade, normalize_observation_date


def make_sample_ipo(ipo_id="ipo_target", sub_date="2026-09-18", final_price=20000.0, band_high=20000.0):
    return {
        "ipo_id": ipo_id,
        "company_name": "테스트기업",
        "market": "KOSDAQ",
        "listing_track": "general",
        "subscription_start": sub_date,
        "final_offer_price": final_price,
        "offer_band_high": band_high,
        "post_offer_shares": 10000000,
        "features": {
            "lockup_commitment_ratio": {"value": 45.0, "status": "ok"},
            "institutional_competition_ratio": {"value": 850.0, "status": "ok"},
            "high_bid_ratio": {"value": 98.0, "status": "ok"},
            "tradable_share_ratio": {"value": 22.0, "status": "ok"},
            "secondary_sale_ratio": {"value": 0.0, "status": "ok"},
            "unlock_3m_ratio": {"value": 5.0, "status": "ok"},
            "relative_valuation": {"value": 0.85, "status": "ok"},
            "revenue_cagr": {"value": 35.0, "status": "ok"},
            "operating_margin": {"value": 18.5, "status": "ok"},
            "net_debt_to_assets": {"value": -10.0, "status": "ok"},
            "recent_ipo_market_return": {"value": 45.0, "status": "ok"},
            "market_20d_return": {"value": 3.5, "status": "ok"},
        },
    }


class IpoScoreTests(unittest.TestCase):
    def test_normalize_observation_date_accepts_dart_and_iso_encodings(self):
        self.assertEqual(str(normalize_observation_date("20260914")), "2026-09-14")
        self.assertEqual(str(normalize_observation_date("2026-09-14")), "2026-09-14")
        self.assertEqual(str(normalize_observation_date("2026-09-14T23:59:59+09:00")), "2026-09-14")
        self.assertEqual(str(normalize_observation_date("20260914235959")), "2026-09-14")
        self.assertIsNone(normalize_observation_date("2026-99-99"))

    def test_dart_compact_source_dates_are_observed_before_subscription(self):
        target = make_sample_ipo(sub_date="2026-09-15")
        target["offer_band_high"] = None
        for name in ("institutional_competition_ratio", "lockup_commitment_ratio", "tradable_share_ratio"):
            target["features"][name]["source_date"] = "20260914"
        result = calculate_wealth_ipo_score(target, [])
        self.assertNotIn("institutional_competition_ratio", result["core_missing"])
        self.assertNotIn("lockup_commitment_ratio", result["core_missing"])
        self.assertNotIn("tradable_share_ratio", result["core_missing"])
        self.assertIn("pricing_discipline", result["core_missing"])

    def test_pricing_discipline_with_observed_offer_band_unblocks_score(self):
        target = make_sample_ipo(sub_date="2026-09-15", final_price=18000.0, band_high=18000.0)
        target["sources"] = {
            "final_offer_price": {"source_date": "20260914"},
            "offer_band_high": {"source_date": "2026-09-14"},
        }
        for name in ("institutional_competition_ratio", "lockup_commitment_ratio", "tradable_share_ratio"):
            target["features"][name]["source_date"] = "20260914"
        result = calculate_wealth_ipo_score(target, [])
        self.assertEqual(result["core_missing"], [])
        self.assertIsNotNone(result["score"])

    def test_invalid_source_date_fails_closed(self):
        target = make_sample_ipo(sub_date="2026-09-15")
        target["features"]["institutional_competition_ratio"]["source_date"] = "not-a-date"
        result = calculate_wealth_ipo_score(target, [])
        self.assertIn("institutional_competition_ratio", result["core_missing"])
    def test_grade_boundaries(self):
        self.assertEqual(determine_grade(100.0), "A")
        self.assertEqual(determine_grade(80.0), "A")
        self.assertEqual(determine_grade(79.9), "B")
        self.assertEqual(determine_grade(65.0), "B")
        self.assertEqual(determine_grade(64.9), "C")
        self.assertEqual(determine_grade(50.0), "C")
        self.assertEqual(determine_grade(49.9), "D")
        self.assertEqual(determine_grade(35.0), "D")
        self.assertEqual(determine_grade(34.9), "E")
        self.assertEqual(determine_grade(0.0), "E")
        self.assertIsNone(determine_grade(None))

    def test_spac_does_not_receive_general_company_score(self):
        target = make_sample_ipo()
        target["listing_track"] = "spac"

        res = calculate_wealth_ipo_score(target, [])

        self.assertEqual(res["status"], "NOT_APPLICABLE")
        self.assertFalse(res["is_calculating"])
        self.assertIsNone(res["score"])
        self.assertIsNone(res["grade"])
        self.assertEqual(res["score_label"], "별도평가")
        self.assertEqual(res["component_scores"], {})
        self.assertEqual(res["feature_scores"], {})

    def test_legacy_named_spac_does_not_receive_general_company_score(self):
        target = make_sample_ipo()
        target["listing_track"] = "general"
        target["company_name"] = "엔에이치스팩34호"

        res = calculate_wealth_ipo_score(target, [])

        self.assertIsNone(res["score"])
        self.assertEqual(res["score_label"], "별도평가")
        self.assertEqual(res["reason"], "SPAC requires a separate evaluation framework")

    def test_full_features_score_calculation(self):
        target = make_sample_ipo()
        cohort = [
            make_sample_ipo(f"ipo_hist_{i}", f"2026-08-{i:02d}", 15000.0 + i * 100)
            for i in range(1, 35)
        ]
        res = calculate_wealth_ipo_score(target, cohort)

        self.assertFalse(res["is_calculating"])
        self.assertIsNotNone(res["score"])
        self.assertIn(res["grade"], ["A", "B", "C", "D", "E"])
        self.assertEqual(res["coverage"], 100.0)
        self.assertEqual(res["confidence_level"], "high")
        self.assertEqual(res["status"], "BETA")
        self.assertEqual(len(res["core_missing"]), 0)

        # Check component scores sum logic
        comps = res["component_scores"]
        self.assertIn("institutional_demand", comps)
        self.assertIn("supply_structure", comps)
        self.assertIn("valuation", comps)
        self.assertIn("fundamentals", comps)
        self.assertIn("market_environment", comps)

    def test_core_feature_missing_returns_calculating(self):
        target = make_sample_ipo()
        # Remove core feature 'lockup_commitment_ratio'
        target["features"]["lockup_commitment_ratio"] = {"value": None, "status": "missing"}

        res = calculate_wealth_ipo_score(target, [])
        self.assertTrue(res["is_calculating"])
        self.assertIsNone(res["score"])
        self.assertIsNone(res["grade"])
        self.assertEqual(res["score_label"], "산정중")
        self.assertIn("lockup_commitment_ratio", res["core_missing"])

    def test_optional_feature_missing_uses_neutral_50(self):
        target = make_sample_ipo()
        # Remove optional feature 'unlock_3m_ratio' (3 pts)
        target["features"]["unlock_3m_ratio"] = {"value": None, "status": "missing"}

        res = calculate_wealth_ipo_score(target, [])
        self.assertFalse(res["is_calculating"])
        # Coverage drops from 100% to 97%
        self.assertEqual(res["coverage"], 97.0)
        # Neutral score 50.0 assigned to unlock_3m_ratio
        self.assertEqual(res["feature_scores"]["unlock_3m_ratio"], 50.0)

    def test_insufficient_coverage_returns_calculating(self):
        target = make_sample_ipo()
        # Remove non-core features so coverage drops below 75%
        for feat in ["high_bid_ratio", "secondary_sale_ratio", "unlock_3m_ratio",
                     "revenue_cagr", "operating_margin", "net_debt_to_assets",
                     "recent_ipo_market_return", "market_20d_return"]:
            target["features"][feat] = {"value": None, "status": "missing"}

        res = calculate_wealth_ipo_score(target, [])
        self.assertTrue(res["is_calculating"])
        self.assertIsNone(res["score"])
        self.assertLess(res["coverage"], 75.0)
        self.assertEqual(res["score_label"], "산정중")

    def test_score_determinism(self):
        target = make_sample_ipo()
        res1 = calculate_wealth_ipo_score(target, [])
        res2 = calculate_wealth_ipo_score(target, [])
        self.assertEqual(res1["score"], res2["score"])
        self.assertEqual(res1["grade"], res2["grade"])
        self.assertEqual(res1["coverage"], res2["coverage"])

    def test_valuation_zero_not_overwritten_by_50(self):
        target = make_sample_ipo()
        # valuation ratio >= 1.40 maps to exactly 0.0 points
        target["features"]["relative_valuation"] = {"value": 1.50, "status": "ok"}
        res = calculate_wealth_ipo_score(target, [])
        # Score must be 0.0, NOT 50.0!
        self.assertEqual(res["feature_scores"]["relative_valuation"], 0.0)

    def test_future_source_date_rejected_for_score(self):
        # Target subscription_start is 2026-09-18 -> score_as_of is 2026-09-17 23:59:59
        target = make_sample_ipo(sub_date="2026-09-18")
        # A core feature having a source_date in the future (e.g. securities issuance report on 2026-09-22)
        target["features"]["institutional_competition_ratio"] = {
            "value": 1200.0,
            "status": "ok",
            "source_date": "2026-09-22",  # After subscription start!
        }
        res = calculate_wealth_ipo_score(target, [])
        # Core feature must be rejected as missing, score must be calculating!
        self.assertTrue(res["is_calculating"])
        self.assertIn("institutional_competition_ratio", res["core_missing"])
        self.assertIsNone(res["score"])

    def test_cohort_excludes_same_subscription_date(self):
        from app.services.ipo.normalize import select_cohort
        target = make_sample_ipo("target_ipo", sub_date="2026-09-18")
        peer_same_day = make_sample_ipo("peer_same_day", sub_date="2026-09-18")
        peer_past = make_sample_ipo("peer_past", sub_date="2026-09-15")

        cohort = select_cohort(target, [peer_same_day, peer_past])
        ipo_ids = [c["ipo_id"] for c in cohort]
        self.assertNotIn("target_ipo", ipo_ids)
        self.assertNotIn("peer_same_day", ipo_ids)  # <= forbidden, strictly < sub_date
        self.assertIn("peer_past", ipo_ids)

    def test_cohort_excludes_future_ipo(self):
        from app.services.ipo.normalize import select_cohort
        target = make_sample_ipo("target_ipo", sub_date="2026-09-18")
        peer_future = make_sample_ipo("peer_future", sub_date="2026-09-25")
        peer_past = make_sample_ipo("peer_past", sub_date="2026-09-01")

        cohort = select_cohort(target, [peer_future, peer_past])
        ipo_ids = [c["ipo_id"] for c in cohort]
        self.assertNotIn("peer_future", ipo_ids)
        self.assertIn("peer_past", ipo_ids)

    def test_cohort_respects_36_month_window(self):
        from app.services.ipo.normalize import select_cohort
        target = make_sample_ipo("target_ipo", sub_date="2026-09-18")
        # 35 candidates within 36 months (e.g. 2025)
        recent_candidates = [
            make_sample_ipo(f"recent_{i}", sub_date="2025-05-10")
            for i in range(35)
        ]
        # 5 candidates older than 36 months (e.g. 2022)
        old_candidates = [
            make_sample_ipo(f"old_{i}", sub_date="2022-01-10")
            for i in range(5)
        ]
        cohort = select_cohort(target, recent_candidates + old_candidates)
        # Since recent candidates >= 30, old candidates (>36m) must not be included
        ipo_ids = set(c["ipo_id"] for c in cohort)
        for i in range(5):
            self.assertNotIn(f"old_{i}", ipo_ids)

    def test_cohort_fallback_still_excludes_future(self):
        from app.services.ipo.normalize import select_cohort
        target = make_sample_ipo("target_ipo", sub_date="2026-09-18")
        # Only 5 past candidates (triggers fallback to full candidate pool)
        past_candidates = [
            make_sample_ipo(f"past_{i}", sub_date="2024-05-10")
            for i in range(5)
        ]
        future_candidates = [
            make_sample_ipo(f"future_{i}", sub_date="2026-10-10")
            for i in range(5)
        ]
        cohort = select_cohort(target, past_candidates + future_candidates)
        ipo_ids = set(c["ipo_id"] for c in cohort)
        # Even under fallback, future IPOs must NEVER be included!
        for i in range(5):
            self.assertNotIn(f"future_{i}", ipo_ids)
            self.assertIn(f"past_{i}", ipo_ids)


if __name__ == "__main__":
    unittest.main()
