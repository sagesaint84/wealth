from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from app.services import planning, portfolio
from regression_support import IsolatedDataTestCase, empty_portfolio


class ManualHistoryTests(IsolatedDataTestCase):
    def setUp(self):
        super().setUp()
        portfolio.write_portfolio(empty_portfolio(), 'A')
        portfolio.write_portfolio(empty_portfolio(), 'B')

    def add(self, day='2001-03-02', owner='모두', net=-500, memo='가상 메모', user='A'):
        return planning.mutate(user,'snapshot-manual',dict(revision=planning.read_planning(user)['revision'],date=day,owner=owner,net_worth=net,memo=memo))

    def test_manual_past_negative_and_memo_without_inventing_breakdown(self):
        before=portfolio.read_portfolio('A')
        record=self.add()['history'][0]
        self.assertEqual((record['date'],record['net_worth'],record['memo']),('2001-03-02',-500,'가상 메모'))
        self.assertEqual(record['source'],'manual')
        self.assertIsNone(record['assets']);self.assertIsNone(record['debt'])
        self.assertEqual(record['fx_rates'],{});self.assertEqual(record['valuation_at'],'')
        after=portfolio.read_portfolio('A');after['settings'].pop('wealth_planning')
        self.assertEqual(after,before)

    def test_today_and_zero_are_allowed(self):
        today=datetime.now(timezone(timedelta(hours=9))).date().isoformat()
        self.assertEqual(self.add(today,net=0,memo='')['history'][0]['net_worth'],0)

    def test_future_and_invalid_dates_do_not_write(self):
        future=(datetime.now(timezone(timedelta(hours=9))).date()+timedelta(days=1)).isoformat()
        before=portfolio._get_portfolio_file('A').read_bytes()
        for day in (future,'2025-02-30','20010302','2001-W09-5','',None):
            with self.subTest(day=day),self.assertRaises(ValueError):self.add(day)
            self.assertEqual(portfolio._get_portfolio_file('A').read_bytes(),before)

    def test_nonfinite_and_bad_memo_rejected(self):
        for value in (float('nan'),float('inf'),float('-inf'),True,'not a number'):
            with self.subTest(value=value),self.assertRaises(ValueError):self.add(net=value)
        for memo in ('x'*1001,{},None):
            with self.assertRaises(ValueError):self.add(memo=memo)
        self.assertEqual(planning.read_planning('A')['revision'],0)

    def test_duplicate_does_not_replace_even_with_replace_flag(self):
        self.add()
        before=portfolio._get_portfolio_file('A').read_bytes()
        with self.assertRaises(planning.PlanningConflict):
            planning.mutate('A','snapshot-manual',dict(revision=1,date='2001-03-02',owner='모두',net_worth=999,replace=True))
        self.assertEqual(portfolio._get_portfolio_file('A').read_bytes(),before)

    def test_owner_and_user_isolation(self):
        for owner in ('모두','아빠','엄마','자녀','공동명의'):self.add(owner=owner)
        self.assertEqual(len(planning.read_planning('A')['history']),5)
        self.assertEqual(planning.read_planning('B')['history'],[])
        self.add(user='B',net=100)
        self.assertEqual(planning.read_planning('B')['history'][0]['net_worth'],100)
        self.assertTrue(all(r['net_worth']==-500 for r in planning.read_planning('A')['history']))

    def test_manual_edit_date_amount_memo_and_sort(self):
        self.add('2001-03-02');self.add('2001-02-01')
        result=planning.mutate('A','snapshot-edit',dict(revision=2,date='2001-03-02',new_date='2001-01-01',owner='모두',net_worth=-700,memo='수정된 가상 메모',confirm=True))
        self.assertEqual([r['date'] for r in result['history']],['2001-01-01','2001-02-01'])
        record=result['history'][0]
        self.assertEqual(record['net_worth'],-700);self.assertEqual(record['memo'],'수정된 가상 메모')
        self.assertEqual(record['source'],'manual');self.assertIsNone(record['assets'])

    def test_edit_collision_and_future_leave_records_unchanged(self):
        self.add('2001-03-02');self.add('2001-02-01')
        before=portfolio._get_portfolio_file('A').read_bytes()
        for day in ('2001-02-01','9999-12-31'):
            with self.assertRaises(ValueError):
                planning.mutate('A','snapshot-edit',dict(revision=2,date='2001-03-02',new_date=day,owner='모두',net_worth=1,confirm=True))
            self.assertEqual(portfolio._get_portfolio_file('A').read_bytes(),before)

    def test_today_snapshot_and_manual_share_sorted_history(self):
        self.add()
        result=planning.mutate('A','snapshot',dict(revision=1,owner='모두',assets=150,debt=50,net_worth=100))
        self.assertEqual([r['source'] for r in result['history']],['manual','user_confirmed'])
        with self.assertRaises(planning.PlanningConflict):self.add(result['history'][-1]['date'])

    def test_snapshot_date_and_memo_edit_keeps_breakdown(self):
        record=planning.mutate('A','snapshot',dict(revision=0,owner='모두',assets=150,debt=50,net_worth=100))['history'][0]
        result=planning.mutate('A','snapshot-edit',dict(revision=1,date=record['date'],new_date='2001-02-03',owner='모두',assets=160,debt=50,net_worth=110,memo='확인',confirm=True))
        self.assertEqual(result['history'][0]['date'],'2001-02-03')
        self.assertEqual(result['history'][0]['assets'],160)

    def test_delete_to_empty_and_stale_mutation(self):
        self.add()
        with self.assertRaises(planning.PlanningConflict):
            planning.mutate('A','snapshot-delete',dict(revision=0,date='2001-03-02',owner='모두',confirm=True))
        result=planning.mutate('A','snapshot-delete',dict(revision=1,date='2001-03-02',owner='모두',confirm=True))
        self.assertEqual(result['history'],[])

    def test_roundtrip_preserves_manual_nulls_and_memo(self):
        self.add(memo='<synthetic> & memo')
        backup=json.loads(json.dumps(portfolio.read_portfolio('A')))
        portfolio.write_portfolio(deepcopy(backup),'B',replace_planning=True)
        self.assertEqual(planning.read_planning('A'),planning.read_planning('B'))
