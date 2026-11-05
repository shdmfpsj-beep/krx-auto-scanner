"""Synthetic faults in whole-market recovery, never empirical performance."""
import copy,csv,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from c3_market_supply_v11 import normalize_cache,control_check,validated_manifest,published_after_close,CACHE_REPO
from c3_supply_v11 import digest,write
from c3_current_candidates_v7 import fresh_snapshot
from c3_supply_runtime_v12 import collect_session

FIELDS=('market','ticker','name','asof','open','high','low','close','volume','turnover_krw','valid_daily_bar','action_boundary')


def rows(day='2026-11-05'):
    return [dict(market=m,ticker=t,name='SYNTHETIC',asof=day,open=100,high=110,low=90,close=105,volume=1000,turnover_krw=102000,valid_daily_bar=True,action_boundary='') for m,t in [('KOSPI','0220W0'),('KOSDAQ','000001')]]


def fixture(folder,day='2026-11-05',research=False):
    root=Path(folder);root.mkdir(parents=True,exist_ok=True);hashes={};files={}
    for market in ('KOSPI','KOSDAQ'):
        p=root/(market+('_research.csv' if research else '_official.csv'))
        with p.open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(r for r in rows(day) if r['market']==market)
        hashes[market]=digest(p.read_bytes());files[market]=p.name
    m=dict(asof=day,retrieval_utc=day+'T07:00:00Z',krx_eod_authenticated=not research,official_dataset_usable=not research,official_market_rows=2,market_file_sha256=hashes,price_basis='UNADJUSTED_AS_TRADED',status='OFFICIAL_AVAILABLE',response_diagnostics=[])
    if research:
        evidence=dict(official_control_complete_match=True,control_asof='2026-11-04',previous_session_checked='2026-11-04',control=dict(rows=2,compared=2,complete_match=True,missing=[],extra=[],mismatches=[]),cache_repository=CACHE_REPO,cache_commit='a'*40,requested_cache_day=day,exchange_max_work_dt=day,quality=dict(status='QUALITY_GATE_PASSED',errors=[],markets={'KOSPI':{},'KOSDAQ':{}}),current_market_file_sha256=hashes,current_rows=2)
        evidence.update(cache_file_commit='a'*40,cache_file_commit_date=day+'T07:00:00Z')
        m.update(schema='C3_SUPPLY_SNAPSHOT_V11',research_dataset_validated=True,data_quality_state='RESEARCH_VALIDATED',source_provider='FINANCEDATA_KRX_CACHE',status='RESEARCH_VALIDATED',price_files=files,validation=evidence,
            validation_sha256=digest(json.dumps(evidence,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()))
    write(root/'krx_v65_collect_status.json',m);return m


def empty(day,folder,key):
    m=dict(asof=day,status='OFFICIAL_MARKETS_NOT_COMPLETE',krx_eod_authenticated=False,official_dataset_usable=False,official_market_rows=0,market_file_sha256={},response_diagnostics=[dict(status='OUTBLOCK_EMPTY',http_status=200)])
    write(Path(folder)/'krx_v65_collect_status.json',m);return m


class SupplyRuntimeV12Tests(unittest.TestCase):
    def test_full_cache_preserves_alpha_code_and_actual_turnover(self):
        data=b'Code,MarketId,Name,Open,High,Low,Close,Volume,Amount,Changes\n0220W0,STK,SYNTHETIC,100,110,90,105,1000,102000,5\n'
        rr,excluded=normalize_cache(data,'2026-11-05');self.assertEqual(rr[0]['ticker'],'0220W0');self.assertEqual(rr[0]['turnover_krw'],102000);self.assertEqual(rr[0]['previous_reference'],100);self.assertFalse(excluded)
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):normalize_cache(data+data.splitlines(keepends=True)[1],'2026-11-05')

    def test_full_control_rejects_any_missing_extra_field_or_market_difference(self):
        a=rows();self.assertTrue(control_check(a,a)['complete_match'])
        for changed in [a[:1],a+[dict(a[0],ticker='999999')],[dict(a[0],market='KOSDAQ'),a[1]],[dict(a[0],turnover_krw=102001),a[1]]]:
            self.assertFalse(control_check(a,changed)['complete_match'])

    def test_research_proof_requires_actual_complete_control_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=fixture(tmp,research=True);self.assertTrue(validated_manifest(m))
            for change in [dict(validation_sha256='bad'),dict(price_basis='NAVER_ADJUSTED'),dict(data_quality_state='OHLCV_UNVERIFIED')]:self.assertFalse(validated_manifest(dict(m,**change)))
            m['validation']['control']['mismatches']=['SYNTHETIC'];m['validation_sha256']=digest(json.dumps(m['validation'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode());self.assertFalse(validated_manifest(m))

    def test_fresh_loader_rechecks_csv_not_just_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=fixture(tmp,research=True);self.assertEqual(len(fresh_snapshot(tmp)[0]),2)
            p=Path(tmp)/m['price_files']['KOSPI'];p.write_text(p.read_text()+'tampered')
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):fresh_snapshot(tmp)

    def test_empty_official_retries_once_then_uses_one_complete_alternative(self):
        calls=[]
        def alternative(day,control,folder,wire,previous_day):calls.append((day,previous_day));return fixture(folder,day,True)
        with tempfile.TemporaryDirectory() as tmp,patch('c3_supply_runtime_v12.completed_day',return_value='2026-11-05'):
            base=Path(tmp)/'base';fixture(base,'2026-11-04');out=Path(tmp)/'fresh'
            m=collect_session('2026-11-05',base,out,'2026-11-04',official=empty,alternative=alternative,pause=lambda _:None)
            self.assertEqual(m['data_quality_state'],'RESEARCH_VALIDATED');self.assertFalse(m['krx_eod_authenticated']);self.assertEqual(len(m['supply_attempts']),3);self.assertEqual(calls,[('2026-11-05','2026-11-04')]);self.assertEqual(len(fresh_snapshot(out)[0]),2)

    def test_valid_official_does_not_probe_other_sources(self):
        def official(day,folder,key):return fixture(folder,day)
        def forbidden(*args,**kwargs):self.fail('No fallback needed for a complete quality-passed official source')
        with tempfile.TemporaryDirectory() as tmp,patch('c3_supply_runtime_v12.completed_day',return_value='2026-11-05'):
            base=Path(tmp)/'base';fixture(base,'2026-11-04')
            m=collect_session('2026-11-05',base,Path(tmp)/'fresh','2026-11-04',official=official,alternative=forbidden)
            self.assertEqual(m['data_quality_state'],'OFFICIAL_VERIFIED');self.assertEqual(len(m['supply_attempts']),1)

    def test_partial_market_cannot_be_supplemented_from_another_provider(self):
        def partial(day,folder,key):
            m=empty(day,folder,key);m['successful_partial_markets']=['KOSPI'];write(Path(folder)/'KOSPI_official.csv',{'not':'a_complete_dataset'});return m
        def conflict(day,control,folder,wire,previous_day):write(Path(folder)/'supply_validation.json',dict(status='CONFLICT',control={'complete_match':False}));raise ValueError('MIRROR_OFFICIAL_CONTROL_CONFLICT')
        with tempfile.TemporaryDirectory() as tmp,patch('c3_supply_runtime_v12.completed_day',return_value='2026-11-05'):
            base=Path(tmp)/'base';fixture(base,'2026-11-04');out=Path(tmp)/'fresh'
            m=collect_session('2026-11-05',base,out,'2026-11-04',official=partial,alternative=conflict,pause=lambda _:None)
            self.assertEqual(m['data_quality_state'],'CONFLICT');self.assertIsNone(fresh_snapshot(out)[0]);self.assertFalse(list(out.glob('*_official.csv')))

    def test_unfinished_eod_cannot_be_requested(self):
        with tempfile.TemporaryDirectory() as tmp,patch('c3_supply_runtime_v12.completed_day',return_value='2026-11-05'):
            with self.assertRaisesRegex(ValueError,'UNFINISHED'):collect_session('2026-11-06',tmp,tmp,'2026-11-05',official=lambda *x:self.fail('Future network request'))

    def test_research_data_does_not_skip_later_official_reconciliation(self):
        from c3_runtime_v9 import already_current
        r=dict(source_price_asof='2026-11-06',errors=[],source_hashes={'pipeline_code':'abc'},data_quality_state='RESEARCH_VALIDATED')
        self.assertFalse(already_current(r,'2026-11-06','abc'));r['data_quality_state']='OFFICIAL_VERIFIED';self.assertTrue(already_current(r,'2026-11-06','abc'))

    def test_arbitrary_research_flag_does_not_unlock_ledger(self):
        from c3_forward_ledger_v8 import market_payload
        meta=dict(asof='2026-11-05',price_basis='UNADJUSTED_AS_TRADED',authenticated=False,provider='C3_KRX_UNADJUSTED_SUPPLY_V12',research_dataset_validated=True,supply_manifest={})
        with self.assertRaisesRegex(ValueError,'UNAUTHENTICATED'):market_payload(rows(),{m:{'2026-11-05':100} for m in ('KOSPI','KOSDAQ')},['2026-11-05'],meta)

    def test_intraday_cache_file_or_future_commit_is_not_completed_eod(self):
        from datetime import datetime,timezone
        clock=datetime(2026,11,5,14,tzinfo=timezone.utc)
        self.assertFalse(published_after_close('2026-11-05','2026-11-05T05:59:00Z',clock))
        self.assertTrue(published_after_close('2026-11-05','2026-11-05T06:30:00Z',clock))
        self.assertFalse(published_after_close('2026-11-05','2026-11-06T00:00:00Z',clock))

if __name__=='__main__':unittest.main()
