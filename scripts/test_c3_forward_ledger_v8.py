"""Synthetic fixtures only; no fixture is a prospective market decision."""
import copy,json,tempfile,unittest
from datetime import date,timedelta
from pathlib import Path

from c3_forward_ledger_v8 import immutable,read_record,hash_value,market_payload,freeze_market,register as register_live,correction,signal_id,advance,selection_observation,paper_observation,rows_for,execution_version
from c3_daily_research_v8 import support_diagnostic,choose
from c3_daily_top2_v4 import structure


def dates(n=26):
    out=[];d=date(2026,11,6)
    while len(out)<n:
        if d.weekday()<5:out.append(d.isoformat())
        d+=timedelta(days=1)
    return out


def market(i,changes=None):
    ds=dates();day=ds[i];prices=[]
    for ticker,name,board in [('005930','TEST_STOCK','KOSPI'),('001234','TEST_OTHER','KOSDAQ')]:
        v=dict(open=10200,high=11500,low=10100 if i else 9500,close=11000 if i else 10000,volume=1000,turnover_krw=10_000_000)
        if changes and ticker=='005930':v.update(changes)
        prices.append(dict(v,ticker=ticker,name=name,market=board,asof=day))
    meta=dict(asof=day,received_at=day+'T07:00:00+00:00',authenticated=True,price_basis='UNADJUSTED_AS_TRADED',source_scope='SYNTHETIC_TEST_FIXTURE',regular_only_certified=False)
    return market_payload(prices,{m:{d:100. for d in ds[:i+1]} for m in ('KOSPI','KOSDAQ')},ds[:i+1],meta)


def batch(m,model_tickers=None):
    d=m['asof'];now=d+'T07:01:00+00:00';models={}
    for model in ('A','B'):
        rows=[]
        for rank,t in enumerate((model_tickers or {}).get(model,['005930']),1):
            p=dict(ticker=t,decision_date=d,method='PULLBACK',signal_key=t+':FROZEN_STRUCTURE',segment=0,stop=9000,support=9500,atr=1000,low=10000,high=10500,resistance=12000,resistance2=13000)
            rows.append(dict(signal_id=signal_id(d,model,t),ticker=t,name=m['rows'][t]['name'],market=m['rows'][t]['market'],rank=rank,model=model,reference_close=m['rows'][t]['close'],decision_date=d,registered_at=now,
                market_regime='SIDEWAYS',source_regular_only_certified=False,entry_plans={'A_SUPPORT_LIMIT':dict(plan=p,reason=None)}))
        models[model]=rows
    return dict(schema='C3_FORWARD_DECISION_V8',decision_date=d,price_asof=d,known_at=now,source_received_at=m['source']['received_at'],expected_last_completed_session=d,
        execution_open_at=dates()[dates().index(d)+1]+'T09:00:00+09:00',models=models,source_snapshot_hash=hash_value(m),model_code_sha256='TEST_CODE_HASH',execution_version=execution_version(),synthetic_source=False),now


def register(root,b,now):
    """Supply each synthetic test's actual fixture receipt, never real quotes."""
    if not (Path(root)/'markets'/(b['decision_date']+'.json.gz')).exists():
        i=dates().index(b['decision_date']);freeze_market(root,market(i),b['decision_date']+'T07:01:00Z')
    return register_live(root,b,now)


class ForwardV8Tests(unittest.TestCase):
    def test_hash_tamper_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'record.json';immutable(p,{'close':100});j=json.loads(p.read_text());j['payload']['close']=101;p.write_text(json.dumps(j))
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):read_record(p)

    def test_immutable_retry_and_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'r.json';self.assertTrue(immutable(p,{'x':1}));self.assertFalse(immutable(p,{'x':1}))
            with self.assertRaisesRegex(ValueError,'CONFLICT'):immutable(p,{'x':2})

    def test_market_future_receipt_and_duplicate_price_rejected(self):
        m=market(0)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'FUTURE_SOURCE'):freeze_market(tmp,m,'2026-11-06T06:59:00Z')
        prices=[dict(m['rows']['005930'],ticker='005930',asof=m['asof'])]*2
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):market_payload(prices,m['indices'],m['sessions'],m['source'])

    def test_market_retry_retains_first_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=market(0);original,_=freeze_market(tmp,m,'2026-11-06T07:01:00Z');m['source']['received_at']='2026-11-06T07:02:00Z'
            retried,new=freeze_market(tmp,m,'2026-11-06T07:03:00Z');self.assertFalse(new);self.assertEqual(original,retried)

    def test_market_revision_not_silently_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=market(0);freeze_market(tmp,m,'2026-11-06T07:01:00Z');m['rows']['005930']['close']=9900
            with self.assertRaisesRegex(ValueError,'CORRECTION'):freeze_market(tmp,m,'2026-11-06T07:02:00Z')

    def test_adjusted_and_aftermarket_prices_rejected(self):
        m=market(0);prices=[dict(v,ticker=t,asof=m['asof']) for t,v in m['rows'].items()]
        for key,value in [('price_basis','ADJUSTED'),('source_scope','AFTERMARKET')]:
            meta=dict(m['source']);meta[key]=value
            with self.assertRaisesRegex(ValueError,'BASIS_OR_SCOPE'):market_payload(prices,m['indices'],m['sessions'],meta)

    def test_index_history_revision_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=market(0);freeze_market(tmp,m,'2026-11-06T07:01:00Z');n=market(1);n['indices']['KOSPI'][dates()[0]]=99
            with self.assertRaisesRegex(ValueError,'BENCHMARK_HISTORY'):freeze_market(tmp,n,dates()[1]+'T07:01:00Z')

    def test_registration_idempotent_and_changed_decision_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            b,now=batch(market(0));saved,new=register(tmp,b,now);self.assertTrue(new);again,new=register(tmp,b,now);self.assertFalse(new);self.assertEqual(saved,again)
            b['models']['B'][0]['entry_plans']['A_SUPPORT_LIMIT']['plan']['stop']=9500
            with self.assertRaisesRegex(ValueError,'CORRECTION'):register(tmp,b,now)

    def test_no_old_signal_registration(self):
        b,now=batch(market(0))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'CURRENT_SESSION'):register(tmp,b,dates()[1]+'T07:01:00Z')

    def test_synthetic_live_and_future_knowledge_rejected(self):
        b,now=batch(market(0))
        with tempfile.TemporaryDirectory() as tmp:
            b['synthetic_source']=True
            with self.assertRaisesRegex(ValueError,'SYNTHETIC'):register(tmp,b,now)
            b['synthetic_source']=False;b['known_at']='2026-11-06T08:00:00Z'
            with self.assertRaisesRegex(ValueError,'FUTURE'):register(tmp,b,now)

    def test_duplicate_signal_id_guard(self):
        b,now=batch(market(0));b['models']['A']*=2
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'DUPLICATE'):register(tmp,b,now)
            b,now=batch(market(0));b['models']['B'][0]['reference_close']=99999
            with self.assertRaisesRegex(ValueError,'REFERENCE_PRICE'):register(tmp,b,now)

    def test_correction_preserves_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'decisions/test.json';immutable(p,{'original':1});old=p.read_bytes()
            q=correction(tmp,p,'DATA_VENDOR_CORRECTION',{'original':2},'2026-11-09T07:01:00Z','TEST_RUN');self.assertEqual(old,p.read_bytes());self.assertFalse(read_record(q)['applied_to_original'])

    def test_zero_or_one_candidate_is_allowed(self):
        for model_tickers in ({'A':[],'B':[]},{'A':['005930'],'B':[]}):
            b,now=batch(market(0),model_tickers)
            with tempfile.TemporaryDirectory() as tmp:self.assertTrue(register(tmp,b,now)[1])

    def test_touch_alone_is_not_broker_fill_or_model_trade_through(self):
        markets={dates()[i]:market(i) for i in range(2)};markets[dates()[1]]=market(1,dict(open=12000,high=12500,low=10500,close=12000))
        s=batch(markets[dates()[0]])[0]['models']['B'][0];rows=rows_for(s,markets,dates()[:2]);p=paper_observation(s,'A_SUPPORT_LIMIT',rows,dates()[:2],5)
        self.assertEqual(p['status'],'TOUCH_WITHOUT_TRADE_THROUGH');self.assertFalse(p['actual_broker_fill'])

    def test_limit_expires_not_filled_on_later_touch(self):
        mm={dates()[i]:market(i) for i in range(7)};mm[dates()[1]]=market(1,dict(open=12000,high=12500,low=11000,close=12000))
        s=batch(mm[dates()[0]])[0]['models']['B'][0];p=paper_observation(s,'A_SUPPORT_LIMIT',rows_for(s,mm,dates()[:7]),dates()[:7],5)
        self.assertEqual(p['status'],'DAY_EXPIRED_NO_TOUCH');self.assertIsNone(p['net_pct'])

    def test_missing_first_session_never_substituted_by_later_fill(self):
        mm={dates()[i]:market(i) for i in [0,2,3,4,5,6]};s=batch(mm[dates()[0]])[0]['models']['B'][0];rows=rows_for(s,mm,dates()[:7])
        self.assertEqual(paper_observation(s,'A_SUPPORT_LIMIT',rows,dates()[:7],5)['status'],'DATA_UNUSABLE')
        self.assertEqual(selection_observation(s,rows,dates()[:7],mm[dates()[6]]['indices']['KOSPI'],5)['status'],'DATA_MISSING')

    def test_stop_next_open_gap_and_halt_wait(self):
        mm={dates()[i]:market(i) for i in range(7)};mm[dates()[2]]=market(2,dict(open=10000,high=10500,low=8000,close=8500))
        mm[dates()[3]]=market(3,dict(open=0,high=0,low=0,close=8500,volume=0,turnover_krw=0));mm[dates()[4]]=market(4,dict(open=7000,high=9000,low=6800,close=8500))
        s=batch(mm[dates()[0]])[0]['models']['B'][0];p=paper_observation(s,'A_SUPPORT_LIMIT',rows_for(s,mm,dates()[:7]),dates()[:7],5)
        self.assertEqual(p['exit']['date'],dates()[4]);self.assertEqual(p['exit']['price'],7000);self.assertLess(p['net_pct'],-30)

    def test_early_exit_does_not_complete_twenty_day_window(self):
        mm={dates()[i]:market(i) for i in range(5)};mm[dates()[2]]=market(2,dict(open=10000,high=10500,low=8000,close=8500));mm[dates()[3]]=market(3,dict(open=8000,high=10500,low=7900,close=10000))
        s=batch(mm[dates()[0]])[0]['models']['B'][0];p=paper_observation(s,'A_SUPPORT_LIMIT',rows_for(s,mm,dates()[:5]),dates()[:5],20)
        self.assertIsNotNone(p['realized_net_pct']);self.assertIsNone(p['net_pct']);self.assertEqual(p['status'],'OBSERVATION_WINDOW_INCOMPLETE')

    def test_selection_continues_after_stopped_trade(self):
        mm={dates()[i]:market(i) for i in range(22)};mm[dates()[2]]=market(2,dict(open=10000,high=10500,low=8000,close=8500));mm[dates()[3]]=market(3,dict(open=8000,high=10500,low=7900,close=10000))
        s=batch(mm[dates()[0]])[0]['models']['B'][0];rows=rows_for(s,mm,dates()[:22]);p=paper_observation(s,'A_SUPPORT_LIMIT',rows,dates()[:22],20);selection=selection_observation(s,rows,dates()[:22],mm[dates()[21]]['indices']['KOSPI'],20)
        self.assertEqual(p['status'],'COMPLETE');self.assertLess(p['net_pct'],0);self.assertEqual(selection['status'],'COMPLETE');self.assertGreater(selection['price_move_pct'],0)

    def test_same_bar_stop_target_order_flagged(self):
        mm={dates()[i]:market(i) for i in range(7)};mm[dates()[1]]=market(1,dict(open=12000,high=12500,low=8500,close=10000))
        s=batch(mm[dates()[0]])[0]['models']['B'][0];p=paper_observation(s,'A_SUPPORT_LIMIT',rows_for(s,mm,dates()[:7]),dates()[:7],5)
        self.assertTrue(p['entry_day_order_uncertain']);self.assertTrue(p['observations']['entry_day_extremes_excluded'])

    def test_no_setup_still_has_selection_outcome(self):
        mm={dates()[i]:market(i) for i in range(7)};s=batch(mm[dates()[0]])[0]['models']['B'][0];s['entry_plans']['A_SUPPORT_LIMIT']=dict(plan=None,reason='NO_CONFIRMED_STRUCTURE')
        rows=rows_for(s,mm,dates()[:7]);self.assertEqual(paper_observation(s,'A_SUPPORT_LIMIT',rows,dates()[:7],5)['status'],'NO_SIGNAL');self.assertEqual(selection_observation(s,rows,dates()[:7],mm[dates()[6]]['indices']['KOSPI'],5)['status'],'COMPLETE')
        with tempfile.TemporaryDirectory() as tmp:
            for d,m in mm.items():freeze_market(tmp,m,d+'T07:01:00Z')
            b,now=batch(mm[dates()[0]]);b['models']['B'][0]=s;register(tmp,b,now);_,summary=advance(tmp,dates()[6]+'T07:01:00Z','SYNTHETIC')
            self.assertEqual(summary['paper']['B']['A_SUPPORT_LIMIT']['5']['status_counts']['NO_SIGNAL'],1)

    def test_price_unit_or_identity_change_censors(self):
        mm={dates()[i]:market(i) for i in range(7)};mm[dates()[2]]['rows']['005930']['name']='NEW_ISSUER'
        s=batch(mm[dates()[0]])[0]['models']['B'][0];rows=rows_for(s,mm,dates()[:7]);self.assertEqual(selection_observation(s,rows,dates()[:7],mm[dates()[6]]['indices']['KOSPI'],5)['status'],'CORPORATE_ACTION_OR_IDENTITY_UNRESOLVED')

    def test_full_pipeline_replay_is_idempotent_and_separates_models(self):
        with tempfile.TemporaryDirectory(prefix='c3-synthetic-only-') as tmp:
            for i in range(22):
                m=market(i);now=m['asof']+'T07:01:00Z';freeze_market(tmp,m,now)
                if i<2:
                    b,now=batch(m);register(tmp,b,now)
            rows,summary=advance(tmp,now,'SYNTHETIC_RUN');again,second=advance(tmp,now,'SYNTHETIC_RETRY')
            self.assertEqual(rows,again);self.assertEqual(summary,second);self.assertEqual(summary['registered_signals'],4)
            for model in ('A','B'):
                self.assertEqual(summary['selection'][model]['20']['completed_nonoverlap'],1)
                self.assertEqual(summary['paper'][model]['A_SUPPORT_LIMIT']['20']['completed'],1)
            self.assertEqual(summary['overlapping_selection_records'],2);self.assertEqual(summary['actual_broker_fills'],0)

    def test_new_unconfirmed_bar_does_not_raise_old_stop(self):
        past=[]
        for i in range(30):past.append(dict(date=f'2026-10-{i+1:02d}',open=100,high=110,low=90 if i==25 else 95+i*.01 if i<25 else 70+i,close=105,volume=100,turnover_krw=10000,segment=0))
        old=structure(past);self.assertIsNotNone(old);frozen=copy.deepcopy(old)
        changed=past+[dict(past[-1],date='2026-11-01',low=98,close=108)]
        self.assertEqual(old,frozen);self.assertEqual(structure(changed)['pivot_date'],old['pivot_date'])

    def test_current_universe_can_shrink_and_selection_is_independent_of_entry(self):
        from collections import defaultdict
        from datetime import datetime
        sessions=[(date(2026,11,6)-timedelta(days=69-i)).isoformat() for i in range(70)];past={};prices={};basic={};kind={};sector=defaultdict(list)
        for t,board in [('005930','KOSPI'),('001234','KOSDAQ')]:
            bars=[]
            for i,d in enumerate(sessions):
                close=1000+i*10+max(0,i-60)**2*10
                bars.append(dict(date=d,name='TEST_'+t,open=close-3,high=close+10,low=close-10,close=close,volume=1000,turnover_krw=1_000_000,segment=0))
            past[t]=bars;prices[t]=dict(ticker=t,name='TEST_'+t,asof=sessions[-1],market=board)
            basic[t]=dict(security_group='주권',share_kind='보통주',market=board)
            kind[t]=dict(market=board,listed_date='2020-01-01',industry='기계',products='모터')
            sector[t]=[dict(market=board,sector='기계',krx_tradable_status='tradable')]
        indices={m:{d:100 for d in sessions} for m in ('KOSPI','KOSDAQ')};meta=dict(asof=sessions[-1],received_at='2026-11-06T07:00:00Z',regular_only_certified=False,price_basis='UNADJUSTED_AS_TRADED')
        models,counts=choose(prices,past,basic,kind,sector,indices,sessions,'2026-11-06T07:01:00Z',meta,'SYNTHETIC','CODE')
        self.assertEqual(counts['analysis_eligible'],2);self.assertEqual(len(models['B']),2)
        del basic['001234'];models,counts=choose(prices,past,basic,kind,sector,indices,sessions,'2026-11-06T07:01:00Z',meta,'SYNTHETIC','CODE')
        self.assertEqual(counts['analysis_eligible'],1);self.assertEqual(len(models['B']),1)
        bad=copy.deepcopy(past);bad['005930'][-1]['date']='2026-11-09'
        with self.assertRaisesRegex(ValueError,'FUTURE_OR_STALE'):choose(prices,bad,basic,kind,sector,indices,sessions,'2026-11-06T07:01:00Z',meta,'SYNTHETIC','CODE')

    def test_current_history_gap_resets_instead_of_skipping_session(self):
        import csv,gzip,hashlib
        from c3_daily_research_v8 import histories
        sessions=[(date(2026,11,6)-timedelta(days=69-i)).isoformat() for i in range(70)]
        rows=[dict(ticker='005930',name='TEST',date=d,open=100,high=110,low=90,close=105,volume=1000,turnover_krw=100000) for d in sessions[:-1]]
        current=dict(rows[-1],date=sessions[-1],asof=sessions[-1]);prices={'005930':current}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'panel.csv.gz';a=Path(tmp)/'audit.json'
            def write(rr):
                with gzip.open(p,'wt') as f:
                    w=csv.DictWriter(f,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr)
                a.write_text(json.dumps(dict(panel_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),reference_rebase_candidates=[])))
            write(rows);valid,_=histories(p,a,prices,{},sessions,sessions[-1]);self.assertIn('005930',valid)
            write(rows[:40]+rows[41:]);valid,excluded=histories(p,a,prices,{},sessions,sessions[-1]);self.assertNotIn('005930',valid);self.assertEqual(excluded['005930'],'CONTINUOUS_VALID_HISTORY_LT_65')


if __name__=='__main__':unittest.main()
