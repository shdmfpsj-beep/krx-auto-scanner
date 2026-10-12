#!/usr/bin/env python3
"""v8.7 experimental pre-ignition base screener and E1/E2/E3 research.
Historical exploratory OHLC daily proxy only; not a trading signal.
Never uses tomorrow's data to construct today's signals. 
"""
from __future__ import annotations
import argparse,csv,io,json,math,statistics,zipfile
from pathlib import Path
from datetime import date
from collections import Counter,defaultdict

VERSION='V8.7_PREIGNITION_RESEARCH_NOT_LIVE'
MODES=('E1_LIMIT_2D','E2_NEXT_OPEN','E3_NEXT_CLOSE_AUCTION_PROXY')
SIGNAL_COLUMNS=['ticker','signal_date','subtype','score','signal_close','resistance','resistance_gap_pct','ma20','ma60','atr14','compression_ratio','volume_dryup','recent5_return_pct','support','stop','ideal_buy_low','ideal_buy_high','no_chase_above','signal_only_asof','risk_note']
TRADE_COLUMNS=['ticker','signal_date','subtype','score','mode','entry_date','entry_price','stop','target1','target2_hypothetical','exit_date','exit_reason','sessions_held','net_pct','net_R','target1_before_stop','split','approximate_fill']

def avg(a):return sum(a)/len(a) if a else 0.
def f(x):
    try:
        y=float(x)
        return y if math.isfinite(y) else None
    except (ValueError,TypeError):return None

def decode_rows(raw):
    try:reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    except UnicodeDecodeError:return None,'UNREADABLE_UTF8'
    out=[]
    for x in reader:
        try:
            d=date.fromisoformat(str(x['Date'])[:10]).isoformat()
            o,h,l,c,v=[f(x[k]) for k in ('Open','High','Low','Close','Volume')]
        except (KeyError,ValueError,TypeError):return None,'MISSING_COLUMNS_OR_DATE'
        if any(q is None for q in (o,h,l,c,v)) or min(o,h,l,c)<=0 or v<0 or h<max(o,c,l) or l>min(o,c,h):return None,'INVALID_OHLCV'
        out.append({'date':d,'o':o,'h':h,'l':l,'c':c,'v':v})
    if len(out)<76:return None,'HISTORY_LT76'
    if any(out[j]['date']<=out[j-1]['date'] for j in range(1,len(out))):return None,'DATES_NOT_INCREASING'
    if any(abs(out[j]['c']/out[j-1]['c']-1)>.40 for j in range(1,len(out))):return None,'SUSPECT_CORPORATE_ACTION'
    return out,'OK'

def source_files(cache_dir,report_zip):
    if bool(cache_dir)==bool(report_zip):raise ValueError('provide exactly one of --cache-dir / --report-zip')
    if report_zip:
        with zipfile.ZipFile(report_zip) as z:
            for n in sorted(z.namelist()):
                if n.startswith('v36_ohlcv_cache/') and n.count('/')==1 and n.endswith('.csv') and len(Path(n).stem)==6 and Path(n).stem.isdigit():yield Path(n).stem,z.read(n)
    else:
        for p in sorted(Path(cache_dir).glob('*.csv')):
            if len(p.stem)==6 and p.stem.isdigit():yield p.stem,p.read_bytes()

def sma(b,i,n):return avg([x['c'] for x in b[i-n+1:i+1]])
def atr(b,i,n=14):return avg([max(b[j]['h']-b[j]['l'],abs(b[j]['h']-b[j-1]['c']),abs(b[j]['l']-b[j-1]['c'])) for j in range(i-n+1,i+1)])

def signal(ticker,b,i):
    """All source windows end at i or earlier. Resistance excludes signal day and two recent candles."""
    if i<75:return None
    t=b[i];c=t['c'];a=atr(b,i)
    if a<=0:return None
    ma20=sma(b,i,20);ma60=sma(b,i,60)
    ma20prev=sma(b,i-5,20);ma60prev=sma(b,i-5,60)
    # A historical ceiling not chosen based on future outcome.
    res=max(x['h'] for x in b[i-27:i-3]); gap=(res-c)/res
    vprev=avg([x['v'] for x in b[i-24:i-4]])
    vnow=avg([x['v'] for x in b[i-4:i+1]])
    if vprev<=0:return None
    dry=vnow/vprev
    range10=max(x['h'] for x in b[i-9:i+1])-min(x['l'] for x in b[i-9:i+1])
    range30=max(x['h'] for x in b[i-29:i+1])-min(x['l'] for x in b[i-29:i+1])
    contraction=range10/max(range30,1e-9)
    low_now=min(x['l'] for x in b[i-7:i+1])
    low_prev=min(x['l'] for x in b[i-27:i-7])
    five_ret=c/b[i-5]['c']-1
    ten_ret=c/b[i-10]['c']-1
    # Hard gates restrict to pre-breakout: no already-confirmed extension.
    if not (.005<=gap<=.08):return None
    if not (c>ma20*.985 and c>ma60*.98):return None
    if not (ma20>ma20prev*1.002 and ma60>=ma60prev*.988):return None
    if not (low_now>low_prev+0.05*a):return None
    if not (contraction<.80 and .25<=dry<=1.25):return None
    if five_ret>.09 or ten_ret>.19 or c>ma20*1.11:return None
    # Recovery bottom allowed only if trend is no longer falling sharply.
    subtype='E_RECOVERY' if ma20<=ma60*1.025 else 'E_TREND_BASE'
    # Categories: trend 20, higher lows 25, contraction 20, volume 15, geometry 20.
    trend=10*(ma20/ma20prev>=1.009)+5*(ma60>=ma60prev)+5*(c>=ma60*1.02)
    structure=12+8*(low_now>=low_prev+0.35*a)+5*(c>=max(x['c'] for x in b[i-7:i-1]))
    compress=10+7*(contraction<=.65)+3*(range10<=2.5*a)
    volume=8+5*(dry<.85)+2*(vnow>=vprev*.50)
    geometry=10+6*(gap<=.04)+4*(c/ma20<=1.06)
    score=int(trend+structure+compress+volume+geometry)
    support=max(ma20*.992,min(x['l'] for x in b[i-7:i+1]))
    stop=low_now-.12*a
    if stop>=c or stop<=0:return None
    risk=(c-stop)/c
    if not (.01<=risk<=.075):return None
    lowlimit=max(stop+.18*a,c-.65*a)
    highlimit=min(c-.15*a,res*.995)
    if lowlimit>=highlimit:return None
    chase=min(res*.995,c+.38*a)
    if chase<=highlimit:return None
    return {'ticker':ticker,'signal_date':t['date'],'subtype':subtype,'score':score,'signal_close':c,'resistance':res,
            'resistance_gap_pct':round(gap*100,3),'ma20':round(ma20,4),'ma60':round(ma60,4),'atr14':round(a,4),
            'compression_ratio':round(contraction,4),'volume_dryup':round(dry,4),'recent5_return_pct':round(five_ret*100,3),
            'support':round(support,4),'stop':round(stop,4),'ideal_buy_low':round(lowlimit,4),
            'ideal_buy_high':round(highlimit,4),'no_chase_above':round(chase,4),
            'signal_only_asof':t['date'],'risk_note':'DAILY_BAR_ONLY; NO intraday order evidence'}

def find_signals(ticker,b,score_min=70):
    last=-10000;res=[]
    for i in range(75,len(b)):
        s=signal(ticker,b,i)
        if s is None or s['score']<score_min or i-last<10:continue
        res.append((i,s));last=i
    return res

def entry(b,i,s,mode):
    start=i+1
    if start>=len(b):return None,'PENDING_NEXT_SESSION'
    stop=s['stop'];cap=s['no_chase_above'];res=s['resistance'];a=s['atr14']
    if mode=='E2_NEXT_OPEN':
        p=b[start]['o']
        if p<=stop:return None,'GAP_BELOW_STOP'
        if p>cap:return None,'GAP_CHASE_CANCELED'
        return (start,p,False),'FILLED'
    if mode=='E3_NEXT_CLOSE_AUCTION_PROXY':
        p=b[start]['c']
        if p<=stop:return None,'CLOSE_BELOW_STOP'
        if p>cap:return None,'CLOSE_ABOVE_PREBREAKOUT_CAP'
        return (start,p,True),'FILLED'
    # E1: conservative trade-through needed; 2 consecutive market sessions then canceled.
    for j in range(start,min(start+2,len(b))):
        bar=b[j]
        if bar['o']<=stop:return None,'CANCEL_GAP_BELOW_STOP'
        limit=s['ideal_buy_high']
        if bar['l']<=limit-.02*a:
            p=min(bar['o'],limit)
            if p<=stop:return None,'CANCEL_BELOW_STOP'
            return (j,p,False),'FILLED'
    return None,'UNFILLED_2D' if start+1<len(b) else 'PENDING_SECOND_SESSION'

def simulate(b,i,s,mode,hold=5,cost_bps=35):
    e,status=entry(b,i,s,mode)
    if e is None:return None,status
    ei,p,auction=e
    stop=s['stop'];risk=(p-stop)/p
    if not (.01<=risk<=.075):return None,'RISK_GATE'
    last=ei+hold-1
    if last>=len(b):return None,'PENDING_OUTCOME'
    target1=p*1.033;target2=p+2*(p-stop)
    # Study targets are hypothetical: no ex-ante wall clearance claim.
    rem=1.0;gross=0.0;hit=0;reason='TIME';exit_i=last
    for j in range(ei,last+1):
        # A next-close auction proxy must not claim fills from earlier intraday movements.
        if j==ei and auction:continue
        bar=b[j]
        if j>ei and bar['o']<=stop:
            gross+=rem*(bar['o']/p-1);rem=0;reason='STOP_GAP';exit_i=j;break
        if bar['l']<=stop:
            gross+=rem*(stop/p-1);rem=0;reason='STOP_FIRST';exit_i=j;break
        # On a limit-fill bar, the intraday sequence is unknown; do not book target.
        if j==ei and mode=='E1_LIMIT_2D':continue
        if not hit and bar['h']>=target1:
            gross+=.5*(target1/p-1);hit=1;rem-=.5
        if bar['h']>=target2 and rem:
            gross+=rem*(target2/p-1);rem=0;reason='TARGET2_HYPOTHETICAL';exit_i=j;break
    if rem:
        gross+=rem*(b[last]['c']/p-1);exit_i=last
        reason='PARTIAL_T1_THEN_TIME' if hit else 'TIME'
    net=100*gross-cost_bps/100
    return {'ticker':s['ticker'],'signal_date':s['signal_date'],'subtype':s['subtype'],'score':s['score'],'mode':mode,
            'entry_date':b[ei]['date'],'entry_price':round(p,4),'stop':stop,'target1':round(target1,4),'target2_hypothetical':round(target2,4),
            'exit_date':b[exit_i]['date'],'exit_reason':reason,'sessions_held':exit_i-ei+1,'net_pct':round(net,4),
            'net_R':round(net/(risk*100),4),'target1_before_stop':hit,'split':'','approximate_fill':True},'CLOSED'

def save_csv(path,rows,cols):
    with open(path,'w',encoding='utf-8-sig',newline='') as f0:
        writer=csv.DictWriter(f0,fieldnames=cols,extrasaction='ignore');writer.writeheader();writer.writerows(rows)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    one=ap.add_mutually_exclusive_group(required=True)
    one.add_argument('--report-zip');one.add_argument('--cache-dir')
    ap.add_argument('--outdir',default='reports')
    ap.add_argument('--score-min',type=int,default=70)
    ap.add_argument('--hold',type=int,default=5)
    ap.add_argument('--cost-bps',type=float,default=35)
    args=ap.parse_args()
    if not (50<=args.score_min<=95 and 1<=args.hold<=10 and 0<=args.cost_bps<=250):ap.error('invalid parameters')
    output=Path(args.outdir);output.mkdir(parents=True,exist_ok=True)
    errors=Counter();dates=Counter();sources=0;signals=[];trades=[];audit=[];newest={}
    for ticker,raw in source_files(args.cache_dir,args.report_zip):
        sources+=1;b,status=decode_rows(raw);errors[status]+=1
        if status!='OK':continue
        dates[b[-1]['date']]+=1
        latest=signal(ticker,b,len(b)-1)
        if latest and latest['score']>=args.score_min:newest[ticker]=latest
        for i,s in find_signals(ticker,b,args.score_min):
            if i>=len(b)-1:continue  # avoid registering unfinished prospective outcomes as backtest signals
            signals.append(s)
            for mode in MODES:
                trade,reason=simulate(b,i,s,mode,args.hold,args.cost_bps)
                audit.append({'ticker':ticker,'signal_date':s['signal_date'],'mode':mode,'status':reason})
                if trade:trades.append(trade)
    signal_dates=sorted(set(x['signal_date'] for x in signals))
    split=signal_dates[int(len(signal_dates)*.7)] if signal_dates else '9999-12-31'
    for x in trades:x['split']='EARLY' if x['signal_date']<split else 'LATE'
    scores=[]
    for subtype in ('E_RECOVERY','E_TREND_BASE','ALL'):
        for mode in MODES:
            for phase in ('EARLY','LATE','ALL'):
                st=[t for t in trades if (t['subtype']==subtype or subtype=='ALL') and t['mode']==mode and (phase=='ALL' or t['split']==phase)]
                ss=[s for s in signals if (s['subtype']==subtype or subtype=='ALL') and (phase=='ALL' or ('EARLY' if s['signal_date']<split else 'LATE')==phase)]
                n=len(st);pos=sum(max(0,t['net_pct']) for t in st);neg=-sum(min(0,t['net_pct']) for t in st)
                scores.append({'subtype':subtype,'entry_mode':mode,'period':phase,'signals':len(ss),'closed':n,
                               'fill_and_close_rate_pct':round(100*n/len(ss),2) if ss else '',
                               'net_win_rate_pct':round(100*sum(t['net_pct']>0 for t in st)/n,2) if n else '',
                               'target1_first_pct':round(100*sum(t['target1_before_stop'] for t in st)/n,2) if n else '',
                               'avg_net_pct':round(avg([t['net_pct'] for t in st]),4) if n else '',
                               'avg_net_R':round(avg([t['net_R'] for t in st]),4) if n else '',
                               'profit_factor':round(pos/neg,3) if neg else ('INF' if pos else ''),
                               'unique_dates':len(set(t['signal_date'] for t in st)),
                               'note':'INSUFFICIENT_SMALL_N' if n<30 else 'EXPLORATORY_ONLY'})
    # Never mix different history end dates for a "latest" shortlist.
    newest_date=max(dates) if dates else ''
    current=[x for x in newest.values() if x['signal_date']==newest_date]
    current.sort(key=lambda s:(-s['score'],s['resistance_gap_pct'],s['ticker']))
    save_csv(output/'v87_preignition_asof_candidates.csv',current,SIGNAL_COLUMNS)
    save_csv(output/'v87_preignition_signals.csv',signals,SIGNAL_COLUMNS)
    save_csv(output/'v87_entry_trades.csv',trades,TRADE_COLUMNS)
    save_csv(output/'v87_entry_rejections.csv',audit,['ticker','signal_date','mode','status'])
    save_csv(output/'v87_entry_scorecard.csv',scores,['subtype','entry_mode','period','signals','closed','fill_and_close_rate_pct','net_win_rate_pct','target1_first_pct','avg_net_pct','avg_net_R','profit_factor','unique_dates','note'])
    summary={'version':VERSION,'cache_files':sources,'bar_verification':dict(errors),'coverage_end_dates':dict(dates),
             'asof_date_selected_most_recent_history':newest_date,'history_count_at_selected_date':dates[newest_date],'asof_candidates':len(current),'total_historical_signals':len(signals),
             'all_execution_mode_closed_trades':len(trades),'time_split_boundary':split,'hold_sessions':args.hold,'cost_bps':args.cost_bps,'score_min':args.score_min,
             'modes':MODES,'BUY_APPROVED':False,'limitations':[
              'Historical ticker cache is preselected and may have severe survivorship and winner-selection bias.',
              'Different end dates: shortlist constrained to modal history end date, not current real-time prices.',
              'Daily OHLC proxy cannot prove intraday execution, closing auction fill, order priority, VWAP, or opening-range triggers.',
              'No corporate actions and tick rounding validation; no exchange price-limit queue or suspended-stock modeling.',
              '2R target is hypothetical, not observed overhead resistance; same-bar stop is conservatively first.',
              'No historical sector membership, earnings/revisions, reliable institutional flows, or benchmark RS.',
              'Overlapping strategy samples and 70/30 time split do not prove independent walk-forward performance.',
              'Selection thresholds are initial hypotheses not proven optimal; no production BUY authorization.'
             ]}
    (output/'v87_research_status.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'source_files':sources,'valid':errors['OK'],'asof':newest_date,'current':len(current),'signals':len(signals),'trades':len(trades),'split':split},ensure_ascii=False))

if __name__=='__main__':main()
