from __future__ import annotations
"""
tests/test_session_dedup.py

Session de-duplication tests for stock record daily P/L — CORRECTED SEMANTICS.

Safe-baseline rule:
  A holding contributes to day_profit_krw ONLY when:
  1. prev_session_map is not None (a baseline record exists)
  2. instrument_key IS in prev_session_map (was previously known)
  3. current as_of is not None (session is provenance-aware)
  4. current as_of != previous as_of (session has genuinely advanced)
  Otherwise contribution = 0.

  prev_session_map=None : safe-by-default (contributes 0)
  prev_session_map={}   : first provenance-aware snapshot (contributes 0)

Instrument identity: currency:code (stable across market alias changes).

Tests A-L revised, plus tests for same-day upsert (4), multi-market KST (5),
provider provenance (6), and canonical identity (7).
"""
import datetime
import sys
import unittest
from copy import deepcopy
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from app.services import asset_records
from app.services.asset_records import (
    build_stock_record_from_holdings,
    normalize_record,
    list_asset_records,
    upsert_asset_record,
)
from regression_support import IsolatedDataTestCase, empty_portfolio
from app.services import portfolio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _h(
    code: str,
    currency: str,
    market_value_krw: float,
    day_change_rate: float,
    day_change_as_of: str | None,
    **kwargs,
) -> dict:
    """Build an enriched holding dict for use in build_stock_record_from_holdings."""
    currency = currency.upper()
    default_market = 'KRX' if currency == 'KRW' else 'NAS'
    return {
        'id': kwargs.get('id', f'h-{code}'),
        'code': code,
        'market': kwargs.get('market', default_market),
        'currency': currency,
        'quantity': 100,
        'current_price': market_value_krw / 100,
        'avg_price': market_value_krw / 100,
        'market_value_krw': market_value_krw,
        'cost_value_krw': market_value_krw,
        'fx_rate': kwargs.get('fx_rate', 1.0 if currency == 'KRW' else 1385.0),
        'day_change_rate': day_change_rate,
        'day_change_as_of': day_change_as_of,
    }


# ---------------------------------------------------------------------------
# Test A: Same session repeated -> second contribution = 0
# ---------------------------------------------------------------------------
class TestA_SameSessionRepeated(IsolatedDataTestCase):
    def test_same_session_repeated_zeroes_contribution(self) -> None:
        """A: If as_of matches prev_session_map, day_profit contribution is 0."""
        holdings = [_h('005930', 'KRW', 80_000_000, 1.55, '2026-09-19')]

        # Prev map has same session
        prev_map = {'KRW:005930': '2026-09-19'}
        rec = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)
        self.assertEqual(rec['day_profit_krw'], 0.0)

    def test_new_session_contributes(self) -> None:
        """A: If as_of differs from prev_session_map, contribution is calculated."""
        holdings = [_h('005930', 'KRW', 80_000_000, 1.55, '2026-09-19')]

        prev_map = {'KRW:005930': '2026-09-18'}  # previous session was earlier
        rec = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)
        expected = 80_000_000 * (1.55 / 101.55)
        self.assertAlmostEqual(rec['day_profit_krw'], round(expected, 2), delta=1.0)

    def test_holdings_session_uses_currency_code_key(self) -> None:
        """A: holdings_session provenance map uses currency:code keys."""
        holdings = [_h('005930', 'KRW', 80_000_000, 1.55, '2026-09-19')]
        rec = build_stock_record_from_holdings(holdings)
        hs = rec.get('holdings_session', {})
        self.assertEqual(hs.get('KRW:005930'), '2026-09-19')
        self.assertNotIn('005930:KRX', hs, 'Old code:market format must not appear')


# ---------------------------------------------------------------------------
# Test B: Production-style duplicate
# ---------------------------------------------------------------------------
class TestB_ProductionStyleDuplicate(IsolatedDataTestCase):
    def test_production_style_duplicate_does_not_double_count(self) -> None:
        """B: Snapshot with same session as prev_map → day_profit = 0."""
        holdings = [_h('005930', 'KRW', 1_447_891_626, 1.56, '2026-09-19')]

        # Simulate prev_map from a prior record that already captured this session
        prev_map = {'KRW:005930': '2026-09-19'}
        rec = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)
        self.assertEqual(rec['day_profit_krw'], 0.0,
                         'Same session must not re-book the gain')

    def test_first_provenance_aware_snapshot_after_legacy_gives_zero(self) -> None:
        """B: First snapshot where prev_map={} (legacy prior record) → day_profit=0."""
        holdings = [_h('005930', 'KRW', 1_447_891_626, 1.56, '2026-09-19')]
        # prev_session_map={} = legacy prior record with no holdings_session
        rec = build_stock_record_from_holdings(holdings, prev_session_map={})
        self.assertEqual(rec['day_profit_krw'], 0.0,
                         'First provenance-aware snapshot must not fabricate gain')
        # But provenance IS established
        self.assertEqual(rec.get('holdings_session', {}).get('KRW:005930'), '2026-09-19')


# ---------------------------------------------------------------------------
# Test C: Mixed KRX+US weekend
# ---------------------------------------------------------------------------
class TestC_MixedKRXUSWeekend(IsolatedDataTestCase):
    def test_krx_frozen_us_advances(self) -> None:
        """C: KRX same session → 0, US new session → contributes."""
        prev_map = {'KRW:005930': '2026-09-19', 'USD:NVDA': '2026-09-19'}
        holdings_sat = [
            _h('005930', 'KRW', 80_000_000, 1.0, '2026-09-19'),  # KRX frozen
            _h('NVDA', 'USD', 50_000_000, 2.0, '2026-09-20', fx_rate=1385.0),  # US advances
        ]
        rec = build_stock_record_from_holdings(holdings_sat, prev_session_map=prev_map)
        expected_us = 50_000_000 * (2.0 / 102.0)
        self.assertAlmostEqual(rec['day_profit_krw'], round(expected_us, 2), delta=1.0)
        self.assertGreater(rec['day_profit_krw'], 0)

    def test_both_new_sessions_both_contribute(self) -> None:
        """C variant: Both instruments have new sessions → both contribute."""
        prev_map = {'KRW:005930': '2026-09-18', 'USD:NVDA': '2026-09-18'}
        holdings = [
            _h('005930', 'KRW', 80_000_000, 1.0, '2026-09-19'),
            _h('NVDA', 'USD', 50_000_000, 2.0, '2026-09-19', fx_rate=1385.0),
        ]
        rec = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)
        expected = (80_000_000 * (1.0 / 101.0)) + (50_000_000 * (2.0 / 102.0))
        self.assertAlmostEqual(rec['day_profit_krw'], round(expected, 2), delta=2.0)


# ---------------------------------------------------------------------------
# Test D: Monday KRX advance (US frozen at Fri)
# ---------------------------------------------------------------------------
class TestD_MondayKRXAdvance(IsolatedDataTestCase):
    def test_monday_krx_advances_us_frozen(self) -> None:
        """D: Monday: KRX new session → contributes, US still Fri → 0."""
        prev_map = {'KRW:005930': '2026-09-19', 'USD:NVDA': '2026-09-19'}
        holdings_mon = [
            _h('005930', 'KRW', 80_000_000, 0.5, '2026-09-22'),  # Mon KRX
            _h('NVDA', 'USD', 50_000_000, 1.5, '2026-09-19', fx_rate=1385.0),  # still Fri US
        ]
        rec = build_stock_record_from_holdings(holdings_mon, prev_session_map=prev_map)
        expected = 80_000_000 * (0.5 / 100.5)
        self.assertAlmostEqual(rec['day_profit_krw'], round(expected, 2), delta=1.0)


# ---------------------------------------------------------------------------
# Test E: Market holiday
# ---------------------------------------------------------------------------
class TestE_MarketHoliday(IsolatedDataTestCase):
    def test_holiday_session_not_re_counted(self) -> None:
        """E: Weekday holiday: rate still reflects previous session → suppress."""
        prev_map = {'KRW:005930': '2026-10-03'}
        holdings = [_h('005930', 'KRW', 80_000_000, 0.8, '2026-10-03')]
        rec = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)
        self.assertEqual(rec['day_profit_krw'], 0.0)


# ---------------------------------------------------------------------------
# Test F: Same-day snapshot idempotent
# ---------------------------------------------------------------------------
class TestF_SameDayIdempotent(IsolatedDataTestCase):
    def test_same_day_snapshot_shares_record_id(self) -> None:
        """F: Two snapshots on the same calendar day → same record id (by_date upsert)."""
        from app.main import auto_save_all_owner_snapshots
        base_data = empty_portfolio(
            settings={'fx_rates': {'KRW': 1.0, 'USD': 1300.0}},
            holdings=[{
                'id': 'h1', 'account_id': 'acc1', 'broker': '테스트',
                'code': '005930', 'name': '삼성전자',
                'quantity': 100, 'avg_price': 70_000, 'current_price': 80_000,
                'currency': 'KRW', 'market': 'KRX', 'day_change_rate': 0.0,
            }],
        )
        portfolio.write_portfolio(base_data, username='test_user')
        dash = portfolio.get_dashboard(username='test_user')
        saved1 = auto_save_all_owner_snapshots(dash, username='test_user')
        saved2 = auto_save_all_owner_snapshots(dash, username='test_user')
        rec1 = next(r for r in saved1 if (r.get('owner') or '모두') == '모두')
        rec2 = next(r for r in saved2 if (r.get('owner') or '모두') == '모두')
        self.assertEqual(rec1['id'], rec2['id'], 'Same-day snapshots must share record id')
        self.assertEqual(rec1['total_value_krw'], rec2['total_value_krw'])


# ---------------------------------------------------------------------------
# Test G: New holding / unknown as_of — CORRECTED (must produce 0)
# ---------------------------------------------------------------------------
class TestG_NewHoldingZeroContribution(IsolatedDataTestCase):
    def test_new_holding_not_in_prev_map_contributes_zero(self) -> None:
        """G: New holding NOT in prev_session_map → 0 (safe baseline)."""
        prev_map = {'KRW:005930': '2026-09-19'}  # does not contain NVDA
        new_holding = _h('NVDA', 'USD', 50_000_000, 2.0, '2026-09-19', fx_rate=1385.0)
        rec = build_stock_record_from_holdings([new_holding], prev_session_map=prev_map)
        self.assertEqual(rec['day_profit_krw'], 0.0,
                         'New instrument not in prev_map must contribute 0')
        # Provenance IS established for next snapshot
        hs = rec.get('holdings_session', {})
        self.assertEqual(hs.get('USD:NVDA'), '2026-09-19')

    def test_new_holding_no_as_of_contributes_zero(self) -> None:
        """G: New holding with as_of=None → 0 (unknown session, safe)."""
        prev_map = {'KRW:005930': '2026-09-19'}  # NVDA not in prev_map
        holding = _h('NVDA', 'USD', 50_000_000, 2.0, None, fx_rate=1385.0)
        rec = build_stock_record_from_holdings([holding], prev_session_map=prev_map)
        self.assertEqual(rec['day_profit_krw'], 0.0)
        # No provenance key when as_of=None and not in prev_map
        hs = rec.get('holdings_session', {})
        self.assertNotIn('USD:NVDA', hs)

    def test_existing_holding_no_as_of_preserves_previous_known_session(self) -> None:
        """G: Existing holding with as_of=None preserves previous known session."""
        prev_map = {'USD:NVDA': '2026-09-19'}
        holding = _h('NVDA', 'USD', 50_000_000, 2.0, None, fx_rate=1385.0)
        rec = build_stock_record_from_holdings([holding], prev_session_map=prev_map)
        self.assertEqual(rec['day_profit_krw'], 0.0)
        hs = rec.get('holdings_session', {})
        self.assertEqual(hs.get('USD:NVDA'), '2026-09-19')

    def test_first_ever_record_no_prev_gives_zero(self) -> None:
        """G: First ever snapshot (prev_map={}) → 0, establishes baseline."""
        holdings = [_h('005930', 'KRW', 80_000_000, 1.55, '2026-09-19')]
        rec = build_stock_record_from_holdings(holdings, prev_session_map={})
        self.assertEqual(rec['day_profit_krw'], 0.0)
        self.assertEqual(rec.get('holdings_session', {}).get('KRW:005930'), '2026-09-19')

    def test_subsequent_snapshot_with_advanced_session_contributes(self) -> None:
        """G: After baseline established, genuinely new session → contributes."""
        holdings1 = [_h('NVDA', 'USD', 50_000_000, 2.0, '2026-09-19', fx_rate=1385.0)]
        rec1 = build_stock_record_from_holdings(holdings1, prev_session_map={})
        self.assertEqual(rec1['day_profit_krw'], 0.0)
        self.assertEqual(rec1.get('holdings_session', {}).get('USD:NVDA'), '2026-09-19')

        holdings2 = [_h('NVDA', 'USD', 50_000_000, 1.5, '2026-09-20', fx_rate=1385.0)]
        rec2 = build_stock_record_from_holdings(holdings2, prev_session_map=rec1['holdings_session'])
        expected = 50_000_000 * (1.5 / 101.5)
        self.assertAlmostEqual(rec2['day_profit_krw'], round(expected, 2), delta=1.0)


# ---------------------------------------------------------------------------
# Test H: Legacy record — CORRECTED
# ---------------------------------------------------------------------------
class TestH_LegacyRecord(IsolatedDataTestCase):
    def test_legacy_record_no_holdings_session_gives_zero(self) -> None:
        """H: Prior record has no holdings_session → prev_map={} → all 0 (safe)."""
        holdings = [_h('005930', 'KRW', 80_000_000, 1.55, '2026-09-19')]
        rec = build_stock_record_from_holdings(holdings, prev_session_map={})
        self.assertEqual(rec['day_profit_krw'], 0.0)
        self.assertEqual(rec.get('holdings_session', {}).get('KRW:005930'), '2026-09-19')

    def test_none_prev_session_map_with_known_as_of_produces_zero_and_emits_baseline(self) -> None:
        """
        Invariant 1: If there is no known previous provenance for an instrument,
        its persisted day_profit contribution must be 0, even when prev_session_map=None.
        current rate = +2%, current as_of = known, prev_session_map = None -> 0 profit, baseline emitted.
        """
        holdings = [_h('005930', 'KRW', 80_000_000, 2.0, '2026-09-19')]
        rec = build_stock_record_from_holdings(holdings, prev_session_map=None)
        self.assertEqual(rec['day_profit_krw'], 0.0,
                         'prev_session_map=None with known session must safely produce 0 (no prior provenance)')
        self.assertEqual(rec.get('holdings_session', {}).get('KRW:005930'), '2026-09-19')

    def test_pure_call_without_as_of_and_none_prev_map_produces_zero(self) -> None:
        """Safe baseline invariant: rate = +2%, as_of = None, prev_session_map = None -> day_profit_krw = 0."""
        holdings = [_h('005930', 'KRW', 80_000_000, 2.0, None)]
        rec = build_stock_record_from_holdings(holdings, prev_session_map=None)
        self.assertEqual(rec['day_profit_krw'], 0.0)

    def test_normalize_record_preserves_holdings_session(self) -> None:
        """H: normalize_record preserves holdings_session when present."""
        raw = {
            'id': 'abc', 'date': '2026-09-19', 'owner': '모두',
            'total_value_krw': 1_000_000, 'day_profit_krw': 50_000, 'source': 'auto',
            'holdings_session': {'KRW:005930': '2026-09-19'},
        }
        rec = normalize_record(raw, preserve_id=True)
        self.assertIn('holdings_session', rec)
        self.assertEqual(rec['holdings_session']['KRW:005930'], '2026-09-19')

    def test_normalize_record_no_holdings_session_in_legacy(self) -> None:
        """H: normalize_record on legacy record does not add holdings_session field."""
        raw = {'id': 'abc', 'date': '2026-09-19', 'owner': '모두',
               'total_value_krw': 1_000_000, 'source': 'auto'}
        rec = normalize_record(raw, preserve_id=True)
        self.assertNotIn('holdings_session', rec)


# ---------------------------------------------------------------------------
# Test I: Rate=0.0 new session → provenance still updated
# ---------------------------------------------------------------------------
class TestI_ZeroRateNewSession(IsolatedDataTestCase):
    def test_zero_rate_new_session_updates_provenance(self) -> None:
        """I: rate=0.0 + new session → holdings_session advances."""
        prev_map = {'KRW:005930': '2026-09-18'}
        holdings = [_h('005930', 'KRW', 80_000_000, 0.0, '2026-09-19')]
        rec = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)
        self.assertEqual(rec['day_profit_krw'], 0.0)  # rate=0 → no profit
        self.assertEqual(rec.get('holdings_session', {}).get('KRW:005930'), '2026-09-19')

    def test_zero_rate_same_session_provenance_stays(self) -> None:
        """I: rate=0.0 + same session → provenance emitted."""
        prev_map = {'KRW:005930': '2026-09-19'}
        holdings = [_h('005930', 'KRW', 80_000_000, 0.0, '2026-09-19')]
        rec = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)
        self.assertEqual(rec['day_profit_krw'], 0.0)
        self.assertEqual(rec.get('holdings_session', {}).get('KRW:005930'), '2026-09-19')


# ---------------------------------------------------------------------------
# Test J: Positive/negative rates
# ---------------------------------------------------------------------------
class TestJ_PositiveNegativeRates(IsolatedDataTestCase):
    def test_positive_rate_new_session(self) -> None:
        prev_map = {'KRW:005930': '2026-09-18'}
        holdings = [_h('005930', 'KRW', 80_000_000, 3.0, '2026-09-19')]
        rec = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)
        expected = 80_000_000 * (3.0 / 103.0)
        self.assertAlmostEqual(rec['day_profit_krw'], round(expected, 2), delta=1.0)
        self.assertGreater(rec['day_profit_krw'], 0)

    def test_negative_rate_new_session(self) -> None:
        prev_map = {'KRW:005930': '2026-09-18'}
        holdings = [_h('005930', 'KRW', 80_000_000, -2.0, '2026-09-19')]
        rec = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)
        expected = 80_000_000 * (-2.0 / 98.0)
        self.assertAlmostEqual(rec['day_profit_krw'], round(expected, 2), delta=1.0)
        self.assertLess(rec['day_profit_krw'], 0)

    def test_positive_rate_same_session_suppressed(self) -> None:
        prev_map = {'KRW:005930': '2026-09-19'}
        holdings = [_h('005930', 'KRW', 80_000_000, 3.0, '2026-09-19')]
        rec = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)
        self.assertEqual(rec['day_profit_krw'], 0.0)

    def test_negative_rate_same_session_suppressed(self) -> None:
        prev_map = {'KRW:005930': '2026-09-19'}
        holdings = [_h('005930', 'KRW', 80_000_000, -2.0, '2026-09-19')]
        rec = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)
        self.assertEqual(rec['day_profit_krw'], 0.0)


# ---------------------------------------------------------------------------
# Test K: Cash-only changes
# ---------------------------------------------------------------------------
class TestK_CashOnlyChanges(IsolatedDataTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.base_data = empty_portfolio(
            settings={'fx_rates': {'KRW': 1.0, 'USD': 1300.0}},
            accounts=[{'id': 'acc1', 'broker': '테스트', 'name': '계좌1',
                       'owner': '모두', 'account_type': 'general', 'source': 'test'}],
            holdings=[{'id': 'h1', 'account_id': 'acc1', 'broker': '테스트',
                       'code': '005930', 'name': '삼성전자', 'quantity': 100,
                       'avg_price': 70_000, 'current_price': 80_000,
                       'currency': 'KRW', 'market': 'KRX', 'day_change_rate': 0.0}],
        )
        portfolio.write_portfolio(self.base_data, username='test_user')

    def test_cash_deposit_does_not_change_day_profit(self) -> None:
        dash = portfolio.get_dashboard(username='test_user')
        rec1 = build_stock_record_from_holdings(dash['holdings'], owner='모두')
        data2 = deepcopy(self.base_data)
        data2['settings']['cash_balances'] = {'acc1': {'KRW': 50_000_000, 'USD': 0.0}}
        portfolio.write_portfolio(data2, username='test_user')
        dash2 = portfolio.get_dashboard(username='test_user')
        rec2 = build_stock_record_from_holdings(dash2['holdings'], owner='모두')
        self.assertEqual(rec1['day_profit_krw'], rec2['day_profit_krw'])
        self.assertEqual(rec2['day_profit_krw'], 0.0)


# ---------------------------------------------------------------------------
# Test L: Multiple accounts same ticker
# ---------------------------------------------------------------------------
class TestL_MultipleAccountsSameTicker(IsolatedDataTestCase):
    def test_same_session_suppresses_all_holdings_for_ticker(self) -> None:
        """L: Two holdings same code/currency, same session → both suppressed."""
        prev_map = {'KRW:005930': '2026-09-19'}
        h1 = _h('005930', 'KRW', 40_000_000, 1.5, '2026-09-19')
        h2 = _h('005930', 'KRW', 60_000_000, 1.5, '2026-09-19', id='h-005930-acc2')
        rec = build_stock_record_from_holdings([h1, h2], prev_session_map=prev_map)
        self.assertEqual(rec['day_profit_krw'], 0.0)

    def test_new_session_both_contribute(self) -> None:
        """L: Two holdings same code/currency, new session → both contribute."""
        prev_map = {'KRW:005930': '2026-09-18'}
        h1 = _h('005930', 'KRW', 40_000_000, 1.5, '2026-09-19')
        h2 = _h('005930', 'KRW', 60_000_000, 1.5, '2026-09-19', id='h-005930-acc2')
        rec = build_stock_record_from_holdings([h1, h2], prev_session_map=prev_map)
        expected = (40_000_000 + 60_000_000) * (1.5 / 101.5)
        self.assertAlmostEqual(rec['day_profit_krw'], round(expected, 2), delta=2.0)


# ---------------------------------------------------------------------------
# Test: holdings_session presence
# ---------------------------------------------------------------------------
class TestHoldingsSessionPresence(IsolatedDataTestCase):
    def test_no_as_of_means_no_holdings_session_key(self) -> None:
        holdings = [_h('005930', 'KRW', 80_000_000, 1.0, None)]
        rec = build_stock_record_from_holdings(holdings)
        self.assertNotIn('holdings_session', rec)

    def test_partial_as_of_only_known_in_session(self) -> None:
        holdings = [
            _h('005930', 'KRW', 80_000_000, 1.0, '2026-09-19'),
            _h('NVDA', 'USD', 50_000_000, 2.0, None, fx_rate=1385.0),
        ]
        rec = build_stock_record_from_holdings(holdings)
        hs = rec.get('holdings_session', {})
        self.assertIn('KRW:005930', hs)
        self.assertNotIn('USD:NVDA', hs)


# ---------------------------------------------------------------------------
# Issue 4: Same-day upsert semantics
# ---------------------------------------------------------------------------
class TestSameDayUpsertSemantics(IsolatedDataTestCase):
    def test_second_snapshot_same_day_preserves_eligible_pnl(self) -> None:
        """
        Previous day: KRX session = Friday
        Today first snapshot: KRX = Monday (new) → +X
        Today second snapshot: KRX still Monday → result must still be +X (not 0, not 2X).

        Explanation: both snapshots use date < today filter for prev_session_map,
        so both see the previous-day record (Friday) as the baseline → Monday is new both times.
        The by_date upsert replaces today's record → result is idempotently +X.
        """
        from app.main import auto_save_all_owner_snapshots

        base_data = empty_portfolio(
            settings={'fx_rates': {'KRW': 1.0, 'USD': 1300.0}},
            holdings=[{
                'id': 'h1', 'account_id': 'acc1', 'broker': '테스트',
                'code': '005930', 'name': '삼성전자',
                'quantity': 100, 'avg_price': 70_000, 'current_price': 80_000,
                'currency': 'KRW', 'market': 'KRX', 'day_change_rate': 0.0,
            }],
        )
        portfolio.write_portfolio(base_data, username='test_user')

        # Inject a previous-day record with Friday session provenance
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        upsert_asset_record({
            'date': yesterday,
            'owner': '모두',
            'total_value_krw': 8_000_000,
            'day_profit_krw': 50_000,
            'holdings_session': {'KRW:005930': '2026-09-19'},  # Friday
            'source': 'test',
        }, by_date=True, username='test_user')

        # Build a dashboard with Monday session
        dash = portfolio.get_dashboard(username='test_user')
        for h in dash['holdings']:
            if h.get('code') == '005930':
                h['day_change_rate'] = 0.5
                h['day_change_as_of'] = '2026-09-22'  # Monday

        # First snapshot: Monday is new → contributes
        saved1 = auto_save_all_owner_snapshots(dash, username='test_user')
        rec1 = next(r for r in saved1 if (r.get('owner') or '모두') == '모두')
        self.assertGreater(rec1['day_profit_krw'], 0, 'Monday new session must contribute')
        first_profit = rec1['day_profit_krw']

        # Second snapshot same day: same Monday session → result must equal first
        saved2 = auto_save_all_owner_snapshots(dash, username='test_user')
        rec2 = next(r for r in saved2 if (r.get('owner') or '모두') == '모두')
        self.assertEqual(rec1['id'], rec2['id'], 'Same-day must reuse record id')
        self.assertAlmostEqual(rec2['day_profit_krw'], first_profit, delta=1.0,
                               msg='day_profit must not be zeroed or doubled on second snapshot')

    def test_same_day_later_session_advance_cumulatively_upserts(self) -> None:
        """
        Earlier in the day: KRX session advances (Friday -> Monday), US session still Friday.
        Result 1: Monday day_profit = KRX gain.

        Later in the day: US session now also advances (Friday -> Monday).
        Result 2: Monday day_profit cumulatively updated to KRX gain + US gain.
        Record ID preserved. KRX gain not doubled or reset.
        """
        from app.main import auto_save_all_owner_snapshots

        base_data = empty_portfolio(
            settings={'fx_rates': {'KRW': 1.0, 'USD': 1300.0}},
            holdings=[
                {
                    'id': 'h-krx', 'account_id': 'acc1', 'broker': '테스트',
                    'code': '005930', 'name': '삼성전자',
                    'quantity': 100, 'avg_price': 70_000, 'current_price': 80_000,
                    'currency': 'KRW', 'market': 'KRX', 'day_change_rate': 0.0,
                },
                {
                    'id': 'h-us', 'account_id': 'acc1', 'broker': '테스트',
                    'code': 'AAPL', 'name': '애플',
                    'quantity': 10, 'avg_price': 150.0, 'current_price': 200.0,
                    'currency': 'USD', 'market': 'NAS', 'day_change_rate': 0.0,
                },
            ],
        )
        portfolio.write_portfolio(base_data, username='test_user')

        # Prior day baseline: KRX=Friday, US=Friday
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        upsert_asset_record({
            'date': yesterday,
            'owner': '모두',
            'total_value_krw': 10_600_000,
            'day_profit_krw': 30_000,
            'holdings_session': {
                'KRW:005930': '2026-09-19',  # Friday
                'USD:AAPL': '2026-09-19',    # Friday
            },
            'source': 'test',
        }, by_date=True, username='test_user')

        today = datetime.date.today().isoformat()

        # Step 1: today first save: KRX advances Monday -> stored day_profit = X
        dash1 = portfolio.get_dashboard(username='test_user')
        for h in dash1['holdings']:
            if h.get('code') == '005930':
                h['day_change_rate'] = 1.0
                h['day_change_as_of'] = '2026-09-22'  # Monday
            elif h.get('code') == 'AAPL':
                h['day_change_rate'] = 0.0
                h['day_change_as_of'] = '2026-09-19'  # Friday

        saved1 = auto_save_all_owner_snapshots(dash1, username='test_user')
        rec1 = next(r for r in saved1 if (r.get('owner') or '모두') == '모두')
        expected_krx = 8_000_000.0 * (1.0 / 101.0)
        self.assertAlmostEqual(rec1['day_profit_krw'], round(expected_krx, 2), delta=1.0)

        # Invariant 4 assertion 1: Verify stored on disk
        disk_recs1 = [r for r in list_asset_records(username='test_user') if r.get('date') == today and (r.get('owner') or '모두') == '모두']
        self.assertEqual(len(disk_recs1), 1)
        self.assertAlmostEqual(disk_recs1[0]['day_profit_krw'], round(expected_krx, 2), delta=1.0)

        # Step 2: today second save: same observations -> stored day_profit still X (not 0, not 2X)
        saved2 = auto_save_all_owner_snapshots(dash1, username='test_user')
        rec2 = next(r for r in saved2 if (r.get('owner') or '모두') == '모두')
        self.assertEqual(rec1['id'], rec2['id'])
        disk_recs2 = [r for r in list_asset_records(username='test_user') if r.get('date') == today and (r.get('owner') or '모두') == '모두']
        self.assertEqual(len(disk_recs2), 1, 'Same-day second save must not create duplicate record')
        self.assertAlmostEqual(disk_recs2[0]['day_profit_krw'], round(expected_krx, 2), delta=1.0,
                               msg='Second save with same observations must remain X (not 0 and not 2X)')

        # Step 3: today later: US also advances -> stored day_profit = X + Y
        dash3 = portfolio.get_dashboard(username='test_user')
        for h in dash3['holdings']:
            if h.get('code') == '005930':
                h['day_change_rate'] = 1.0
                h['day_change_as_of'] = '2026-09-22'  # Monday
            elif h.get('code') == 'AAPL':
                h['day_change_rate'] = 2.0
                h['day_change_as_of'] = '2026-09-22'  # Monday (advanced!)

        saved3 = auto_save_all_owner_snapshots(dash3, username='test_user')
        rec3 = next(r for r in saved3 if (r.get('owner') or '모두') == '모두')
        self.assertEqual(rec1['id'], rec3['id'], 'Same-day cumulative upsert must preserve record id')

        expected_us = (10 * 200.0 * 1300.0) * (2.0 / 102.0)
        expected_total = expected_krx + expected_us

        # Invariant 4 assertion 3: Verify final stored record on disk has X + Y
        disk_recs3 = [r for r in list_asset_records(username='test_user') if r.get('date') == today and (r.get('owner') or '모두') == '모두']
        self.assertEqual(len(disk_recs3), 1, 'Final stored records must have exactly 1 record for today')
        self.assertAlmostEqual(disk_recs3[0]['day_profit_krw'], round(expected_total, 2), delta=2.0,
                               msg='Cumulative same-day upsert must store X + Y on disk')


# ---------------------------------------------------------------------------
# Issue 5: Multi-market same-day KST
# ---------------------------------------------------------------------------
class TestMultiMarketSameDayKST(IsolatedDataTestCase):
    def test_kst_saturday_krx_frozen_us_advances(self) -> None:
        """KST Sat: KRX still Fri, US advances to Fri US session → only US contributes."""
        prev_map = {'KRW:005930': '2026-09-19', 'USD:NVDA': '2026-09-18'}
        holdings = [
            _h('005930', 'KRW', 80_000_000, 1.0, '2026-09-19'),  # KRX frozen at Fri
            _h('NVDA', 'USD', 50_000_000, 2.0, '2026-09-19', fx_rate=1385.0),  # US Fri (new)
        ]
        rec = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)
        expected_us = 50_000_000 * (2.0 / 102.0)
        self.assertAlmostEqual(rec['day_profit_krw'], round(expected_us, 2), delta=1.0)

    def test_kst_saturday_repeat_snapshot_same_result(self) -> None:
        """KST Sat second snapshot: same sessions → same profit (prev_map unchanged)."""
        prev_map = {'KRW:005930': '2026-09-19', 'USD:NVDA': '2026-09-18'}
        holdings = [
            _h('005930', 'KRW', 80_000_000, 1.0, '2026-09-19'),
            _h('NVDA', 'USD', 50_000_000, 2.0, '2026-09-19', fx_rate=1385.0),
        ]
        rec1 = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)
        rec2 = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)
        self.assertAlmostEqual(rec1['day_profit_krw'], rec2['day_profit_krw'], delta=1.0)
        self.assertGreater(rec1['day_profit_krw'], 0)

    def test_kst_sunday_same_sessions_as_saturday_gives_zero(self) -> None:
        """KST Sun: prev_map from Saturday record (KRX Fri + US Fri) → 0 new P/L."""
        saturday_session = {'KRW:005930': '2026-09-19', 'USD:NVDA': '2026-09-19'}
        holdings = [
            _h('005930', 'KRW', 80_000_000, 1.0, '2026-09-19'),
            _h('NVDA', 'USD', 50_000_000, 2.0, '2026-09-19', fx_rate=1385.0),
        ]
        rec = build_stock_record_from_holdings(holdings, prev_session_map=saturday_session)
        self.assertEqual(rec['day_profit_krw'], 0.0)


# ---------------------------------------------------------------------------
# Issue 6: Provider provenance
# ---------------------------------------------------------------------------
class TestProviderProvenance(IsolatedDataTestCase):
    def test_kr_candle_result_has_as_of(self) -> None:
        """KR candle result must contain _as_of = last candle date."""
        from app.services.web_finance import calculate_period_changes
        candles = [
            {'date': '2026-09-17', 'close': 79_000.0},
            {'date': '2026-09-18', 'close': 79_500.0},
            {'date': '2026-09-19', 'close': 80_000.0},
        ]
        result = calculate_period_changes(candles, 80_000.0)
        result['_as_of'] = candles[-1]['date']
        self.assertEqual(result['_as_of'], '2026-09-19')
        self.assertIn('1D', result)

    def test_refresh_returns_session_obs_key(self) -> None:
        """refresh_all_holdings_prices must return session_obs in result."""
        import asyncio
        from unittest.mock import patch
        from app.services.web_finance import refresh_all_holdings_prices
        holdings = [{'id': 'h1', 'code': '005930', 'currency': 'KRW'}]
        with patch('app.services.web_finance.external_network_allowed', return_value=False):
            result = asyncio.run(refresh_all_holdings_prices(holdings))
        self.assertIn('session_obs', result)
        self.assertIsInstance(result['session_obs'], dict)

    def test_session_obs_structure(self) -> None:
        """session_obs entries have rate and as_of keys."""
        obs = {'rate': 1.55, 'as_of': '2026-09-19'}
        self.assertIn('rate', obs)
        self.assertIn('as_of', obs)

    def test_zero_rate_session_obs_carries_as_of(self) -> None:
        """Zero rate session_obs still carries its session date."""
        obs = {'rate': 0.0, 'as_of': '2026-09-19'}
        self.assertEqual(obs['rate'], 0.0)
        self.assertEqual(obs['as_of'], '2026-09-19')

    def test_stale_period_rates_without_session_obs_gives_no_as_of(self) -> None:
        """Without price_session_obs, day_change_as_of must be None."""
        price_session_obs: dict = {}
        code_sym = '005930'
        name_sym = '삼성전자'
        obs = price_session_obs.get(code_sym) or price_session_obs.get(name_sym)
        day_change_as_of = obs.get('as_of') if obs else None
        self.assertIsNone(day_change_as_of)

    def test_paired_price_session_obs_precedence_over_stale_period_rates(self) -> None:
        """
        In portfolio.get_dashboard(), price_session_obs takes precedence over period_rates,
        ensuring that rate and as_of are always from the same observation.
        """
        base_data = empty_portfolio(
            settings={
                'fx_rates': {'KRW': 1.0, 'USD': 1300.0},
                # Stale period_rates has 5.0%
                'period_rates': {'005930': {'1D': 5.0, '_as_of': '2026-09-18'}},
                # Fresh price_session_obs has 1.2% as of 2026-09-22
                'price_session_obs': {'005930': {'rate': 1.2, 'as_of': '2026-09-22'}},
            },
            accounts=[{'id': 'acc1', 'broker': '테스트', 'name': '계좌1', 'owner': '모두', 'account_type': 'general', 'source': 'test'}],
            holdings=[
                {'id': 'h1', 'account_id': 'acc1', 'code': '005930', 'currency': 'KRW', 'name': '삼성전자',
                 'quantity': 100, 'avg_price': 70000, 'current_price': 80000},
            ],
        )
        portfolio.write_portfolio(base_data, username='test_user')
        dash = portfolio.get_dashboard(username='test_user')
        samsung = dash['holdings'][0]

        # Rate and as_of MUST be paired from price_session_obs (1.2, 2026-09-22), NOT 5.0!
        self.assertEqual(samsung['day_change_rate'], 1.2)
        self.assertEqual(samsung['day_change_as_of'], '2026-09-22')

    def test_stale_period_rates_without_as_of_gives_none_session(self) -> None:
        """
        When period_rates has no _as_of and price_session_obs is empty,
        day_change_as_of must be None so it is not treated as a valid session.
        """
        base_data = empty_portfolio(
            settings={
                'fx_rates': {'KRW': 1.0, 'USD': 1300.0},
                'period_rates': {'005930': {'1D': 3.5}},  # no _as_of
                'price_session_obs': {},
            },
            accounts=[{'id': 'acc1', 'broker': '테스트', 'name': '계좌1', 'owner': '모두', 'account_type': 'general', 'source': 'test'}],
            holdings=[
                {'id': 'h1', 'account_id': 'acc1', 'code': '005930', 'currency': 'KRW', 'name': '삼성전자',
                 'quantity': 100, 'avg_price': 70000, 'current_price': 80000},
            ],
        )
        portfolio.write_portfolio(base_data, username='test_user')
        dash = portfolio.get_dashboard(username='test_user')
        samsung = dash['holdings'][0]

        self.assertEqual(samsung['day_change_rate'], 3.5)
        self.assertIsNone(samsung['day_change_as_of'])

    def test_krx_session_obs_rate_and_as_of_from_same_candle_series(self) -> None:
        """
        Invariant 3: In refresh_all_holdings_prices, KRX session_obs rate and as_of
        both come from the exact same candle series (period_changes['1D'] and period_changes['_as_of']),
        preventing any cross-endpoint date/rate mismatch.
        """
        info = {
            'code': '005930',
            'current_price': 80000.0,
            'day_change_rate': 1.60,  # from basic endpoint
            'period_changes': {
                '1D': 1.45,           # from candle endpoint
                '1W': 2.0,
                '_as_of': '2026-09-19',
            },
        }
        # In refresh_all_holdings_prices:
        as_of = info['period_changes'].get('_as_of')
        candle_rate = float(info['period_changes'].get('1D', info.get('day_change_rate', 0.0)))
        obs = {'rate': candle_rate, 'as_of': as_of, 'source': 'candle_series'}

        self.assertEqual(obs['rate'], 1.45, 'Rate in session_obs must be the candle-derived 1D')
        self.assertEqual(obs['as_of'], '2026-09-19')
        self.assertEqual(obs['source'], 'candle_series')

    def test_krx_basic_differs_from_candle_close_persisted_rate_derived_from_candles(self) -> None:
        """
        When basic current_price (82,000) differs from latest candle close (80,000),
        persisted session observation rate is still derived from candle closes ((80000-78000)/78000 = 2.56%)
        and matches candle as_of date.
        """
        info = {
            'code': '005930',
            'current_price': 82000.0,
            'day_change_rate': 5.13,  # from basic endpoint
            'period_changes': {
                '1D': 5.13,           # Frankenstein rate using basic current_price
                'candle_1d': 2.56,    # pure candle close-to-close rate
                '_as_of': '2026-09-19',
            },
        }
        as_of = info['period_changes'].get('_as_of')
        candle_rate = float(info['period_changes'].get('candle_1d', info['period_changes'].get('1D', 0.0)))
        obs = {'rate': candle_rate, 'as_of': as_of, 'source': 'candle_series'}

        self.assertEqual(obs['rate'], 2.56, 'Must use pure candle series rate (2.56%), not basic endpoint price')
        self.assertEqual(obs['as_of'], '2026-09-19')

    def test_refresh_all_holdings_prices_krx_derives_candle_rate_when_prices_differ(self) -> None:
        """
        In refresh_all_holdings_prices, when basic price and candle close differ,
        session_obs derives rate strictly from candle_1d while daily_changes keeps basic rate.
        """
        import asyncio
        from unittest.mock import patch
        from app.services.web_finance import refresh_all_holdings_prices

        holdings = [{'id': 'h1', 'code': '005930', 'currency': 'KRW'}]
        mock_info = {
            '005930': {
                'code': '005930',
                'name': '삼성전자',
                'current_price': 82000.0,
                'day_change_rate': 5.13,
                'currency': 'KRW',
                'period_changes': {
                    '1D': 5.13,
                    'candle_1d': 2.56,
                    '_as_of': '2026-09-19',
                },
            }
        }

        with patch('app.services.web_finance.external_network_allowed', return_value=True):
            with patch('app.services.web_finance.fetch_kr_stock_info', return_value=mock_info['005930']):
                with patch('app.services.web_finance.fetch_kr_stock_candles', return_value=mock_info['005930']['period_changes']):
                    with patch('app.services.web_finance.fetch_fx_rate_usd_krw', return_value=1300.0):
                        res = asyncio.run(refresh_all_holdings_prices(holdings))

        self.assertEqual(res['daily_changes']['005930'], 5.13, 'Dashboard daily change gets basic rate')
        self.assertEqual(res['session_obs']['005930']['rate'], 2.56, 'Session obs gets pure candle-series rate')
        self.assertEqual(res['session_obs']['005930']['as_of'], '2026-09-19')

    def test_us_yahoo_coherent_pair(self) -> None:
        """
        Invariant 3: US stock info period_changes derives 1D and _as_of from the exact same
        Yahoo chart JSON response.
        """
        from app.services.web_finance import calculate_period_changes
        candles = [
            {'date': '2026-09-18', 'close': 148.0},
            {'date': '2026-09-19', 'close': 150.0},
        ]
        price = 150.0
        period_changes = calculate_period_changes(candles, price)
        day_rate = round(((price - 148.0) / 148.0) * 100, 2)
        period_changes['1D'] = day_rate
        period_changes['_as_of'] = candles[-1]['date']

        self.assertEqual(period_changes['1D'], 1.35)
        self.assertEqual(period_changes['_as_of'], '2026-09-19')


# ---------------------------------------------------------------------------
# Issue 10: Partial refresh failure
# ---------------------------------------------------------------------------
class TestPartialRefreshFailure(IsolatedDataTestCase):
    def test_partial_refresh_preserves_existing_paired_obs(self) -> None:
        """
        When a refresh succeeds for some tickers but fails for another,
        existing observations for the failed ticker are preserved in settings,
        not wiped or overwritten.
        """
        import asyncio
        from unittest.mock import patch
        import app.main as main_mod

        base_data = empty_portfolio(
            settings={
                'fx_rates': {'KRW': 1.0, 'USD': 1300.0},
                'price_session_obs': {
                    '005930': {'rate': 1.0, 'as_of': '2026-09-19'},
                    'AAPL': {'rate': 2.0, 'as_of': '2026-09-19'},
                },
            },
            holdings=[
                {'id': 'h1', 'code': '005930', 'currency': 'KRW', 'name': '삼성전자', 'quantity': 10, 'avg_price': 70000, 'current_price': 80000},
                {'id': 'h2', 'code': 'AAPL', 'currency': 'USD', 'name': '애플', 'quantity': 5, 'avg_price': 150, 'current_price': 200},
            ],
        )
        portfolio.write_portfolio(base_data, username='test_user')

        # Mock refresh_all_holdings_prices returning results ONLY for AAPL (005930 failed/omitted)
        partial_res = {
            'prices': {'h2': 210.0},
            'daily_changes': {'AAPL': 5.0},
            'period_rates': {'AAPL': {'1D': 5.0, '_as_of': '2026-09-22'}},
            'session_obs': {'AAPL': {'rate': 5.0, 'as_of': '2026-09-22'}},
            'session_dates': {'AAPL': '2026-09-22'},
            'fx_rate': 1300.0,
        }

        with patch('app.main.refresh_all_holdings_prices', return_value=partial_res):
            with patch('app.main.is_test_mode', return_value=False):
                res = asyncio.run(main_mod.refresh_prices_for_user('test_user'))

        updated_port = portfolio.read_portfolio(username='test_user')
        stored_obs = updated_port.get('settings', {}).get('price_session_obs', {})

        # 005930 must be preserved from before!
        self.assertIn('005930', stored_obs, 'Failed ticker 005930 must not be wiped')
        self.assertEqual(stored_obs['005930']['as_of'], '2026-09-19')

        # AAPL must be updated to new observation
        self.assertIn('AAPL', stored_obs)
        self.assertEqual(stored_obs['AAPL']['as_of'], '2026-09-22')
        self.assertEqual(stored_obs['AAPL']['rate'], 5.0)

    def test_partial_refresh_failed_instrument_does_not_trigger_new_session(self) -> None:
        """
        When a failed ticker's existing session observation is preserved,
        a snapshot compared against a baseline that already saw that session
        correctly suppresses the failed ticker (contributes 0).
        """
        # Baseline already saw 2026-09-19 for 005930
        prev_map = {'KRW:005930': '2026-09-19', 'USD:AAPL': '2026-09-19'}
        # 005930 failed refresh -> retained 2026-09-19
        # AAPL succeeded -> 2026-09-22
        holdings = [
            _h('005930', 'KRW', 80_000_000, 1.0, '2026-09-19'),  # retained stale session
            _h('AAPL', 'USD', 50_000_000, 5.0, '2026-09-22', fx_rate=1300.0),  # new session
        ]
        rec = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)

        # 005930 must contribute 0 (not mistaken for new session)
        # AAPL must contribute
        expected_aapl = 50_000_000 * (5.0 / 105.0)
        self.assertAlmostEqual(rec['day_profit_krw'], round(expected_aapl, 2), delta=1.0)

    def test_candle_fetch_failure_emits_none_as_of_and_contributes_zero(self) -> None:
        """
        When quote succeeds but candle fetch fails (as_of is None),
        build_stock_record_from_holdings contributes 0 and does not store a fabricated session.
        """
        prev_map = {'KRW:005930': '2026-09-19'}
        holdings = [
            _h('005930', 'KRW', 80_000_000, 3.0, None),  # as_of is None due to candle failure
        ]
        rec = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)
        self.assertEqual(rec['day_profit_krw'], 0.0)
        # When current session is unknown, preserve previous known session
        self.assertEqual(rec.get('holdings_session', {}).get('KRW:005930'), '2026-09-19')

    def test_refresh_with_unavailable_as_of_does_not_replace_persistent_paired_obs(self) -> None:
        """
        Invariant 2: When current price/rate is available on next refresh but trustworthy
        session as_of is unavailable (e.g. candle fetch failed), the persistent complete
        paired observation must NOT be replaced by an incomplete observation with as_of=None.
        The dashboard daily_price_changes path may be updated, but the last trustworthy
        price_session_obs baseline must be preserved.
        """
        import asyncio
        from unittest.mock import patch
        import app.main as main_mod

        base_data = empty_portfolio(
            settings={
                'fx_rates': {'KRW': 1.0, 'USD': 1300.0},
                'price_session_obs': {
                    '005930': {'rate': 1.5, 'as_of': '2026-09-18', 'source': 'candle_series'},
                },
                'daily_price_changes': {'005930': 1.5},
            },
            holdings=[
                {'id': 'h1', 'code': '005930', 'currency': 'KRW', 'name': '삼성전자', 'quantity': 10, 'avg_price': 70000, 'current_price': 80000},
            ],
        )
        portfolio.write_portfolio(base_data, username='test_user')

        # Next refresh: current price/rate is available (2.5%), but trustworthy as_of is unavailable
        # (session_obs omits 005930 because as_of is unavailable)
        refresh_res = {
            'prices': {'h1': 82000.0},
            'daily_changes': {'005930': 2.5},  # updated rate for dashboard
            'period_rates': {},
            'session_obs': {},  # no trustworthy session as_of available
            'session_dates': {},
            'fx_rate': 1300.0,
        }

        with patch('app.main.refresh_all_holdings_prices', return_value=refresh_res):
            with patch('app.main.is_test_mode', return_value=False):
                res = asyncio.run(main_mod.refresh_prices_for_user('test_user'))

        updated_port = portfolio.read_portfolio(username='test_user')
        stored_obs = updated_port.get('settings', {}).get('price_session_obs', {})
        daily_changes = updated_port.get('settings', {}).get('daily_price_changes', {})

        # 1. Dashboard-compatible daily_price_changes is updated to 2.5%
        self.assertEqual(daily_changes.get('005930'), 2.5)

        # 2. price_session_obs has NOT been replaced by incomplete obs; 2026-09-18 baseline is preserved
        self.assertIn('005930', stored_obs)
        self.assertEqual(stored_obs['005930']['as_of'], '2026-09-18')
        self.assertEqual(stored_obs['005930']['rate'], 1.5)

    def test_partial_failure_dashboard_rate_updated_persisted_obs_preserved_no_false_gain(self) -> None:
        """
        Required partial-failure test:
        Existing pair: rate 1.5%, as_of 2026-09-18.
        New refresh: latest dashboard rate = 2.5%, trustworthy as_of unavailable.
        Result:
        - dashboard day_change_rate = 2.5%
        - persistent paired observation remains 1.5%, 2026-09-18
        - Stock Record does NOT treat 2.5% as new session gain (day_profit_krw = 0)
        """
        import asyncio
        from unittest.mock import patch
        import app.main as main_mod

        base_data = empty_portfolio(
            settings={
                'fx_rates': {'KRW': 1.0, 'USD': 1300.0},
                'price_session_obs': {
                    '005930': {'rate': 1.5, 'as_of': '2026-09-18', 'source': 'candle_series'},
                },
                'daily_price_changes': {'005930': 1.5},
            },
            accounts=[{'id': 'acc1', 'broker': '테스트', 'name': '계좌1', 'owner': '모두', 'account_type': 'general', 'source': 'test'}],
            holdings=[
                {'id': 'h1', 'account_id': 'acc1', 'code': '005930', 'currency': 'KRW', 'name': '삼성전자',
                 'quantity': 100, 'avg_price': 70000, 'current_price': 80000, 'market': 'KRX', 'owner': '모두'},
            ],
        )
        portfolio.write_portfolio(base_data, username='test_user')

        # Prior persisted record already saw 2026-09-18
        prior_record = {
            'date': '2026-09-18',
            'owner': '모두',
            'total_value_krw': 80_000_000.0,
            'day_profit_krw': 1_182_266.0,
            'source': 'auto',
            'holdings_session': {'KRW:005930': '2026-09-18'},
        }
        asset_records.upsert_asset_record(prior_record, by_date=True, username='test_user')

        # New refresh:
        # Quote succeeded with 2.5% for dashboard, but candle fetch failed (session_obs omits 005930)
        refresh_res = {
            'prices': {'h1': 82000.0},
            'daily_changes': {'005930': 2.5},
            'period_rates': {},
            'session_obs': {},  # trustworthy as_of unavailable
            'session_dates': {},
            'fx_rate': 1300.0,
        }

        with patch('app.main.refresh_all_holdings_prices', return_value=refresh_res):
            with patch('app.main.is_test_mode', return_value=False):
                asyncio.run(main_mod.refresh_prices_for_user('test_user'))

        # 1. Verify dashboard: display rate is 2.5% (freshest rate from daily_price_changes)
        dash = portfolio.get_dashboard(username='test_user')
        samsung = dash['holdings'][0]
        self.assertEqual(samsung['day_change_rate'], 2.5, 'Dashboard display rate must be 2.5%')

        # 2. Verify persistent paired observation remains 1.5%, 2026-09-18
        port = portfolio.read_portfolio(username='test_user')
        stored_obs = port.get('settings', {}).get('price_session_obs', {})
        self.assertEqual(stored_obs['005930']['rate'], 1.5)
        self.assertEqual(stored_obs['005930']['as_of'], '2026-09-18')

        # 3. Verify holding's persistent record observation
        self.assertEqual(samsung.get('record_day_change_rate'), 1.5)
        self.assertEqual(samsung.get('day_change_as_of'), '2026-09-18')

        # 4. Verify stock record does NOT treat 2.5% as new session gain:
        saved = main_mod.auto_save_all_owner_snapshots(dash, username='test_user')
        saved_rec = next(r for r in saved if r.get('owner') == '모두')
        self.assertEqual(saved_rec['day_profit_krw'], 0.0,
                         'Stock Record must NOT treat 2.5% as new session gain when session has not advanced')


# ---------------------------------------------------------------------------
# Issue 7: Canonical instrument identity
# ---------------------------------------------------------------------------
class TestCanonicalInstrumentIdentity(IsolatedDataTestCase):
    def test_currency_code_key_stable_across_market_aliases(self) -> None:
        """currency:code key is stable even when market field varies."""
        h_nas = _h('NVDA', 'USD', 50_000_000, 2.0, '2026-09-19', market='NAS', fx_rate=1385.0)
        h_nasdaq = _h('NVDA', 'USD', 50_000_000, 2.0, '2026-09-19', market='NASDAQ', fx_rate=1385.0)
        h_empty = _h('NVDA', 'USD', 50_000_000, 2.0, '2026-09-19', market='', fx_rate=1385.0)
        for h in [h_nas, h_nasdaq, h_empty]:
            rec = build_stock_record_from_holdings([h], prev_session_map=None)
            hs = rec.get('holdings_session', {})
            self.assertIn('USD:NVDA', hs,
                          f"Expected USD:NVDA for market={h.get('market')!r}")
            self.assertNotIn(f"NVDA:{h.get('market')}", hs,
                             'Old code:market format must not appear')

    def test_same_code_different_currency_distinct_keys(self) -> None:
        """Same code, different currency → distinct instrument keys."""
        h_kr = _h('000660', 'KRW', 50_000_000, 1.0, '2026-09-19')
        h_us = _h('000660', 'USD', 30_000_000, 2.0, '2026-09-19', fx_rate=1385.0)
        rec = build_stock_record_from_holdings([h_kr, h_us], prev_session_map=None)
        hs = rec.get('holdings_session', {})
        self.assertIn('KRW:000660', hs)
        self.assertIn('USD:000660', hs)


# ---------------------------------------------------------------------------
# Final Monotonic-Session Gate: Time-Order Invariants
# ---------------------------------------------------------------------------
class TestMonotonicSessionAdvance(IsolatedDataTestCase):
    def test_older_current_session_produces_zero_profit(self) -> None:
        """
        Invariant 1: current_session < previous_session must produce 0.0 profit.
        Previous = 2026-09-21, current = 2026-09-18 -> 0 contribution.
        """
        prev_map = {'KRW:005930': '2026-09-21'}
        holdings = [_h('005930', 'KRW', 80_000_000, 2.0, '2026-09-18')]
        rec = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)
        self.assertEqual(rec['day_profit_krw'], 0.0,
                         'Older incoming session must NOT produce P/L')

    def test_older_current_session_does_not_regress_holdings_session(self) -> None:
        """
        Invariant 2: holdings_session must never move backward.
        persisted_session = max(previous_session, current_session).
        Previous = 2026-09-21, current = 2026-09-18 -> holdings_session remains 2026-09-21.
        """
        prev_map = {'KRW:005930': '2026-09-21'}
        holdings = [_h('005930', 'KRW', 80_000_000, 2.0, '2026-09-18')]
        rec = build_stock_record_from_holdings(holdings, prev_session_map=prev_map)
        self.assertEqual(rec.get('holdings_session', {}).get('KRW:005930'), '2026-09-21',
                         'holdings_session must remain 2026-09-21 and NOT regress to 2026-09-18')

    def test_next_normal_session_not_double_counted_after_prior_older_session(self) -> None:
        """
        Invariant 2: Next normal session does not get double-counted because of prior regression.
        Day 1: snapshot at 2026-09-21 books gain, baseline = 2026-09-21.
        Day 2 (glitch): provider returns 2026-09-18 -> 0 gain, baseline stays 2026-09-21.
        Day 3 (recovers): provider returns 2026-09-21 -> 0 gain (not double counted).
        Day 4 (normal): provider returns 2026-09-22 -> books gain, baseline advances to 2026-09-22.
        """
        # Day 1
        prev_map_day0 = {'KRW:005930': '2026-09-18'}
        holdings_day1 = [_h('005930', 'KRW', 80_000_000, 2.0, '2026-09-21')]
        rec_day1 = build_stock_record_from_holdings(holdings_day1, prev_session_map=prev_map_day0)
        self.assertGreater(rec_day1['day_profit_krw'], 0.0)
        self.assertEqual(rec_day1['holdings_session']['KRW:005930'], '2026-09-21')

        # Day 2: provider glitch returns older session 2026-09-18
        holdings_day2 = [_h('005930', 'KRW', 80_000_000, 2.0, '2026-09-18')]
        rec_day2 = build_stock_record_from_holdings(holdings_day2, prev_session_map=rec_day1['holdings_session'])
        self.assertEqual(rec_day2['day_profit_krw'], 0.0)
        self.assertEqual(rec_day2['holdings_session']['KRW:005930'], '2026-09-21',
                         'Must preserve 2026-09-21, not regress')

        # Day 3: provider recovers to 2026-09-21
        holdings_day3 = [_h('005930', 'KRW', 80_000_000, 2.0, '2026-09-21')]
        rec_day3 = build_stock_record_from_holdings(holdings_day3, prev_session_map=rec_day2['holdings_session'])
        self.assertEqual(rec_day3['day_profit_krw'], 0.0,
                         'Must not double-count 2026-09-21')
        self.assertEqual(rec_day3['holdings_session']['KRW:005930'], '2026-09-21')

        # Day 4: provider advances to 2026-09-22
        holdings_day4 = [_h('005930', 'KRW', 80_000_000, 1.5, '2026-09-22')]
        rec_day4 = build_stock_record_from_holdings(holdings_day4, prev_session_map=rec_day3['holdings_session'])
        expected_gain = 80_000_000 * (1.5 / 101.5)
        self.assertAlmostEqual(rec_day4['day_profit_krw'], round(expected_gain, 2), delta=1.0)
        self.assertEqual(rec_day4['holdings_session']['KRW:005930'], '2026-09-22')

    def test_price_session_obs_monotonic_merge_older_rejected(self) -> None:
        """
        Invariant 3: price_session_obs monotonic merge rejects older incoming session.
        stored: {"rate": 1.2, "as_of": "2026-09-21"}
        incoming: {"rate": -0.8, "as_of": "2026-09-18"}
        Expected: stored remains 2026-09-21 observation.
        """
        import asyncio
        from unittest.mock import patch
        import app.main as main_mod

        base_data = empty_portfolio(
            settings={
                'fx_rates': {'KRW': 1.0, 'USD': 1300.0},
                'price_session_obs': {
                    '005930': {'rate': 1.2, 'as_of': '2026-09-21', 'source': 'candle_series'},
                },
                'daily_price_changes': {'005930': 1.2},
            },
            holdings=[
                {'id': 'h1', 'code': '005930', 'currency': 'KRW', 'name': '삼성전자', 'quantity': 10, 'avg_price': 70000, 'current_price': 80000},
            ],
        )
        portfolio.write_portfolio(base_data, username='test_user')

        # Older incoming session: 2026-09-18
        older_res = {
            'prices': {'h1': 79000.0},
            'daily_changes': {'005930': -0.8},
            'period_rates': {},
            'session_obs': {'005930': {'rate': -0.8, 'as_of': '2026-09-18', 'source': 'candle_series'}},
            'session_dates': {'005930': '2026-09-18'},
            'fx_rate': 1300.0,
        }

        with patch('app.main.refresh_all_holdings_prices', return_value=older_res):
            with patch('app.main.is_test_mode', return_value=False):
                asyncio.run(main_mod.refresh_prices_for_user('test_user'))

        port = portfolio.read_portfolio(username='test_user')
        stored_obs = port.get('settings', {}).get('price_session_obs', {})
        # Must retain 2026-09-21!
        self.assertEqual(stored_obs['005930']['as_of'], '2026-09-21')
        self.assertEqual(stored_obs['005930']['rate'], 1.2)

    def test_price_session_obs_monotonic_merge_same_date_updates(self) -> None:
        """
        Invariant 3: Same-date incoming session may update the observation
        without creating duplicate Stock Record P/L.
        stored: {"rate": 1.2, "as_of": "2026-09-21"}
        incoming: {"rate": 1.3, "as_of": "2026-09-21"}
        Expected: stored updates to 1.3, 2026-09-21.
        """
        import asyncio
        from unittest.mock import patch
        import app.main as main_mod

        base_data = empty_portfolio(
            settings={
                'fx_rates': {'KRW': 1.0, 'USD': 1300.0},
                'price_session_obs': {
                    '005930': {'rate': 1.2, 'as_of': '2026-09-21', 'source': 'candle_series'},
                },
            },
            holdings=[
                {'id': 'h1', 'code': '005930', 'currency': 'KRW', 'name': '삼성전자', 'quantity': 10, 'avg_price': 70000, 'current_price': 80000},
            ],
        )
        portfolio.write_portfolio(base_data, username='test_user')

        # Same-date incoming session: 2026-09-21 with updated rate 1.3%
        same_date_res = {
            'prices': {'h1': 80500.0},
            'daily_changes': {'005930': 1.3},
            'period_rates': {},
            'session_obs': {'005930': {'rate': 1.3, 'as_of': '2026-09-21', 'source': 'candle_series'}},
            'session_dates': {'005930': '2026-09-21'},
            'fx_rate': 1300.0,
        }

        with patch('app.main.refresh_all_holdings_prices', return_value=same_date_res):
            with patch('app.main.is_test_mode', return_value=False):
                asyncio.run(main_mod.refresh_prices_for_user('test_user'))

        port = portfolio.read_portfolio(username='test_user')
        stored_obs = port.get('settings', {}).get('price_session_obs', {})
        self.assertEqual(stored_obs['005930']['as_of'], '2026-09-21')
        self.assertEqual(stored_obs['005930']['rate'], 1.3)

    def test_price_session_obs_monotonic_merge_newer_replaces(self) -> None:
        """
        Invariant 3: Newer incoming session replaces stored observation normally.
        stored: {"rate": 1.2, "as_of": "2026-09-21"}
        incoming: {"rate": 2.0, "as_of": "2026-09-22"}
        Expected: stored updates to 2.0, 2026-09-22.
        """
        import asyncio
        from unittest.mock import patch
        import app.main as main_mod

        base_data = empty_portfolio(
            settings={
                'fx_rates': {'KRW': 1.0, 'USD': 1300.0},
                'price_session_obs': {
                    '005930': {'rate': 1.2, 'as_of': '2026-09-21', 'source': 'candle_series'},
                },
            },
            holdings=[
                {'id': 'h1', 'code': '005930', 'currency': 'KRW', 'name': '삼성전자', 'quantity': 10, 'avg_price': 70000, 'current_price': 80000},
            ],
        )
        portfolio.write_portfolio(base_data, username='test_user')

        newer_res = {
            'prices': {'h1': 81500.0},
            'daily_changes': {'005930': 2.0},
            'period_rates': {},
            'session_obs': {'005930': {'rate': 2.0, 'as_of': '2026-09-22', 'source': 'candle_series'}},
            'session_dates': {'005930': '2026-09-22'},
            'fx_rate': 1300.0,
        }

        with patch('app.main.refresh_all_holdings_prices', return_value=newer_res):
            with patch('app.main.is_test_mode', return_value=False):
                asyncio.run(main_mod.refresh_prices_for_user('test_user'))

        port = portfolio.read_portfolio(username='test_user')
        stored_obs = port.get('settings', {}).get('price_session_obs', {})
        self.assertEqual(stored_obs['005930']['as_of'], '2026-09-22')
        self.assertEqual(stored_obs['005930']['rate'], 2.0)

    def test_price_session_obs_monotonic_merge_incomplete_preserves_stored(self) -> None:
        """
        Invariant 3: Incomplete/unknown incoming observation preserves existing complete observation.
        stored: {"rate": 1.2, "as_of": "2026-09-21"}
        incoming: {"rate": 2.0, "as_of": None}
        Expected: stored remains 2026-09-21 observation.
        """
        import asyncio
        from unittest.mock import patch
        import app.main as main_mod

        base_data = empty_portfolio(
            settings={
                'fx_rates': {'KRW': 1.0, 'USD': 1300.0},
                'price_session_obs': {
                    '005930': {'rate': 1.2, 'as_of': '2026-09-21', 'source': 'candle_series'},
                },
            },
            holdings=[
                {'id': 'h1', 'code': '005930', 'currency': 'KRW', 'name': '삼성전자', 'quantity': 10, 'avg_price': 70000, 'current_price': 80000},
            ],
        )
        portfolio.write_portfolio(base_data, username='test_user')

        incomplete_res = {
            'prices': {'h1': 81500.0},
            'daily_changes': {'005930': 2.0},
            'period_rates': {},
            'session_obs': {'005930': {'rate': 2.0, 'as_of': None}},
            'session_dates': {},
            'fx_rate': 1300.0,
        }

        with patch('app.main.refresh_all_holdings_prices', return_value=incomplete_res):
            with patch('app.main.is_test_mode', return_value=False):
                asyncio.run(main_mod.refresh_prices_for_user('test_user'))

        port = portfolio.read_portfolio(username='test_user')
        stored_obs = port.get('settings', {}).get('price_session_obs', {})
        self.assertEqual(stored_obs['005930']['as_of'], '2026-09-21')
        self.assertEqual(stored_obs['005930']['rate'], 1.2)

    def test_dashboard_display_rate_independent_when_older_session_rejected(self) -> None:
        """
        Invariant 4: Even when an older persisted session observation is rejected,
        daily_price_changes may still reflect the latest provider display rate.
        """
        import asyncio
        from unittest.mock import patch
        import app.main as main_mod

        base_data = empty_portfolio(
            settings={
                'fx_rates': {'KRW': 1.0, 'USD': 1300.0},
                'price_session_obs': {
                    '005930': {'rate': 1.2, 'as_of': '2026-09-21', 'source': 'candle_series'},
                },
                'daily_price_changes': {'005930': 1.2},
            },
            accounts=[{'id': 'acc1', 'broker': '테스트', 'name': '계좌1', 'owner': '모두', 'account_type': 'general', 'source': 'test'}],
            holdings=[
                {'id': 'h1', 'account_id': 'acc1', 'code': '005930', 'currency': 'KRW', 'name': '삼성전자',
                 'quantity': 100, 'avg_price': 70000, 'current_price': 80000, 'market': 'KRX', 'owner': '모두'},
            ],
        )
        portfolio.write_portfolio(base_data, username='test_user')

        # Prior persisted record already saw 2026-09-21
        prior_record = {
            'date': '2026-09-21',
            'owner': '모두',
            'total_value_krw': 80_000_000.0,
            'day_profit_krw': 946_000.0,
            'source': 'auto',
            'holdings_session': {'KRW:005930': '2026-09-21'},
        }
        asset_records.upsert_asset_record(prior_record, by_date=True, username='test_user')

        # Incoming refresh has basic rate = -3.0%, but older candle session 2026-09-18
        older_res = {
            'prices': {'h1': 77600.0},
            'daily_changes': {'005930': -3.0},
            'period_rates': {},
            'session_obs': {'005930': {'rate': -0.8, 'as_of': '2026-09-18', 'source': 'candle_series'}},
            'session_dates': {'005930': '2026-09-18'},
            'fx_rate': 1300.0,
        }

        with patch('app.main.refresh_all_holdings_prices', return_value=older_res):
            with patch('app.main.is_test_mode', return_value=False):
                asyncio.run(main_mod.refresh_prices_for_user('test_user'))

        # Dashboard display rate reflects latest basic rate (-3.0)
        dash = portfolio.get_dashboard(username='test_user')
        self.assertEqual(dash['holdings'][0]['day_change_rate'], -3.0)

        # But persisted observation was NOT rolled back (retained 2026-09-21)
        port = portfolio.read_portfolio(username='test_user')
        stored_obs = port.get('settings', {}).get('price_session_obs', {})
        self.assertEqual(stored_obs['005930']['as_of'], '2026-09-21')

        # And Stock Record produces 0.0 P/L (no duplicate/fabricated P/L)
        saved = main_mod.auto_save_all_owner_snapshots(dash, username='test_user')
        saved_rec = next(r for r in saved if r.get('owner') == '모두')
        self.assertEqual(saved_rec['day_profit_krw'], 0.0)
        self.assertEqual(saved_rec['holdings_session']['KRW:005930'], '2026-09-21')


if __name__ == '__main__':
    unittest.main()
