#!/usr/bin/env python3
"""Isolated live/replay integration, reusing production technical calculations.

No Telegram credentials, send reservation, order, ledger or operating receipt
writes. Outputs live under a new directory. Replays are not live collection.
"""
import argparse
import ast
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from c3_balanced_financials import collect_balanced, SnapshotCache
from c3_top5_financial_selection import financial_review_candidates, REVIEW_SCOPE, APPROVAL_POLICY, select
from c3_all_candidate_report import image_identity
from c3_entry_geometry import sanitize_archived_geometry, audit_archived_zone
from c3_candidate_decisions import report as decision_report, save as save_decisions

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / '.github/workflows/c3_top5_daily_telegram.yml'


def embedded(name):
    lines = WORKFLOW.read_text().splitlines()
    step = next(i for i, line in enumerate(lines) if line.strip() == '- name: ' + name)
    first = next(i for i in range(step+1, len(lines)) if " - <<'PY'" in lines[i]) + 1
    last = next(i for i in range(first, len(lines)) if lines[i].strip() == 'PY')
    code = '\n'.join(x[10:] for x in lines[first:last])
    ast.parse(code)
    return code


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def recent_signals(asof, sessions, receipts, ledger):
    """Read reservations too: an uncertain prior delivery is not resent as new.

    Count actual KRX sessions, not calendar days. Never edit either source.
    """
    prior = [x for x in sessions if x < asof][-20:]
    blocked = set()
    for source in receipts.glob('*.json') if receipts.is_dir() else []:
        item = json.loads(source.read_text())
        if item.get('asof') in prior:
            codes = item.get('selected_codes')
            if not isinstance(codes, list) or any(not isinstance(x, str) for x in codes):
                raise ValueError('SIGNAL_HISTORY_INVALID')
            blocked.update(codes)
    if ledger.is_file():
        data = json.loads(ledger.read_text())
        for position in data.get('positions', {}).values():
            plan = position.get('plan', {})
            when = str(plan.get('selection_date', '')).replace('-', '')
            if when in prior:
                if not isinstance(plan.get('ticker'), str):
                    raise ValueError('LEDGER_SIGNAL_HISTORY_INVALID')
                blocked.add(plan['ticker'])
    return blocked


def verify_images(root, report):
    from PIL import Image
    selected = [r for r in report['candidates'] if r['top5']]
    for row in report['candidates']:
        path = root / 'all_candidate_report' / row['image']
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['image_sha256']:
            raise ValueError('IMAGE_HASH_MISMATCH')
        with Image.open(path) as image:
            if image.size != (1400, 1710) or json.loads(image.info['c3_candidate']) != image_identity(row, report['asof']):
                raise ValueError('IMAGE_METADATA_MISMATCH')
            image.verify()
    return len(selected)


def run(root, cache_root, source=None, live=False):
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    # Guard against accidentally overwriting the existing working outputs.
    if root == REPO / 'output/c3_top5' or root == REPO:
        raise ValueError('ISOLATED_OUTPUT_REQUIRED')
    summary = {'status': 'RUNNING', 'live_krx_collection': live, 'telegram_photos_sent': 0,
               'orders_enabled': False, 'main_or_ledger_writes': False}
    write(root/'validation_result.json', summary)
    try:
        if live:
            if source is not None:
                raise ValueError('LIVE_REPLAY_MUTUALLY_EXCLUSIVE')
            env = {k: v for k, v in os.environ.items() if k not in
                   ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID')}
            env.update(GITHUB_EVENT_NAME='workflow_dispatch', C3_TEST_SEND_TELEGRAM='false',
                       C3_MANUAL_ASOF='', PYTHONPATH=str(REPO/'scripts'))
            code = embedded('Collect KRX sessions and render one classic image per stock')
            script = root / 'production_technical_collection.py'
            script.write_text(code)
            with (root/'krx_collection.log').open('w') as log:
                completed = subprocess.run([sys.executable, str(script)], cwd=root, env=env,
                    stdout=log, stderr=subprocess.STDOUT, timeout=1800)
            if completed.returncode:
                raise ValueError('LIVE_KRX_COLLECTION_FAILED_SEE_LOG')
            source = root/'output/c3_top5'
        if source is None:
            raise ValueError('SOURCE_OR_LIVE_REQUIRED')
        receipt, geometry, pool = [json.loads((source/(n+'.json')).read_text()) for n in
                                  ('receipt', 'entry_geometry_audit', 'qualified_chart_pool')]
        if len({receipt.get('asof'), geometry.get('asof'), pool.get('asof')}) != 1:
            raise ValueError('SOURCE_ASOF_MISMATCH')
        geometry = {**geometry, 'candidates': [sanitize_archived_geometry(c) for c in geometry.get('candidates', [])]}
        geometry['entry_valid_until'] = pool.get('entry_valid_until')
        original_geometry={c['code']:c for c in geometry.get('candidates',[])}
        for row in pool.get('candidates',[]):
            source_geometry=original_geometry.get(row['code'],{})
            row['pivot_support']=source_geometry.get('pivot_support')
            row['rejection_reasons']=source_geometry.get('rejection_reasons', [])
            row['technical_selection_reason']='EXISTING_C3_TREND_RS_RVOL_PULLBACK_GATE'
        integrity = receipt.get('source_integrity', {})
        if (receipt.get('status') == 'HOLD_ERROR' or integrity.get('session_count') != 60 or
            integrity.get('last_session') != pool.get('asof') or
            integrity.get('market_rows_min', {}).get('KOSPI', 0) < 500 or
            integrity.get('market_rows_min', {}).get('KOSDAQ', 0) < 800):
            raise ValueError('SOURCE_PREFLIGHT_FAILED')
        sessions = [x['date'] for x in pool.get('candidates', [{}])[0].get('bars', [])] if pool.get('candidates') else []
        if geometry.get('candidates') and len(sessions) != 60:
            raise ValueError('SIGNAL_SESSION_HISTORY_INCOMPLETE')
        pool_by_code = {c['code']:c for c in pool.get('candidates',[])}
        if len(pool_by_code)!=len(pool.get('candidates',[])) or set(pool_by_code)!=set(original_geometry):
            raise ValueError('SOURCE_CANDIDATE_SET_MISMATCH')
        # Legacy offline fixtures lack pivot/ATR evidence. Actual KRX audits
        # always carry it; the live/archive branch must validate those values.
        zone_audits = [audit_archived_zone(c, pool_by_code[c['code']]['bars'])
                       for c in geometry['candidates'] if 'atr14' in c]
        write(root/'entry_zone_replay_audit.json', {'asof':pool['asof'],'candidates':zone_audits,
            'prices_used_for_selection':'ORIGINAL_VALID_GEOMETRY_ONLY_EMPTY_INTERVALS_SUPPRESSED'})
        for c in geometry['candidates']:
            check = next((z for z in zone_audits if z['code']==c['code']),None)
            if check:
                c['structural_stop_diagnostic']=check['structural_stop']
                c['rejected_structural_stop_ref']=check['structural_stop']
        if not (REPO/'receipts/c3_top5_daily').is_dir() or not (REPO/'reports/c3_paper/paper_ledger.json').is_file():
            raise ValueError('SIGNAL_HISTORY_SOURCE_MISSING')
        blocked = recent_signals(pool['asof'], sessions, REPO/'receipts/c3_top5_daily',
                                 REPO/'reports/c3_paper/paper_ledger.json')
        geometry = {**geometry, 'candidates': [c for c in geometry['candidates'] if c['code'] not in blocked]}
        write(root/'duplicate_signal_audit.json', {'blocked_codes': sorted(blocked), 'sessions': 20,
            'policy': 'READ_ONLY_EXISTING_RESERVATIONS_AND_LEDGER'})
        asof = datetime.strptime(pool['asof'], '%Y%m%d').date()
        key = os.environ.get('OPENDART_API_KEY') or os.environ.get('OPEN_DART_API_KEY') or os.environ.get('DART_API_KEY')
        stocks = [{'ticker': c['code'], 'name': c.get('name', '')} for c in financial_review_candidates(geometry)]
        financial = collect_balanced(asof, stocks, key, datetime.now(ZoneInfo('Asia/Seoul')).date(), SnapshotCache(cache_root))
        financial['request_scope'] = REVIEW_SCOPE
        financial['aggregate_policy']=APPROVAL_POLICY
        write(root/'financial_pool_input.json', {'asof':pool['asof'], 'request_scope':REVIEW_SCOPE,
            'candidates':[{'code':s['ticker'],'name':s['name']} for s in stocks]})
        selection = select(geometry, financial)
        synthetic = pool.get('fixture_kind')=='SYNTHETIC_NOT_MARKET_SELECTION'
        selection.update(system_name='강현AI PRO · C3 TOP5 — Balanced Quality & Timing',
            stop_execution_rule='CLOSE_BELOW_STRUCTURAL_STOP_EXIT_NEXT_SESSION_MANUALLY',
            source_mode='SYNTHETIC_PIPELINE_FIXTURE' if synthetic else
                        'LIVE' if live else 'ARCHIVED_PRICE_REPLAY_LIVE_FINANCIAL_OBSERVATION')
        for name, value in (('receipt', receipt), ('qualified_chart_pool', pool),
                            ('entry_geometry_audit', geometry), ('financial_pool_gate', financial),
                            ('financial_selection_research', selection)):
            write(root/(name+'.json'), value)
        decisions = decision_report(receipt, geometry, selection, financial)
        save_decisions(root, decisions)
        # Produce diagnostics even when finance is incomplete; no send is possible.
        args = [sys.executable, str(REPO/'scripts/c3_all_candidate_report.py'), '--pool', str(root/'qualified_chart_pool.json'),
                '--selection', str(root/'financial_selection_research.json'), '--financial', str(root/'financial_pool_gate.json'),
                '--out', str(root/'all_candidate_report')]
        subprocess.run(args, check=True, capture_output=True, text=True)
        report = json.loads((root/'all_candidate_report/manifest.json').read_text())
        count = verify_images(root, report)
        fields = ['code', 'name', 'status', 'asof_close', 'entry_low', 'entry_high', 'stop_ref', 'risk_pct',
                  'r1_ref', 'r2_ref', 'financial_points', 'ma5', 'ma20', 'ma60', 'volume', 'support', 'entry_valid_until']
        with (root/'top5.csv').open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(x for x in report['candidates'] if x['top5'])
        with (root/'top5.csv').open(encoding='utf-8-sig') as stream:
            csv_rows=list(csv.DictReader(stream))
        if len(csv_rows) != count:
            raise ValueError('CSV_IMAGE_COUNT_MISMATCH')
        for saved,row in zip(csv_rows,(r for r in report['candidates'] if r['top5'])):
            if any(saved[field] != (str(row.get(field)) if row.get(field) is not None else '') for field in fields):
                raise ValueError('CSV_JSON_VALUE_MISMATCH')
            signal = next(c for c in selection['selected'] if c['code']==row['code'])
            if any(signal.get(k)!=row.get(k) for k in
                   ('asof_close','entry_low','entry_high','stop_ref','risk_pct','r1_ref','r2_ref','entry_valid_until')):
                raise ValueError('SELECTION_JSON_IMAGE_VALUE_MISMATCH')
        # Validate the original manifest/delivery boundary with credentials absent.
        # Its manual branch must terminate at DRY_RUN (or CASH), before reservation.
        work = root/'delivery_boundary'
        target = work/'output/c3_top5'
        target.mkdir(parents=True, exist_ok=True)
        import shutil
        for name in ('receipt.json', 'financial_selection_research.json', 'qualified_chart_pool.json', 'financial_pool_gate.json'):
            shutil.copy2(root/name, target/name)
        shutil.copytree(root/'all_candidate_report', target/'all_candidate_report', dirs_exist_ok=True)
        (target/'financial_preview').mkdir(exist_ok=True)
        selected_rows = [r for r in report['candidates'] if r['top5']]
        previews = []
        for row in selected_rows:
            shutil.copy2(root/'all_candidate_report'/row['image'], target/'financial_preview'/row['image'])
            previews.append({'code': row['code'], 'image': row['image']})
        write(target/'financial_preview/financial_preview_manifest.json', {'asof': pool['asof'], 'images': previews})
        safe_env = {'PATH': os.environ['PATH'], 'PYTHONPATH': str(REPO/'scripts'),
                    'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REF_NAME': 'balanced-no-send-validation',
                    'GITHUB_RUN_ID': os.environ.get('GITHUB_RUN_ID', 'local'), 'C3_TEST_SEND_TELEGRAM': 'false'}
        for name in ('Build finance-first conditional signal delivery manifest',
                     'Validate delivery on every run; send only on scheduled main'):
            # Any attempted network access here is a regression, even before send.
            guard = "import urllib.request\ndef forbidden(*a, **k): raise ValueError('DELIVERY_NETWORK_FORBIDDEN')\nurllib.request.urlopen=forbidden\n"
            process = subprocess.run([sys.executable, '-c', guard+embedded(name)], cwd=work,
                                      env=safe_env, capture_output=True, text=True)
            if process.returncode and selection['decision'] not in ('ERROR','REVIEW_REQUIRED'):
                raise ValueError('DELIVERY_BOUNDARY_FAILED')
        delivery = json.loads((target/'delivery_result.json').read_text())
        write(root/'delivery_result.json', delivery)
        shutil.copy2(target/'finance_first_delivery_manifest.json', root/'finance_first_delivery_manifest.json')
        summary.update(status='ERROR' if selection['decision'] == 'ERROR' else 'REVIEW_REQUIRED' if selection['decision']=='REVIEW_REQUIRED' else 'COMPLETE', asof=pool['asof'],
            input_kind='SYNTHETIC_NOT_MARKET_SELECTION' if synthetic else 'ACTUAL_KRX_AND_OPENDART',
            live_dart_observation=not synthetic,
            decision=selection['decision'], source_integrity=integrity, technical_candidates=len(pool['candidates']),
            requested_financial=len(stocks), selected_codes=[x['code'] for x in selection['selected']],
            final_png_count=count, diagnostic_png_count=len(report['candidates']),
            delivery_status=delivery['status'], telegram_live_transport_verified=False,
            financial_evidence_status=financial['status'],
            financial_decision_counts=selection.get('financial_decision_counts',{}),
            operational_status=selection.get('operational_status'), candidate_summary=decisions['summary'],
            approval_required_count=selection.get('approval_required_count'),
            approval_financial_complete=selection.get('approval_financial_complete'),
            nonblocking_financial_unverified_codes=selection.get('nonblocking_financial_unverified_codes',[]),
            comparison_conservative_operational_status=selection.get('comparison_conservative_operational_status'),
            source_provenance={'price_artifact_sha256':os.environ.get('C3_SOURCE_ARTIFACT_SHA256'),
                               'price_source_run_id':os.environ.get('C3_SOURCE_RUN_ID')})
    except Exception as exc:
        summary.update(status='ERROR', error=str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
        summary['operational_status'] = ('HOLD_DATA_INCOMPLETE' if isinstance(exc, ValueError) and
            str(exc).startswith(('SOURCE_', 'SIGNAL_', 'LIVE_KRX_')) else 'ERROR')
    write(root/'validation_result.json', summary)
    print(json.dumps(summary, ensure_ascii=False))
    return summary


def exit_code(result, operational=False):
    # Preserve the old exit-2 contract for existing external callers.
    if not operational:
        return 1 if result.get('status')=='ERROR' else 2 if result.get('status')=='REVIEW_REQUIRED' else 0
    if result.get('operational_status')=='ERROR' or (result.get('status')=='ERROR' and
        result.get('operational_status')!='HOLD_DATA_INCOMPLETE'):return 1
    holding=str(result.get('operational_status','')).startswith('HOLD_') or result.get('status')=='REVIEW_REQUIRED'
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--require-latest-source',action='store_true')
    parser.add_argument('--operational-exit-codes',action='store_true',
        help='Completed HOLD is exit 0 with an explicit outcome; ERROR stays nonzero. Default keeps exit 2.')
    args = parser.parse_args()
    if args.require_latest_source and args.source:
        from c3_top5_session_policy import session_plan
        latest=session_plan(datetime.now(ZoneInfo('Asia/Seoul')))['asof']
        source_day=json.loads((args.source/'receipt.json').read_text()).get('asof') if (args.source/'receipt.json').is_file() else None
        if source_day != latest:
            print('ARCHIVED_PRICE_NOT_LATEST_COLLECT_FRESH',source_day,latest)
            args.source=None;args.live=True
    result = run(args.out, args.cache, args.source, args.live)
    outcome=dict(operational_status=result.get('operational_status'),
        program_status='ERROR' if exit_code(result,True)==1 else 'COMPLETED',
        exit_code=exit_code(result,args.operational_exit_codes),compatibility_exit_code=exit_code(result),
        telegram_photos_sent=result.get('telegram_photos_sent',0),
        delivery_permitted=result.get('operational_status')=='TOP5_READY')
    write(args.out/'execution_outcome.json',outcome)
    print('C3_EXECUTION_OUTCOME',json.dumps(outcome,ensure_ascii=False))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
            f.write('### C3 operational outcome\n\n'+json.dumps(outcome,ensure_ascii=False)+'\n')
    raise SystemExit(outcome['exit_code'])


if __name__ == '__main__':
    main()
