"""Fault tests for publication time, exact-day reuse and immutable revisions."""
import base64,copy,csv,importlib.util,io,json,os,tempfile,unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from c3_telegram_inputs import canonical
from c3_morning_source_v1 import cache_rows,normalized_hash
from c3_early_source_v1 import (PREFIX,quality,eligibility,session_context,publish,load_prefetch,
    differences,sha,fdr_snapshot,trusted_wakeup,WAKEUPS)

def rows():
    return [dict(ticker=t,name='SYNTHETIC',market=m,asof='2026-11-12',open=100.,high=110.,low=90.,close=105.,volume=100.,turnover_krw=10000.) for t,m in [('000001','KOSPI'),('000002','KOSDAQ')]]

def raw_csv(rs):
    stream=io.StringIO();fields=['Code','Name','MarketId','Market','Open','High','Low','Close','Volume','Amount'];w=csv.DictWriter(stream,fields);w.writeheader()
    for r in rs:w.writerow(dict(Code=r['ticker'],Name=r['name'],MarketId={'KOSPI':'STK','KOSDAQ':'KSQ'}[r['market']],Market='KOSDAQ GLOBAL' if r['market']=='KOSDAQ' else 'KOSPI',**{c:r[k] for k,c in [('open','Open'),('high','High'),('low','Low'),('close','Close'),('volume','Volume'),('turnover_krw','Amount')]}))
    return stream.getvalue().encode()

def meta(rs=None,commit='a',at='2026-11-12T14:01:06Z'):
    rs=rs or rows();raw=raw_csv(rs)
    return dict(asof='2026-11-12',provider='FDR_DATED_CSV',path='data/listing/krx/2026-11-12.csv',
        snapshot_commit=commit*40,snapshot_commit_at=at,file_commit=commit*40,file_commit_at=at,
        cutoff_at='2026-11-13T00:00:00Z',collected_at='2026-11-13T06:00:00Z',raw_sha256=sha(raw),
        normalized_rows_sha256=normalized_hash(rs),markets={'KOSPI':1,'KOSDAQ':1},price_basis='UNADJUSTED_AS_REPORTED_FDR')

def context(*args,**kwargs):return dict(day='2026-11-12',reference_close_at='2026-11-12T06:30:00Z')

class MemoryGit:
    def __init__(self):self.blobs={};self.trees={'h0':{}};self.current='h0';self.count=0;self.paths=[]
    def head(self,branch):return self.current
    def file(self,path,ref,missing_ok=False):
        b=self.trees[ref].get(path)
        if b is None and missing_ok:return None
        return self.blobs[b]
    def api(self,path,method='GET',payload=None,**kwargs):
        if method=='GET':
            if path.startswith('git/commits/'):return {'tree':{'sha':path.split('/')[-1]}}
            if path.startswith('git/trees/'):
                ref=path.split('/')[-1].split('?')[0];return {'tree':[dict(path=p,sha=s,type='blob') for p,s in self.trees[ref].items()]}
            if path.startswith('git/blobs/'):return {'content':base64.b64encode(self.blobs[path.split('/')[-1]]).decode()}
            raise AssertionError(path)
        if path=='git/blobs':
            b=base64.b64decode(payload['content']);s=sha(b);self.blobs[s]=b;return {'sha':s}
        if path=='git/trees':
            tree=dict(self.trees[payload['base_tree']])
            for e in payload['tree']:
                self.paths.append(e['path']);b=e.get('content','').encode();s=e.get('sha',sha(b))
                if 'sha' not in e:self.blobs[s]=b
                tree[e['path']]=s
            self.count+=1;s='h'+str(self.count);self.trees[s]=tree;return {'sha':s}
        if path=='git/commits':return {'sha':payload['tree']}
        if path.startswith('git/refs/heads/'):
            self.current=payload['sha'];return {'object':{'sha':self.current}}
        raise AssertionError(path)

class Eligibility(unittest.TestCase):
    def test_intraday_version_rejected_even_with_later_head_or_clock(self):
        m=meta();m['file_commit_at']='2026-11-12T05:43:14Z';m['snapshot_commit_at']='2026-11-12T22:01:13Z'
        with patch('c3_early_source_v1.session_context',context),self.assertRaisesRegex(ValueError,'PRE_CLOSE'):eligibility(m,m['cutoff_at'])
    def test_future_snapshot_cannot_be_used_even_if_prices_are_unchanged(self):
        m=meta();m['snapshot_commit_at']='2026-11-12T22:01:13Z'
        with patch('c3_early_source_v1.session_context',context),self.assertRaisesRegex(ValueError,'FUTURE'):eligibility(m,'2026-11-12T14:10:00Z')
    def test_postclose_is_research_eligibility_not_approval(self):
        with patch('c3_early_source_v1.session_context',context):self.assertEqual(eligibility(meta(),meta()['cutoff_at'])['day'],'2026-11-12')
    def test_global_board_is_kosdaq_without_hardcoded_universe_count(self):
        r,e=cache_rows(raw_csv(rows()),'2026-11-12');self.assertEqual(r[1]['market'],'KOSDAQ');quality(r,'2026-11-12')
    def test_invalid_empty_duplicate_wrong_day_or_missing_board_is_blocked(self):
        for r in ([],rows()+[rows()[0]],[dict(rows()[0],low=200),rows()[1]],[dict(rows()[0],asof='2026-11-11'),rows()[1]],[rows()[0]]):
            with self.assertRaises(ValueError):quality(r,'2026-11-12')
    def test_changed_price_and_code_coverage_are_counted(self):
        rs=rows();rs[0]['close']=106;d=differences(rows(),rs);self.assertEqual(d['matched_rows'],1);self.assertEqual(d['changed_fields']['close'],1)
    def test_only_known_completed_main_events_can_wake_capture(self):
        r=dict(name=WAKEUPS[0],head_branch='main',head_repository={'full_name':'shdmfpsj-beep/krx-auto-scanner'},status='completed',event='schedule',conclusion='failure')
        self.assertTrue(trusted_wakeup({'workflow_run':r},r['head_repository']['full_name']))
        for field,value in [('head_branch','foreign'),('event','pull_request'),('status','in_progress'),('name','unknown')]:
            self.assertFalse(trusted_wakeup({'workflow_run':dict(r,**{field:value})},r['head_repository']['full_name']))

@unittest.skipUnless(importlib.util.find_spec('exchange_calendars'),'reference calendar dependency installed in Actions')
class Calendar(unittest.TestCase):
    def test_before_and_after_close_and_monday(self):
        self.assertEqual(session_context('2026-11-13T06:29:00Z')['day'],'2026-11-12')
        self.assertEqual(session_context('2026-11-13T06:31:00Z')['day'],'2026-11-13')
        self.assertEqual(session_context('2026-11-15T23:10:00Z')['day'],'2026-11-13')
    def test_holiday_and_uncompleted_explicit_date(self):
        self.assertEqual(session_context('2026-12-25T03:00:00Z')['day'],'2026-12-24')
        with self.assertRaises(ValueError):session_context('2026-11-13T05:00:00Z','2026-11-13')

class Archive(unittest.TestCase):
    def setUp(self):
        self.gh=MemoryGit();self.key='SYNTHETIC_TEST_ONLY_KEY';self.ctx=patch('c3_early_source_v1.session_context',context);self.ctx.start()
        self.env=patch.dict(os.environ,{'GITHUB_RUN_ID':'101','GITHUB_RUN_ATTEMPT':'1'});self.env.start()
    def tearDown(self):self.ctx.stop();self.env.stop()
    def save(self,rs=None,m=None):
        rs=rs or rows();return publish(raw_csv(rs),rs,m or meta(rs),self.gh,self.key)
    def test_same_source_is_deduplicated_and_only_research_paths_written(self):
        self.save();before=len(self.gh.blobs);r=self.save();self.assertEqual(r['status'],'ALREADY_RECORDED');self.assertEqual(len(self.gh.blobs),before)
        self.assertTrue(all(p.startswith(PREFIX) for p in self.gh.paths))
    def test_new_price_version_preserves_previous_and_old_replay_cannot_roll_back(self):
        self.save();rs=rows();rs[0]['close']=106
        with patch.dict(os.environ,{'GITHUB_RUN_ID':'102'}):r=self.save(rs,meta(rs,'b','2026-11-12T15:00:00Z'))
        self.assertEqual(r['state'],'PRICE_REVISION');self.assertEqual(r['price_difference']['changed_fields']['close'],1)
        with patch.dict(os.environ,{'GITHUB_RUN_ID':'103'}):old=self.save()
        self.assertFalse(old['latest_advanced']);pointer=json.loads(self.gh.file(PREFIX+'days/2026-11-12.json',self.gh.current));self.assertEqual(pointer['file_commit'],'b'*40)
        self.assertEqual(len([p for p in self.gh.trees[self.gh.current] if '/versions/' in p]),2)
    def test_exact_day_loader_checks_raw_and_normalized_hashes(self):
        self.save()
        with tempfile.TemporaryDirectory() as root:
            rs,proof=load_prefetch('2026-11-12',root,self.gh,self.key);self.assertEqual(rs,rows());self.assertTrue(proof['early_archive_used'])
            with self.assertRaises(ValueError):load_prefetch('2026-11-13',root,self.gh,self.key)
    def test_corrupted_encrypted_object_is_never_reused(self):
        self.save();tree=self.gh.trees[self.gh.current];obj=next(p for p in tree if '/objects/' in p);self.gh.blobs[tree[obj]]=b'broken'
        with self.assertRaises(Exception):self.save()
    def test_tampered_input_cannot_be_published(self):
        m=meta();m['raw_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'HASH'):self.save(m=m)

if __name__=='__main__':unittest.main()
