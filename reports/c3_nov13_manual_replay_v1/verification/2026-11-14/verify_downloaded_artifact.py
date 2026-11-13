"""Read-only verification of the downloaded Nov13 research artifact."""
from pathlib import Path
from collections import Counter
from decimal import Decimal
import csv, hashlib, io, json, math
from PIL import Image

ROOT=Path(__file__).resolve().parent
P=ROOT/'run-43508677372'
def read(p): return json.loads(p.read_text())
def canonical(d): return json.dumps(d,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(raw): return hashlib.sha256(raw).hexdigest()
def objsha(d): return sha(canonical(d))
checks=[]
def passed(name,**facts): checks.append(dict(check=name,status='PASS',**facts))

archive=ROOT/'C3_20261113_manual_43508677372.zip'
assert sha(archive.read_bytes())=='1440eba159eb0e8eeaf6e5b2352e0be0b12593e72e0c3ab55733599d7bf35cf8'
passed('artifact_zip_digest',sha256=sha(archive.read_bytes()))
pref=read(P/'evidence/live-prefetch/prefetch.json')
source=read(P/'output/source/collection.json')
norm=read(P/'output/source/normalized_market.json')
report=read(P/'output/analysis/report.json')
raw=(P/'evidence/live-prefetch/original.csv').read_bytes()
assert sha(raw)==pref['raw_sha256']==source['raw_sha256']
assert pref['day']==norm['asof']==source['asof']==report['source_date']=='2026-11-13'
assert source['source_run_id']==report['source_run_id']=='43508677372'
assert source['execution_mode']=='AUTHENTICATED_WORKFLOW_DISPATCH'
passed('dated_raw_source',raw_sha256=sha(raw),collected_at=pref['collected_at'],file_commit=pref['file_commit'],file_commit_at=pref['file_commit_at'])
fields=('open','high','low','close','volume','turnover_krw')
cached=[];excluded=Counter()
for r in csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))):
    if r['MarketId']=='KNX': excluded['KONEX']+=1; continue
    market={'STK':'KOSPI','KSQ':'KOSDAQ'}[r['MarketId']]
    item=dict(ticker=r['Code'],name=r['Name'],market=market,asof='2026-11-13')
    item.update({k:float(str(r[c]).replace(',','')) for k,c in zip(fields,('Open','High','Low','Close','Volume','Amount'))})
    cached.append(item)
rows=norm['rows']; assert len(rows)==len(cached)==len({r['ticker'] for r in rows})==2770
def comparable(rows):
    return sorted([dict(ticker=r['ticker'],name=r['name'],market=r['market'],asof=r['asof'],**{k:float(r[k]) for k in fields}) for r in rows],key=lambda r:r['ticker'])
assert comparable(rows)==comparable(cached)
assert objsha(comparable(rows))==pref['normalized_rows_sha256']==source['normalized_rows_sha256']==report['normalized_rows_sha256']
assert Counter(r['market'] for r in rows)==Counter(KOSPI=936,KOSDAQ=1834)
assert excluded==Counter(KONEX=107)
assert pref['quality']['status']=='QUALITY_GATE_PASSED' and not pref['quality']['errors']
for r in rows:
    assert all(math.isfinite(r[k]) and r[k]>=0 for k in fields)
    if r['volume']>0:
        assert 0<r['low']<=min(r['open'],r['close'])<=max(r['open'],r['close'])<=r['high']
    assert r['volume']==int(r['volume'])
passed('all_raw_normalized_fields',rows=len(rows),markets=dict(Counter(r['market'] for r in rows)),excluded=dict(excluded),normalized_sha256=source['normalized_rows_sha256'],full_current_listing_census_verified=pref['quality']['full_current_listing_census_verified'])
prices={r['ticker']:r for r in rows}
payload=dict(schema='C3_NEW_DATED_SOURCE_V1',asof='2026-11-13',price_basis=source['price_basis'],regular_only_certified=False,rows=prices)
assert objsha(payload)==report['source_hash']
without_hash={k:v for k,v in report.items() if k!='report_payload_sha256'}
assert objsha(without_hash)==report['report_payload_sha256']
passed('report_source_canonical_link',source_hash=report['source_hash'],report_hash=report['report_payload_sha256'])
idx=read(P/'output/source/indices/index_manifest.json')['series']
for market,meta in idx.items():
    path=P/'output/source/indices'/(market+'_index.csv')
    assert sha(path.read_bytes())==meta['csv_sha256']
    data=list(csv.DictReader(io.StringIO(path.read_text())))
    assert len(data)==meta['rows']==374 and data[-1]['date']==meta['end']=='2026-11-13'
    assert len({r['date'] for r in data})==len(data) and all(r['date']<='2026-11-13' and float(r['close'])>0 for r in data)
passed('same_day_board_indices',rows_each=374,asof='2026-11-13',official_certification=False)
charts=[]
for role,manifest_file,source_folder,png_folder in [('ENTRY_FIT','card_manifest.json','chart_sources','cards'),('WATCH','watch_card_manifest.json','watch_chart_sources','watch_cards')]:
    manifest=read(P/'output/analysis'/manifest_file)
    assert manifest['report_hash']==report['report_payload_sha256']
    for c in manifest['cards']:
        path=P/'output/analysis'/png_folder/c['png']; body=read(P/'output/analysis'/source_folder/(c['ticker']+'.json'))
        assert sha(path.read_bytes())==c['png_sha256'] and objsha(body)==c['chart_source_sha256']
        with Image.open(path) as im:
            assert im.size==(1400,2400)
            embedded=json.loads(im.info['C3_manifest'])
        assert embedded=={k:v for k,v in c.items() if k not in ('png','png_sha256')}
        assert c['source_hash']==body['source_hash']==report['source_hash'] and c['report_hash']==report['report_payload_sha256']
        assert c['source_run_id']=='43508677372' and c['price_asof']==body['source_date']=='2026-11-13'
        bars=body['bars'];assert len(bars)==c['source_bars']==119 and c['visible_bars']==c['ma60_visible_points']==60
        assert [r['date'] for r in bars]==sorted({r['date'] for r in bars}) and bars[-1]['date']=='2026-11-13'
        assert len({r['segment'] for r in bars})==1 and all(r['tradable'] and not r['action_boundary'] for r in bars)
        assert c['close']==bars[-1]['close']==prices[c['ticker']]['close'] and c['name']==prices[c['ticker']]['name']
        assert all(bars[-1][k]==prices[c['ticker']][k] for k in fields)
        assert all(r['date']<='2026-11-13' and 0<r['low']<=min(r['open'],r['close'])<=max(r['open'],r['close'])<=r['high'] for r in bars)
        for n in (5,20,60):
            calculated=[float(sum((Decimal(str(x['close'])) for x in bars[i-n+1:i+1]),Decimal(0))/n) for i in range(len(bars)-5,len(bars))]
            assert calculated==c['ma_audit'][str(n)]['last5'] and c['ma_audit'][str(n)]['max_decimal_error_krw']<=1e-7
        if role=='ENTRY_FIT':
            row=next(x for x in report['final_research_top2'] if x['ticker']==c['ticker']);plan=row['display_plan'];r=plan['range']
            assert c['range']==[r['low'],r['high']] and all(c[k]==plan[k] for k in ('stop','r1','r2'))
        else:
            row=next(x for x in report['watch_top2'] if x['ticker']==c['ticker'])
            assert row['rank']==c['rank'] and row['entry_fit_selected']==c['entry_fit_selected']
        assert not c['buy_approved']
        charts.append(dict(role=role,ticker=c['ticker'],name=c['name'],close=c['close'],range=c['range'],stop=c['stop'],r1=c['r1'],r2=c['r2'],png=path.relative_to(P).as_posix(),png_sha256=c['png_sha256'],chart_source_sha256=c['chart_source_sha256'],source_bars=119,ma60_visible_points=60))
passed('three_pngs_json_raw_ma_and_payload_match',count=len(charts),charts=charts)
assert len(charts)==3 and len(report['watch_top2'])==2 and len(report['final_research_top2'])==1
row=report['final_research_top2'][0];plan=row['display_plan'];r=plan['range']
b=(1+.0015)*(1+.001);s=(1-.005)*(1-.001)
for endpoint in r['endpoints'].values():
    e=endpoint['price'];loss=e*b-plan['stop']*s
    assert abs(endpoint['net_r1_rr']-(plan['r1']*s-e*b)/loss)<1e-12
    assert abs(endpoint['net_r2_rr']-(plan['r2']*s-e*b)/loss)<1e-12
    assert abs(endpoint['stop_risk_pct']-100*(e-plan['stop'])/e)<1e-12
assert 0<plan['stop']<r['low']<=r['high']<plan['r1']<plan['r2'] and r['ticks_checked']==13 and r['all_legal_ticks_passed']
assert plan['evidence']['confirmed_pivots'][0]['known_on']<='2026-11-13'
passed('entry_plan_prices_and_cost_adjusted_rr',ticker=row['ticker'],range=[r['low'],r['high']],stop=plan['stop'],r1=plan['r1'],r2=plan['r2'],upper_risk_pct=r['endpoints']['upper']['stop_risk_pct'],min_net_r1_rr=r['min_net_r1_rr'],fees_are_inherited_research_assumptions=True)
before=read(P/'output/integrity/before.json');after=read(P/'output/integrity/after.json')
assert before['protected']==after['protected'] and before['protected_sha256']==after['protected_sha256']
assert after['originals_and_receipts_unchanged'] and after['counts']==before['counts']
assert after['ledger_writes']==after['telegram_requests']==0
delivery=read(P/'output/analysis/delivery_status.json')
assert delivery['status']=='RESEARCH_NOT_SENT' and delivery['actual_telegram_requests']==0 and delivery['repeat']=='DUPLICATE_BLOCKED'
assert not report['buy_approved'] and not report['orders_enabled'] and not report['automated_order_enabled'] and report['telegram_requests']==report['new_forward_records']==0
assert not report['approved_original_registered'] and report['current_action']=='CASH'
assert not source['official_krx_match_verified'] and not source['regular_only_certified'] and not report['financial_original_pit_verified']
assert source['lookahead_relative_to_target_close'] and not source['historical_point_in_time_backtest'] and not source['publication_timestamp_attested']
passed('protected_originals_receipts_and_no_live_actions',counts=after['counts'],protected_sha256=after['protected_sha256'],telegram_status=delivery['status'],duplicate_test=delivery['repeat'],new_original_signals=0,orders=0)
history=read(P/'output/analysis/history_provenance.json')
assert history['approved_90_suffix_equal'] and all(x['asof']<'2026-11-13' for x in history['prior_research_sources'])
passed('existing_history_and_prior_research_prices',approved_90_suffix_equal=True,prior_research_sources=history['prior_research_sources'])
official=read(ROOT/'ops-43508657689/14077816258/official_comparison.json')
assert not official['official_krx_match_verified'] and not official['manual_source_manifest_modified']
diagnostics={k:[{x:r.get(x) for x in ('asof','market','endpoint','http_status','outblock_rows','normalized_rows','status','credential_present','provider_error','body_sha256','received_at')} for r in official[k]['response_diagnostics']] for k in ('official','control_20261112')}
passed('official_failure_not_promoted',official_gate='HOLD',diagnostics=diagnostics)
audit=dict(schema='C3_NOV13_DOWNLOADED_ARTIFACT_VERIFICATION_V1',asof='2026-11-13',run_id='43508677372',run_commit=report['research_commit'],checks=checks,checks_passed=len(checks),checks_failed=0,research_analysis='COMPLETE',official_krx_gate='HOLD',actual_buy_approved=False,live_telegram_sent=False)
(ROOT/'artifact_verification.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(check_groups_passed=len(checks),check_groups_failed=0,charts=[{k:c[k] for k in ('role','ticker','name','png_sha256')} for c in charts],protected_sha256=after['protected_sha256'],official_krx_gate='HOLD'),ensure_ascii=False))
