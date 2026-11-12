"""Dated global/domestic observations with availability and missing-data gates.

Reuses v618 logical risk classifications. Later fetched context is never
backdated into the frozen Nov11 signal. No sentiment or flow imputation.
"""
import hashlib,json,statistics
from datetime import datetime,date,timedelta,timezone
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from global_macro_risk_v618 import classify

KST=ZoneInfo('Asia/Seoul')
SYMBOLS={'SP500_INDEX':'^GSPC','NASDAQ_INDEX':'^IXIC','SOX_INDEX':'^SOX','VIX_INDEX':'^VIX','NVDA':'NVDA','MSFT':'MSFT','AAPL':'AAPL'}

def iso(s):
    value=datetime.fromisoformat(s.replace('Z','+00:00'))
    if value.tzinfo is None:raise ValueError('SOURCE_TIMEZONE_REQUIRED')
    return value

def last_completed_us(clock):
    import exchange_calendars as xc
    cal=xc.get_calendar('XNYS');day=clock.astimezone(ZoneInfo('America/New_York')).date()
    session=cal.date_to_session(day,direction='previous')
    if cal.session_close(session).to_pydatetime()>clock:session=cal.previous_session(session)
    return str(session.date()),cal.session_close(session).to_pydatetime().isoformat()

def load_prior_macro(doc,clock):
    observed=iso(doc['generated_at_kst'])
    if observed>clock or clock-observed>timedelta(hours=24):raise ValueError('FUTURE_OR_STALE_GLOBAL_SNAPSHOT')
    day,closed=last_completed_us(clock);etf={};fred={};missing={}
    for key,row in doc.get('global_etf_data',{}).items():
        session=row.get('us_session')
        if session!=day or iso(row['us_close_kst'])>clock:
            missing[key]='INCOMPLETE_OR_STALE_US_SESSION';continue
        etf[key]=dict(row,source='YAHOO_ADJUSTED_PRICE_V618_SNAPSHOT',collected_at=doc['generated_at_kst'],
            session_completed_at=closed,vintage_pit_verified=False,status='OBSERVED_NOT_PIT_VERIFIED')
    for key,row in doc.get('fred_macro_data',{}).items():
        max_age=7 if key in ('DEXKOUS','DTWEXBGS') else 5
        age=(clock.astimezone(KST).date()-date.fromisoformat(row['date'])).days
        if age<0 or age>max_age:
            missing[key]='STALE_OR_FUTURE_OBSERVATION';continue
        fred[key]=dict(row,source='https://fred.stlouisfed.org/graph/fredgraph.csv?id='+key,
            collected_at=doc['generated_at_kst'],release_timestamp_verified=False,
            vintage_pit_verified=False,status='OBSERVED_NOT_PIT_VERIFIED')
    result=classify(etf,fred)
    return dict(collected_at=doc['generated_at_kst'],us_last_complete_session=day,us_session_closed_at=closed,
        etf=etf,macro=fred,unavailable=missing,legacy_risk_classification=result,
        news=dict(status='UNAVAILABLE',reason='NO_DATED_VERIFIED_FIRST_PARTY_NEWS_INPUT'),
        fed_policy=dict(status='UNAVAILABLE',reason='NO_DATED_RELEASE_INPUT'),
        historical_point_in_time_verified=False,post_hoc_context_not_nov11_selection_reason=True)

def fetch_indices(clock,out):
    """One bounded free vendor request per symbol; missing stays missing."""
    day,closed=last_completed_us(clock);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    def one(item):
        name,symbol=item
        try:
            import yfinance as yf
            hist=yf.Ticker(symbol).history(start=(date.fromisoformat(day)-timedelta(days=100)).isoformat(),
                end=(date.fromisoformat(day)+timedelta(days=1)).isoformat(),auto_adjust=False,actions=False,timeout=12,raise_errors=True)
            rows=[]
            for stamp,r in hist.iterrows():
                d=stamp.date().isoformat()
                if d>day:continue
                o,h,l,c=[float(r[k]) for k in ('Open','High','Low','Close')]
                if not all(__import__('math').isfinite(v) for v in (o,h,l,c)) or not 0<l<=min(o,c)<=max(o,c)<=h:raise ValueError('INVALID_OHLC')
                rows.append(dict(date=d,open=o,high=h,low=l,close=c))
            if len(rows)<21 or rows[-1]['date']!=day or len({r['date'] for r in rows})!=len(rows):raise ValueError('MISSING_COMPLETED_US_SESSION')
            blob=json.dumps(rows,sort_keys=True,allow_nan=False).encode();(out/(name+'.json')).write_bytes(blob)
            c=[r['close'] for r in rows]
            return name,dict(status='OBSERVED_VENDOR_DATA',source='YAHOO:'+symbol,session=day,
                session_closed_at=closed,collected_at=datetime.now(timezone.utc).isoformat(),close=c[-1],
                ret1_pct=100*(c[-1]/c[-2]-1),ret5_pct=100*(c[-1]/c[-6]-1),ma20=statistics.mean(c[-20:]),
                raw_sha256=hashlib.sha256(blob).hexdigest(),vintage_pit_verified=False)
        except Exception as e:return name,dict(status='UNAVAILABLE',source='YAHOO:'+symbol,error_type=type(e).__name__)
    with ThreadPoolExecutor(max_workers=4) as pool:return dict(pool.map(one,SYMBOLS.items()))

def domestic_context(current,meta,indices,day):
    breadth={};sectors={};sector_rows={}
    for market in ('KOSPI','KOSDAQ'):
        rows=[b for t,b in current.items() if meta.get(t,{}).get('market')==market]
        up=sum(b[-1]['close']>b[-2]['close'] for b in rows);down=sum(b[-1]['close']<b[-2]['close'] for b in rows)
        idx=[(d,v) for d,v in sorted(indices[market].items()) if d<=day];values=[v for d,v in idx]
        if not idx or idx[-1][0]!=day or len(values)<60:raise ValueError('DOMESTIC_BENCHMARK_DATE_OR_WARMUP_MISMATCH')
        state='UP' if values[-1]>statistics.mean(values[-20:])>statistics.mean(values[-60:]) else 'DOWN' if values[-1]<statistics.mean(values[-20:])<statistics.mean(values[-60:]) else 'SIDEWAYS'
        breadth[market]=dict(asof=day,index_close=values[-1],index_ret1_pct=100*(values[-1]/values[-2]-1),
            ret20_pct=100*(values[-1]/values[-21]-1),regime=state,covered_continuous_nonbio_common=len(rows),advancing=up,declining=down,
            unchanged=len(rows)-up-down,advance_share_pct=100*up/len(rows) if rows else None,
            turnover_krw=sum(b[-1]['turnover_krw'] for b in rows),coverage='ANALYSIS_ELIGIBLE_SUBSET_NOT_ALL_MARKET_BREADTH')
    for t,bs in current.items():
        m=meta.get(t)
        if not m or len(bs)<21:continue
        ix=indices[m['market']]
        if bs[-21]['date'] not in ix:continue
        rs=100*(bs[-1]['close']/bs[-21]['close']-ix[day]/ix[bs[-21]['date']])
        sector_rows.setdefault(m['sector'],[]).append(rs)
    for name,values in sector_rows.items():
        if len(values)>=5:sectors[name]=dict(members=len(values),median_own_board_rs20_pct=statistics.median(values),
            classification_pit_verified=False,status='UNWEIGHTED_CURRENT_MEMBERSHIP_PRICE_PROXY')
    return dict(asof=day,boards=breadth,sectors=sectors,
        leading_sector_proxies=sorted(sectors,key=lambda s:-sectors[s]['median_own_board_rs20_pct'])[:5],
        foreign_flow='UNAVAILABLE',institutional_flow='UNAVAILABLE',regular_only_certified=False)

def combine(global_context,domestic):
    risk=global_context['legacy_risk_classification']
    # v618 returns a dictionary. Missing coverage must never become bullish.
    label=risk.get('regime','UNVERIFIED') if isinstance(risk,dict) else 'UNVERIFIED'
    boards=[v['regime'] for v in domestic['boards'].values()]
    stress='RISK_OFF' in label or all(v=='DOWN' for v in boards)
    bull=all(v=='UP' for v in boards) and 'SUPPORTIVE' in label
    observed='UNVERIFIED' if 'INCOMPLETE' in label else 'BEAR' if stress else 'BULL' if bull else 'MIXED'
    return dict(observed_regime=observed,verified_regime='UNVERIFIED',global_label=label,
        risk_posture='CASH_FIRST' if observed=='BEAR' else 'OBSERVE_ONLY',
        buy_approved=False,reason='REGULAR_SESSION_AND_FINANCIAL_PIT_GATES_STILL_REQUIRED',
        sector_mapping_to_us_verified=False)
