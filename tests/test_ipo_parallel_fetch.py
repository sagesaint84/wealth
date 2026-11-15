"""Controlled concurrency regressions; events/barriers prove overlap, not clocks."""
import copy
import threading
from unittest.mock import patch


from app.services.ipo import source_discovery as sd


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
