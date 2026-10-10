"""Canonical planning metadata only; synthetic user portfolios."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from unittest.mock import patch

from app.services import planning, portfolio
from regression_support import IsolatedDataTestCase, empty_portfolio


class DirectBucketTests(IsolatedDataTestCase):
    def setUp(self):
        super().setUp()
        self.pf = empty_portfolio(accounts=[{'id': 'a', 'cash_krw': 1000, 'cash_usd': 1}],
                                 holdings=[{'id': 'h1', 'account_id': 'a', 'code': 'SAME', 'quantity': 5, 'market_value_krw': 5000},
                                           {'id': 'h2', 'account_id': 'a', 'code': 'SAME', 'quantity': 3, 'market_value_krw': 3000}])
        self.pf['settings']['wealth_planning'] = {**planning.empty(), 'buckets': [
            {'id': 'core', 'name': '코어', 'target': 50}, {'id': 'growth', 'name': '성장', 'target': 50}],
            'accounts': {'a': 'core'}}
        portfolio.write_portfolio(self.pf, 'alice')
        portfolio.write_portfolio(empty_portfolio(accounts=[{'id': 'bob-account'}], holdings=[{'id': 'bob-holding'}]), 'bob')

    def assign(self, **extra):
        return planning.mutate('alice', 'bucket-assignment', {
            'revision': planning.read_planning('alice')['revision'], 'assignment_type': 'holding',
            'target_id': 'h1', 'mode': 'bucket', 'bucket_id': 'growth', **extra})

    def test_exact_identity_all_modes_and_financial_purity(self):
        before = deepcopy(portfolio.read_portfolio('alice'))
        bob = portfolio._get_portfolio_file('bob').read_bytes()
        saved = self.assign()
        self.assertEqual(saved['holdings'], {'h1': 'growth'})
        self.assertEqual(saved['revision'], 1)
        self.assertEqual(self.assign(mode='unclassified')['holdings'], {'h1': ''})
        self.assertEqual(self.assign(mode='inherit')['holdings'], {})
        after = portfolio.read_portfolio('alice')
        before['settings'].pop('wealth_planning'); after['settings'].pop('wealth_planning')
        self.assertEqual(after, before)
        self.assertEqual(portfolio._get_portfolio_file('bob').read_bytes(), bob)

    def test_invalid_target_bucket_mode_and_cross_user_rejected_without_write(self):
        path = portfolio._get_portfolio_file('alice'); before = path.read_bytes()
        for extra in ({'target_id': 'bob-holding'}, {'target_id': 'missing'}, {'target_id': 'a'},
                      {'assignment_type': 'cash'}, {'bucket_id': '__cash__'}, {'bucket_id': 'missing'},
                      {'mode': 'other'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.assign(**extra)
            self.assertEqual(path.read_bytes(), before)

    def test_same_revision_writers_one_conflict_no_lost_update(self):
        barrier = Barrier(2)
        def writer(key):
            barrier.wait()
            try:
                return planning.mutate('alice', 'bucket-assignment', {'revision': 0, 'assignment_type': 'holding',
                    'target_id': key, 'mode': 'bucket', 'bucket_id': 'growth'})
            except planning.PlanningConflict:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(writer, ['h1', 'h2']))
        self.assertEqual(results.count('conflict'), 1)
        saved = planning.read_planning('alice')
        self.assertEqual(saved['revision'], 1)
        self.assertEqual(len(saved['holdings']), 1)

    def test_replace_failure_preserves_canonical_bytes(self):
        path = portfolio._get_portfolio_file('alice'); before = path.read_bytes()
        with patch('app.services.financial_json.os.replace', side_effect=OSError('synthetic replace failure')):
            with self.assertRaises(OSError): self.assign()
        self.assertEqual(path.read_bytes(), before)

    def test_legacy_read_does_not_add_colors_cash_or_revision(self):
        path = portfolio._get_portfolio_file('alice'); before = path.read_bytes()
        for _ in range(3):
            result = planning.read_planning('alice')
            self.assertEqual(result['revision'], 0)
            self.assertTrue(all('color' not in b for b in result['buckets']))
            self.assertEqual(len(result['buckets']), 2)
        self.assertEqual(path.read_bytes(), before)

    def test_missing_portfolio_read_does_not_bootstrap(self):
        path = portfolio._get_portfolio_file('new-user')
        self.assertFalse(path.exists())
        self.assertEqual(planning.read_planning('new-user'), planning.empty())
        self.assertFalse(path.exists())

    def test_account_assignment_changes_metadata_only(self):
        before = portfolio.read_portfolio('alice')['accounts']
        saved = self.assign(assignment_type='account', target_id='a')
        self.assertEqual(saved['accounts'], {'a': 'growth'})
        self.assertEqual(portfolio.read_portfolio('alice')['accounts'], before)

    def save_colors(self, color):
        state = planning.read_planning('alice')
        state['buckets'][0]['color'] = color
        return planning.mutate('alice', 'buckets', state)

    def test_color_normalization_persistence_and_rename(self):
        self.assertEqual(self.save_colors('#a78bfa')['buckets'][0]['color'], '#A78BFA')
        state = planning.read_planning('alice'); state['buckets'][0]['name'] = '새 이름'
        del state['buckets'][0]['color']  # Older clients also preserve an existing chosen color.
        saved = planning.mutate('alice', 'buckets', state)
        self.assertEqual(saved['buckets'][0]['color'], '#A78BFA')

    def test_malformed_colors_rejected_without_partial_commit(self):
        path = portfolio._get_portfolio_file('alice'); before = path.read_bytes()
        for color in ('A78BFA', '#FFF', '#A78BFAFF', 'red', 'rgb(1,2,3)', 'var(--text)', 'url(x)', '', None, 12):
            with self.subTest(color=color), self.assertRaises(ValueError): self.save_colors(color)
            self.assertEqual(path.read_bytes(), before)

    def test_reserved_virtual_ids_cannot_be_persisted(self):
        for key in ('__cash__', '__unclassified__', '__unallocated__', '__inherit__'):
            state = planning.read_planning('alice'); state['buckets'][0]['id'] = key
            with self.subTest(key=key), self.assertRaises(ValueError): planning.mutate('alice', 'buckets', state)
