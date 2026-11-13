import copy,json,tempfile,unittest
from datetime import date,timedelta
from pathlib import Path
from c3_watch_quality_audit_v1 import price_metrics,finance_metrics,audit,digest,sort_key,prior_reviews

def bars(day='2026-11-13'):
    end=date.fromisoformat(day)
    return [dict(date=str(end-timedelta(days=79-i)),open=100+i,high=104+i,low=99+i,close=102+i,volume=1000+i,turnover_krw=100000+i,segment=0,tradable=True) for i in range(80)]

def row(ticker,turnover=100):
    return dict(ticker=ticker,name='Synthetic '+ticker,close=181.,own_rs20=20.,rs_accel5=4.,turnover20=turnover,sector='TEST',
        financial=dict(confirmed=False,growth_observed=True,observed_positive=True,required_metrics_complete=True,statement={}),
        momentum_pass=True,liquidity_pass=True,sector_proxy_positive=True,range_review=dict(plans=[],best=None))

class WatchQualityTests(unittest.TestCase):
    def test_full_price_metrics_are_causal_and_reject_future_or_duplicate_bars(self):
        b=bars();m=price_metrics(b,'2026-11-13')
        self.assertAlmostEqual(m['ma']['20'],171.5);self.assertAlmostEqual(m['returns_pct']['5'],100*(181/176-1))
        with self.assertRaises(ValueError):price_metrics(b,'2026-11-12')
        with self.assertRaises(ValueError):price_metrics(b[:-1]+[b[-2]],'2026-11-12')
    def test_audit_cannot_certify_missing_net_income_interest_or_original_pit(self):
        x=row('000001');x['financial']['statement']=dict(revenue_krw=100,operating_profit_krw=20,liabilities_krw=30,equity_krw=70,assets_krw=100)
        q=finance_metrics(x);self.assertEqual(q['operating_margin_pct'],20);self.assertFalse(q['quality_certified'])
        self.assertIn('ORIGINAL_DOCUMENT_PIT',q['missing_quality_evidence']);self.assertIn('UNAVAILABLE',q['interest_coverage_status'])
    def test_entry_fit_can_be_rank_seventeen_without_changing_watch_top_two(self):
        pool=[row(f'{i:06}',100-i) for i in range(1,19)];before=copy.deepcopy(pool)
        result=audit(pool,{r['ticker']:bars() for r in pool},pool,[pool[16]],'2026-11-13')
        self.assertEqual(result['watch_top2'],['000001','000002']);self.assertEqual(result['entry_fit_top2'],['000017'])
        self.assertEqual(result['observations']['000017']['quality_pool_rank'],17);self.assertEqual(pool,before)
        self.assertEqual(result['adjacent_rank_decisions'][0]['first_deciding_sort_field'],'turnover20')
    def test_previous_candidates_never_receive_a_rank_advantage(self):
        a,b,c=row('000001',20),row('000002',10),row('000003',30);pool=sorted([a,b,c],key=sort_key)
        prior=dict(source_date='2026-11-12',generated_at='2026-11-13T00:00:00Z',source_run_id='OLD',report_payload_sha256='old',watch_top2=[dict(ticker=a['ticker'],name=a['name'],rank=1,close=180.)])
        r=audit([a,b,c],{x['ticker']:bars() for x in [a,b,c]},pool,[],'2026-11-13',[prior])
        self.assertEqual(r['watch_top2'],['000003','000001']);self.assertEqual(r['observations']['000001']['watch_rank_change'],-1)
        self.assertFalse(r['reused_previous_candidates'])
    def test_unknown_financials_are_unknown_not_a_certified_bad_company(self):
        x=row('000001');x['financial']=dict(confirmed=False,observed_positive=False,required_metrics_complete=False)
        r=audit([x],{x['ticker']:bars()},[],[],'2026-11-13');self.assertEqual(r['observations'][x['ticker']]['watch_fail_reasons'],['FINANCIAL_UNKNOWN'])
    def test_prior_review_hash_is_required_and_same_day_is_not_yesterday(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'reports/c3_new_session_v1/reviews/2026-11-12/a.json';p.parent.mkdir(parents=True)
            r=dict(source_date='2026-11-12',selection_status='RESEARCH_ANALYSIS_COMPLETE');r['report_payload_sha256']=digest(r);p.write_text(json.dumps(r))
            self.assertEqual(len(prior_reviews(root,'2026-11-13')),1)
            r['source_date']='2026-11-11';p.write_text(json.dumps(r))
            with self.assertRaises(ValueError):prior_reviews(root,'2026-11-13')
        with self.assertRaises(ValueError):audit([],{},[],[],'2026-11-13',[dict(source_date='2026-11-13')])
    def test_frozen_entry_models_keep_signal_prices_and_apply_gap_stop_conservatively(self):
        from c3_entry_timing_audit_v1 import execute
        bs=bars();sessions=[b['date'] for b in bs];i=40;p=dict(low=130,high=135,stop=125,resistance=170,resistance2=190,reference_close=bs[i]['close'])
        before=copy.deepcopy(p);r=execute('CONDITIONAL_NEXT_OPEN',p,bs,i,sessions,5,sessions[-1])
        self.assertTrue(r['filled']);self.assertEqual(r['entry_price'],bs[i+1]['open']);self.assertEqual(p,before)
        bs[i+1].update(open=124,low=120,close=124)
        r=execute('CONDITIONAL_NEXT_OPEN',p,bs,i,sessions,5,sessions[-1]);self.assertEqual(r['status'],'CANCEL_GAP_BELOW_STOP');self.assertFalse(r['filled'])
    def test_ma_limit_is_frozen_before_future_prices_and_no_fill_keeps_cash(self):
        from c3_entry_timing_audit_v1 import execute
        bs=bars();sessions=[b['date'] for b in bs];i=40;p=dict(low=130,high=135,stop=100,resistance=300,resistance2=350,reference_close=bs[i]['close'])
        for b in bs[i+1:]:b.update(open=240,low=230,high=250,close=240)
        r=execute('MA20_LIMIT',p,bs,i,sessions,5,sessions[-1]);self.assertEqual(r['status'],'PASS_UNFILLED');self.assertEqual(r['return_pct'],0)
    def test_entry_followed_by_action_boundary_stays_censored_not_a_successful_trade(self):
        from c3_entry_timing_audit_v1 import execute
        bs=bars();sessions=[b['date'] for b in bs];i=40
        p=dict(low=130,high=135,stop=100,resistance=300,resistance2=350,reference_close=bs[i]['close'])
        bs[i+3]['action_boundary']=True
        r=execute('CONDITIONAL_NEXT_OPEN',p,bs,i,sessions,5,sessions[-1])
        self.assertEqual(r['status'],'CENSORED_PRICE_ACTION_OR_GAP');self.assertIsNone(r['return_pct'])
        self.assertNotIn('initial_net_r1_rr',r)
    def test_daily_workflow_preserves_schedule_and_records_real_source_and_protected_hashes(self):
        s=(Path(__file__).resolve().parents[1]/'.github/workflows/c3_research_daily_caller.yml').read_text()
        for cron in ('10 23 * * 0-4','20 23 * * 0-4','30 23 * * 0-4'):self.assertIn(cron,s)
        job=s.split('\n  new-session-review:\n',1)[1]
        for value in ('OPENDART_API_KEY','before.json','after.json','evidence/recovery/collection.json','evidence/recovery/normalized_market.json',"before['protected']==after['protected']"):self.assertIn(value,job)
        self.assertNotIn('--timing-cohort',job)

if __name__=='__main__':unittest.main()
