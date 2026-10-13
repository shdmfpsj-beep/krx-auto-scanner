#!/usr/bin/env python3
"""V9.7 research only: PIT-safe US-sector -> KRX lead/lag audit.

Never turns an ETF close into a recommendation. No sector inference without a
point-in-time verified mapping. Missing feeds are explicit and never imputed.
"""
import argparse
import csv
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, time as clock
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
KST = ZoneInfo('Asia/Seoul')
ETFS = {
    'SPY': ('US', 'US_BENCHMARK'),
    'SMH': ('US', 'SEMICONDUCTOR'),
    'SOXX': ('US', 'SEMICONDUCTOR'),
    'XLK': ('US', 'TECH'),
    'XLI': ('US', 'INDUSTRIAL'),
    'XLU': ('US', 'POWER_DEMAND_PROXY'),
    'XLE': ('US', 'ENERGY'),
    'XLB': ('US', 'MATERIALS'),
    'EWT': ('US', 'TAIWAN_US_LISTED_PROXY'),
    'EWJ': ('US', 'JAPAN_US_LISTED_PROXY'),
    'FXI': ('US', 'CHINA_US_LISTED_PROXY'),
}
# The sector-to-stock PIT mapping is supplied externally; an ETF is not proof
# that any individual Korean listed company benefits from that ETF's sector.


def parse_day(x):
    return date.fromisoformat(str(x).strip()[:10])


def us_close_kst(day):
    # Close of regular U.S. session. Zoneinfo handles historical DST.
    return datetime.combine(day, clock(16, 0), tzinfo=NY).astimezone(KST)


def cutoff_kst(day, hhmm='08:35'):
    hh, mm = (int(x) for x in hhmm.split(':'))
    return datetime.combine(day, clock(hh, mm), tzinfo=KST)


def csv_read(path):
    if not Path(path).is_file() or not Path(path).stat().st_size:
        return []
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader(); w.writerows(rows)


def clean_float(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (ValueError, TypeError):
        return None


def parse_ohlc(path, min_history=0):
    rows = []
    seen = set()
    for r in csv_read(path):
        try:
            d = parse_day(r.get('Date') or r.get('date'))
            o = clean_float(r.get('Open') or r.get('open'))
            h = clean_float(r.get('High') or r.get('high'))
            l = clean_float(r.get('Low') or r.get('low'))
            c = clean_float(r.get('Close') or r.get('close'))
        except (ValueError, TypeError):
            continue
        if d in seen or any(x is None or x <= 0 for x in (o, h, l, c)):
            continue
        if l > min(o, c) + 1e-6 or h < max(o, c) - 1e-6 or l > h:
            continue
        seen.add(d)
        rows.append({'day': d, 'open': o, 'high': h, 'low': l, 'close': c,
                     'volume': clean_float(r.get('Volume') or r.get('volume'))})
    rows.sort(key=lambda r: r['day'])
    return rows if len(rows) >= min_history else []


def ensure_history(cache, start, end, provider='yahoo'):
    """Fetch only absent or stale history; any provider failure stays visible.
    Use daily split/dividend-adjusted OHLC to avoid artificial price jumps
    from ETF splits; historical adjustments may be revised by the vendor. Requires optional yfinance module.
    """
    result = []
    if provider == 'none':
        return [{'symbol': s, 'status': 'NO_FETCH', 'rows': len(parse_ohlc(Path(cache) / (s+'.csv')))} for s in ETFS]
    try:
        import yfinance as yf
    except ImportError:
        return [{'symbol': s, 'status': 'MISSING_YFINANCE', 'rows': 0} for s in ETFS]
    Path(cache).mkdir(parents=True, exist_ok=True)
    for symbol in ETFS:
        dest = Path(cache) / (symbol + '.csv')
        existing = parse_ohlc(dest)
        # refresh the most recent 5 calendar days to catch revisions
        needs_update = not existing or existing[-1]['day'] < end - timedelta(days=4)
        if not needs_update:
            result.append({'symbol': symbol, 'status': 'CACHED', 'rows': len(existing)})
            continue
        try:
            frame = yf.download(symbol, start=start.isoformat(),
                                end=(end+timedelta(days=1)).isoformat(),
                                auto_adjust=True, progress=False, threads=False)
            if frame is None or frame.empty:
                raise ValueError('NO_ROWS_FROM_PROVIDER')
            # yfinance versions may return a MultiIndex for single symbols.
            if getattr(frame.columns, 'nlevels', 1) > 1:
                frame.columns = frame.columns.get_level_values(0)
            hist = []
            for dt, row in frame.iterrows():
                day = dt.date() if hasattr(dt, 'date') else parse_day(dt)
                vals = {k: clean_float(row.get(k)) for k in ('Open', 'High', 'Low', 'Close', 'Volume')}
                if any(vals[k] is None or vals[k] <= 0 for k in ('Open', 'High', 'Low', 'Close')):
                    continue
                hist.append({'Date': day.isoformat(), **vals})
            if len(hist) < 50:
                raise ValueError('HISTORY_TOO_SHORT')
            # Atomic only after basic OHLC sanity checks.
            temp = dest.with_suffix('.tmp')
            write_csv(temp, hist, ['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
            validated = parse_ohlc(temp, min_history=50)
            if len(validated) < 50:
                temp.unlink(missing_ok=True)
                raise ValueError('INVALID_PROVIDER_OHLC')
            temp.replace(dest)
            result.append({'symbol':symbol,'status':'FETCHED','rows':len(validated)})
        except Exception as exc:
            result.append({'symbol': symbol, 'status': 'ERROR_'+type(exc).__name__,
                           'message': str(exc)[:160], 'rows':len(existing)})
        time.sleep(0.4)
    return result


def us_asof(prices, date_kr, at='08:35', max_stale_days=5):
    cutoff = cutoff_kst(date_kr, at)
    eligible = [i for i, row in enumerate(prices) if us_close_kst(row['day']) <= cutoff]
    if not eligible:
        return None
    idx = eligible[-1]
    age = (cutoff - us_close_kst(prices[idx]['day'])).total_seconds()/86400
    if age > max_stale_days:
        return None
    return idx


def factor(prices, spy_by_date, d, at='08:35'):
    i = us_asof(prices, d, at=at)
    if i is None or i < 20:
        return None
    # Compare ETF and SPY from the same actual U.S. sessions, not an
    # arbitrarily selected calendar-day lag. Unmatched dates are rejected.
    last = prices[i]
    pairs = []
    for p in prices[:i+1]:
        other = spy_by_date.get(p['day'])
        if other and other > 0:
            pairs.append((p['day'], p['close'], other))
    if len(pairs) < 21 or pairs[-1][0] != last['day']:
        return None
    def excess(n):
        a, b, s, t = pairs[-1][1], pairs[-n-1][1], pairs[-1][2], pairs[-n-1][2]
        return round(100 * ((a/b)/(s/t) - 1), 4)
    close20 = [p['close'] for p in prices[max(0, i-19):i+1]]
    if len(close20) != 20:
        return None
    ex5, ex20 = excess(5), excess(20)
    strong = (ex5 >= 1.0 and ex20 > 0 and last['close'] > statistics.mean(close20))
    return {'us_session':last['day'].isoformat(), 'available_kst':us_close_kst(last['day']).isoformat(),
            'excess5_pp':ex5, 'excess20_pp':ex20, 'above_ma20': last['close']>statistics.mean(close20),
            'strong': strong}


def verified_map(rows, ticker, signal_date):
    matches = []
    for r in rows:
        if str(r.get('ticker','')).zfill(6) != ticker or str(r.get('verified','')).strip().lower() not in ('true','1','yes'):
            continue
        try:
            begin = parse_day(r.get('valid_from',''))
            available = parse_day(r.get('available_date',''))
            end = parse_day(r['valid_to']) if r.get('valid_to') else date(9999,12,31)
        except (ValueError,TypeError):
            continue
        if not r.get('source') or not (begin <= signal_date <= end) or available > signal_date:
            continue
        theme = r.get('global_theme','')
        if theme not in ETFS or theme == 'SPY':
            continue
        matches.append(r)
    return max(matches,key=lambda x:x['available_date']) if matches else None


def future_returns(bars, day, horizons=(5,10,20), cost_pct=0.35):
    # Entry NEXT Korea trading session OPEN. Exit after h held sessions CLOSE.
    future = [b for b in bars if b['day'] > day]
    if not future:
        return {str(h):None for h in horizons}, None
    entry=future[0]['open']
    if entry <= 0:
        return {str(h):None for h in horizons}, None
    returns={str(h):(round(100*(future[h-1]['close']/entry - 1) - cost_pct, 4)
                     if len(future)>=h else None) for h in horizons}
    return returns, future[0]['day'].isoformat()


def summarize(rows, tag, status_key="global_status", statuses=("STRONG","NOT_STRONG","MISSING_GLOBAL","MISSING_SECTOR_MAP")):
    out=[]
    for status in statuses:
        subset=[r for r in rows if r[status_key]==status]
        row={'cohort':tag,'global_status':status,'signal_count':len(subset)}
        for h in ('5','10','20'):
            v=[float(r['net'+h+'_pct']) for r in subset if r['net'+h+'_pct'] != '']
            row['n_'+h]=len(v)
            row['mean_net_'+h+'_pct']=round(statistics.mean(v),4) if v else ''
            row['median_net_'+h+'_pct']=round(statistics.median(v),4) if v else ''
            row['positive_'+h+'_pct']=round(100*sum(x>0 for x in v)/len(v),2) if v else ''
        out.append(row)
    return out


MACRO_THEMES = ('SMH','XLK','XLI','XLU','XLE','XLB') # one ETF per broad theme

def execute(args):
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    fetch_info=ensure_history(args.global_cache,parse_day(args.start),parse_day(args.end),provider=args.provider)
    bars_global={s:parse_ohlc(Path(args.global_cache)/(s+'.csv')) for s in ETFS}
    spy_by_date={r['day']:r['close'] for r in bars_global['SPY']}
    raw=csv_read(args.signals)
    mapping=csv_read(args.mapping)
    mapping_approved=sum(str(r.get('verified','')).lower() in ('true','1','yes') for r in mapping)
    stk_bars={};detail=[];seen=set();excluded=Counter()
    for r in raw:
        ticker=str(r.get('ticker','')).strip().zfill(6)
        try:d=parse_day(r.get('signal_date') or r.get('signal_asof'))
        except (TypeError,ValueError):excluded['BAD_SIGNAL_DATE']+=1;continue
        if len(ticker)!=6 or not ticker.isdigit():excluded['BAD_TICKER']+=1;continue
        if (ticker,d) in seen:excluded['DUPLICATE_SIGNAL']+=1;continue
        seen.add((ticker,d))
        clean=(r.get('selection_status')=='MISSING_ASOF_SECTOR')
        if not clean:excluded['PRIOR_BREAKOUT_NOT_CLEAN']+=1;continue
        if ticker not in stk_bars:stk_bars[ticker]=parse_ohlc(Path(args.krx_cache)/(ticker+'.csv'))
        sb=stk_bars[ticker]
        if not sb or not any(p['day']==d for p in sb):excluded['MISSING_KRX_SIGNAL_BAR']+=1;continue
        ret,entryday=future_returns(sb,d,cost_pct=args.round_trip_cost_pct)
        if not entryday:excluded['NO_FORWARD_BARS']+=1;continue
        m=verified_map(mapping,ticker,d)
        global_symbols=set(MACRO_THEMES) | ({m['global_theme']} if m else set())
        facs={s:factor(bars_global[s],spy_by_date,d,at=args.cutoff) for s in global_symbols}
        macro_known=[f for s,f in facs.items() if s in MACRO_THEMES and f is not None]
        macro_up=sum(bool(f['strong']) for f in macro_known)
        macro_status=('MISSING_GLOBAL' if len(macro_known)<4 else
                      'GLOBAL_BREADTH_ON' if macro_up>=3 else 'GLOBAL_BREADTH_OFF')
        if m:
            result=facs[m['global_theme']]
            status=('STRONG' if result['strong'] else 'NOT_STRONG') if result else 'MISSING_GLOBAL'
            active=m['global_theme']; approved=bool(result)
        else:
            # Macro-only diagnostic: best-performing ETF is NOT a valid link
            # to the Korean firm's industry. This cannot pass sector gate.
            eligible=[(s,f) for s,f in facs.items() if f]
            status='MISSING_SECTOR_MAP';active='';approved=False
            result=None
        detail.append({'ticker':ticker,'signal_date':d.isoformat(),'entry_date':entryday,
                       'chart_score':r.get('signal_score',''),'strict_sector_link':int(approved),
                       'global_theme':active,'global_status':status,
                       'macro_regime':macro_status,'macro_up':macro_up,'macro_coverage':len(macro_known),
                       'us_session':result['us_session'] if result else '',
                       'us_available_kst':result['available_kst'] if result else '',
                       'excess5_pp':result['excess5_pp'] if result else '',
                       'excess20_pp':result['excess20_pp'] if result else '',
                       **{'net'+h+'_pct':ret[h] if ret[h] is not None else '' for h in ('5','10','20')},
                       'study_only':True})
    fields=['ticker','signal_date','entry_date','chart_score','strict_sector_link','global_theme','global_status','macro_regime','macro_up','macro_coverage','us_session','us_available_kst','excess5_pp','excess20_pp','net5_pct','net10_pct','net20_pct','study_only']
    write_csv(out/'v97_signal_global_audit.csv',detail,fields)
    grouped=summarize(detail,'CLEAN_CHART')
    grouped += summarize(detail, 'MACRO_BREADTH_DIAGNOSTIC', status_key='macro_regime',
                         statuses=('GLOBAL_BREADTH_ON','GLOBAL_BREADTH_OFF','MISSING_GLOBAL'))
    write_csv(out/'v97_global_cohort_comparison.csv',grouped,
              ['cohort','global_status','signal_count']+[t for h in ('5','10','20') for t in ('n_'+h,'mean_net_'+h+'_pct','median_net_'+h+'_pct','positive_'+h+'_pct')])
    write_csv(out/'v97_global_fetch_status.csv',fetch_info,['symbol','status','rows','message'])
    # For diagnostics only, report daily global factors at the most recent
    # KST 08:35 as-of so users can verify U.S. DST & availability.
    today=parse_day(args.end)
    daily=[]
    for s, (venue, theme) in ETFS.items():
        if s=='SPY':continue
        f=factor(bars_global[s],spy_by_date,today,at=args.cutoff)
        daily.append({'ticker':s,'theme':theme,'status':'READY' if f else 'MISSING_OR_STALE',
                      'us_session':f['us_session'] if f else '',
                      'available_kst':f['available_kst'] if f else '',
                      'excess5_pp':f['excess5_pp'] if f else '',
                      'excess20_pp':f['excess20_pp'] if f else '',
                      'strong':f['strong'] if f else ''})
    write_csv(out/'v97_global_radar_today.csv',daily,
              ['ticker','theme','status','us_session','available_kst','excess5_pp','excess20_pp','strong'])
    strict=[x for x in detail if x['strict_sector_link'] and x['global_status'] in ('STRONG','NOT_STRONG')]
    strict_counts=Counter(x['global_status'] for x in strict)
    status={
        'version':'v9.7_US_SESSION_PIT_RESEARCH','research_only':True,'buy_approval':False,
        'strict_pit_approved':False,'global_data_source':'Yahoo Finance via unofficial yfinance; current-vendor split/dividend adjusted price',
        'observations':{'source_chart_signals':len(raw),'clean_signals_with_price_data':len(detail),
                        'excluded':dict(excluded),'krx_cached_tickers':len(stk_bars),
                        'available_global_histories':{s:len(bars_global[s]) for s in ETFS}},
        'point_in_time_verified_sector_mapping_rows':mapping_approved,
        'strict_global_link_signal_count':len(strict),'strict_strong':strict_counts['STRONG'],
        'strict_not_strong':strict_counts['NOT_STRONG'],
        'strict_signal_gate':('NOT_READY_NO_VERIFIED_SECTOR_LINKS' if not mapping_approved else
                              'BLOCKED_NO_US_ETF_DATA' if not any(bars_global.values()) else
                              'READY_FOR_RESEARCH_ONLY' if strict else 'NO_MATCHING_SIGNALS'),
        'etf_fetch':fetch_info,'cutoff_kst':args.cutoff,'round_trip_cost_pct':args.round_trip_cost_pct,
        'holding_days':[5,10,20],
        'limitations':[
            'Prior v9.0 cohort is selected and contains incomplete/survivorship-biased OHLCV; not all KRX securities.',
            'ETF sectors are broad proxies; XLU is not a direct proxy for Korean electrical-equipment earnings.',
            'Country ETFs EWT/EWJ/FXI trade in U.S. hours; NOT local Asian exchange closing bars.',
            'Yahoo adjusted historical prices may have missing sessions and retrospective adjustments; check corporate actions.',
            'No causal inference, no walk-forward regime matching or point-in-time consensus/capex data.',
            'Exit at held-session close, round-trip friction flat, gaps/stops/order feasibility excluded.',
            'Missing sector-PIT mapping blocks theme-specific strategy proof, despite ETF data.',
            'Data available at US 16:00 New York and inferred availability from session close; provider ingestion lag not independently verified.'
        ]}
    (out/'v97_global_research_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in status.items() if k in ('version','observations','strict_global_link_signal_count','strict_signal_gate')},ensure_ascii=False))
    return status


def main():
    p=argparse.ArgumentParser(description='V9.7 foreign-sector lead/lag experiment; no trade execution')
    p.add_argument('--signals',default='reports/v90_pit_candidate_audit.csv')
    p.add_argument('--krx-cache',default='reports/v36_ohlcv_cache')
    p.add_argument('--global-cache',default='reports/v97_global_history')
    p.add_argument('--mapping',default='config/v97_sector_links_pit.csv')
    p.add_argument('--outdir',default='reports/v97')
    p.add_argument('--provider',choices=['yahoo','none'],default='none')
    p.add_argument('--cutoff',choices=['08:35','15:00'],default='08:35')
    p.add_argument('--start',default='2022-01-01')
    p.add_argument('--end',default=date.today().isoformat())
    p.add_argument('--round-trip-cost-pct',type=float,default=0.35)
    a=p.parse_args()
    if a.round_trip_cost_pct<0: p.error('Negative friction not allowed')
    execute(a)

if __name__=='__main__':main()
