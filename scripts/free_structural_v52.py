#!/usr/bin/env python3
"""Free C3/K100 completed daily-bar structural research. No orders or live BUY."""
import argparse,csv,json,math
from collections import defaultdict
from datetime import date,datetime
from pathlib import Path
from zoneinfo import ZoneInfo

FIELDS=('ticker','name','snapshot_date','data_source','close_reference','atr14',
 'confirmed_pivot_date','confirmed_pivot_low','structural_stop_reference',
 'entry1_close_reference','entry2_ma20_proxy','no_chase_reference',
 'prior_60d_resistance','rr_to_prior_resistance','structural_risk_pct',
 'c3_preliminary_score','k100_preliminary_score','structure_status',
 'blocking_reasons','trade_approval')

def read_csv(path):
    if not path.is_file():return []
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def number(x,zero=False):
    try:v=float(x)
    except (TypeError,ValueError):return None
    return v if math.isfinite(v) and (v>=0 if zero else v>0) else None

def day(x):
    try:return date.fromisoformat(str(x)[:10])
    except (TypeError,ValueError):return None

def history_check(rows,ticker,snapshot):
    if len(rows)<80:return None,'INSUFFICIENT_DAILY_HISTORY'
    bars=[]
    for r in rows:
        d=day(r.get('date'))
        prices=[number(r.get(k)) for k in ('open','high','low','close')]
        v=number(r.get('volume'),zero=True)
        if d is None or any(x is None for x in prices) or v is None:
            return None,'INVALID_HISTORY_ROW'
        op,hi,lo,cl=prices
        if not lo<=min(op,cl)<=max(op,cl)<=hi:return None,'INVALID_HISTORY_OHLC'
        if str(r.get('ticker','')).zfill(6)!=ticker:return None,'HISTORY_TICKER_MISMATCH'
        if r.get('data_source') not in ('pykrx','FinanceDataReader'):
            return None,'HISTORY_SOURCE_UNTRUSTED'
        bars.append(dict(date=d,open=op,high=hi,low=lo,close=cl,volume=v,source=r['data_source']))
    ds=[r['date'] for r in bars]
    if any(a>=b for a,b in zip(ds,ds[1:])):return None,'HISTORY_NOT_CHRONOLOGICAL'
    if snapshot is None or ds[-1]!=snapshot:return None,'HISTORY_DATE_MISMATCH'
    if len({r['source'] for r in bars})!=1:return None,'MIXED_HISTORY_SOURCES'
    return bars,None

def atr14(bars):
    ranges=[]
    for i in range(len(bars)-14,len(bars)):
        r,p=bars[i],bars[i-1]
        ranges.append(max(r['high']-r['low'],abs(r['high']-p['close']),abs(r['low']-p['close'])))
    return sum(ranges)/14

def last_confirmed_pivot(bars,lookback=35):
    end=len(bars)-1
    for i in range(end-2,max(2,end-lookback)-1,-1):
        low=bars[i]['low']
        if (low<bars[i-1]['low'] and low<bars[i-2]['low']
          and low<=bars[i+1]['low'] and low<=bars[i+2]['low']
          and all(x['low']>=low for x in bars[i+1:])):
            return bars[i]['date'],low
    return None,None

def structural_row(candidate,history,snapshot,c3=None,k100=None):
    ticker=str(candidate.get('ticker','')).strip().zfill(6)
    out=dict.fromkeys(FIELDS,'')
    out.update(ticker=ticker,name=candidate.get('name',''),snapshot_date=str(snapshot) if snapshot else '',
               data_source=candidate.get('data_source',''),trade_approval='NO')
    if c3:out['c3_preliminary_score']=c3.get('c3_preliminary_score','')
    if k100:out['k100_preliminary_score']=k100.get('k100_preliminary_score','')
    errors=[]
    if not c3 or not k100:errors.append('PRELIMINARY_RANKING_MISSING')
    typ=str(candidate.get('instrument_type','')).upper().strip()
    if typ=='NON_COMMON_OR_SPECIAL':errors.append('SPECIAL_INSTRUMENT_EXCLUDED')
    elif typ not in ('COMMON','COMMON_STOCK'):errors.append('COMMON_STOCK_NOT_VERIFIED')
    if candidate.get('turnover_source')!='SOURCE_REPORTED':errors.append('TURNOVER_IS_ESTIMATED')
    bars,problem=history_check(history,ticker,snapshot)
    if problem:errors.append(problem)
    else:
        close=bars[-1]['close'];atr=atr14(bars)
        out.update(close_reference=round(close,2),atr14=round(atr,2))
        when,pivot=last_confirmed_pivot(bars)
        if pivot is None or pivot>=close:errors.append('NO_CONFIRMED_DAILY_PIVOT')
        else:
            stop=pivot-max(0.25*atr,0.003*close)
            risk=(close-stop)/close
            out.update(confirmed_pivot_date=when.isoformat(),confirmed_pivot_low=round(pivot,2),
                       structural_stop_reference=round(stop,2),structural_risk_pct=round(risk*100,2))
            if not 0.015<=risk<=0.12:errors.append('STRUCTURAL_RISK_NEEDS_REVIEW')
            else:
                out['entry1_close_reference']=round(close,2)
                ma20=sum(r['close'] for r in bars[-20:])/20
                if stop<ma20<close:out['entry2_ma20_proxy']=round(ma20,2)
                else:errors.append('NO_VALID_SECOND_ENTRY_PROXY')
                chase=close+min(0.5*atr,0.03*close)
                out['no_chase_reference']=round(chase,2)
                resistance=max(r['high'] for r in bars[-61:-1])
                if resistance>chase:
                    out['prior_60d_resistance']=round(resistance,2)
                    rr=(resistance-chase)/(chase-stop)
                    out['rr_to_prior_resistance']=round(rr,2)
                    if rr<2:errors.append('REWARD_RISK_BELOW_2')
                else:errors.append('NO_PRIOR_HIGH_ABOVE_NO_CHASE')
    out['structure_status']=('STRUCTURE_REFERENCE_ONLY'
      if out['structural_stop_reference']!='' and
      'STRUCTURAL_RISK_NEEDS_REVIEW' not in errors and
      'SPECIAL_INSTRUMENT_EXCLUDED' not in errors else 'WAIT_DATA_OR_STRUCTURE')
    out['blocking_reasons']='|'.join(dict.fromkeys(errors))
    return out

def build(status,candidates,histories,c3_rank,k100_rank,asof):
    snapshot=day(status.get('market_data_date'))
    problems=[]
    if not status.get('scan_complete') or not status.get('data_date_verified'):
        problems.append('SCANNER_NOT_VERIFIED')
    coverage=number(status.get('coverage_ratio'))
    if coverage is None or coverage<0.95:problems.append('INSUFFICIENT_MARKET_COVERAGE')
    if snapshot is None or not 0<=(asof-snapshot).days<=4:
        problems.append('MARKET_DATA_STALE_OR_FUTURE')
    if not candidates:problems.append('NO_CANDIDATE_ROWS')
    if snapshot and any(day(r.get('latest_date'))!=snapshot for r in candidates):
        problems.append('INCONSISTENT_CANDIDATE_DATES')
    c3={str(r.get('ticker','')).zfill(6):r for r in c3_rank}
    k100={str(r.get('ticker','')).zfill(6):r for r in k100_rank}
    grouped=defaultdict(list)
    for r in histories:grouped[str(r.get('ticker','')).zfill(6)].append(r)
    plans=[structural_row(r,grouped.get(str(r.get('ticker','')).zfill(6),[]),
       snapshot,c3.get(str(r.get('ticker','')).zfill(6)),
       k100.get(str(r.get('ticker','')).zfill(6))) for r in candidates]
    def top(key):
        valid=[r for r in plans if r['structure_status']=='STRUCTURE_REFERENCE_ONLY'
          and 'SPECIAL_INSTRUMENT_EXCLUDED' not in r['blocking_reasons']]
        def rank(r):
            try:return int(r[key])
            except (ValueError,TypeError):return 0
        return [r['ticker'] for r in sorted(valid,key=lambda x:(-rank(x),x['ticker']))[:5]]
    report=dict(version='free_structural_v52',asof_kst=str(asof),
      market_data_date=str(snapshot) if snapshot else None,coverage_ratio=coverage,
      candidates=len(candidates),structural_reference_count=sum(
      r['structure_status']=='STRUCTURE_REFERENCE_ONLY' for r in plans),
      c3_research_top5=top('c3_preliminary_score'),
      k100_research_top5=top('k100_preliminary_score'),
      global_blockers=list(dict.fromkeys(problems+[
       'VERIFIED_SECTOR_AND_FOREIGN_INSTITUTION_FLOWS_MISSING',
       'FUNDAMENTAL_AND_CATALYST_CHECK_MISSING',
       'LIVE_PRICE_CAPITAL_AND_ENTRY_TRIGGER_MISSING'])),
      decision='CASH',trade_approved=False,orders_enabled=False,
      note='Preliminary technical score is not an 85+ final score or validated five-day rise probability.',
      required_next_data=[
       'Current completed market close and verified universe',
       'Source-verified sector breadth and institutional/foreign net buying',
       'Common share type, audited financials and dated catalysts',
       'Live price and trigger, account cash and existing positions'])
    return plans,report

def write_output(out,rows,report):
    out.mkdir(parents=True,exist_ok=True)
    with (out/'free_structural_v52_all.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS)
        writer.writeheader();writer.writerows(rows)
    (out/'free_structural_v52_status.json').write_text(
       json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lookup={x['ticker']:x for x in rows}
    lines=['# C3 · K100 무료 일봉 구조 분석 v5.2','',
     '- 시장자료 기준일: '+str(report['market_data_date']),
     '- **최종 권고: CASH (신규매수 승인 없음)**',
     '- 기술 예비점수는 최종 85점 점수나 상승확률이 아닙니다.',
     '- 구조 가격은 완료된 일봉 기준 참고치이며 실시간 주문 가격이 아닙니다.','']
    for title,key in [('C3 단기 연구 후보','c3_research_top5'),
                       ('K100 교체 연구 후보','k100_research_top5')]:
        lines += ['## '+title,'','| 종목 | 기준 종가 | 구조손절 참고 | MA20 2차 참고 | 연구 손익비 |',
          '|---|---:|---:|---:|---:|']
        if not report[key]:lines.append('| 없음 | — | — | — | — |')
        for ticker in report[key]:
            r=lookup[ticker]
            lines.append('| {ticker} {name} | {close_reference} | {structural_stop_reference} | {entry2_ma20_proxy} | {rr_to_prior_resistance} |'.format(**r))
        lines.append('')
    lines.extend(['## 검증 미충족','','; '.join(report['global_blockers']),'',
                  '## Required Next Data',''])
    lines.extend('- '+x for x in report['required_next_data'])
    (out/'free_structural_v52_mobile.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--status',type=Path,default=Path('reports/status.json'))
    p.add_argument('--candidates',type=Path,default=Path('reports/candidates.csv'))
    p.add_argument('--history',type=Path,default=Path('reports/candidate_daily_history_v52.csv'))
    p.add_argument('--c3-ranked',type=Path,default=Path('reports/c3_preliminary.csv'))
    p.add_argument('--k100-ranked',type=Path,default=Path('reports/k100_preliminary.csv'))
    p.add_argument('--outdir',type=Path,default=Path('reports'))
    p.add_argument('--asof',default=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat())
    a=p.parse_args()
    if not a.status.is_file():raise SystemExit('MISSING_SCANNER_STATUS')
    status=json.loads(a.status.read_text(encoding='utf-8'))
    rows,report=build(status,read_csv(a.candidates),read_csv(a.history),
      read_csv(a.c3_ranked),read_csv(a.k100_ranked),date.fromisoformat(a.asof))
    write_output(a.outdir,rows,report)
    print(json.dumps({k:report[k] for k in ('market_data_date','candidates',
      'structural_reference_count','decision','global_blockers',
      'c3_research_top5','k100_research_top5')},ensure_ascii=False))

if __name__=='__main__':main()
