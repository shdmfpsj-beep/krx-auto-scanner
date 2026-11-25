"""Separate observation-only delivery; never writes TOP5 decisions or receipts."""
import argparse
import base64
import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from PIL.PngImagePlugin import PngInfo
from c3_all_candidate_report import image_identity
from c3_top5_financial_selection import valid_entry, classify, finite, validate_selection_approval
from c3_top5_session_policy import session_plan
from c3_delivery_authorization import approved_manual_delivery

ALLOWED = ('TOP5_READY', 'CASH_NO_ELIGIBLE')
LABEL = 'WATCH5 관찰용 — 매수 승인 아님'
REVIEW_LABEL = '재무 미확인 참고용 — 정식 선정 및 매수 승인 아님'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def choose(report, selection, blocked, exclusions=None):
    if selection.get('operational_status') not in ALLOWED:
        return []
    if report['asof'] != selection['asof']:
        raise ValueError('WATCH_DATE_MISMATCH')
    rows = report['candidates']
    if len({r['code'] for r in rows}) != len(rows):
        raise ValueError('WATCH_DUPLICATE_CODE')
    selected = {r['code'] for r in selection['selected']}
    if len(selection['selected']) > 5 or len(selected) != len(selection['selected']):
        raise ValueError('WATCH_TOP5_COUNT_INVALID')
    result = []
    for row in rows:
        reason = None
        if row['code'] in selected or row.get('top5'):
            reason = 'OFFICIAL_TOP5'
        elif row['code'] in blocked:
            reason = 'EXISTING_TOP5_HISTORY_BLOCK'
        elif row.get('status') != 'WATCH':
            reason = 'NOT_TECHNICAL_WATCH'
        elif row.get('financial_verdict') != 'PASS' or selection['financial_verdicts'].get(row['code']) != 'PASS':
            reason = 'FINANCIAL_NOT_PASS'
        elif not valid_entry({**row, 'close': row.get('asof_close')}, allow_watch=True):
            reason = 'INVALID_EXISTING_ENTRY_GEOMETRY'
        elif not finite(row.get('composite_score')):
            reason = 'INVALID_COMPOSITE_SCORE'
        else:
            distance = (row['asof_close'] - row['entry_high']) / row['asof_close'] * 100
            if 2 < distance <= 5:
                result.append({**row, 'distance_pct': distance})
            else:
                reason = 'OUTSIDE_WATCH_DISTANCE_2_TO_5PCT'
        if reason and exclusions is not None:
            exclusions[row['code']] = reason
    result.sort(key=lambda r: (-r['composite_score'], r['distance_pct'], r['code']))
    if exclusions is not None:
        exclusions.update({r['code']: 'OUTSIDE_MAXIMUM_FIVE' for r in result[5:]})
    return result[:5]


def same(a, b):
    return (math.isclose(a, b, rel_tol=1e-10, abs_tol=.00001)
            if finite(a) and finite(b) else a == b)


def choose_reference(report, selection, geometry, financial, blocked):
    if selection.get('operational_status') not in ALLOWED:return []
    if any(r.get('asof')!=report['asof'] for r in (selection,geometry,financial)):
        raise ValueError('WATCH_DATE_MISMATCH')
    if len({r['code'] for r in report['candidates']})!=len(report['candidates']):raise ValueError('WATCH_DUPLICATE_CODE')
    if len(selection['selected'])>5 or len({r['code'] for r in selection['selected']})!=len(selection['selected']):
        raise ValueError('WATCH_TOP5_COUNT_INVALID')
    technical={r['code']:r for r in geometry['candidates']}
    facts={r['ticker']:r for r in financial.get('researched',[])+financial.get('excluded',[])}
    if len(technical)!=len(geometry['candidates']) or len(facts)!=len(financial.get('researched',[])+financial.get('excluded',[])):
        raise ValueError('WATCH_SOURCE_DUPLICATE_CODE')
    selected={r['code'] for r in selection['selected']};result=[]
    for row in report['candidates']:
        code=row['code'];fact=facts.get(code,{});chart=technical.get(code,{})
        if (code in blocked or code in selected or row.get('top5') or row.get('financial_verdict')!='REVIEW_REQUIRED'
            or selection['financial_verdicts'].get(code)!='REVIEW_REQUIRED'
            or fact.get('financial_verdict')!='REVIEW_REQUIRED' or fact.get('error')
            or classify(fact,report['asof'])!='REVIEW_INSUFFICIENT_EVIDENCE'
            or fact.get('risk_assessment',{}).get('hard_failures') or not valid_entry(chart)):
            continue
        missing=fact.get('risk_assessment',{}).get('mandatory_missing',[])
        if not missing or not all(isinstance(s,str) and s for s in missing):continue
        if not finite(row.get('composite_score')):raise ValueError('WATCH_TECHNICAL_SCORE_INVALID')
        result.append({**row,'technical_status':chart['entry_status'],'financial_unverified_reasons':missing})
    result.sort(key=lambda r:(-r['composite_score'],r['code']))
    return result[:5]


def validate_sources(root, report, selection, receipt, outcome, rows, review=False):
    def read(name): return json.loads((root / name).read_text())
    date = report['asof']
    if not isinstance(date, str) or not re.fullmatch(r'\d{8}', date) or datetime.strptime(date, '%Y%m%d').strftime('%Y%m%d') != date:
        raise ValueError('WATCH_DATE_FORMAT')
    pool, geometry, financial, decisions, delivery = [read(name + '.json') for name in
        ('qualified_chart_pool', 'entry_geometry_audit', 'financial_pool_gate', 'candidate_decisions', 'delivery_result')]
    # Older isolated-validation artifacts omit outcome.asof. Require every dated
    # original to agree; when outcome.asof exists, it must agree as well.
    if any(x.get('asof') != date for x in (selection, receipt, pool, geometry, financial, decisions, delivery)) or outcome.get('asof', date) != date:
        raise ValueError('WATCH_DATE_MISMATCH')
    if outcome.get('operational_status') != selection.get('operational_status') or selection.get('shared_system_error'):
        raise ValueError('WATCH_OUTCOME_MISMATCH')
    if not validate_selection_approval(selection,geometry,financial,pool):raise ValueError('WATCH_SELECTION_APPROVAL_INVALID')
    if outcome.get('program_status') != 'COMPLETED' or delivery.get('status') not in (
            ('SENT', 'DRY_RUN') if outcome['operational_status'] == 'TOP5_READY' else ('CASH',)):
        raise ValueError('WATCH_OFFICIAL_DELIVERY_NOT_COMPLETE')
    integrity = receipt.get('source_integrity', {})
    if integrity.get('session_count') != 60 or integrity.get('last_session') != date:
        raise ValueError('WATCH_PRICE_INTEGRITY_INCOMPLETE')
    expiry = receipt.get('entry_valid_until')
    if not expiry or report.get('entry_valid_until') != expiry or pool.get('entry_valid_until') != expiry:
        raise ValueError('WATCH_VALIDITY_MISMATCH')
    if datetime.fromisoformat(expiry).utcoffset() is None:
        raise ValueError('WATCH_VALIDITY_TIMEZONE_REQUIRED')
    def indexed(items, key):
        if len({x[key] for x in items}) != len(items): raise ValueError('WATCH_SOURCE_DUPLICATE_CODE')
        return {x[key]: x for x in items}
    prices = indexed(pool['candidates'], 'code')
    technical = indexed(geometry['candidates'], 'code')
    facts = indexed(financial.get('researched', []) + financial.get('excluded', []), 'ticker')
    decision_map = indexed(decisions['candidates'], 'code')
    for row in rows:
        code = row['code']
        if not re.fullmatch(r'[0-9A-Z]{6}', code) or Path(row['image']).name != row['image']:
            raise ValueError('WATCH_PATH')
        if row['entry_valid_until'] != expiry:
            raise ValueError('WATCH_VALIDITY_MISMATCH')
        if code not in prices or code not in technical or code not in facts or code not in decision_map:
            raise ValueError('WATCH_SOURCE_CANDIDATE_MISSING')
        expected='REVIEW_INSUFFICIENT_EVIDENCE' if review else 'QUALIFIED_BASIC_FINANCIAL_RISK'
        verdict='REVIEW_REQUIRED' if review else 'PASS'
        if classify(facts[code], date) != expected or decision_map[code]['financial_verdict'] != verdict:
            raise ValueError('WATCH_FINANCIAL_SOURCE_MISMATCH')
        if ((not review and technical[code].get('entry_status')!='WATCH') or
            not valid_entry(technical[code],allow_watch=not review)):
            raise ValueError('WATCH_TECHNICAL_SOURCE_MISMATCH')
        if review and (row.get('financial_unverified_reasons')!=facts[code].get('risk_assessment',{}).get('mandatory_missing')
            or facts[code].get('risk_assessment',{}).get('hard_failures')):raise ValueError('WATCH_REVIEW_REASONS_MISMATCH')
        for key in ('entry_low', 'entry_high', 'stop_ref', 'risk_pct', 'r1_ref', 'r2_ref'):
            if not same(row.get(key), prices[code].get(key)) or not same(row.get(key), technical[code].get(key)):
                raise ValueError('WATCH_PRICE_SOURCE_MISMATCH')
        bars = prices[code]['bars']
        if len(bars) != 60 or [b['date'] for b in bars] != sorted({b['date'] for b in bars}) or bars[-1]['date'] != date:
            raise ValueError('WATCH_BAR_DATE_MISMATCH')
        for bar in bars:
            values = [bar.get(k) for k in ('open', 'high', 'low', 'close', 'volume')]
            if not all(finite(v) and v > 0 for v in values) or not (bar['low'] <= min(bar['open'], bar['close']) <= max(bar['open'], bar['close']) <= bar['high']):
                raise ValueError('WATCH_INVALID_OHLCV')
        if not same(bars[-1]['close'], row['asof_close']) or not same(prices[code]['close'], row['asof_close']):
            raise ValueError('WATCH_CLOSE_MISMATCH')
        for n in (5, 20, 60):
            if not same(row['ma' + str(n)], sum(b['close'] for b in bars[-n:]) / n):
                raise ValueError('WATCH_MOVING_AVERAGE_MISMATCH')
        if not same(row['volume'], bars[-1]['volume']): raise ValueError('WATCH_VOLUME_MISMATCH')
    return date, expiry


def render(root, row, date, font_dir, review=False):
    source = root / 'all_candidate_report' / row['image']
    if hashlib.sha256(source.read_bytes()).hexdigest() != row['image_sha256']:
        raise ValueError('WATCH_SOURCE_IMAGE_HASH_MISMATCH')
    identity = image_identity(row, date)
    with Image.open(source) as image:
        if image.format != 'PNG' or image.size != (1400, 1710) or json.loads(image.info['c3_candidate']) != identity:
            raise ValueError('WATCH_SOURCE_IMAGE_IDENTITY_MISMATCH')
        image.load()
        header=160 if review else 100
        canvas = Image.new('RGB', (1400, 1710+header), '#74512f' if review else '#28577d')
        canvas.paste(image.convert('RGB'), (0, header))
    draw = ImageDraw.Draw(canvas)
    font = lambda n: ImageFont.truetype(str(font_dir / 'NanumGothicBold.ttf'), n)
    draw.text((700, 33), REVIEW_LABEL if review else LABEL, font=font(34 if review else 36), fill='white', anchor='mm')
    if review:
        import textwrap
        draw.text((700,75),f"재무 REVIEW_REQUIRED · {row['technical_status']} · 위험 {row['risk_pct']:.2f}%",font=font(25),fill='white',anchor='mm')
        for i,line in enumerate(textwrap.wrap(' / '.join(row['financial_unverified_reasons']),width=110)):
            draw.text((700,108+i*23),line,font=font(17),fill='white',anchor='mm')
    else:draw.text((700, 78), f"재무 PASS · 진입 이격 {row['distance_pct']:.2f}% · 구조손절 위험 {row['risk_pct']:.2f}%",
              font=font(25), fill='white', anchor='mm')
    watch_identity = dict(schema='C3_REVIEW_IMAGE_V1' if review else 'C3_WATCH5_IMAGE_V1', label=REVIEW_LABEL if review else LABEL, trade_approved=False,
                          distance_pct=row.get('distance_pct'), source_image_sha256=row['image_sha256'],
                          candidate=identity)
    if review:watch_identity.update(financial_verdict='REVIEW_REQUIRED',financial_unverified_reasons=row['financial_unverified_reasons'])
    info = PngInfo()
    info.add_text('c3_candidate', json.dumps(identity, ensure_ascii=False, sort_keys=True))
    info.add_text('c3_review' if review else 'c3_watch5', json.dumps(watch_identity, ensure_ascii=False, sort_keys=True))
    dest = root / ('review_unverified' if review else 'watch5') / (row['code'] + ('_review.png' if review else '_watch.png'))
    canvas.save(dest, pnginfo=info)
    return {**row, 'source_image': row['image'], 'source_image_sha256': row['image_sha256'],
            'image': dest.name, 'image_sha256': hashlib.sha256(dest.read_bytes()).hexdigest(),
            ('review_identity' if review else 'watch_identity'): watch_identity, 'trade_approved': False}


def image_bytes(root, item, review=False):
    path = root / ('review_unverified' if review else 'watch5') / item['image']
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != item['image_sha256']:
        raise ValueError('WATCH_OUTPUT_IMAGE_HASH_MISMATCH')
    with Image.open(path) as image:
        if image.format != 'PNG' or image.size != (1400, 1870 if review else 1810) or json.loads(image.info['c3_review' if review else 'c3_watch5']) != item['review_identity' if review else 'watch_identity']:
            raise ValueError('WATCH_OUTPUT_IMAGE_IDENTITY_MISMATCH')
        image.verify()
    return data


def run(root, env=None, opener=None, clock=None, review=False):
    env = dict(os.environ if env is None else env)
    opener = opener or urllib.request.urlopen
    clock = clock or datetime.now(timezone.utc)
    root = Path(root);folder='review_unverified' if review else 'watch5'
    result_name='review_delivery_result.json' if review else 'watch_delivery_result.json'
    (root / folder).mkdir(parents=True, exist_ok=True)
    # Only our generated previews are replaced. Never touch reservations or
    # official TOP5 outputs, including when this directory is reused for HOLD.
    for stale in (root / folder).glob('*_review.png' if review else '*_watch.png'):
        if re.fullmatch(r'[0-9A-Z]{6}_'+('review' if review else 'watch')+r'\.png', stale.name): stale.unlink()
    (root / folder / 'manifest.json').unlink(missing_ok=True)
    result = dict(schema='C3_REVIEW_DELIVERY_V1' if review else 'C3_WATCH5_DELIVERY_V1', status='ERROR', stage='PREFLIGHT',
                  selected=[], photos=[], telegram_photos_sent=0, trade_approved=False,
                  run_id=env.get('GITHUB_RUN_ID'), automatic_retry=False)
    def save():
        result['telegram_photos_sent'] = len(result['photos'])
        result['selected_count'] = len(result['selected'])
        write(root / result_name, result)
    def read(name): return json.loads((root / name).read_text())
    save()
    try:
        outcome = read('execution_outcome.json')
        result['official_operational_status'] = outcome.get('operational_status')
        if env.get('C3_REVIEW_UPSTREAM_SUCCESS' if review else 'C3_WATCH_UPSTREAM_SUCCESS', 'true') != 'true':
            result.update(status='BLOCKED', reason='UPSTREAM_WORKFLOW_FAILURE'); save(); return result
        if outcome.get('operational_status') not in ALLOWED:
            result.update(status='BLOCKED', reason='OFFICIAL_HOLD_OR_ERROR'); save(); return result
        if env.get('C3_FINANCIAL_MODEL') != 'balanced':
            result.update(status='NOT_APPLICABLE', reason='LEGACY_MODEL'); save(); return result
        report, selection, receipt = [read(n + '.json') for n in
                                      ('all_candidate_report/manifest', 'financial_selection_research', 'receipt')]
        blocked = read('duplicate_signal_audit.json')['blocked_codes']
        if not isinstance(blocked, list) or any(not isinstance(code, str) for code in blocked):
            raise ValueError('WATCH_DUPLICATE_HISTORY_INVALID')
        result['exclusions'] = {}
        if review:
            watch=read('watch_delivery_result.json')
            if watch.get('status') not in ('SENT','DRY_RUN','EMPTY'):
                result.update(status='BLOCKED',reason='WATCH_DELIVERY_NOT_COMPLETE');save();return result
            blocked=list(set(blocked)|{r['code'] for r in watch.get('selected',[])})
        rows = (choose_reference(report,selection,read('entry_geometry_audit.json'),read('financial_pool_gate.json'),set(blocked))
                if review else choose(report, selection, set(blocked), result['exclusions']))
        date, expiry = validate_sources(root, report, selection, receipt, outcome, rows, review)
        result.update(asof=date, entry_valid_until=expiry)
        for row in rows:
            result['selected'].append(render(root, row, date, Path(env.get('C3_FONT_DIR', '/usr/share/fonts/truetype/nanum')),review))
        write(root / folder / 'manifest.json', dict(schema='C3_REVIEW_MANIFEST_V1' if review else 'C3_WATCH5_MANIFEST_V1', asof=date,
            entry_valid_until=expiry, trade_approved=False, selected=result['selected']))
        prepared = [image_bytes(root, item,review) for item in result['selected']]
        if not rows:
            result.update(status='EMPTY', stage='COMPLETE'); save(); return result
        manual_live = approved_manual_delivery(env, date, expiry, clock)
        result['execution_event'] = env.get('GITHUB_EVENT_NAME')
        result['delivery_mode'] = 'MANUAL_USER_APPROVED' if manual_live else 'SCHEDULED_PRODUCTION' if env.get('GITHUB_EVENT_NAME') == 'schedule' else 'PREVIEW'
        result['operation_request_id'] = env.get('C3_OPERATION_REQUEST_ID', '')
        if not (manual_live or (env.get('GITHUB_EVENT_NAME') == 'schedule' and env.get('GITHUB_REF_NAME') == 'main'
                and env.get('GITHUB_REPOSITORY') == 'shdmfpsj-beep/krx-auto-scanner')):
            result.update(status='DRY_RUN', stage='COMPLETE'); save(); return result
        if session_plan(clock)['asof'] != date or datetime.fromisoformat(expiry) <= clock:
            raise ValueError('WATCH_PRODUCTION_DATE_OR_VALIDITY_MISMATCH')
        token, chat, gh_token = (env.get(k, '').strip() for k in ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'GH_TOKEN'))
        if not token or not gh_token or not chat.lstrip('-').isdigit():
            raise ValueError('WATCH_CREDENTIALS')
        marker_path = 'receipts/'+('c3_review_daily' if review else 'c3_watch5_daily')+'/' + date + '.json'
        if review:
            for path in (marker_path,'receipts/c3_review_daily/'+date+'.sent.json'):
                request=urllib.request.Request('https://api.github.com/repos/'+env['GITHUB_REPOSITORY']+'/contents/'+path,
                    headers={'Authorization':'Bearer '+gh_token,'Accept':'application/vnd.github+json'})
                try:
                    with opener(request,timeout=20) as response:
                        if response.status==200:
                            result.update(status='BLOCKED',reason='DUPLICATE_OR_UNCERTAIN_REVIEW_RECEIPT');save();return result
                        raise ValueError('WATCH_REVIEW_RECEIPT_STATE_UNVERIFIED')
                except urllib.error.HTTPError as error:
                    if error.code!=404:raise ValueError('WATCH_REVIEW_RECEIPT_STATE_UNVERIFIED') from None
        marker = dict(asof=date, status='RESERVED_BEFORE_SEND_NO_AUTOMATIC_RETRY', run_id=env.get('GITHUB_RUN_ID'),
                      selected=[{k: x[k] for k in ('code', 'image', 'image_sha256')} for x in result['selected']],
                      trade_approved=False)
        if review:marker.update(financial_verdict='REVIEW_REQUIRED',purpose='UNVERIFIED_REFERENCE_NOT_SELECTION')
        payload = dict(message=('Reserve unverified reference ' if review else 'Reserve WATCH5 observation ') + date, branch='main',
                       content=base64.b64encode(json.dumps(marker).encode()).decode())
        result.update(stage='CREATE_ONLY_REFERENCE_RESERVATION' if review else 'CREATE_ONLY_WATCH_RESERVATION'); save()
        request = urllib.request.Request('https://api.github.com/repos/' + env['GITHUB_REPOSITORY'] + '/contents/' + marker_path,
            data=json.dumps(payload).encode(), method='PUT', headers={'Authorization': 'Bearer ' + gh_token,
            'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json', 'X-GitHub-Api-Version': '2022-11-28'})
        try:
            with opener(request, timeout=20) as response:
                if response.status != 201: raise ValueError('WATCH_RESERVATION_NOT_CREATED')
        except urllib.error.HTTPError as exc:
            if exc.code in (409, 422):
                result.update(status='BLOCKED', reason='DUPLICATE_OR_UNCERTAIN_WATCH_RESERVATION', http_status=exc.code); save(); return result
            raise
        result['reservation_path'] = marker_path
        for item, data in zip(result['selected'], prepared):
            result.update(stage='TELEGRAM_SEND', attempting_code=item['code']); save()
            boundary = '----C3' + uuid.uuid4().hex
            def part(name, value, extra=''):
                return ('--' + boundary + '\r\nContent-Disposition: form-data; name="' + name + '"' + extra + '\r\n\r\n').encode() + value + b'\r\n'
            body = part('chat_id', chat.encode()) + part('photo', data, '; filename="' + item['image'] + '"\r\nContent-Type: image/png') + ('--' + boundary + '--\r\n').encode()
            request = urllib.request.Request('https://api.telegram.org/bot' + token + '/sendPhoto', data=body,
                method='POST', headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
            with opener(request, timeout=30) as response:
                status, answer = response.status, json.load(response)
            message = answer.get('result', {}); message_id = message.get('message_id')
            if status != 200 or answer.get('ok') is not True or type(message_id) is not int or message_id <= 0:
                raise ValueError('WATCH_TELEGRAM_RESPONSE_INVALID')
            matches = str(message.get('chat', {}).get('id')) == str(int(chat))
            result['photos'].append({k: item[k] for k in ('code', 'image', 'image_sha256')})
            result['photos'][-1].update(telegram_message_id=message_id, destination_matches=matches,
                                       sent_at=datetime.now(timezone.utc).isoformat())
            save()
            if not matches: raise ValueError('WATCH_TELEGRAM_DESTINATION_MISMATCH')
        if review:
            final_path='receipts/c3_review_daily/'+date+'.sent.json'
            payload=dict(message='Record unverified reference photo delivery '+date,branch='main',
                content=base64.b64encode(json.dumps(dict(asof=date,trade_approved=False,financial_verdict='REVIEW_REQUIRED',
                    run_id=env.get('GITHUB_RUN_ID'),photos=result['photos']),ensure_ascii=False).encode()).decode())
            request=urllib.request.Request('https://api.github.com/repos/'+env['GITHUB_REPOSITORY']+'/contents/'+final_path,
                data=json.dumps(payload).encode(),method='PUT',headers={'Authorization':'Bearer '+gh_token,
                    'Accept':'application/vnd.github+json','Content-Type':'application/json'})
            with opener(request,timeout=20) as response:
                if response.status!=201:raise ValueError('WATCH_REFERENCE_RECEIPT_NOT_CREATED')
            result['sent_receipt_path']=final_path
        result.update(status='SENT', stage='COMPLETE'); save(); return result
    except Exception as exc:
        result.update(status='PARTIAL_ERROR' if result['photos'] else 'ERROR', exception_type=type(exc).__name__,
                      reason=str(exc) if type(exc) is ValueError and str(exc).startswith('WATCH_') else 'WATCH_FAILURE_NO_AUTOMATIC_RETRY')
        if isinstance(exc, urllib.error.HTTPError): result['http_status'] = exc.code
        save(); return result


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--root', type=Path, default=Path('output/c3_top5'))
    result = run(parser.parse_args().root)
    print('C3_WATCH5_DELIVERY', json.dumps({k: result.get(k) for k in
        ('status', 'stage', 'asof', 'selected_count', 'telegram_photos_sent', 'reason', 'exception_type')}))
    raise SystemExit(1 if result['status'] in ('ERROR', 'PARTIAL_ERROR') else 0)


if __name__ == '__main__':
    main()
