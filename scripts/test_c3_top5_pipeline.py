"""Exercise actual embedded workflow code offline; every HTTP call is forbidden or mocked."""
import ast
import collections
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from c3_top5_financial_selection import select, entry_state
from c3_top5_financial_preview import render
from test_c3_top5_financial_selection import candidate, record, evidence, ASOF

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO/'.github/workflows/c3_top5_daily_telegram.yml'

def embedded(name):
    lines = WORKFLOW.read_text().splitlines()
    step = next(i for i, line in enumerate(lines) if line.strip() == '- name: '+name)
    start = next(i for i in range(step+1, len(lines)) if " - <<'PY'" in lines[i])+1
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == 'PY')
    return '\n'.join(line[10:] for line in lines[start:end])

BUILD = 'Build finance-first conditional signal delivery manifest'
DELIVERY = 'Validate delivery on every run; send only on scheduled main'
NO_HTTP = """
import urllib.request
def forbidden(*a, **k): raise AssertionError('NETWORK_FORBIDDEN')
urllib.request.urlopen = forbidden
"""

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cwd = Path(self.tmp.name)
        self.root = self.cwd/'output/c3_top5'
        self.root.mkdir(parents=True)
        self.env = {'PATH':os.environ.get('PATH', ''), 'PYTHONPATH':str(REPO/'scripts'),
                    'GITHUB_EVENT_NAME':'workflow_dispatch', 'GITHUB_REF_NAME':'audit-test',
                    'GITHUB_RUN_ID':'offline', 'C3_TEST_SEND_TELEGRAM':'false'}

    def write(self, name, value):
        p = self.root/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value))

    def execute(self, name, prefix=NO_HTTP):
        return subprocess.run([sys.executable, '-c', prefix+'\n'+embedded(name)],
                              cwd=self.cwd, env=self.env, capture_output=True, text=True)

    def prepare(self, empty=False, count=1):
        c = candidate(name='검증용')
        end = datetime.strptime(ASOF, '%Y%m%d')
        c['bars'] = [dict(date=(end-timedelta(days=59-i)).strftime('%Y%m%d'),
            open=9800, high=10100, low=9700, close=9900, volume=10000+i*500) for i in range(60)]
        codes = [str(111111+i*111111) for i in range(count)] if not empty else []
        expiry='2026-11-23T15:30:00+09:00'
        pool = dict(asof=ASOF, entry_valid_until=expiry,candidates=[dict(c, code=code) for code in codes])
        geometry = dict(asof=ASOF, candidates=[candidate(code, name='검증용') for code in codes])
        financial = evidence(*(record(code) for code in codes),
                             status='FINANCIAL_RESEARCH_GATE_PASSED' if codes else 'NO_CANDIDATES')
        selection = select(geometry, financial)
        self.write('qualified_chart_pool.json', pool)
        self.write('financial_pool_gate.json', financial)
        self.write('financial_selection_research.json', selection)
        self.write('receipt.json', dict(asof=ASOF,entry_valid_until=expiry,source_integrity=dict(
            session_count=60, last_session=ASOF, market_rows_min=dict(KOSPI=935, KOSDAQ=1836))))
        images = render(pool, selection, self.root/'financial_preview')
        self.write('financial_preview/financial_preview_manifest.json', dict(asof=ASOF, images=images))
        report = subprocess.run([sys.executable, str(REPO/'scripts/c3_all_candidate_report.py'),
            '--pool', str(self.root/'qualified_chart_pool.json'),
            '--selection', str(self.root/'financial_selection_research.json'),
            '--financial', str(self.root/'financial_pool_gate.json'),
            '--out', str(self.root/'all_candidate_report')], cwd=self.cwd, env=self.env,
            capture_output=True, text=True)
        self.assertEqual(report.returncode, 0, report.stderr)
        built = self.execute(BUILD)
        self.assertEqual(built.returncode, 0, built.stderr)
        return pool, selection

    def result(self):
        return json.loads((self.root/'delivery_result.json').read_text())

    def test_every_embedded_python_block_compiles(self):
        lines = WORKFLOW.read_text().splitlines()
        count = 0
        for i, line in enumerate(lines):
            if " - <<'PY'" in line:
                end = next(j for j in range(i+1, len(lines)) if lines[j].strip() == 'PY')
                compile('\n'.join(x[10:] for x in lines[i+1:end]), str(WORKFLOW), 'exec')
                count += 1
        self.assertGreaterEqual(count, 5)

    def test_collection_state_matches_selection_contract(self):
        code = embedded('Collect KRX sessions and render one classic image per stock')
        tree = ast.parse(code)
        assignment = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == 'entry_status' for t in n.targets))
        for low, high, close in ((9800,10000,9790), (9800,10000,9800),
                                 (9800,10000,10000), (9800,10000,10100), (9800,10000,10300)):
            ns = dict(entry_lo=low, entry_hi=high, last=close,
                      entry_gap_pct=max(low-close,0,close-high)/close*100)
            exec(compile(ast.Module(body=[assignment], type_ignores=[]), '<entry-state>', 'exec'), ns)
            self.assertEqual(ns['entry_status'], entry_state(low,high,close))

    def test_krx_ingestion_keeps_official_alphanumeric_codes(self):
        tree=ast.parse(embedded('Collect KRX sessions and render one classic image per stock'))
        condition=next(n.test for n in ast.walk(tree) if isinstance(n,ast.If)
                       and 'code.isascii()' in ast.unparse(n.test))
        check=compile(ast.Expression(condition),'<KRX-row-validation>','eval')
        for code in ('005930','0220W0','0220WL'):
            self.assertFalse(eval(check,dict(code=code,o=100,h=110,l=90,c=100,vol=100,val=10000)))
        for code in ('0220w0','１２３４５６','../../','12345','1234567'):
            self.assertTrue(eval(check,dict(code=code,o=100,h=110,l=90,c=100,vol=100,val=10000)))

    def test_actual_renderers_and_delivery_dry_run_agree(self):
        self.prepare()
        p = self.execute(DELIVERY)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.result()['status'], 'DRY_RUN')
        self.assertEqual(self.result()['telegram_photos_sent'], 0)
        self.assertFalse((self.cwd/'receipts').exists())

    def test_deployment_push_is_dry_run_even_on_main(self):
        self.prepare()
        self.env.update(GITHUB_EVENT_NAME='push',GITHUB_REF_NAME='main')
        p=self.execute(DELIVERY)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.result()['status'],'DRY_RUN')
        self.assertEqual(self.result()['telegram_photos_sent'],0)

    def ingest(self, snapshots):
        tree=ast.parse(embedded('Collect KRX sessions and render one classic image per stock'))
        number=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='num')
        loop=next(n for n in ast.walk(tree) if isinstance(n,ast.For)
                  and isinstance(n.target,ast.Name) and n.target.id=='r'
                  and isinstance(n.iter,ast.Name) and n.iter.id=='rows')
        import math
        scope=dict(math=math,data=collections.defaultdict(dict),names={},
                   rejected_rows=collections.Counter(),dated_rows_checked=0,market='KOSPI',
                   rejected_row_reasons=collections.defaultdict(collections.Counter))
        exec(compile(ast.Module(body=[number],type_ignores=[]),'<real-number-parser>','exec'),scope)
        code=compile(ast.Module(body=[loop],type_ignores=[]),'<real-KRX-ingestion>','exec')
        for day,row in snapshots:
            scope.update(ds=day,rows=[row]);exec(code,scope)
        return scope

    def row(self, day='20261120',name='현재 회사명'):
        return dict(BAS_DD=day,ISU_CD='005930',ISU_NM=name,TDD_OPNPRC='9900',
                    TDD_HGPRC='10100',TDD_LWPRC='9800',TDD_CLSPRC='10000',
                    ACC_TRDVOL='1000',ACC_TRDVAL='10000000')

    def test_newest_company_name_survives_historical_rename(self):
        x=self.ingest([('20261120',self.row()),('20261119',self.row('20261119','이전 회사명'))])
        self.assertEqual(x['names'][('KOSPI','005930')],'현재 회사명')
        self.assertEqual(x['dated_rows_checked'],2)

    def test_duplicate_source_rows_fail_instead_of_overwriting(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE_KRX_TICKER'):
            self.ingest([('20261120',self.row()),('20261120',self.row())])

    def test_wrong_source_date_is_a_data_error(self):
        with self.assertRaisesRegex(ValueError,'KRX_ROW_DATE_MISMATCH'):
            self.ingest([('20261120',self.row('20261119'))])

    def test_zero_turnover_is_distinct_from_corrupt_ohlcv_and_never_filled(self):
        for changes, reason in ((dict(ACC_TRDVOL='0',ACC_TRDVAL='0'),
                                'NO_TRADING_OR_SUSPENSION_UNCONFIRMED'),
                               (dict(TDD_HGPRC='9000'), 'INVALID_OHLCV_VALUES_OR_ORDER'),
                               (dict(TDD_HGPRC='9000',ACC_TRDVOL='0',ACC_TRDVAL='0'),
                                'INVALID_OHLCV_VALUES_OR_ORDER'),
                               (dict(TDD_CLSPRC='NaN'), 'MISSING_OR_NONFINITE_VALUE')):
            with self.subTest(changes=changes):
                x=self.ingest([('20261120',{**self.row(),**changes})])
                self.assertEqual(x['rejected_row_reasons']['KOSPI'][reason],1)
                self.assertFalse(x['data'])

    def test_price_discontinuities_are_excluded_before_support_calculation(self):
        tree=ast.parse(embedded('Collect KRX sessions and render one classic image per stock'))
        loop=next(n for n in ast.walk(tree) if isinstance(n,ast.For)
                  and isinstance(n.target,ast.Tuple) and
                  [getattr(x,'id',None) for x in n.target.elts]==['key','s'])
        bars=lambda closes:{str(i):(c,c+10,c-10,100,10000,c) for i,c in enumerate(closes)}
        import statistics
        scope=dict(data={('KOSPI','GOOD'):bars([100,110,120]),
                         ('KOSPI','SPLIT'):bars([100,100,50])},
                   days=['0','1','2'],large_moves=[],eligible={},statistics=statistics,
                   bench=collections.defaultdict(list))
        # Use 60 actual positions, as required by the existing benchmark formula.
        scope['days']=[str(i) for i in range(60)]
        scope['data']={('KOSPI','GOOD'):bars([100]*60),
                       ('KOSPI','SPLIT'):bars([100]*59+[50])}
        exec(compile(ast.Module(body=[loop],type_ignores=[]),'<real-series-validation>','exec'),scope)
        self.assertEqual(list(scope['eligible']),[('KOSPI','GOOD')])
        self.assertEqual(len(scope['large_moves']),1)

    def test_empty_selection_is_normal_cash(self):
        self.prepare(empty=True)
        p = self.execute(DELIVERY)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.result()['status'], 'CASH')

    def test_financial_failure_is_nonzero_and_not_cash(self):
        self.write('financial_selection_research.json', dict(status='ERROR_FINANCIAL_EVIDENCE',
                    financial_evidence_status='MISSING_DART_KEY'))
        self.write('receipt.json', dict(asof=ASOF))
        self.execute(BUILD)
        p = self.execute(DELIVERY)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.result()['status'], 'ERROR')
        self.assertEqual(self.result()['stage'], 'FINANCIAL_VERIFICATION')

    def test_missing_image_blocks_delivery(self):
        self.prepare()
        next((self.root/'all_candidate_report').glob('*.png')).unlink()
        p = self.execute(DELIVERY)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('MISSING_CANDIDATE_IMAGE', self.result()['error'])
        self.assertEqual(self.result()['telegram_photos_sent'], 0)

    def test_mutated_risk_or_status_cannot_reach_delivery(self):
        self.prepare()
        path = self.root/'all_candidate_report/manifest.json'
        original = json.loads(path.read_text())
        for change in (dict(stop_ref=9400), dict(asof_close=9790, status='NEAR_ENTRY'),
                       dict(status='WATCH'), dict(r1_ref=9900),dict(entry_valid_until='2026-11-24')):
            report = copy.deepcopy(original)
            report['candidates'][0].update(change)
            path.write_text(json.dumps(report))
            p = self.execute(DELIVERY)
            self.assertNotEqual(p.returncode, 0)
            self.assertEqual(self.result()['status'], 'ERROR')

    def test_renderer_blocks_wrong_source_date(self):
        pool, selection = self.prepare()
        pool['candidates'][0]['bars'][-1]['date'] = '20261119'
        with self.assertRaisesRegex(ValueError, 'CHART_SOURCE_MISMATCH'):
            render(pool, selection, self.root/'bad-preview')

    def test_valid_but_replaced_png_is_rejected(self):
        self.prepare()
        from PIL import Image
        path = next((self.root/'all_candidate_report').glob('*.png'))
        with Image.open(path) as original:
            changed = original.copy()
        changed.putpixel((0, 0), (123, 45, 67))
        changed.save(path)
        p = self.execute(DELIVERY)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('IMAGE_HASH_MISMATCH', self.result()['error'])

    def test_otherwise_valid_report_prices_must_match_rendered_png(self):
        self.prepare()
        path = self.root/'all_candidate_report/manifest.json'
        report = json.loads(path.read_text())
        report['candidates'][0].update(entry_low=9810)
        path.write_text(json.dumps(report))
        p = self.execute(DELIVERY)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('IMAGE_CONTENT_MISMATCH', self.result()['error'])

    def test_ok_response_without_message_id_is_never_sent(self):
        self.prepare()
        self.env.update(GITHUB_EVENT_NAME='schedule', GITHUB_REF_NAME='main',
                        GITHUB_REPOSITORY='offline/example', GH_TOKEN='fake',
                        TELEGRAM_BOT_TOKEN='fake', TELEGRAM_CHAT_ID='fake')
        prefix = '''
import io,json,urllib.request
class Response(io.BytesIO):
    def __init__(self, status, payload):
        super().__init__(json.dumps(payload).encode()); self.status=status
def fake(req, **kwargs):
    if '/contents/' in req.full_url: return Response(201, {})
    return Response(200, {'ok':True,'result':{}})
urllib.request.urlopen=fake
'''
        p = self.execute(DELIVERY, prefix)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.result()['status'], 'ERROR')
        self.assertEqual(self.result()['stage'], 'TELEGRAM_SEND')
        self.assertEqual(self.result()['telegram_photos_sent'], 0)
        self.assertIn('TELEGRAM_MESSAGE_ID_MISSING', self.result()['error'])

    def test_caption_free_payload_and_message_receipt_offline(self):
        self.prepare()
        # Entire send branch runs against an in-process fake, never the network.
        self.env.update(GITHUB_EVENT_NAME='schedule', GITHUB_REF_NAME='main',
                        GITHUB_REPOSITORY='offline/example', GH_TOKEN='fake',
                        TELEGRAM_BOT_TOKEN='fake', TELEGRAM_CHAT_ID='fake')
        prefix = '''
import io,json,urllib.request
class Response(io.BytesIO):
    def __init__(self, status, payload):
        super().__init__(json.dumps(payload).encode()); self.status=status
calls=[]
def fake(req, **kwargs):
    calls.append(req.full_url)
    if '/contents/' in req.full_url:
        assert len(calls)==1
        return Response(201, {})
    assert req.full_url=='https://api.telegram.org/botfake/sendPhoto'
    assert b'name="caption"' not in req.data
    return Response(200, {'ok':True,'result':{'message_id':123}})
urllib.request.urlopen=fake
'''
        p = self.execute(DELIVERY, prefix)
        self.assertEqual(p.returncode, 0, p.stderr)
        result = self.result()
        self.assertEqual(result['status'], 'SENT')
        self.assertEqual(result['photos'][0]['telegram_message_id'], 123)
        self.assertEqual(result['telegram_photos_sent'], 1)
        self.assertEqual(len(result['photos'][0]['image_sha256']), 64)

    def test_partial_send_failure_preserves_first_receipt_without_retry(self):
        self.prepare(count=2)
        self.env.update(GITHUB_EVENT_NAME='schedule', GITHUB_REF_NAME='main',
                        GITHUB_REPOSITORY='offline/example', GH_TOKEN='fake',
                        TELEGRAM_BOT_TOKEN='fake', TELEGRAM_CHAT_ID='fake')
        prefix = '''
import io,json,urllib.request,urllib.error
class Response(io.BytesIO):
    def __init__(self, status, payload):
        super().__init__(json.dumps(payload).encode()); self.status=status
calls=[]
def fake(req, **kwargs):
    calls.append(req.full_url)
    if len(calls)==1: return Response(201, {})
    if len(calls)==2: return Response(200, {'ok':True,'result':{'message_id':123}})
    raise urllib.error.URLError('credential-bearing URL must not enter receipt')
urllib.request.urlopen=fake
'''
        p = self.execute(DELIVERY, prefix)
        self.assertNotEqual(p.returncode, 0)
        result = self.result()
        self.assertEqual(result['status'], 'ERROR')
        self.assertEqual(result['stage'], 'TELEGRAM_SEND')
        self.assertEqual(result['telegram_photos_sent'], 1)
        self.assertEqual(result['photos'][0]['telegram_message_id'], 123)
        self.assertEqual(result['error'], 'URLError')

    def test_failed_reservation_blocks_all_sends(self):
        self.prepare()
        self.env.update(GITHUB_EVENT_NAME='schedule', GITHUB_REF_NAME='main',
                        GITHUB_REPOSITORY='offline/example', GH_TOKEN='fake',
                        TELEGRAM_BOT_TOKEN='fake', TELEGRAM_CHAT_ID='fake')
        prefix = '''
import io,urllib.request
class Response(io.BytesIO):
    status=422
def fake(req, **kwargs):
    assert '/contents/' in req.full_url
    return Response(b'{}')
urllib.request.urlopen=fake
'''
        p = self.execute(DELIVERY, prefix)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.result()['stage'], 'SEND_RESERVATION')
        self.assertEqual(self.result()['telegram_photos_sent'], 0)

if __name__ == '__main__': unittest.main()
