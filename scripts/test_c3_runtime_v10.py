"""Synthetic operation failures, separate from actual market evidence."""
import copy,json,tempfile,unittest
from pathlib import Path
from c3_runtime_v10 import REPO,sha,validate_scanner,scanner,quality,quarantine


def upstream():
    run=dict(id=12345678901,name='KRX daily candidate scan',path='.github/workflows/daily.yml',head_branch='main',head_sha='a'*40,event='schedule',status='completed',conclusion='success',repository=dict(full_name=REPO))
    jobs=dict(jobs=[dict(id=9,run_id=run['id'],conclusion='success',steps=[dict(name=n,conclusion='success') for n in ('Collect and screen','Test and record C3 screening timestamps','Upload report artifact')])])
    arts=dict(artifacts=[dict(id=8,name='krx-scan-report',workflow_run=dict(id=run['id']),size_in_bytes=100,expired=False)])
    return run,jobs,arts


def prices(n=25):
    return [dict(ticker=str(i+(1000 if m=='KOSPI' else 2000)).zfill(6),market=m,asof='2026-11-05',open=100,high=110,low=90,close=105,volume=1000,turnover_krw=100000) for m in ('KOSPI','KOSDAQ') for i in range(n)]


def receipts(root):
    p=Path(root);runtime=dict(run_context=dict(GITHUB_RUN_ID='12345678901'));(p/'c3_source_runtime_v1.json').write_text(json.dumps(runtime))
    (p/'status.json').write_text(json.dumps(dict(scan_complete=True,data_date_verified=True,market_data_date='2026-11-05')))
    (p/'c3_universe_capture_v1.json').write_text(json.dumps(dict(reference_date='2026-11-05',tickers=['005930'])))
    r=dict(ticker='005930',runtime_manifest_sha256=sha((p/'c3_source_runtime_v1.json').read_bytes()),latest_observed_date='2026-11-05',latest_raw_close=100,request=dict(adjusted=True),source_label='pykrx',route=dict(trace_completed=True,actual_provider_calls=[dict(module='pykrx.website.naver.wrap',function='get_market_ohlcv_by_date')]),response_received_at_utc='2026-11-05T12:00:00+00:00',raw_response_csv_sha256='b'*64)
    (p/'c3_source_observations_v1.jsonl').write_text(json.dumps(r)+'\n');return r


class RuntimeV10Tests(unittest.TestCase):
    def test_genuine_collect_and_artifact_required(self):
        r,j,a=upstream();self.assertEqual(validate_scanner(r,j,a)['run_id'],str(r['id']))
    def test_continue_on_error_success_workflow_rejected(self):
        r,j,a=upstream();j['jobs'][0]['steps'][0]['conclusion']='failure'
        with self.assertRaisesRegex(ValueError,'COLLECTION_NOT_SUCCESSFUL'):validate_scanner(r,j,a)
    def test_rerank_or_skipped_collect_cannot_trigger_research(self):
        r,j,a=upstream();j['jobs'][0]['steps'][0]['conclusion']='skipped'
        with self.assertRaises(ValueError):validate_scanner(r,j,a)
    def test_artifact_expiry_identity_and_duplicates_rejected(self):
        for mode in ('expired','wrong_run','duplicate','missing'):
            r,j,a=upstream()
            if mode=='expired':a['artifacts'][0]['expired']=True
            elif mode=='wrong_run':a['artifacts'][0]['workflow_run']['id']=99
            elif mode=='duplicate':a['artifacts']*=2
            else:a['artifacts']=[]
            with self.assertRaisesRegex(ValueError,'ARTIFACT'):validate_scanner(r,j,a)
    def test_untrusted_or_wrong_upstream_rejected(self):
        for field,value in [('path','.github/workflows/untrusted.yml'),('head_branch','feature'),('repository',dict(full_name='other/repo')),('head_repository',dict(full_name='other/repo'))]:
            r,j,a=upstream();r[field]=value
            with self.assertRaisesRegex(ValueError,'UPSTREAM'):validate_scanner(r,j,a)
    def test_invalid_run_id_never_used_in_url(self):
        with self.assertRaisesRegex(ValueError,'ID_INVALID'):scanner('../main',lambda p:self.fail(p))
    def test_latest_true_collection_skips_successful_rerank(self):
        r,j,a=upstream();bad=copy.deepcopy(r);bad['id']+=1
        def reader(path):
            if path.startswith('actions/workflows'):return dict(workflow_runs=[bad,r])
            if path.endswith('/artifacts?per_page=100'):return a
            if '/'+str(bad['id'])+'/' in path:return dict(jobs=[])
            return j
        self.assertEqual(len(scanner(reader=reader)['rejected_prior_runs']),1)
    def test_explicit_failed_source_does_not_silently_pick_another(self):
        r,j,a=upstream();j['jobs'][0]['steps']=[]
        def reader(path):return a if '/artifacts' in path else j if '/jobs' in path else r
        with self.assertRaisesRegex(ValueError,'COLLECTION'):scanner(str(r['id']),reader)
    def test_partial_two_market_payload_rejected(self):
        original=prices();self.assertEqual(quality(original,original,'2026-11-05')['errors'],[])
        self.assertTrue(quality([original[0],original[-1]],original,'2026-11-05')['errors'])
    def test_new_and_disappeared_codes_are_not_asserted_delistings(self):
        original=prices();new=copy.deepcopy(original);new[0]['ticker']='999999';q=quality(new,original,'2026-11-05')
        self.assertEqual(q['errors'],[]);self.assertFalse(q['markets']['KOSPI']['listing_or_delisting_cause_confirmed']);self.assertEqual(q['markets']['KOSPI']['newly_observed'],['999999'])
    def test_duplicate_wrong_date_and_bad_ohlc_rejected(self):
        for kind in ('duplicate','date','ohlc'):
            rows=prices()
            if kind=='duplicate':rows.append(rows[0])
            elif kind=='date':rows[0]['asof']='2026-11-04'
            else:rows[0]['low']=1000
            self.assertTrue(quality(rows,prices(),'2026-11-05')['errors'])
    def test_halt_like_is_separate_from_invalid_ohlc(self):
        rows=prices();rows[0].update(open=0,high=0,low=0,volume=0,turnover_krw=0)
        q=quality(rows,prices(),'2026-11-05');self.assertFalse(q['errors']);self.assertEqual(q['markets']['KOSPI']['halt_like'],1)
    def test_adjusted_close_quarantine_is_immutable_and_not_a_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir();receipts(source);audit=dict(run_id='12345678901',artifact_id=8)
            a=quarantine(source,root/'ledger',root/'out',audit);b=quarantine(source,root/'ledger',root/'out',audit)
            self.assertEqual(a['record_sha256'],b['record_sha256']);self.assertEqual(len(list((root/'ledger').rglob('*.gz'))),1);self.assertFalse((root/'ledger/decisions').exists());self.assertFalse((root/'ledger/markets').exists());self.assertFalse(a['used_for_paper_fills']);self.assertEqual(a['rows'],1)
    def test_changed_price_basis_or_receipt_hash_rejected(self):
        for mode in ('basis','hash','duplicate'):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);r=receipts(root)
                if mode=='basis':r['request']['adjusted']=False
                if mode=='hash':r['runtime_manifest_sha256']='a'*64
                line=json.dumps(r)+'\n';(root/'c3_source_observations_v1.jsonl').write_text(line* (2 if mode=='duplicate' else 1))
                with self.assertRaises(ValueError):quarantine(root,root/'ledger',root/'out',dict(run_id='12345678901',artifact_id=8))
    def test_market_provider_change_rejected_even_if_prices_match(self):
        from test_c3_forward_ledger_v8 import market
        from c3_forward_ledger_v8 import freeze_market
        with tempfile.TemporaryDirectory() as tmp:
            m=market(0);freeze_market(tmp,m,'2026-11-06T08:00:00Z');other=copy.deepcopy(m);other['source']['provider']='DIFFERENT_PROVIDER'
            with self.assertRaisesRegex(ValueError,'PROVIDER_OR_BASIS'):freeze_market(tmp,other,'2026-11-06T08:01:00Z')


if __name__=='__main__':unittest.main()
