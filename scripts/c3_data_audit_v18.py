"""Later corroboration of frozen research prices; no signal, price or fill writes."""
import argparse,collections,csv,hashlib,json,os,re,time
from datetime import datetime,timezone
from pathlib import Path
from c3_data_quality_v17 import classify_bar,regular_contract
from c3_runtime_v10 import quality

FIELDS=('open','high','low','close','volume','turnover_krw')


def comparison(left,right,day):
    def index(rows):
        out={}
        for r in rows:
            t=r['ticker']
            if not re.fullmatch('[A-Z0-9]{6}',t) or t in out:raise ValueError('INVALID_OR_DUPLICATE_SECURITY')
            if r.get('asof')!=day or r['market'] not in ('KOSPI','KOSDAQ'):raise ValueError('WRONG_DATE_OR_MARKET')
            out[t]=r
        return out
    a=index(left);b=index(right);joined=sorted(a.keys()&b.keys());diff=[]
    for t in joined:
        f=[k for k in FIELDS if float(a[t][k])!=float(b[t][k])]
        if a[t]['market']!=b[t]['market']:f.append('market')
        if f:diff.append(dict(ticker=t,fields=f))
    return dict(asof=day,left_rows=len(a),right_rows=len(b),compared=len(joined),
        missing_on_right=sorted(a.keys()-b.keys()),extra_on_right=sorted(b.keys()-a.keys()),
        field_mismatches=diff,matched_rows=len(joined)-len(diff),
        same_ultimate_origin='KRX',independent_vendor_certified=False,regular_only_certified=False)


def census(prices,basic,day):
    by={};seen=set()
    for r in basic:
        t=r['ticker']
        if t in seen or not re.fullmatch('[A-Z0-9]{6}',t):raise ValueError('DUPLICATE_OR_INVALID_BASIC_CODE')
        seen.add(t)
        if r.get('asof_requested')!=day or r['market'] not in ('KOSPI','KOSDAQ'):raise ValueError('BASIC_DATE_OR_MARKET_MISMATCH')
        if r.get('listed_date','')>day.replace('-',''):raise ValueError('FUTURE_LISTING')
        by[t]=r
    p={r['ticker']:r for r in prices};markets={}
    for m in ('KOSPI','KOSDAQ'):
        expected={t for t,r in by.items() if r['market']==m};found={t for t,r in p.items() if r['market']==m}
        markets[m]=dict(official_requested_date_rows=len(expected),price_rows=len(found),
            missing=sorted(expected-found),extra=sorted(found-expected),exact_membership_match=bool(expected) and expected==found)
    return dict(asof=day,markets=markets,requested_date_membership_match=all(v['exact_membership_match'] for v in markets.values()),
        share_kind_counts=dict(collections.Counter(r['share_kind'] for r in basic)),
        security_group_counts=dict(collections.Counter(r['security_group'] for r in basic)),
        historical_vintage_independently_certified=False,halt_status_not_inferred_from_zero_volume=True,
        industry_and_spac_classification_not_supplied_by_basic_api=True,
        historical_classification_and_decisions_unchanged=True)


def run(day,ledger,outdir):
    from c3_forward_ledger_v8 import read_record
    from c3_eod_source_v9 import collect_day
    from official_issuer_entry_v610 import retrieve,load_basic
    from c3_artifact_audit_v18 import write
    root=Path(outdir);private=root.parent/'private-v18';private.mkdir(parents=True,exist_ok=True);started=time.monotonic()
    def protected():
        base=Path(ledger)/'lanes'
        return {str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest() for p in base.rglob('*') if p.is_file()}
    preserved=protected()
    path=Path(ledger)/'lanes/krx_unadjusted_v12/markets'/(day+'.json.gz');before=path.read_bytes();record=read_record(path)
    if record['asof']!=day:raise ValueError('FROZEN_MARKET_DATE_MISMATCH')
    prices=[dict(r,ticker=t,asof=day) for t,r in record['rows'].items()]
    m=record['source']['supply_manifest'];v=m.get('validation',{});q=quality(prices,prices,day)
    if q['errors']:raise ValueError('FROZEN_SOURCE_NEW_QUALITY_CHECK_REJECTED')
    official=collect_day(day,private/'official',os.environ.get('KRX_AUTH_KEY'))
    official_rows=[]
    if official['official_dataset_usable']:
        for market in ('KOSPI','KOSDAQ'):
            p=private/'official'/(market+'_official.csv')
            if hashlib.sha256(p.read_bytes()).hexdigest()!=official['market_file_sha256'][market]:raise ValueError('OFFICIAL_FILE_HASH_MISMATCH')
            with p.open(encoding='utf-8-sig') as f:official_rows+=list(csv.DictReader(f))
    basic_meta=retrieve(day,private/'basic',os.environ.get('KRX_AUTH_KEY'));basic=load_basic(private/'basic',basic_meta)
    captured=record['source']['received_at']
    result=dict(schema='C3_DATA_AUDIT_V18',asof=day,audited_at=datetime.now(timezone.utc).isoformat(),
        original_snapshot_sha256=hashlib.sha256(before).hexdigest(),source_provider=m.get('source_provider'),
        original_received_at=captured,original_price_basis=record['source']['price_basis'],
        original_cache_commit=v.get('cache_commit'),original_cache_file_commit=v.get('cache_file_commit'),
        originally_published_after_close=v.get('dated_file_published_after_close'),
        quality=q,bar_states=dict(collections.Counter(classify_bar(r) for r in prices)),
        original_session_contract=regular_contract(m.get('source_provider'),day,captured),
        official_status=official['status'],official_response_diagnostics=official['response_diagnostics'],
        comparison=comparison(prices,official_rows,day) if official_rows else None,
        official_numeric_quality=quality(official_rows,prices,day) if official_rows else None,
        official_listing_status=basic_meta['error'],
        census=census(prices,list(basic.values()),day) if basic else None,
        full_current_listing_census_independently_verified=False,
        no_retroactive_price_or_classification_substitution=True,registered_signals_changed=False,
        new_registered_signals=0,telegram_sends=0,regular_only_certified=False,trade_approved=False,orders_enabled=False,
        elapsed_seconds=time.monotonic()-started,official_request_count=len(official['response_diagnostics'])+2,
        unavailable_followup=['REGULAR_ONLY_VOLUME_AND_TURNOVER','INDEPENDENT_VENDOR_SESSION_ATTESTATION','OFFICIAL_HISTORICAL_LISTING_VINTAGE','DATED_HALT_AND_DELISTING_EVENTS'])
    if path.read_bytes()!=before:raise ValueError('FROZEN_SOURCE_CHANGED_DURING_AUDIT')
    if protected()!=preserved:raise ValueError('IMMUTABLE_LEDGER_CHANGED_DURING_AUDIT')
    result['immutable_files_verified_unchanged']=len(preserved)
    result['immutable_tree_sha256']=hashlib.sha256(json.dumps(preserved,sort_keys=True).encode()).hexdigest()
    write(root/'data_audit.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--asof',required=True);p.add_argument('--ledger',required=True);p.add_argument('--outdir',required=True);a=p.parse_args()
    r=run(a.asof,a.ledger,a.outdir);print(json.dumps(r,ensure_ascii=False))
