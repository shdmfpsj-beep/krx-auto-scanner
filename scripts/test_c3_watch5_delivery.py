"""WATCH5 selection, actual classic rendering and mocked transport boundaries."""
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import patch
from PIL import Image

from c3_watch5_delivery import choose, run, image_bytes, LABEL
from c3_candidate_decisions import report as decisions
from c3_top5_financial_selection import select
from test_c3_approval_scope import fact, financial
from test_c3_top5_financial_selection import candidate, ASOF

REPO = Path(__file__).resolve().parents[1]
CLOCK = datetime(2026, 11, 23, 8, tzinfo=ZoneInfo('Asia/Seoul'))
EXPIRY = '2026-11-23T15:30:00+09:00'


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False))


def fixture(root, watches=2, top5=0):
    root.mkdir(parents=True, exist_ok=True)
    charts = [candidate(str(100000+i), 'ENTRY_READY' if i < top5 else 'WATCH',
        close=9900 if i < top5 else 10300, name='합성 검증용', opportunity_score=90-i)
        for i in range(top5+watches)]
    end = datetime.strptime(ASOF, '%Y%m%d')
    for row in charts:
        row['bars'] = [dict(date=(end-timedelta(days=59-i)).strftime('%Y%m%d'),
            open=row['close']-10, high=row['close']+100, low=row['close']-100,
            close=row['close'], volume=10000+i) for i in range(60)]
    geometry = dict(asof=ASOF, entry_valid_until=EXPIRY, candidates=charts)
    pool = {**copy.deepcopy(geometry), 'fixture_kind':'SYNTHETIC_NOT_MARKET_SELECTION'}
    finance = financial(*(fact(c['code']) for c in charts))
    selection = select(geometry, finance)
    receipt = dict(asof=ASOF, entry_valid_until=EXPIRY, source_integrity=dict(
        session_count=60, last_session=ASOF, market_rows_min=dict(KOSPI=935, KOSDAQ=1836)))
    for name, obj in dict(receipt=receipt, entry_geometry_audit=geometry,
        qualified_chart_pool=pool, financial_pool_gate=finance,
        financial_selection_research=selection,
        duplicate_signal_audit=dict(blocked_codes=[], sessions=20),
        candidate_decisions=decisions(receipt, geometry, selection, finance),
        execution_outcome=dict(asof=ASOF, operational_status=selection['operational_status'], program_status='COMPLETED'),
        delivery_result=dict(asof=ASOF, status='DRY_RUN' if top5 else 'CASH', photos=[], telegram_photos_sent=0)).items():
        write(root/(name+'.json'), obj)
    rendered = subprocess.run([sys.executable, str(REPO/'scripts/c3_all_candidate_report.py'),
        '--pool', str(root/'qualified_chart_pool.json'), '--selection', str(root/'financial_selection_research.json'),
        '--financial', str(root/'financial_pool_gate.json'), '--out', str(root/'all_candidate_report')],
        capture_output=True, text=True)
    if rendered.returncode: raise AssertionError(rendered.stderr)
    return json.loads((root/'all_candidate_report/manifest.json').read_text()), selection


class Response(io.BytesIO):
    def __init__(self, status, body):
        super().__init__(json.dumps(body).encode()); self.status=status


class Transport:
    def __init__(self, duplicate=False, fail_at=None, bad_response=None):
        self.calls=[]; self.sent=0; self.duplicate=duplicate; self.fail_at=fail_at; self.bad_response=bad_response
    def __call__(self, request, timeout):
        self.calls.append(request)
        if request.full_url.startswith('https://api.github.com/'):
            if self.duplicate: raise urllib.error.HTTPError(request.full_url,422,'exists',{},None)
            return Response(201,{})
        self.sent+=1
        if self.sent==self.fail_at: raise urllib.error.HTTPError(request.full_url,503,'token-bearing URL',{},None)
        return Response(200,self.bad_response or dict(ok=True,result=dict(message_id=100+self.sent,chat=dict(id=-123))))


class WatchSelectionTests(unittest.TestCase):
    def inputs(self, count=1):
        rows=[{**candidate(str(100000+i), 'WATCH', close=10300), 'asof_close':10300,
               'financial_verdict':'PASS','financial_eligibility':'WATCH_ONLY','composite_score':70}
              for i in range(count)]
        return dict(asof=ASOF,candidates=rows), dict(asof=ASOF,operational_status='CASH_NO_ELIGIBLE',
            selected=[],financial_verdicts={r['code']:'PASS' for r in rows})
    def test_watch_only_financial_eligibility_does_not_override_actual_pass(self):
        report, selection=self.inputs();self.assertEqual(len(choose(report,selection,set())),1)
    def test_financial_review_rejection_error_and_cross_field_mismatch_are_excluded(self):
        for verdict in ('REVIEW_REQUIRED','REJECTED_FINANCIAL_RISK','ERROR',None):
            report,selection=self.inputs();report['candidates'][0]['financial_verdict']=verdict
            self.assertEqual(choose(report,selection,set()),[])
            report['candidates'][0]['financial_verdict']='PASS';selection['financial_verdicts']['100000']=verdict
            self.assertEqual(choose(report,selection,set()),[])
    def test_exact_five_percent_risk_allowed_but_above_five_blocked(self):
        report,selection=self.inputs();row=report['candidates'][0]
        row.update(stop_ref=9500,risk_pct=5);self.assertEqual(len(choose(report,selection,set())),1)
        row.update(stop_ref=9490,risk_pct=5.1);self.assertEqual(choose(report,selection,set()),[])
    def test_distance_boundaries_two_exclusive_five_inclusive(self):
        for high, expected in ((9800,0),(9790,1),(9500,1),(9490,0)):
            report,selection=self.inputs();row=report['candidates'][0]
            row.update(asof_close=10000,entry_high=high,entry_low=high-100,stop_ref=high-300,risk_pct=300/high*100)
            self.assertEqual(len(choose(report,selection,set())),expected)
    def test_empty_and_inverted_entry_intervals_are_not_repaired(self):
        report,selection=self.inputs();report['candidates'][0]['entry_low']=10001
        self.assertEqual(choose(report,selection,set()),[])
    def test_top5_and_twenty_session_blocked_codes_never_overlap(self):
        report,selection=self.inputs(3);selection['selected']=[dict(code='100000')]
        self.assertEqual([r['code'] for r in choose(report,selection,{'100001'})],['100002'])
    def test_maximum_five_and_score_distance_code_sort(self):
        report,selection=self.inputs(7);report['candidates'][6]['composite_score']=90
        report['candidates'][5]['asof_close']=10250
        actual=[r['code'] for r in choose(report,selection,set())]
        self.assertEqual(actual,['100006','100005','100000','100001','100002'])
    def test_hold_and_error_are_blocked(self):
        report,selection=self.inputs()
        for state in ('HOLD_FINANCIAL_UNVERIFIED','HOLD_DATA_INCOMPLETE','ERROR'):
            selection['operational_status']=state;self.assertEqual(choose(report,selection,set()),[])
    def test_dates_duplicates_and_top5_overflow_fail_closed(self):
        report,selection=self.inputs();selection['asof']='20261119'
        with self.assertRaises(ValueError):choose(report,selection,set())
        report,selection=self.inputs();report['candidates']*=2
        with self.assertRaises(ValueError):choose(report,selection,set())
        report,selection=self.inputs();selection['selected']=[dict(code=str(i)) for i in range(6)]
        with self.assertRaises(ValueError):choose(report,selection,set())


class WatchPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'output/c3_top5'
        self.env=dict(C3_FINANCIAL_MODEL='balanced',GITHUB_EVENT_NAME='workflow_dispatch',
            GITHUB_REF_NAME='main',GITHUB_REPOSITORY='shdmfpsj-beep/krx-auto-scanner',GITHUB_RUN_ID='mock',
            TELEGRAM_BOT_TOKEN='never-print-token',TELEGRAM_CHAT_ID='-123',GH_TOKEN='never-print-gh')
        if os.environ.get('C3_FONT_DIR'):self.env['C3_FONT_DIR']=os.environ['C3_FONT_DIR']
    def execute(self, **kwargs):return run(self.root,self.env,clock=CLOCK,**kwargs)
    def read(self,name):return json.loads((self.root/name).read_text())
    def forbid(self,*args,**kwargs):self.fail('Network forbidden in DRY_RUN')
    def test_cash_with_two_watch_images_preserves_official_results(self):
        fixture(self.root)
        before={n:hashlib.sha256((self.root/n).read_bytes()).hexdigest() for n in
                ('financial_selection_research.json','execution_outcome.json','delivery_result.json','receipt.json')}
        result=self.execute(opener=self.forbid)
        self.assertEqual((result['status'],result['selected_count'],result['telegram_photos_sent']),('DRY_RUN',2,0))
        self.assertEqual(len(list((self.root/'watch5').glob('*.png'))),2)
        for n,digest in before.items():self.assertEqual(hashlib.sha256((self.root/n).read_bytes()).hexdigest(),digest)
        for item in result['selected']:
            self.assertFalse(item['trade_approved']);self.assertEqual(item['watch_identity']['label'],LABEL)
            with Image.open(self.root/'watch5'/item['image']) as image:
                self.assertEqual(image.size,(1400,1810));self.assertFalse(json.loads(image.info['c3_watch5'])['trade_approved'])
            self.assertTrue(image_bytes(self.root,item))
        self.assertFalse((self.root.parents[1]/'receipts').exists())
    def test_five_top5_and_five_watch_remain_separate_maximum_ten(self):
        _,selection=fixture(self.root,watches=5,top5=5)
        result=self.execute(opener=self.forbid)
        self.assertEqual(result['status'],'DRY_RUN',result)
        self.assertEqual(len(selection['selected'])+result['selected_count'],10)
        self.assertFalse({r['code'] for r in selection['selected']} & {r['code'] for r in result['selected']})
    def test_empty_watch_generates_no_images(self):
        fixture(self.root,watches=0,top5=1)
        result=self.execute(opener=self.forbid)
        self.assertEqual((result['status'],result['selected_count']),('EMPTY',0))
        self.assertEqual(list((self.root/'watch5').glob('*.png')),[])
    def test_older_actual_validation_outcome_without_asof_is_compatible(self):
        fixture(self.root);obj=self.read('execution_outcome.json');obj.pop('asof');write(self.root/'execution_outcome.json',obj)
        self.assertEqual(self.execute(opener=self.forbid)['status'],'DRY_RUN')
    def test_manual_pr_and_feature_schedule_never_reserve_or_send(self):
        fixture(self.root)
        for event,branch in [('workflow_dispatch','main'),('pull_request','main'),('push','main'),('schedule','feature')]:
            self.env.update(GITHUB_EVENT_NAME=event,GITHUB_REF_NAME=branch)
            self.assertEqual(self.execute(opener=self.forbid)['status'],'DRY_RUN')
    def test_schedule_main_validates_multipart_response_and_create_only_reservation(self):
        fixture(self.root);self.env['GITHUB_EVENT_NAME']='schedule';transport=Transport()
        result=self.execute(opener=transport)
        self.assertEqual((result['status'],result['telegram_photos_sent']),('SENT',2),result)
        marker=json.loads(transport.calls[0].data)
        self.assertNotIn('sha',marker);self.assertIn('/receipts/c3_watch5_daily/'+ASOF+'.json',transport.calls[0].full_url)
        self.assertEqual([x['telegram_message_id'] for x in result['photos']],[101,102])
        for request in transport.calls[1:]:
            msg=BytesParser(policy=default).parsebytes(('Content-Type: '+request.headers['Content-type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+request.data)
            parts=list(msg.iter_parts());self.assertEqual(len(parts),2)
            self.assertEqual(parts[0].get_payload(decode=True),b'-123')
            self.assertEqual(parts[1].get_content_type(),'image/png');self.assertTrue(parts[1].get_filename().endswith('_watch.png'))
            self.assertTrue(parts[1].get_payload(decode=True).startswith(b'\x89PNG'))
        self.assertNotIn('never-print',json.dumps(result))
    def test_existing_reservation_blocks_all_telegram_calls(self):
        fixture(self.root);self.env['GITHUB_EVENT_NAME']='schedule';transport=Transport(duplicate=True)
        result=self.execute(opener=transport)
        self.assertEqual(result['status'],'BLOCKED');self.assertEqual(len(transport.calls),1)
        self.assertEqual(result['telegram_photos_sent'],0)
    def test_partial_failure_keeps_successes_and_never_retries(self):
        fixture(self.root);self.env['GITHUB_EVENT_NAME']='schedule';transport=Transport(fail_at=2)
        result=self.execute(opener=transport)
        self.assertEqual((result['status'],result['telegram_photos_sent']),('PARTIAL_ERROR',1))
        self.assertEqual(result['photos'][0]['telegram_message_id'],101)
        self.assertEqual(len(transport.calls),3);self.assertFalse(result['automatic_retry'])
        self.assertNotIn('never-print',json.dumps(result));self.assertEqual(self.read('execution_outcome.json')['operational_status'],'CASH_NO_ELIGIBLE')
    def test_invalid_message_id_chat_or_ok_never_becomes_sent(self):
        fixture(self.root);self.env['GITHUB_EVENT_NAME']='schedule'
        for answer in [dict(ok=False),dict(ok=True,result=dict(message_id=True,chat=dict(id=-123))),
                       dict(ok=True,result=dict(message_id=9,chat=dict(id=-999)))]:
            result=self.execute(opener=Transport(bad_response=answer))
            self.assertNotEqual(result['status'],'SENT');self.assertFalse(result['automatic_retry'])
    def test_hash_and_metadata_mismatch_block_before_network(self):
        fixture(self.root);manifest=self.read('all_candidate_report/manifest.json')
        row=manifest['candidates'][0];p=self.root/'all_candidate_report'/row['image'];p.write_bytes(p.read_bytes()+b'corrupt')
        result=self.execute(opener=self.forbid)
        self.assertEqual(result['status'],'ERROR');self.assertEqual(result['reason'],'WATCH_SOURCE_IMAGE_HASH_MISMATCH')
    def test_generated_image_hash_mismatch_blocks_before_reservation(self):
        fixture(self.root);self.env['GITHUB_EVENT_NAME']='schedule'
        import c3_watch5_delivery as module
        original=module.render
        def corrupt(*args,**kwargs):
            item=original(*args,**kwargs);p=self.root/'watch5'/item['image'];p.write_bytes(p.read_bytes()+b'corrupt');return item
        with patch.object(module,'render',side_effect=corrupt):result=self.execute(opener=self.forbid)
        self.assertEqual(result['reason'],'WATCH_OUTPUT_IMAGE_HASH_MISMATCH')
    def test_rehashed_source_with_wrong_png_metadata_is_blocked(self):
        from PIL.PngImagePlugin import PngInfo
        fixture(self.root);manifest=self.read('all_candidate_report/manifest.json')
        row=manifest['candidates'][0];path=self.root/'all_candidate_report'/row['image']
        with Image.open(path) as source:
            image=source.copy();identity=json.loads(source.info['c3_candidate'])
        identity['asof']='20261119';info=PngInfo();info.add_text('c3_candidate',json.dumps(identity))
        image.save(path,pnginfo=info);row['image_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        write(self.root/'all_candidate_report/manifest.json',manifest)
        self.assertEqual(self.execute(opener=self.forbid)['reason'],'WATCH_SOURCE_IMAGE_IDENTITY_MISMATCH')
    def test_pass_labels_cannot_override_unverified_financial_original(self):
        fixture(self.root);obj=self.read('financial_pool_gate.json')
        obj['researched'][0]['risk_assessment']['mandatory_missing']=['BORROWING_TOTAL']
        write(self.root/'financial_pool_gate.json',obj)
        self.assertEqual(self.execute(opener=self.forbid)['reason'],'WATCH_FINANCIAL_SOURCE_MISMATCH')
    def test_reused_output_removes_only_stale_watch_previews_on_hold(self):
        fixture(self.root);self.assertEqual(self.execute(opener=self.forbid)['selected_count'],2)
        outcome=self.read('execution_outcome.json');outcome['operational_status']='HOLD_DATA_INCOMPLETE'
        write(self.root/'execution_outcome.json',outcome)
        original=(self.root/'all_candidate_report/manifest.json').read_bytes()
        result=self.execute(opener=self.forbid)
        self.assertEqual(result['status'],'BLOCKED');self.assertFalse(list((self.root/'watch5').glob('*.png')))
        self.assertEqual((self.root/'all_candidate_report/manifest.json').read_bytes(),original)
    def test_date_and_financial_source_mismatch_block_before_network(self):
        fixture(self.root)
        for name,key,value in [('receipt.json','asof','20261119'),('financial_pool_gate.json','asof','20261119'),
                                ('execution_outcome.json','asof','20261119')]:
            original=self.read(name);write(self.root/name,{**original,key:value})
            self.assertEqual(self.execute(opener=self.forbid)['reason'],'WATCH_DATE_MISMATCH')
            write(self.root/name,original)
    def test_hold_error_and_legacy_are_blocked_before_images(self):
        fixture(self.root);original=self.read('execution_outcome.json')
        for state in ['HOLD_FINANCIAL_UNVERIFIED','HOLD_DATA_INCOMPLETE','ERROR']:
            write(self.root/'execution_outcome.json',{**original,'operational_status':state})
            self.assertEqual(self.execute(opener=self.forbid)['status'],'BLOCKED')
        write(self.root/'execution_outcome.json',original);self.env['C3_FINANCIAL_MODEL']='legacy'
        self.assertEqual(self.execute(opener=self.forbid)['status'],'NOT_APPLICABLE')
        self.assertFalse(list((self.root/'watch5').glob('*.png')))
    def test_stale_production_date_is_blocked_without_reservation(self):
        fixture(self.root);self.env['GITHUB_EVENT_NAME']='schedule'
        result=run(self.root,self.env,opener=self.forbid,clock=datetime(2026,11,24,8,tzinfo=ZoneInfo('Asia/Seoul')))
        self.assertEqual(result['reason'],'WATCH_PRODUCTION_DATE_OR_VALIDITY_MISMATCH')
    def test_upstream_workflow_failure_blocks_even_with_a_completed_cash_file(self):
        fixture(self.root);self.env.update(GITHUB_EVENT_NAME='schedule',C3_WATCH_UPSTREAM_SUCCESS='false')
        result=self.execute(opener=self.forbid)
        self.assertEqual(result['status'],'BLOCKED');self.assertEqual(result['reason'],'UPSTREAM_WORKFLOW_FAILURE')
    def test_watch_receipts_do_not_block_future_official_top5(self):
        from c3_balanced_validation import recent_signals
        base=self.root.parents[1]
        write(base/'receipts/c3_watch5_daily/20261119.json',dict(asof='20261119',selected=[dict(code='100000')]))
        write(base/'reports/c3_paper/paper_ledger.json',dict(positions={}))
        before=(base/'reports/c3_paper/paper_ledger.json').read_bytes()
        self.assertEqual(recent_signals(ASOF,['20261119',ASOF],base/'receipts/c3_top5_daily',base/'reports/c3_paper/paper_ledger.json'),set())
        self.assertEqual((base/'reports/c3_paper/paper_ledger.json').read_bytes(),before)
    def test_incomplete_live_source_is_recorded_as_blocked_without_fake_asof(self):
        from c3_watch5_validation import validate
        write(self.root/'execution_outcome.json',dict(operational_status='HOLD_DATA_INCOMPLETE',program_status='COMPLETED'))
        proof=validate(self.root,self.root.parents[1]/'blocked-proof','20261124')
        self.assertEqual(proof['status'],'BLOCKED');self.assertIsNone(proof['asof'])
        self.assertEqual(proof['requested_asof'],'20261124');self.assertEqual(proof['network_calls'],0)
    def test_workflow_checkout_timeout_and_top5_independence(self):
        workflow=(REPO/'.github/workflows/c3_top5_daily_telegram.yml').read_text()
        start=workflow.index('      - name: Checkout minimal OpenDART research adapter')
        end=workflow.index('      - name: Restore KRX research outputs after checkout')
        self.assertIn('scripts/c3_watch5_delivery.py',workflow[start:end])
        self.assertIn('timeout-minutes: 35',workflow);self.assertNotIn('  schedule:',workflow);self.assertIn('  workflow_dispatch:',workflow)
        self.assertNotIn('  schedule:',(REPO/'.github/workflows/c3_operating_recovery.yml').read_text())
        watch=workflow[workflow.index('      - name: Deliver separate WATCH5 observation images'):]
        self.assertIn('continue-on-error: true',watch)
        self.assertIn('if: always()',watch);self.assertIn("C3_WATCH_UPSTREAM_SUCCESS: ${{ job.status == 'success' }}",watch)
        self.assertLess(workflow.index('Publish operational outcome without sending'),workflow.index('Deliver separate WATCH5'))
        # GitHub rejects status-check functions inside env expressions, even
        # though they are valid in step.if. Reproduce the post-merge parser rule.
        import re
        env_indent=None
        for line in workflow.splitlines():
            indent=len(line)-len(line.lstrip())
            if line.strip()=='env:':env_indent=indent;continue
            if env_indent is not None and line.strip() and indent<=env_indent:env_indent=None
            if env_indent is not None:
                self.assertIsNone(re.search(r'\$\{\{\s*(success|failure|cancelled|always)\s*\(',line),line)

    def test_balanced_change_detector_works_when_its_own_file_is_sparse_excluded(self):
        name='.github/workflows/c3_balanced_quality_validation.yml'
        path=REPO/name
        workflow=path.read_text() if path.is_file() else subprocess.check_output(['git','-C',str(REPO),'show','HEAD:'+name],text=True)
        lines=workflow.splitlines();start=next(i for i,s in enumerate(lines) if s.strip()=="python - <<'PY'")+1
        end=next(i for i in range(start,len(lines)) if lines[i].strip()=='PY')
        code='\n'.join(s[10:] for s in lines[start:end])
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp)
            def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.STDOUT,text=True).strip()
            git('init');git('config','user.name','WATCH5 test');git('config','user.email','watch5-test@example.invalid')
            daily=repo/'.github/workflows/c3_top5_daily_telegram.yml';daily.parent.mkdir(parents=True)
            daily.write_text('name: unchanged\n')
            control=repo/name
            control.write_text('name: control\n      - name: Detect executable changes and avoid repeating APIs for documentation\n        run: old\n      - uses: actions/setup-python@v5\n')
            git('add','.');git('commit','-m','before');before=git('rev-parse','HEAD')
            daily.write_text(daily.read_text()+'            scripts/c3_watch5_delivery.py\n')
            control.write_text(control.read_text().replace('run: old','run: new'))
            git('add','.');git('commit','-m','watch only')
            git('sparse-checkout','init','--no-cone')
            git('sparse-checkout','set','/.github/workflows/c3_top5_daily_telegram.yml')
            self.assertFalse(control.exists())
            output=repo/'decision.txt'
            env={**os.environ,'BEFORE_SHA':before,'GITHUB_OUTPUT':str(output)}
            process=subprocess.run([sys.executable,'-c',code],cwd=repo,env=env,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr);self.assertIn('execute=false',output.read_text())
            daily.write_text(daily.read_text().replace('unchanged','changed engine setting'))
            git('add','.github/workflows/c3_top5_daily_telegram.yml');git('commit','-m','core change');output.unlink()
            process=subprocess.run([sys.executable,'-c',code],cwd=repo,env=env,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr);self.assertIn('execute=true',output.read_text())


def positive_fixture(root):
    report,selection=fixture(root,watches=5,top5=5)
    env=dict(os.environ,C3_FINANCIAL_MODEL='balanced',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF_NAME='watch-positive-fixture')
    for key in ('TELEGRAM_BOT_TOKEN','TELEGRAM_CHAT_ID','GH_TOKEN'):env.pop(key,None)
    def forbidden(*a,**k):raise AssertionError('WATCH_NETWORK_FORBIDDEN')
    result=run(root,env,opener=forbidden)
    assert result['status']=='DRY_RUN' and result['selected_count']==5,result
    assert len(selection['selected'])==5 and len(report['candidates'])==10
    write(root/'positive_watch5_proof.json',dict(input_kind='SYNTHETIC_NOT_MARKET_SELECTION',
        official_top5=5,watch5=5,maximum_delivery_images=10,status='PASS',
        watch_delivery_status=result['status'],telegram_photos_sent=0))


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--write-positive-fixture':positive_fixture(Path(sys.argv[2]))
    else:unittest.main()
