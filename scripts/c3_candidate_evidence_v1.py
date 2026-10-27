#!/usr/bin/env python3
"""C3 candidate evidence ledger; all candidates retained, no trade authorization.

Consumes existing dated sources without network, credentials or account inputs.
Official share-kind labels describe their own snapshot date. They do not prove
industry, SPAC exclusion, historical vintage, or today's unchanged membership.
Actual source turnover and regular-session price certification are separate.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SCHEMA = 'C3_CANDIDATE_EVIDENCE_V1'
BASIC_SCHEMA = 'C3_K100_KRX_ISSUER_BASE_INFO_V610'
EOD_SCHEMA = 'C3_K100_KRX_OPENAPI_COLLECTION_V65'
SCOPE_SCHEMA = 'C3_PRIMARY_BUSINESS_SCOPE_REVIEW_V1'
MARKETS = {'KOSPI': 'stk_isu_base_info', 'KOSDAQ': 'ksq_isu_base_info'}
FIELDS = (
    'raw_rank', 'ticker', 'name', 'asof', 'raw_c3_preliminary_score',
    'raw_instrument_type', 'basic_snapshot_asof', 'security_group', 'share_kind',
    'basic_evidence_status', 'instrument_review', 'business_scope_status',
    'scope_reviewed_at', 'scope_source_url', 'scope_reason',
    'raw_turnover_estimate_krw', 'raw_turnover_source',
    'actual_source_turnover_krw', 'actual_turnover_status',
    'official_eod_close_reference', 'raw_close_reference', 'close_sources_equal',
    'regular_session_certified', 'review_status', 'blocking_reasons',
    'final_score80', 'approved_buy_range', 'trade_approved', 'orders_enabled',
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def day(value):
    d = date.fromisoformat(value)
    if d.isoformat() != value:
        raise ValueError('INVALID_ISO_DATE')
    return d


def clock(value):
    d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('TIMESTAMP_REQUIRES_TIMEZONE')
    return d


def number(value):
    if isinstance(value, bool) or value in (None, ''):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (ValueError, TypeError):
        return None


def code(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-Z]{6}', value):
        raise ValueError('INVALID_SHORT_CODE_NO_ISIN_TRUNCATION')
    return value


def checked_sources(folder, meta, hash_key, names, asof, endpoint_check=False):
    """Verify every source byte, count, short code and date before joining."""
    rows, files = {}, {}
    for market, filename in names.items():
        p = folder / filename
        if not p.is_file() or sha(p) != meta.get(hash_key, {}).get(market):
            raise ValueError('OFFICIAL_SOURCE_HASH_MISMATCH')
        records = read_csv(p)
        if not records:
            raise ValueError('EMPTY_OFFICIAL_MARKET')
        if endpoint_check and len(records) != meta.get('market_counts', {}).get(market):
            raise ValueError('OFFICIAL_BASIC_COUNT_MISMATCH')
        for r in records:
            t = code(r.get('ticker'))
            returned_day = r.get('asof_requested') if endpoint_check else r.get('asof')
            if t in rows or returned_day != asof or r.get('market') != market:
                raise ValueError('OFFICIAL_DUPLICATE_OR_DATE_MARKET_MISMATCH')
            if endpoint_check:
                if r.get('source_endpoint') != MARKETS[market]:
                    raise ValueError('OFFICIAL_BASIC_ENDPOINT_MISMATCH')
                listed = str(r.get('listed_date', ''))
                if listed and (not re.fullmatch(r'\d{8}', listed)
                               or listed > asof.replace('-', '')):
                    raise ValueError('OFFICIAL_FUTURE_OR_INVALID_LISTING')
            rows[t] = r
        files[filename] = sha(p)
    return rows, files


def load_basic(folder, asof, evaluated_at):
    if folder is None or not (folder / 'krx_basic_v610_status.json').exists():
        return {}, {'status': 'MISSING', 'asof': None, 'file_sha256': {}}
    meta_path = folder / 'krx_basic_v610_status.json'
    m = read_json(meta_path)
    source_day = m.get('asof')
    if (m.get('schema') != BASIC_SCHEMA or day(source_day) > day(asof)
            or clock(m.get('received_utc')) > clock(evaluated_at)):
        raise ValueError('BASIC_SCHEMA_FUTURE_DATE_OR_RECEIPT')
    info = {'status': 'UNAVAILABLE', 'asof': source_day,
            'received_utc': m['received_utc'],
            'historical_vintage_certified': False,
            'file_sha256': {'krx_basic_v610_status.json': sha(meta_path)}}
    if m.get('official_base_usable') is not True or m.get('official_base_approved') is not True:
        return {}, info
    rows, files = checked_sources(folder, m, 'source_file_sha256',
        {k: k + '_basic_v610.csv' for k in MARKETS}, source_day, True)
    info['file_sha256'].update(files)
    info['status'] = ('CURRENT_DATED_SNAPSHOT' if source_day == asof
                      else 'PRIOR_DATED_SNAPSHOT_REQUIRES_REFRESH')
    return rows, info


def load_eod(folder, asof, evaluated_at):
    if folder is None or not (folder / 'krx_v65_collect_status.json').exists():
        return {}, {'status': 'MISSING', 'file_sha256': {}}
    path = folder / 'krx_v65_collect_status.json'
    m = read_json(path)
    if (m.get('schema') != EOD_SCHEMA or day(m.get('asof')) > day(asof)
            or clock(m.get('retrieval_utc')) > clock(evaluated_at)):
        raise ValueError('EOD_SCHEMA_FUTURE_DATE_OR_RECEIPT')
    info = {'status': 'UNAVAILABLE', 'asof': m['asof'],
            'file_sha256': {'krx_v65_collect_status.json': sha(path)},
            'regular_session_certified': False}
    if m.get('official_dataset_usable') is not True or m.get('krx_eod_authenticated') is not True:
        return {}, info
    rows, files = checked_sources(folder, m, 'market_file_sha256',
        {k: k + '_official.csv' for k in MARKETS}, m['asof'])
    if len(rows) != m.get('official_market_rows'):
        raise ValueError('OFFICIAL_EOD_COUNT_MISMATCH')
    info['file_sha256'].update(files)
    if m['asof'] != asof:
        info['status'] = 'STALE_NOT_SAME_DAY_TURNOVER'
        return {}, info
    # v6.5 authenticates the provider but has no regular-only session proof.
    # An upstream boolean alone cannot elevate its mixed/unknown session prices.
    info['status'] = 'ACTUAL_SOURCE_TURNOVER_SESSION_UNCERTIFIED'
    return rows, info


def load_scope(path, evaluated_at):
    if path is None or not path.exists():
        return {}, {'status': 'MISSING', 'file_sha256': {}}
    m = read_json(path)
    if m.get('schema') != SCOPE_SCHEMA:
        raise ValueError('SCOPE_SCHEMA_MISMATCH')
    ix = {}
    for r in m.get('reviews', []):
        t = code(r.get('ticker'))
        if t in ix:
            raise ValueError('DUPLICATE_PRIMARY_SCOPE_REVIEW')
        if r.get('status') not in ('EXCLUDE_PHARMA_BIOTECH', 'BUSINESS_REVIEWED_NON_PHARMA',
                                   'BOUNDARY_REVIEW_REQUIRED'):
            raise ValueError('INVALID_SCOPE_DECISION')
        if (r.get('identity_verified') is not True or not r.get('reason')
                or not str(r.get('source_url', '')).startswith('https://')):
            raise ValueError('SCOPE_PRIMARY_IDENTITY_OR_PROVENANCE_MISSING')
        if clock(r.get('reviewed_at')) > clock(evaluated_at):
            continue  # Not yet observed: never use a later analyst classification.
        ix[t] = r
    return ix, {'status': 'TARGETED_REVIEW_NOT_EXHAUSTIVE_TAXONOMY',
                'historical_vintage_certified': False,
                'file_sha256': {path.name: sha(path)}}


def assess(row, raw_rank, asof, basic, basic_info, scope, eod):
    t = code(row.get('ticker'))
    name = str(row.get('name') or '')
    b = basic.get(t, {})
    sr = scope.get(t, {})
    why = []
    group, share_kind = b.get('security_group', ''), b.get('share_kind', '')
    raw_type = str(row.get('instrument_type') or 'UNKNOWN')
    special_name = any(s in name.upper() for s in ('스팩', 'SPAC', '리츠', 'REIT', 'ETF', 'ETN'))
    if raw_type == 'NON_COMMON_OR_SPECIAL' or special_name:
        instrument = 'EXCLUDE_SPECIAL'
    elif group and (group != '주권' or share_kind != '보통주'):
        instrument = 'EXCLUDE_NON_DOMESTIC_COMMON'
    elif group == '주권' and share_kind == '보통주':
        instrument = ('COMMON_IN_CURRENT_SNAPSHOT' if basic_info.get('asof') == asof
                      else 'COMMON_IN_PRIOR_SNAPSHOT')
    else:
        instrument = 'UNKNOWN_REQUIRES_OFFICIAL_BASIC'
    if instrument.startswith('EXCLUDE'):
        why.append(instrument)
    elif instrument != 'COMMON_IN_CURRENT_SNAPSHOT':
        why.append('CURRENT_COMMON_SHARE_PROOF_MISSING')
    scope_status = sr.get('status', 'UNREVIEWED_BUSINESS')
    if scope_status == 'EXCLUDE_PHARMA_BIOTECH':
        why.append(scope_status)
    elif scope_status != 'BUSINESS_REVIEWED_NON_PHARMA':
        why.append('BUSINESS_SCOPE_REVIEW_REQUIRED')
    actual, eod_close = None, None
    actual_status = 'ACTUAL_SOURCE_TURNOVER_MISSING'
    source = eod.get(t)
    if source:
        actual, eod_close = number(source.get('turnover_krw')), number(source.get('close'))
        if (source.get('valid_daily_bar') not in (True, 'True')
                or eod_close is None or eod_close <= 0
                or number(source.get('volume')) is None):
            actual, eod_close = None, None
            actual_status = 'OFFICIAL_DAILY_ROW_INVALID'
        elif actual is None:
            actual_status = 'ACTUAL_SOURCE_TURNOVER_INVALID'
        elif actual == 0:
            actual_status = 'ACTUAL_SOURCE_TURNOVER_ZERO_NO_LIQUIDITY_PASS'
        else:
            actual_status = 'ACTUAL_SOURCE_VALUE_SESSION_UNCERTIFIED'
    if actual is None or actual == 0:
        why.append(actual_status)
    why.extend(['REGULAR_SESSION_PRICE_PROOF_MISSING',
                'COMPANY_SECTOR_FLOW_FINAL_SCORE_AND_ENTRY_REVIEW_REQUIRED'])
    excluded = instrument.startswith('EXCLUDE') or scope_status == 'EXCLUDE_PHARMA_BIOTECH'
    raw_close = number(row.get('close_reference'))
    return dict(raw_rank=raw_rank, ticker=t, name=name, asof=asof,
        raw_c3_preliminary_score=row.get('c3_preliminary_score', ''),
        raw_instrument_type=raw_type, basic_snapshot_asof=basic_info.get('asof'),
        security_group=group, share_kind=share_kind,
        basic_evidence_status=basic_info['status'], instrument_review=instrument,
        business_scope_status=scope_status, scope_reviewed_at=sr.get('reviewed_at'),
        scope_source_url=sr.get('source_url'), scope_reason=sr.get('reason'),
        raw_turnover_estimate_krw=number(row.get('turnover_krw')),
        raw_turnover_source=row.get('turnover_source'),
        actual_source_turnover_krw=actual, actual_turnover_status=actual_status,
        official_eod_close_reference=eod_close, raw_close_reference=raw_close,
        close_sources_equal=(eod_close == raw_close if eod_close is not None and raw_close is not None else None),
        regular_session_certified=False,
        review_status='EXCLUDE_FROM_C3' if excluded else 'EVIDENCE_PENDING',
        blocking_reasons=';'.join(why), final_score80=None, approved_buy_range=None,
        trade_approved=False, orders_enabled=False)


def calculate(reports, basic_dir, scope_path, eod_dir, evaluated_at):
    clock(evaluated_at)
    status = read_json(reports / 'status.json')
    asof = status.get('market_data_date')
    day(asof)
    if (status.get('scan_complete') is not True or status.get('data_date_verified') is not True
            or day(asof) > clock(evaluated_at).astimezone(ZoneInfo('Asia/Seoul')).date()):
        raise ValueError('INCOMPLETE_OR_FUTURE_SCAN')
    source = read_csv(reports / 'c3_preliminary.csv')
    seen = set()
    for r in source:
        t = code(r.get('ticker'))
        if t in seen or r.get('latest_date') != asof:
            raise ValueError('CANDIDATE_DUPLICATE_OR_WRONG_DATE')
        seen.add(t)
    basic, bi = load_basic(basic_dir, asof, evaluated_at)
    scope, si = load_scope(scope_path, evaluated_at)
    eod, ei = load_eod(eod_dir, asof, evaluated_at)
    rows = [assess(r, i, asof, basic, bi, scope, eod) for i, r in enumerate(source, 1)]
    meta = dict(schema=SCHEMA, evidence_audit_completed=True, asof=asof, evaluated_at_utc=clock(evaluated_at).astimezone(timezone.utc).isoformat(),
        evaluated_at_kst=clock(evaluated_at).astimezone(ZoneInfo('Asia/Seoul')).isoformat(),
        candidate_rows=len(rows), all_raw_candidates_preserved=True,
        raw_scan_target=status.get('universe'), raw_valid_count=status.get('valid_ohlcv'),
        raw_score_not_final80=True, previous_results_not_rewritten=True,
        input_sha256={f: sha(reports / f) for f in ('status.json', 'c3_preliminary.csv')},
        basic_source=bi, business_scope_source=si, actual_turnover_source=ei,
        instrument_counts=dict(Counter(r['instrument_review'] for r in rows)),
        business_counts=dict(Counter(r['business_scope_status'] for r in rows)),
        decision_counts=dict(Counter(r['review_status'] for r in rows)),
        actual_turnover_observed_count=sum(r['actual_source_turnover_krw'] is not None for r in rows),
        regular_session_certified_count=0, approved_buy_count=0,
        first_discovery_times_not_inferred=True, historical_vintage_certified=False,
        account_values_used=False, raw_ranking_changed=False, decision='CASH',
        profitability_proven=False, trade_approved=False, orders_enabled=False)
    return rows, meta


def write_outputs(outdir, rows, meta):
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / 'c3_candidate_evidence_v1.csv'
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    meta['output_sha256'] = {path.name: sha(path)}
    lines = ['# 🤖 제갈AI Pro · C3 후보 검증', '',
             f"자료일 **{meta['asof']}** / 검토 **{meta['evaluated_at_kst']}**", '',
             f"예비후보 **{len(rows)}개** · 제외 **{meta['decision_counts'].get('EXCLUDE_FROM_C3', 0)}개** · 승인 매수 **0개 · CASH**", '',
             '과거 공식 종목분류는 해당 날짜의 관찰 근거다. 현재 보통주 확인·정규장 가격·실제 거래대금·기업과 타점 검증을 대신하지 않는다.', '',
             '| 원순위 | 종목 | 유형 검토 | 사업 범위 | 결과 |',
             '|---|---|---|---|---|']
    labels = {'COMMON_IN_PRIOR_SNAPSHOT': '과거 보통주 근거·현재 확인 필요',
              'COMMON_IN_CURRENT_SNAPSHOT': '당일 보통주 원본 확인',
              'EXCLUDE_SPECIAL': '스팩·리츠 등 제외',
              'EXCLUDE_NON_DOMESTIC_COMMON': '국내 일반 보통주 범위 제외',
              'UNKNOWN_REQUIRES_OFFICIAL_BASIC': '종목유형 원본 필요',
              'EXCLUDE_PHARMA_BIOTECH': '제약·바이오 제외',
              'BUSINESS_REVIEWED_NON_PHARMA': '주사업 검토·기업가치 별도',
              'UNREVIEWED_BUSINESS': '사업 원문 검토 필요',
              'BOUNDARY_REVIEW_REQUIRED': '사업 범위 추가 검토',
              'EXCLUDE_FROM_C3': '선정 대상 제외',
              'EVIDENCE_PENDING': '추가 검증 대기'}
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')
    for r in rows:
        values = [r['raw_rank'], f"{r['name']} {r['ticker']}",
                  labels[r['instrument_review']], labels[r['business_scope_status']],
                  labels[r['review_status']]]
        lines.append('| ' + ' | '.join(cell(v) for v in values) + ' |')
    lines.extend(['', '종가가 보유 당시 구조선 아래로 마감하면 다음 관측 시가 정리. 동일 종가와 장중 꼬리는 종가 이탈로 처리하지 않는다.'])
    md = outdir / 'c3_candidate_evidence_v1_mobile.md'
    md.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    meta['output_sha256'][md.name] = sha(md)
    (outdir / 'c3_candidate_evidence_v1_status.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reports', type=Path, default=Path('reports'))
    p.add_argument('--basic-dir', type=Path, default=Path('config/c3_screening_evidence/basic_20261023'))
    p.add_argument('--scope', type=Path, default=Path('config/c3_screening_evidence/business_scope_review_v1.json'))
    p.add_argument('--eod-dir', type=Path, default=Path('reports/c3_official_eod'))
    p.add_argument('--outdir', type=Path, default=Path('reports'))
    p.add_argument('--evaluated-at', default=None, help='Explicit frozen aware clock for offline replay only')
    a = p.parse_args()
    now = a.evaluated_at or datetime.now(timezone.utc).isoformat()
    try:
        rows, meta = calculate(a.reports, a.basic_dir, a.scope, a.eod_dir, now)
    except (ValueError, TypeError, KeyError, OSError):
        # Invalidate the current status; never accept a previous CSV as today's audit.
        a.outdir.mkdir(parents=True, exist_ok=True)
        failure = dict(schema=SCHEMA, evidence_audit_completed=False,
            error='EVIDENCE_INPUT_INVALID_OR_UNAVAILABLE', output_sha256={},
            approved_buy_count=0, decision='CASH', trade_approved=False,
            orders_enabled=False)
        (a.outdir / 'c3_candidate_evidence_v1_status.json').write_text(
            json.dumps(failure, indent=2) + '\n', encoding='utf-8')
        raise SystemExit('C3_EVIDENCE_INPUT_INVALID_CASH') from None
    write_outputs(a.outdir, rows, meta)
    print(json.dumps({k: meta[k] for k in ('schema', 'asof', 'candidate_rows', 'decision_counts',
                                         'actual_turnover_observed_count', 'approved_buy_count', 'decision')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
