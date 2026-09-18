import json
import math
import tempfile
import unittest
from pathlib import Path

from app.services.ipo.features import CORE_MANDATORY_FEATURES
from tools.ipo_backtest import (
    calculate_median,
    evaluate_quarterly_consistency,
    generate_synthetic_dataset,
    is_excluded_from_universe,
    run_backtest,
    spearman_correlation,
)


class IpoBacktestTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_core_mandatory_features_imported_and_checked(self):
        self.assertEqual(len(CORE_MANDATORY_FEATURES), 4)
        expected = {
            'institutional_competition_ratio',
            'lockup_commitment_ratio',
            'tradable_share_ratio',
            'pricing_discipline',
        }
        self.assertEqual(set(CORE_MANDATORY_FEATURES), expected)

    def test_synthetic_never_production(self):
        result = run_backtest(synthetic_test=True)
        self.assertNotEqual(result.get('score_status'), 'PRODUCTION')
        self.assertEqual(result.get('score_status'), 'BETA')
        self.assertFalse(result.get('all_criteria_passed', False))

    def test_no_real_dataset_never_production(self):
        non_existent = self.tmp_path / 'does_not_exist.json'
        result = run_backtest(data_path=non_existent, synthetic_test=False)
        self.assertEqual(result.get('status'), 'BACKTEST DATA NOT AVAILABLE')
        self.assertEqual(result.get('score_status'), 'BETA')

    def test_empty_manual_file_cannot_pass(self):
        empty_mv = self.tmp_path / 'manual_val_empty.json'
        with open(empty_mv, 'w', encoding='utf-8') as f:
            f.write('[]')

        result = run_backtest(synthetic_test=True, manual_validation_path=empty_mv)
        self.assertFalse(result.get('manual_validation_passed', False))
        self.assertFalse(result.get('all_criteria_passed', False))

    def test_49_manual_samples_cannot_pass(self):
        mv_49 = self.tmp_path / 'manual_val_49.json'
        samples = [{'date_price_correct': True, 'feature_correct': True} for _ in range(49)]
        with open(mv_49, 'w', encoding='utf-8') as f:
            json.dump(samples, f)

        result = run_backtest(synthetic_test=True, manual_validation_path=mv_49)
        self.assertFalse(result.get('manual_validation_passed', False))
        self.assertEqual(result.get('manual_validation_stats', {}).get('sample_count'), 49)

    def test_date_price_accuracy_below_98_fails(self):
        mv_path = self.tmp_path / 'manual_val_low_dp.json'
        samples = [{'date_price_correct': i < 48, 'feature_correct': True} for i in range(50)]
        with open(mv_path, 'w', encoding='utf-8') as f:
            json.dump(samples, f)

        result = run_backtest(synthetic_test=True, manual_validation_path=mv_path)
        self.assertFalse(result.get('manual_validation_passed', False))
        self.assertAlmostEqual(result.get('manual_validation_stats', {}).get('date_price_accuracy'), 96.0)

    def test_feature_accuracy_below_95_fails(self):
        mv_path = self.tmp_path / 'manual_val_low_f.json'
        samples = [{'date_price_correct': True, 'feature_correct': i < 47} for i in range(50)]
        with open(mv_path, 'w', encoding='utf-8') as f:
            json.dump(samples, f)

        result = run_backtest(synthetic_test=True, manual_validation_path=mv_path)
        self.assertFalse(result.get('manual_validation_passed', False))
        self.assertAlmostEqual(result.get('manual_validation_stats', {}).get('feature_accuracy'), 94.0)

    def test_manual_validation_50_passing(self):
        mv_path = self.tmp_path / 'manual_val_pass.json'
        samples = [{'date_price_correct': i < 49, 'feature_correct': i < 48} for i in range(50)]
        with open(mv_path, 'w', encoding='utf-8') as f:
            json.dump(samples, f)

        result = run_backtest(synthetic_test=True, manual_validation_path=mv_path)
        self.assertTrue(result.get('manual_validation_passed', False))
        self.assertAlmostEqual(result.get('manual_validation_stats', {}).get('date_price_accuracy'), 98.0)
        self.assertAlmostEqual(result.get('manual_validation_stats', {}).get('feature_accuracy'), 96.0)

    def test_quarterly_uses_20_percent(self):
        items = []
        for i in range(10):
            items.append({
                'subscription_start': f'2024-02-{10+i:02d}',
                'score': float(i * 10),
                'R0': float(i * 5),
            })
        rate, pos, total = evaluate_quarterly_consistency(items)
        self.assertEqual(total, 1)
        self.assertEqual(pos, 1)
        self.assertEqual(rate, 100.0)

    def test_regime_ge_20_negative_spread_fails(self):
        # Create dataset where R1 (2021-07 to 2025-06) has negative spread
        records = generate_synthetic_dataset(30)
        for r in records:
            r['returns']['R0'] = -r['returns']['R0']

        mv_path = self.tmp_path / 'mv_pass.json'
        with open(mv_path, 'w') as f:
            json.dump([{'date_price_correct': True, 'feature_correct': True} for _ in range(50)], f)

        ds_path = self.tmp_path / 'r1_ds.json'
        with open(ds_path, 'w') as f:
            json.dump(records, f)

        res = run_backtest(data_path=ds_path, manual_validation_path=mv_path)
        self.assertFalse(res.get('meets_regimes', True))
        self.assertEqual(res.get('regime_results', {}).get('R1', {}).get('status'), 'FAIL')

    def test_regime_lt_20_insufficient_does_not_fail(self):
        records = []
        for i in range(15):
            records.append({
                'ipo_id': f'r2-{i}',
                'company_name': f'Co_{i}',
                'subscription_start': '2025-08-10',
                'listing_date': '2025-08-20',
                'final_offer_price': 10000.0,
                'offer_band_high': 10000.0,
                'features': {k: {'value': 50.0, 'status': 'ok'} for k in CORE_MANDATORY_FEATURES},
                'returns': {'R0': -10.0, 'R1M': -10.0},
            })
        mv_path = self.tmp_path / 'mv_pass.json'
        with open(mv_path, 'w') as f:
            json.dump([{'date_price_correct': True, 'feature_correct': True} for _ in range(50)], f)

        ds_path = self.tmp_path / 'r2_ds.json'
        with open(ds_path, 'w') as f:
            json.dump(records, f)

        res = run_backtest(data_path=ds_path, manual_validation_path=mv_path)
        self.assertTrue(res.get('meets_regimes', False))
        self.assertEqual(res.get('regime_results', {}).get('R2', {}).get('status'), 'insufficient_sample')

    def test_universe_exclusion_rules(self):
        self.assertTrue(is_excluded_from_universe({'company_name': 'KB제24호스팩'}))
        self.assertTrue(is_excluded_from_universe({'company_name': '이지스리츠'}))
        self.assertTrue(is_excluded_from_universe({'company_name': '삼성전자우'}))
        self.assertTrue(is_excluded_from_universe({'company_name': '현대차2우B'}))
        self.assertTrue(is_excluded_from_universe({'listing_track': 'SPAC'}))
        self.assertTrue(is_excluded_from_universe({'listing_track': 'reit'}))
        self.assertTrue(is_excluded_from_universe({'listing_track': 'merger'}))
        self.assertFalse(is_excluded_from_universe({'company_name': '두산로보틱스', 'listing_track': 'general'}))


if __name__ == '__main__':
    unittest.main()
