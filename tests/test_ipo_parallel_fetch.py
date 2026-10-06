"""Controlled concurrency regressions; events/barriers prove overlap, not clocks."""
import copy
from datetime import datetime
import json
import threading
from unittest.mock import Mock, patch

import pytest

from app.services.ipo import source_discovery as sd, refresh_adapter
from app.services.ipo import dart_offering_schedule
from tests.test_ipo_alice_metalogos_acceptance import alice, parsed
from tests.test_ipo_source_discovery import _DartOn


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 6, 21, tzinfo=tz)


class AliceDart(_DartOn):
    def get_corp_code_master(self):
        return [{'corp_name': '엘리스그룹', 'corp_code': '01000001', 'stock_code': '0158S0'}]

    def get_filing_list(self, **kwargs):
        result = super().get_filing_list(**kwargs)
        result['list'][0].update(corp_name='엘리스그룹', stock_code='0158S0')
        return result

    def get_equity_registration_statements(self, **kwargs):
        result = super().get_equity_registration_statements(**kwargs)
        result['group'][0]['list'][0]['corp_name'] = '엘리스그룹'
        return result


def run_discovery(market, *, dart=None, metalogos=None):
    kind, npay, naver = Mock(), Mock(), Mock()
    kind.fetch_pubofr_schedule_items.return_value = []
    npay.fetch_upcoming_ipos.return_value = []
    naver.fetch_ipo_discovery_items.return_value = []
    if metalogos is None:
        metalogos = Mock()
        metalogos.fetch_company_items.return_value = [parsed()]
    if dart is None:
        dart = AliceDart()
    caller = threading.get_ident()
    saved = []
    merges = []
    original = sd._apply_observation

    def merge(*args, **kwargs):
        assert threading.get_ident() == caller
        merges.append(kwargs['source_name'])
        return original(*args, **kwargs)

    def write(value):
        assert threading.get_ident() == caller
        saved.append(copy.deepcopy(value))

    before = copy.deepcopy(market)
    with patch.object(sd, 'read_market_store', return_value=market), \
         patch.object(sd, 'write_market_store', side_effect=write), \
         patch.object(sd, '_apply_observation', side_effect=merge), \
         patch.object(sd, 'datetime', FixedDatetime), \
         patch.object(dart_offering_schedule, 'datetime', FixedDatetime):
        result = sd.discover_and_merge_primary_sources(
            username='test-user', target_date_str='2026-10-06', kind_client=kind,
            npay_client=npay, naver_client=naver, metalogos_client=metalogos, dart_client=dart)
    assert market == before  # provider/reconciliation cannot mutate the input store
    assert len(saved) == 1
    return result, saved[0], merges


def test_provider_overlap_completion_order_cannot_change_serialized_market_or_score():
    outputs = []
    for first in ('metalogos', 'dart'):
        barrier = threading.Barrier(2)
        completed = threading.Event()
        completion_order = []
        original_m = sd._fetch_metalogos_candidates
        original_d = sd._fetch_dart_schedules
        original_read = sd._provider_read

        def stage(name, read, *args, **kwargs):
            barrier.wait(timeout=5)  # both stages are in-flight simultaneously
            if name != first:
                assert completed.wait(timeout=5)
            return read(*args, **kwargs)

        def observed_read(read):
            result = original_read(read)
            assert result['error'] is None
            name = 'metalogos' if isinstance(result['data'], list) else 'dart'
            completion_order.append(name)
            if name == first:
                completed.set()
            return result

        target = alice()
        with patch.object(sd, '_fetch_metalogos_candidates',
                          side_effect=lambda *a, **kw: stage('metalogos', original_m, *a, **kw)), \
             patch.object(sd, '_fetch_dart_schedules',
                          side_effect=lambda *a, **kw: stage('dart', original_d, *a, **kw)), \
             patch.object(sd, '_provider_read', side_effect=observed_read):
            result, saved, merges = run_discovery({'ipos': [target]})
        assert completion_order == [first, 'dart' if first == 'metalogos' else 'metalogos']
        assert merges == ['metalogos160', 'dart']
        row = saved['ipos'][0]
        assert row['final_offer_price'] == 24000  # official structured DART fixture wins
        assert row['sources']['dart_schedule']['offer_price_confirmed'] is True
        assert row['sources']['dart_schedule']['structured_offer_price_reference'] == 24000
        assert row['sources']['metalogos160']['attractiveness_score'] == 79
        assert row['features'] == target['features']
        assert row['score']['score'] != 79
        assert result['metalogos_rows'][0]['sources']['metalogos160']['url'].endswith('B202605261')
        assert {'kind_discovery_ms', 'npay_discovery_ms', 'naver_discovery_ms',
                'metalogos_discovery_ms', 'dart_schedule_ms',
                'primary_provider_parallel_wall_ms'} <= result['timings'].keys()
        assert all(value >= 0 for value in result['timings'].values())
        outputs.append(json.dumps(saved, ensure_ascii=False, sort_keys=True))
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize('failed_provider', ['metalogos', 'dart'])
def test_provider_failure_keeps_other_provider_results(failed_provider):
    metalogos = Mock()
    metalogos.fetch_company_items.return_value = [parsed()]
    dart = AliceDart()
    if failed_provider == 'metalogos':
        metalogos.fetch_company_items.side_effect = RuntimeError('provider unavailable')
        result, saved, _ = run_discovery({'ipos': [alice()]}, dart=dart, metalogos=metalogos)
        assert saved['ipos'][0]['final_offer_price'] == 24000
        assert result['statuses']['metalogos160'] == 'source_error (RuntimeError)'
    else:
        with patch.object(sd, '_fetch_dart_schedules', side_effect=RuntimeError('provider unavailable')):
            result, saved, _ = run_discovery({'ipos': [alice()]}, dart=dart, metalogos=metalogos)
        assert saved['ipos'][0]['final_offer_price'] == 90500
        assert result['statuses']['dart_schedule'] == 'source_error (RuntimeError)'
        assert saved['ipos'][0]['sources']['metalogos160']['attractiveness_score'] == 79


def test_dart_candidate_reads_bounded_ordered_isolated_and_master_loaded_once():
    barrier = threading.Barrier(3)
    lock = threading.Lock()
    release = [threading.Event() for _ in range(3)]
    release[2].set()
    active = peak = 0
    completed = []
    master_calls = []
    calls = []
    caller = threading.get_ident()
    market = {'ipos': [{'ipo_id': str(i), 'company_name': f'회사{i}',
                       'subscription_start': '2026-10-07', 'sources': {}} for i in range(6)]}
    before = copy.deepcopy(market)

    class Dart:
        def get_corp_code_master(self):
            master_calls.append(threading.get_ident())
            return [{'corp_name': f'회사{i}', 'corp_code': str(i), 'stock_code': 'DUPLICATE'}
                    for i in range(6)]

        def get_filing_list(self, *, corp_code, **kwargs):
            nonlocal active, peak
            assert threading.get_ident() != caller
            i = int(corp_code)
            with lock:
                active += 1
                peak = max(peak, active)
                calls.append((i, 'filing'))
            barrier.wait(timeout=5)
            if i < 3:
                assert release[i].wait(timeout=5)
            return {'list': [{'corp_code': corp_code, 'corp_name': f'회사{i}'}]}

        def get_equity_registration_statements(self, *, corp_code, **kwargs):
            nonlocal active
            i = int(corp_code)
            with lock:
                calls.append((i, 'structured'))
                completed.append(i)
                active -= 1
            if 0 < i < 3:
                release[i - 1].set()
            if i == 1:
                raise RuntimeError('one candidate fails')
            return {'candidate': i}

    dart = Dart()
    start, end = sd._month_window('2026-10-06')
    with patch.object(sd, 'select_dart_schedule_filing', side_effect=lambda filings, raw: filings[0]):
        reads = sd._fetch_dart_schedules(market, dart=dart, target_date_str='2026-10-06', start=start, end=end)
    assert market == before
    assert len(master_calls) == 1
    assert peak == sd.DART_CANDIDATE_WORKERS == 3
    assert completed[:3] == [2, 1, 0]
    assert [r['index'] for r in reads['candidates']] == list(range(6))
    assert reads['candidates'][1]['status'] == 'failed'
    for i in range(6):
        assert [kind for index, kind in calls if index == i] == ['filing', 'structured']
    applied = []

    def build(raw, *, filing):
        assert threading.get_ident() == caller
        i = raw['candidate']
        applied.append(i)
        return {'company_name': f'회사{i}', 'subscription_start': '2026-10-07',
                'final_offer_price': 1000 + i, 'sources': {'dart_schedule': {}}}

    with patch.object(sd, 'build_dart_offering_schedule', side_effect=build):
        assert sd._apply_dart_schedules(market, dart=dart, target_date_str='2026-10-06',
                                       start=start, end=end, prefetched=reads) == (5, 1, 0)
    assert applied == [0, 2, 3, 4, 5]
    assert len(master_calls) == 1  # applying must not perform any new external read
    assert sum(row.get('stock_code') == 'DUPLICATE' for row in market['ipos']) == 1
    for row in market['ipos'][1:]:
        assert row['sources']['dart_identity']['stock_code_conflict_ipo_id'] == '0'


def test_unconfigured_dart_never_fetches_and_wrong_metalogos_is_rejected():
    dart, metalogos = Mock(), Mock()
    dart.is_configured.return_value = False
    wrong = parsed()
    wrong['company_name'] = '다른회사'
    metalogos.fetch_company_items.return_value = [wrong]
    result, saved, _ = run_discovery({'ipos': [alice()]}, dart=dart, metalogos=metalogos)
    assert result['statuses']['dart_schedule'] == 'source_unavailable (api_key_missing)'
    assert result['metalogos_rows'] == []
    assert saved['ipos'][0]['final_offer_price'] is None
    dart.get_corp_code_master.assert_not_called()
    dart.get_filing_list.assert_not_called()
    dart.get_equity_registration_statements.assert_not_called()


def test_interactive_response_preserves_timing_fields_and_adds_parallel_wall():
    discovery_timings = {key: 1.0 for key in (
        'kind_discovery_ms', 'npay_discovery_ms', 'naver_discovery_ms',
        'metalogos_discovery_ms', 'dart_schedule_ms', 'primary_provider_parallel_wall_ms')}
    from contextlib import nullcontext
    with patch.object(refresh_adapter, '_BASE_REFRESH_MARKET', return_value={'status': 'ok'}), \
         patch.object(refresh_adapter._base, '_refresh_file_lock', return_value=nullcontext()), \
         patch.object(refresh_adapter, 'discover_and_merge_primary_sources',
                      return_value={'statuses': {}, 'timings': discovery_timings, 'metalogos_rows': []}), \
         patch.object(refresh_adapter, 'refresh_missing_metalogos_references', return_value={'status': 'ok'}) as reference, \
         patch.object(refresh_adapter, '_targeted_dart_enrichment', return_value={}) as recovery:
        result = refresh_adapter.refresh_ipo_market(target_date_str='2026-10-06')
    assert discovery_timings.keys() | {'base_refresh_ms', 'metalogos_reference_ms',
                                    'targeted_dart_ms', 'total_ms'} == result['timings'].keys()
    reference.assert_called_once_with(target_date_str='2026-10-06', prefetched_rows=[])
    assert recovery.call_args.kwargs['score_recovery_only'] is True
    assert recovery.call_args.kwargs['max_candidates'] == 4
