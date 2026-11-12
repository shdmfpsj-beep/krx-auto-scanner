import copy,json,tempfile,unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from c3_range_daily_v4 import lineage,freeze,decision_identity,isolated_outputs
from c3_range_forward_v1 import hash_value,update_existing
from c3_morning_source_v1 import normalized_hash


class DailyLineage(unittest.TestCase):
    def fixture(self):
        day='2026-11-12';clock=datetime.fromisoformat('2026-11-13T08:30:00+09:00')
        row=dict(name='가상기업',market='KOSPI',open=100,high=110,low=90,close=100,volume=100,turnover_krw=10000)
        market=dict(asof=day,source={'source_run_id':'123'},rows={'000001':row,'000002':dict(row,market='KOSDAQ')})
        decision=dict(price_asof=day,source_snapshot_hash=hash_value(market))
        latest=dict(source_price_asof=day,source_run_id='123',research_top2_registered_for_source_session=True,current_scope={'price_rows':2})
        source=dict(schema='C3_MORNING_OFFICIAL_SOURCE_V1',ready=True,status='OFFICIAL_CACHE_MATCHED',requested_day=day,
            normalized_rows_sha256=normalized_hash([dict(r,ticker=t,asof=day) for t,r in market['rows'].items()]),final_collection_at='2026-11-13T08:10:00+09:00')
        proof=dict(schema='C3_MORNING_REGISTERED_SOURCE_V1',mode='APPROVED_PIPELINE',source_day=day,source_run_id='123',registration_run_id='456',
            registered_state_sha='a'*40,market_payload_sha256=hash_value(market),decision_payload_sha256=hash_value(decision))
        return [latest,market,decision,source,proof,'a'*40,'456',clock,'forward']
    def test_new_date_not_nov11_is_accepted_with_exact_handoff(self):
        self.assertTrue(lineage(*self.fixture())['forward_allowed'])
    def test_replay_performs_no_forward_approval(self):
        a=self.fixture();a[-1]='replay';a[4]={};self.assertFalse(lineage(*a)['forward_allowed'])
    def test_missing_registration_is_blocked(self):
        a=self.fixture();a[4]={}
        with self.assertRaises(ValueError):lineage(*a)
    def test_wrong_caller_is_blocked(self):
        a=self.fixture();a[6]='999'
        with self.assertRaises(ValueError):lineage(*a)
    def test_wrong_commit_is_blocked(self):
        a=self.fixture();a[5]='b'*40
        with self.assertRaises(ValueError):lineage(*a)
    def test_valid_shape_wrong_payload_is_blocked(self):
        a=self.fixture();a[4]['market_payload_sha256']='b'*64
        with self.assertRaises(ValueError):lineage(*a)
    def test_source_cache_disagreement_is_blocked(self):
        a=self.fixture();a[3]['normalized_rows_sha256']='b'*64
        with self.assertRaises(ValueError):lineage(*a)
    def test_missing_official_data_is_not_zero_candidates(self):
        a=self.fixture();a[3]['ready']=False
        with self.assertRaises(ValueError):lineage(*a)
    def test_stale_day_cannot_be_new_report(self):
        a=self.fixture();a[7]+=timedelta(days=1)
        with self.assertRaisesRegex(ValueError,'STALE'):lineage(*a)
    def test_after_open_cannot_create_hindsight_signal(self):
        a=self.fixture();a[7]=datetime.fromisoformat('2026-11-13T10:00:00+09:00')
        with self.assertRaisesRegex(ValueError,'AFTER_ENTRY_OPEN'):lineage(*a)
    def test_future_collection_is_blocked(self):
        a=self.fixture();a[3]['final_collection_at']='2026-11-13T08:40:00+09:00'
        with self.assertRaisesRegex(ValueError,'RECEIPT_TIME'):lineage(*a)
    def test_konex_or_partial_universe_is_blocked(self):
        a=self.fixture();a[0]['current_scope']['price_rows']=3
        with self.assertRaisesRegex(ValueError,'FULL_MARKET'):lineage(*a)


class FrozenDaily(unittest.TestCase):
    def test_card_uses_actual_date_instead_of_nov11(self):
        from c3_range_card_v1 import hold_card
        from test_c3_range_structure_v3 import ReferenceCard
        r=ReferenceCard().report('2026-11-12');r['mode']='PROSPECTIVE_RESEARCH_OBSERVATION';seen=[]
        with tempfile.TemporaryDirectory() as root,patch('c3_range_card_v1.text',side_effect=lambda *a,**kw:seen.append(str(a[3]))),patch('c3_range_card_v1.wrap',side_effect=lambda d,s,*a:[s]):
            m=hold_card(r,Path(root)/'cash.png')
        self.assertEqual(m['price_asof'],'2026-11-12');self.assertFalse(any('11월 11일' in x for x in seen))
        self.assertTrue(any('2026-11-12 전일장 연구 관찰' in x for x in seen))
    def test_output_cannot_modify_source_checkout_or_original_ledger(self):
        with tempfile.TemporaryDirectory() as root:
            b=Path(root)
            for output in (b/'state/out',b/'engine',b/'old/out',b/'reports/c3_forward_v8'):
                with self.assertRaises(ValueError):isolated_outputs(b/'engine',b/'state',b/'old',b/'new-out',output)
            isolated_outputs(b/'engine',b/'state',b/'old',b/'new-out',b/'new-records')
    def fixture(self):
        return dict(model_version='C3_STRUCTURE_TYPED_RANGE_V4',model_code_sha256='a'*64,source_date='2026-11-12',source_run_id='123',
            source_hash='b'*64,original_decision_hash='c'*64,analysis_identity_sha256='d'*64,watch_top2=[],final_research_top2=[],
            funnel={'technical':0},regime={'observed_regime':'UNVERIFIED'},mode='PROSPECTIVE_RESEARCH_OBSERVATION',buy_approved=False,
            generated_at='2026-11-13T08:30:00+09:00',source_received_at='2026-11-13T08:10:00+09:00')
    def test_zero_candidates_still_has_immutable_daily_decision(self):
        r=self.fixture()
        with tempfile.TemporaryDirectory() as root:
            a=freeze(root,r,datetime.fromisoformat(r['generated_at']),'forward')
            self.assertEqual(a['status'],'CREATED');self.assertEqual(a['entry_fit'],0)
            self.assertEqual(len(list(Path(root).rglob('*.json'))),1)
    def test_zero_candidates_cannot_bypass_stale_date_guard(self):
        r=self.fixture()
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError,'STALE'):freeze(root,r,datetime.fromisoformat('2026-11-14T08:30:00+09:00'),'forward')
            self.assertFalse(list(Path(root).rglob('*.json')))
    def test_retry_different_clock_keeps_first_decision(self):
        r=self.fixture()
        with tempfile.TemporaryDirectory() as root:
            freeze(root,r,datetime.fromisoformat(r['generated_at']),'forward');r['generated_at']='2026-11-13T08:35:00+09:00'
            self.assertEqual(freeze(root,r,datetime.fromisoformat(r['generated_at']),'forward')['status'],'ALREADY_RECORDED')
    def test_changed_source_or_stop_conflicts_instead_of_duplicate(self):
        for field in ['source_hash','model_code_sha256','analysis_identity_sha256']:
            r=self.fixture()
            with tempfile.TemporaryDirectory() as root:
                freeze(root,r,datetime.fromisoformat(r['generated_at']),'forward');r[field]='f'*64
                with self.assertRaisesRegex(ValueError,'CONFLICT'):freeze(root,r,datetime.fromisoformat(r['generated_at']),'forward')
    def test_watch_is_not_fabricated_entry_plan(self):
        r=self.fixture();r['watch_top2']=[dict(ticker='000001',display_plan=None,reason_text='가상 WATCH')]
        with tempfile.TemporaryDirectory() as root:
            a=freeze(root,r,datetime.fromisoformat(r['generated_at']),'forward');self.assertEqual(a['watch_only'],1)
            saved=json.loads(next((Path(root)/'observations').rglob('*.json')).read_text())['record']
            self.assertIsNone(saved['stop']);self.assertIsNone(saved['range']);self.assertEqual(saved['selection_role'],'WATCH_ONLY')
            self.assertEqual(freeze(root,r,datetime.fromisoformat(r['generated_at']),'forward')['records'][0]['status'],'ALREADY_RECORDED')
    def test_replay_leaves_no_decision_or_observation(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(freeze(root,self.fixture(),datetime.now().astimezone(),'replay')['writes'],0)
            self.assertFalse(list(Path(root).rglob('*.json')))
    def test_historical_report_cannot_be_relabelled_by_freeze(self):
        r=self.fixture();r['mode']='ARCHIVED_PRICE_CURRENT_CONTEXT_REVIEW'
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):freeze(root,r,datetime.fromisoformat(r['generated_at']),'forward')
    def test_corrupt_snapshot_is_detected(self):
        r=self.fixture()
        with tempfile.TemporaryDirectory() as root:
            freeze(root,r,datetime.fromisoformat(r['generated_at']),'forward');p=next((Path(root)/'decisions').rglob('*.json'))
            d=json.loads(p.read_text());d['record']['report']['buy_approved']=True;p.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):freeze(root,r,datetime.fromisoformat(r['generated_at']),'forward')
    def test_identity_does_not_include_wall_clock_or_run(self):
        r=self.fixture();a=decision_identity(r);r.update(generated_at='2099-01-01',research_run_id='999')
        self.assertEqual(a,decision_identity(r))
    def test_forward_updates_pending_then_observed_5_10_20(self):
        r=self.fixture();r['watch_top2']=[dict(ticker='000001',display_plan=None)]
        import exchange_calendars as xc
        cal=xc.get_calendar('XKRX');sessions=[d.strftime('%Y-%m-%d') for d in cal.sessions_in_range('2026-11-12','2026-12-31')][:22]
        bars=[dict(date=d,close=100+i,segment=0,tradable=True,action_boundary=False) for i,d in enumerate(sessions)]
        ix={d:200+i for i,d in enumerate(sessions)}
        with tempfile.TemporaryDirectory() as root:
            freeze(root,r,datetime.fromisoformat(r['generated_at']),'forward')
            first=update_existing(root,{'000001':bars},{'000001':ix},sessions,sessions[0])
            self.assertEqual(first['results'][0]['horizons']['20']['status'],'PENDING_FUTURE_SESSIONS')
            end=update_existing(root,{'000001':bars},{'000001':ix},sessions,sessions[-1])
            for h in (5,10,20):self.assertAlmostEqual(end['results'][0]['horizons'][str(h)]['selection_return_pct'],h)
            self.assertFalse(end['original_records_modified'])
            self.assertEqual(update_existing(root,{'000001':bars},{'000001':ix},sessions,sessions[-1])['results'][0]['status'],'ALREADY_RECORDED')


if __name__=='__main__':unittest.main()
