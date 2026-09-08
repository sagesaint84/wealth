from copy import deepcopy
import asyncio
import json
from unittest.mock import patch
from fastapi import HTTPException
from app.services import planning, portfolio
from regression_support import IsolatedDataTestCase, empty_portfolio, authenticated_request, import_main_without_loading_real_env


class PlanningTests(IsolatedDataTestCase):
    def setUp(self):
        super().setUp()
        self.pf = empty_portfolio(accounts=[{'id':'a','owner':'아빠'},{'id':'b','owner':'엄마'}],
                                  holdings=[{'id':'h1','account_id':'a','code':'FAKE'}, {'id':'h2','account_id':'b','code':'FAKE'}])
        portfolio.write_portfolio(deepcopy(self.pf), 'A')
        portfolio.write_portfolio(empty_portfolio(), 'B')

    def snapshot(self, **kwargs):
        return dict(revision=0, owner='모두', assets=150, debt=50, net_worth=100, fx_rates={'KRW':1,'USD':1300}, **kwargs)

    def test_history_is_user_isolated_and_keeps_valuation(self):
        before=portfolio.read_portfolio('A')
        result=planning.mutate('A','snapshot',self.snapshot())
        self.assertEqual(result['history'][0]['net_worth'],100)
        self.assertEqual(result['history'][0]['fx_rates']['USD'],1300)
        self.assertEqual(result['history'][0]['source'],'user_confirmed')
        self.assertEqual(planning.read_planning('B')['history'],[])
        after=portfolio.read_portfolio('A')
        after['settings'].pop('wealth_planning')
        self.assertEqual(after,before)

    def test_stale_financial_write_preserves_new_planning(self):
        stale = portfolio.read_portfolio('A')
        saved = planning.mutate('A', 'snapshot', self.snapshot())
        stale['accounts'][0]['name'] = 'Synthetic renamed account'
        portfolio.write_portfolio(stale, 'A')
        self.assertEqual(planning.read_planning('A'), saved)
        self.assertEqual(portfolio.read_portfolio('A')['accounts'][0]['name'], 'Synthetic renamed account')

    def test_explicit_restore_can_remove_planning(self):
        planning.mutate('A', 'snapshot', self.snapshot())
        portfolio.write_portfolio(deepcopy(self.pf), 'A', replace_planning=True)
        self.assertEqual(planning.read_planning('A'), planning.empty())

    def test_history_edit_preserves_identity_fx_and_financial_accounts(self):
        saved=planning.mutate('A','snapshot',self.snapshot())
        record=saved['history'][0]
        result=planning.mutate('A','snapshot-edit',dict(revision=1,date=record['date'],owner=record['owner'],assets=180,debt=40,net_worth=140,confirm=True))
        edited=result['history'][0]
        for field in ('date','owner','fx_rates','recorded_at','valuation_at'):
            self.assertEqual(edited[field],record[field])
        self.assertEqual(edited['net_worth'],140)
        self.assertEqual(edited['source'],'user_corrected')
        self.assertEqual(portfolio.read_portfolio('A')['accounts'],self.pf['accounts'])

    def test_history_delete_requires_confirmation_identity_and_revision(self):
        record=planning.mutate('A','snapshot',self.snapshot())['history'][0]
        valid=dict(revision=1,date=record['date'],owner=record['owner'],confirm=True)
        before=portfolio._get_portfolio_file('A').read_bytes()
        for extra in ({'confirm':False},{'revision':0},{'owner':'Other'},{'date':'1900-01-01'}):
            with self.assertRaises(ValueError): planning.mutate('A','snapshot-delete',{**valid,**extra})
            self.assertEqual(portfolio._get_portfolio_file('A').read_bytes(),before)
        result=planning.mutate('A','snapshot-delete',valid)
        self.assertEqual(result['history'],[])
        self.assertEqual(result['revision'],2)

    def test_history_edit_cannot_create_or_write_invalid_amount(self):
        record=planning.mutate('A','snapshot',self.snapshot())['history'][0]
        valid=dict(revision=1,date=record['date'],owner=record['owner'],assets=150,debt=50,net_worth=100,confirm=True)
        before=portfolio._get_portfolio_file('A').read_bytes()
        for extra in ({'date':'1900-01-01'},{'owner':'Other'},{'assets':-1},{'net_worth':float('nan')},{'net_worth':99},{'confirm':False}):
            with self.assertRaises(ValueError): planning.mutate('A','snapshot-edit',{**valid,**extra})
            self.assertEqual(portfolio._get_portfolio_file('A').read_bytes(),before)

    def test_daily_replace_requires_explicit_confirmation(self):
        planning.mutate('A','snapshot',self.snapshot())
        with self.assertRaises(planning.PlanningConflict):
            planning.mutate('A','snapshot',{**self.snapshot(),'revision':1})
        result=planning.mutate('A','snapshot',{**self.snapshot(),'revision':1,'replace':True,'assets':160,'net_worth':110})
        self.assertEqual(len(result['history']),1)
        self.assertEqual(result['history'][0]['net_worth'],110)

    def test_owner_records_are_separate_and_no_backfill(self):
        planning.mutate('A','snapshot',self.snapshot())
        result=planning.mutate('A','snapshot',{**self.snapshot(),'revision':1,'owner':'아빠','date':'2000-01-01'})
        self.assertEqual(len(result['history']),2)
        self.assertNotEqual(result['history'][0]['date'],'2000-01-01')

    def test_invalid_snapshots_do_not_write(self):
        path=portfolio._get_portfolio_file('A'); before=path.read_bytes()
        for change in ({'assets':float('nan')},{'debt':-1},{'net_worth':3},{'fx_rates':{'USD':float('inf')}},{'fx_rates':{'USD':0}}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                planning.mutate('A','snapshot',{**self.snapshot(),**change})
            self.assertEqual(path.read_bytes(),before)

    def test_bucket_assignments_distinguish_same_stock_across_accounts(self):
        payload={'revision':0,'buckets':[{'id':'growth','name':'가상 성장','target':60},{'id':'income','name':'가상 배당','target':40}],
                 'accounts':{'a':'growth'},'holdings':{'h1':'income','h2':''}}
        result=planning.mutate('A','buckets',payload)
        self.assertEqual(result['holdings'],{'h1':'income','h2':''})
        self.assertEqual(portfolio.read_portfolio('A')['holdings'],self.pf['holdings'])
        self.assertEqual(planning.read_planning('B')['buckets'],[])

    def test_bad_targets_references_and_stale_revisions_are_rejected(self):
        for payload in (
            {'revision':0,'buckets':[{'id':'x','name':'X','target':101}]},
            {'revision':0,'buckets':[{'id':'x','name':'X','target':60},{'id':'y','name':'Y','target':60}]},
            {'revision':0,'accounts':{'foreign':'x'}},
            {'revision':0,'holdings':{'h1':'missing'}},
            {'revision':1,'buckets':[]},
        ):
            with self.subTest(payload=payload),self.assertRaises(ValueError):
                planning.mutate('A','buckets',payload)
        self.assertEqual(planning.read_planning('A')['revision'],0)

    def test_portfolio_backup_roundtrip_preserves_planning(self):
        planning.mutate('A','snapshot',self.snapshot())
        main=import_main_without_loading_real_env()
        clean=main._sanitize_export_data(portfolio.read_portfolio('A'))
        portfolio.write_portfolio(json.loads(json.dumps(clean)), 'B')
        self.assertEqual(planning.read_planning('B'),planning.read_planning('A'))

    def test_failed_write_leaves_original_portfolio_untouched(self):
        from pathlib import Path
        before=portfolio._get_portfolio_file('A').read_bytes()
        with patch.object(Path,'replace',side_effect=OSError('fixture failure')):
            with self.assertRaises(OSError): planning.mutate('A','snapshot',self.snapshot())
        self.assertEqual(portfolio._get_portfolio_file('A').read_bytes(),before)

    def test_authenticated_route_ignores_payload_username(self):
        main=import_main_without_loading_real_env()
        request=authenticated_request('A')
        async def body(): return {**self.snapshot(),'username':'B'}
        request.json=body
        asyncio.run(main.save_planning('snapshot',request))
        self.assertEqual(planning.read_planning('B')['history'],[])
        request.state.username=None
        with self.assertRaises(HTTPException) as error:
            asyncio.run(main.get_planning(request))
        self.assertEqual(error.exception.status_code,401)
