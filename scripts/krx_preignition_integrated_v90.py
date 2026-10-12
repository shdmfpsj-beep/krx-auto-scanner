#!/usr/bin/env python3
"""V9.0 research-only pre-ignition backtest: historical sector+filings+entry+exit.
Never infer a missing point-in-time fundamental, map sectors backwards, or issue BUY.
The strict mode is intentionally blocked when dated evidence is absent.
"""
from __future__ import annotations
import argparse,csv,json,math,statistics,sys,zipfile
from collections import Counter,defaultdict
from dataclasses import dataclass
from pathlib import Path
from datetime import date

try:
    from krx_preignition_v87 import decode_rows, source_files, find_signals
except ImportError:
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from krx_preignition_v87 import decode_rows, source_files, find_signals

VERSION='V9.0_PIT_GATE_RESEARCH_ONLY'
ENTRIES=('E1_LIMIT_2D','E2_NEXT_OPEN','E3_NEXT_CLOSE_PROXY')
EXITS=('X10_FULL','X33_HALF_TRAIL')
HOLDS=(5,10,15,20)
TRADES_COLS=['tier','ticker','signal_date','signal_score','sector','mode','exit_model','horizon','entry_date','entry_price','stop','exit_date','exit_reason','net_pct','net_R','hit10_before_stop','hit33_before_stop','mfe_pct','mae_pct','approx_fill','research_only']
CAND_COLS=['ticker','signal_date','signal_score','sector','price_score','sector_median5_pct','sector_excess5_pp','sector_breadth','sector_turnover_accel','leader5_pct','stock_rs20_pp','filing_date','financial_available_date','revenue_yoy_pct','op_profit_yoy_pct','op_margin_pct','debt_ratio_pct','selection_status']
DIAG_COLS=['ticker','signal_date','score','subtype','entry_mode','exit_model','horizon','entry_date','entry_price','stop','exit_date','exit_reason','net_pct','hit10_before_stop','hit33_before_stop']

def numeric(v):
    try:
        y=float(v)
        return y if math.isfinite(y) else None
    except (TypeError,ValueError):return None

def read_csv(p,cols):
    if not p or not Path(p).is_file():return [],'MISSING_FILE'
    with open(p,'r',encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f)
        if not set(cols).issubset(set(r.fieldnames or [])):
            return [],'MISSING_COLUMNS:'+','.join(sorted(set(cols)-set(r.fieldnames or [])))
        return list(r),'OK'

def write_csv(p,rows,columns):
    with open(p,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(rows)

@dataclass(frozen=True)
class Membership:
    ticker:str
    sector:str
    valid_from:str
    available_date:str
    valid_to:str
    source:str
    verified:bool

@dataclass(frozen=True)
class Filing:
    ticker:str
    filing_date:str
    available_date:str
    revenue_yoy_pct:float
    op_profit_yoy_pct:float
    op_margin_pct:float
    debt_ratio_pct:float
    receipt_no:str

MAP_COLS=['ticker','sector','valid_from','available_date','valid_to','source','verified']
FIN_COLS=['ticker','filing_date','available_date','revenue_yoy_pct','op_profit_yoy_pct','op_margin_pct','debt_ratio_pct','receipt_no']

def build_memberships(rows):
    out=defaultdict(list);reject=Counter()
    for r in rows:
        try:
            t=str(r['ticker']).zfill(6); start=r['valid_from'].strip(); known=r['available_date'].strip();stop=r['valid_to'].strip()
            date.fromisoformat(start);date.fromisoformat(known)
            if stop:date.fromisoformat(stop)
            verified=str(r['verified']).lower() in ('true','1','yes')
            if not (t.isdigit() and len(t)==6 and r['sector'].strip() and r['source'].strip()):raise ValueError()
            # A classification may be announced before its effective date; both dates gate use.
            if not verified:reject['UNVERIFIED_CLASSIFICATION']+=1;continue
            out[t].append(Membership(t,r['sector'].strip(),start,known,stop,r['source'].strip(),verified))
        except (ValueError,TypeError,KeyError):reject['INVALID_MAP_ROW']+=1
    for x in out.values():x.sort(key=lambda z:z.available_date)
    return out,reject

def build_filings(rows):
    out=defaultdict(list);reject=Counter()
    for r in rows:
        try:
            t=str(r['ticker']).zfill(6);filed=r['filing_date'].strip();available=r['available_date'].strip()
            date.fromisoformat(filed);date.fromisoformat(available)
            values=[numeric(r[n]) for n in ('revenue_yoy_pct','op_profit_yoy_pct','op_margin_pct','debt_ratio_pct')]
            if any(x is None for x in values) or available<=filed or not (t.isdigit() and len(t)==6 and r['receipt_no'].strip().isdigit() and len(r['receipt_no'].strip())==14):raise ValueError()
            out[t].append(Filing(t,filed,available,*values,r['receipt_no'].strip()))
        except (ValueError,TypeError,KeyError):reject['INVALID_FILING_OR_TIMING']+=1
    for x in out.values():x.sort(key=lambda z:z.available_date)
    return out,reject

def asof_membership(members,t,d):
    a=[x for x in members.get(t,[]) if x.available_date<=d and x.valid_from<=d and (not x.valid_to or d<=x.valid_to)]
    return a[-1] if a else None

def asof_financial(fin,t,d,stale_days=400):
    a=[x for x in fin.get(t,[]) if x.available_date<=d]
    if not a:return None
    f=a[-1]
    if (date.fromisoformat(d)-date.fromisoformat(f.available_date)).days>stale_days:return None
    return f

def fin_pass(f):
    return f is not None and f.revenue_yoy_pct>0 and f.op_profit_yoy_pct>0 and f.op_margin_pct>=3 and 0<=f.debt_ratio_pct<=200

def calc_market_per_date(bars):
    bydate=defaultdict(list); index={}
    for t,b in bars.items():
        lookup={bar['date']:i for i,bar in enumerate(b)};index[t]=lookup
        for d,i in lookup.items():
            if i>=20 and b[i-5]['c']>0 and b[i-20]['c']>0:
                bydate[d].append((100*(b[i]['c']/b[i-5]['c']-1),100*(b[i]['c']/b[i-20]['c']-1)))
    bm={d:(statistics.median(x[0] for x in a),statistics.median(x[1] for x in a),len(a)) for d,a in bydate.items() if len(a)>=10}
    return index,bm

def sector_gate(t,d,members,bars,index,bench,sector_cache):
    key=(t,d)
    own=asof_membership(members,t,d)
    if own is None:return None,'MISSING_ASOF_SECTOR'
    key2=(own.sector,d)
    if key2 not in sector_cache:
        entries=[]
        for code,b in bars.items():
            m=asof_membership(members,code,d)
            i=index[code].get(d)
            if m is None or m.sector!=own.sector or i is None or i<20:continue
            last=b[i]['c']; p5=b[i-5]['c'];p20=b[i-20]['c']
            turns=[x['c']*x['v'] for x in b[i-19:i+1]]
            prev=sum(turns[:15])/15 if any(turns[:15]) else 0
            now=sum(turns[15:])/5
            accel=now/prev if prev else 0
            entries.append((100*(last/p5-1),100*(last/p20-1),accel))
        sector_cache[key2]=entries
    entries=sector_cache[key2]
    if d not in bench:return None,'MISSING_BENCHMARK_DATE'
    if len(entries)<3:return None,'INSUFFICIENT_ASOF_SECTOR_MEMBERS'
    sec5=statistics.median(x[0] for x in entries);breadth=sum(x[0]>0 for x in entries)/len(entries)
    turnover=statistics.median(x[2] for x in entries);leader=max(x[0] for x in entries)
    idx=index[t].get(d)
    if idx is None or idx<20:return None,'INSUFFICIENT_STOCK_HISTORY'
    stock20=100*(bars[t][idx]['c']/bars[t][idx-20]['c']-1)
    relative20=stock20-bench[d][1]
    result={'sector':own.sector,'sector_median5_pct':round(sec5,3),'sector_excess5_pp':round(sec5-bench[d][0],3),
            'sector_breadth':round(breadth,3),'sector_turnover_accel':round(turnover,3),
            'leader5_pct':round(leader,3),'stock_rs20_pp':round(relative20,3)}
    if sec5-bench[d][0]<1.5 or breadth<.55 or turnover<1.05 or leader<6 or relative20<=0:
        return result,'SECTOR_FLOW_GATE_FAIL'
    return result,'OK'

def plan_entry(b,i,s,mode):
    if i+1>=len(b):return None,'NO_NEXT_DAY'
    stop=s['stop'];cap=s['no_chase_above']
    if mode=='E2_NEXT_OPEN':
        p=b[i+1]['o']
        if p<=stop or p>cap:return None,'GAP_OR_CHASE'
        return (i+1,p),'FILLED'
    if mode=='E3_NEXT_CLOSE_PROXY':
        # A real close-auction order cannot know the final close in advance.
        # Never condition fill on the unknown close; this is a non-executable proxy only.
        p=b[i+1]['c']
        return (i+1,p),'CLOSE_PROXY_NOT_EXECUTABLE'
    lim=s['ideal_buy_high'];buffer=.02*s['atr14']
    for j in range(i+1,min(i+3,len(b))):
        bar=b[j]
        if bar['o']<=stop:return None,'CANCEL_STOP_GAP'
        if bar['l']<=lim-buffer:
            # A fill at the order limit (not improved at open) is conservative.
            p=lim
            if p<=stop:return None,'INVALID_LIMIT'
            return (j,p),'FILLED'
    return None,'LIMIT_UNFILLED'

def simulate_exit(b,ei,p,stop,mode,exit_model,hold=10,cost_bps=35,slip_bps=5):
    last=ei+hold-1
    if last>=len(b):return None,'PENDING_FUTURE'
    if p<=stop or hold<1:return None,'BAD_RISK'
    gapcost=slip_bps/10000;target10=p*1.10;target33=p*1.033
    remain=1.;gross=0.;hit10=False;hit33=False
    peak=p;active_stop=stop;exit_i=last;reason='TIME'
    highs=[];lows=[]
    for j in range(ei,last+1):
        bar=b[j]
        if j==ei and mode=='E3_NEXT_CLOSE_PROXY':continue
        highs.append(bar['h']);lows.append(bar['l'])
        if j>ei and bar['o']<=active_stop:
            px=bar['o']*(1-gapcost)
            gross+=remain*(px/p-1);remain=0.;reason='GAP_STOP';exit_i=j;break
        if bar['l']<=active_stop:
            px=active_stop*(1-gapcost)
            gross+=remain*(px/p-1);remain=0.;reason='STOP_FIRST';exit_i=j;break
        # Same bar limit fill has no proven price ordering. Do not count gains on fill day.
        if j==ei and mode=='E1_LIMIT_2D':continue
        if exit_model=='X10_FULL':
            if bar['h']>=target10:
                hit10=True;gross+=remain*(target10/p-1);remain=0.;reason='TARGET10';exit_i=j;break
        else:
            if not hit33 and bar['h']>=target33:
                hit33=True;gross+=.5*(target33/p-1);remain=.5
            if bar['h']>=target10:
                hit10=True;gross+=remain*(target10/p-1);remain=0.;reason='TARGET10_REMAINDER';exit_i=j;break
            # trailing stop updated after closing price; applied starting next bar only
            if hit33:
                peak=max(peak,bar['c'])
                active_stop=max(active_stop,peak-2*sma_atr(b,ei))
    if remain:
        px=b[last]['c'];gross+=remain*(px/p-1)
    net=100*gross-cost_bps/100
    return {'entry_price':round(p,4),'stop':round(stop,4),'exit_date':b[exit_i]['date'],'exit_reason':reason,
            'net_pct':round(net,4),'net_R':round(net/(100*(p-stop)/p),4),
            'hit10_before_stop':int(hit10),'hit33_before_stop':int(hit33),
            'mfe_pct':round(100*(max(highs)/p-1),3) if highs else '',
            'mae_pct':round(100*(min(lows)/p-1),3) if lows else '',
            'exit_idx':exit_i,'approx_fill':True},'CLOSED'

def sma_atr(b,i,n=14):
    vals=[]
    for j in range(max(1,i-n+1),i+1):
        q=b[j];prev=b[j-1]['c'];vals.append(max(q['h']-q['l'],abs(q['h']-prev),abs(q['l']-prev)))
    return sum(vals)/len(vals) if vals else 0

def scorecard(rows):
    agg=defaultdict(list)
    for x in rows:agg[(x['tier'],x['mode'],x['exit_model'],int(x['horizon']))].append(x)
    out=[]
    for (tier,mode,xmodel,h),items in sorted(agg.items()):
        gains=[float(t['net_pct']) for t in items]
        wins=sum(v>0 for v in gains);pos=sum(max(0,v) for v in gains);loss=-sum(min(0,v) for v in gains)
        out.append({'tier':tier,'mode':mode,'exit_model':xmodel,'horizon':h,'trades':len(items),'unique_signal_dates':len(set(x['signal_date'] for x in items)),
                    'avg_net_pct':round(statistics.mean(gains),4),'win_pct':round(100*wins/len(gains),2),
                    'hit10_before_stop_pct':round(100*sum(x['hit10_before_stop'] for x in items)/len(items),2),
                    'profit_factor':round(pos/loss,3) if loss else '',
                    'approval':'NO_RESEARCH_ONLY'})
    return out

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    one=ap.add_mutually_exclusive_group(required=True)
    one.add_argument('--report-zip');one.add_argument('--cache-dir')
    ap.add_argument('--sector-pit',default='config/v90_sector_membership_pit.csv')
    ap.add_argument('--financial-pit',default='config/v90_financial_pit.csv')
    ap.add_argument('--outdir',default='reports')
    ap.add_argument('--score-min',type=int,default=70)
    ap.add_argument('--cost-bps',type=float,default=35)
    args=ap.parse_args()
    if args.score_min<50 or args.score_min>95 or not 0<=args.cost_bps<=250:ap.error('invalid args')
    dest=Path(args.outdir);dest.mkdir(parents=True,exist_ok=True)
    rm,map_status=read_csv(args.sector_pit,MAP_COLS);rf,fin_status=read_csv(args.financial_pit,FIN_COLS)
    members,mapreject=build_memberships(rm);fin,finreject=build_filings(rf)
    bars={};quality=Counter();sources=0
    for ticker,raw in source_files(args.cache_dir,args.report_zip):
        sources+=1;b,reason=decode_rows(raw);quality[reason]+=1
        if b is not None:bars[ticker]=b
    index,bench=calc_market_per_date(bars)
    signals=[];bykey={};block=Counter();candidates=[];sector_cache={}
    for ticker,b in bars.items():
        for i,s in find_signals(ticker,b,args.score_min):
            if i>=len(b)-1:continue
            signals.append((ticker,i,s))
            recent_resistance_breached=any(x['h']>=s['resistance'] for x in b[i-3:i+1])
            stat={'ticker':ticker,'signal_date':s['signal_date'],'signal_score':s['score'],'price_score':s['score'],
                  'sector':'','selection_status':''}
            sec,sec_status=sector_gate(ticker,s['signal_date'],members,bars,index,bench,sector_cache)
            if sec:stat.update(sec)
            f=asof_financial(fin,ticker,s['signal_date'])
            if f:
                stat.update({'filing_date':f.filing_date,'financial_available_date':f.available_date,'revenue_yoy_pct':f.revenue_yoy_pct,
                             'op_profit_yoy_pct':f.op_profit_yoy_pct,'op_margin_pct':f.op_margin_pct,'debt_ratio_pct':f.debt_ratio_pct})
            if recent_resistance_breached:reason='PRIOR_BREAKOUT_OR_TEST_NOT_CLEAN'
            elif sec_status!='OK':reason=sec_status
            elif f is None:reason='MISSING_ASOF_FINANCIAL'
            elif not fin_pass(f):reason='FINANCIAL_GATE_FAIL'
            else:reason='STRICT_GATE_PASS'
            block[reason]+=1;stat['selection_status']=reason;candidates.append(stat)
            if reason=='STRICT_GATE_PASS':
                stat['signal_score']=s['score']+min(10,max(0,sec['sector_excess5_pp']))+min(10,max(0,sec['stock_rs20_pp']))
                bykey[(s['signal_date'],ticker)]=(ticker,i,s,stat)
    # No portfolio-level hindsight selection: rank only by contemporaneous inputs.
    strict_bydate=defaultdict(list)
    for (d,t),x in bykey.items():strict_bydate[d].append(x)
    chosen={d:sorted(rows,key=lambda x:(-x[3]['signal_score'],x[0]))[0] for d,rows in strict_bydate.items()}
    trades=[];strict_reject=Counter()
    for mode in ENTRIES:
        if mode=='E3_NEXT_CLOSE_PROXY':
            strict_reject['E3_UNEXECUTABLE_WITH_DAILY_BARS']+=len(chosen)
            continue
        for xmodel in EXITS:
            for h in HOLDS:
                occupied_until=''
                for d in sorted(chosen):
                    t,i,s,meta=chosen[d]
                    if occupied_until and d<=occupied_until:continue
                    e,st=plan_entry(bars[t],i,s,mode)
                    if e is None:strict_reject[st]+=1;continue
                    ei,p=e
                    if not .01<=(p-s['stop'])/p<=.075:strict_reject['RISK_REJECT']+=1;continue
                    result,status=simulate_exit(bars[t],ei,p,s['stop'],mode,xmodel,h,args.cost_bps)
                    if result is None:strict_reject[status]+=1;continue
                    occupied_until=result['exit_date']
                    trades.append({'tier':'STRICT_PIT','ticker':t,'signal_date':d,'signal_score':meta['signal_score'],
                                   'sector':meta['sector'],'mode':mode,'exit_model':xmodel,'horizon':h,'entry_date':bars[t][ei]['date'],
                                   **result,'research_only':True})
    # A separate limited diagnostic deliberately ignores missing PIT inputs and is NOT the integrated strategy.
    # To avoid misleading large overlapping raw trade counts, select one highest-scoring signal per date.
    diag_bydate={}
    for t,i,s in signals:
        # Match the desired genuinely pre-breakout subtype, not an earlier resistance probe.
        if any(x['h']>=s['resistance'] for x in bars[t][i-3:i+1]):continue
        d=s['signal_date'];x=diag_bydate.get(d)
        if x is None or (-s['score'],t)<(-x[2]['score'],x[0]):diag_bydate[d]=(t,i,s)
    diag=[];diag_block=Counter()
    for mode in ENTRIES:
        for xmodel in EXITS:
            for h in HOLDS:
                occupied_until=''
                for d in sorted(diag_bydate):
                    if occupied_until and d<=occupied_until:continue
                    t,i,s=diag_bydate[d]
                    e,status=plan_entry(bars[t],i,s,mode)
                    if e is None:diag_block[status]+=1;continue
                    ei,p=e
                    if not .01<=(p-s['stop'])/p<=.075:diag_block['RISK_GATE']+=1;continue
                    result,st=simulate_exit(bars[t],ei,p,s['stop'],mode,xmodel,h,args.cost_bps)
                    if result is None:diag_block[st]+=1;continue
                    occupied_until=result['exit_date']
                    diag.append({'ticker':t,'signal_date':d,'score':s['score'],'subtype':s['subtype'],
                                 'entry_mode':mode,'exit_model':xmodel,'horizon':h,'entry_date':bars[t][ei]['date'],**result})
    # Matched max-20-session cohort: hold horizon cannot silently change which
    # signals are traded. A single 20-session reserved slot is used for all holds.
    paired=[];paired_skips=Counter()
    for mode in ENTRIES:
        occupied_until=''
        for d in sorted(diag_bydate):
            if occupied_until and d<=occupied_until:continue
            t,i,ss=diag_bydate[d];b=bars[t]
            e,reason=plan_entry(b,i,ss,mode)
            if e is None:paired_skips[reason]+=1;continue
            ei,p=e
            if not .01<=(p-ss['stop'])/p<=.075:paired_skips['RISK_GATE']+=1;continue
            if ei+19>=len(b):paired_skips['NO_COMPLETE_20_SESSION_FUTURE']+=1;continue
            occupied_until=b[ei+19]['date']
            for xmodel in EXITS:
                for h in HOLDS:
                    result,reason=simulate_exit(b,ei,p,ss['stop'],mode,xmodel,h,args.cost_bps)
                    if result is None:raise RuntimeError('paired 20d cohort yielded missing outcome')
                    paired.append({'tier':'CHART_ONLY_PAIRED_20D','ticker':t,'signal_date':d,'signal_score':ss['score'],
                                   'sector':'','mode':mode,'exit_model':xmodel,'horizon':h,'entry_date':b[ei]['date'],
                                   **result,'research_only':True})
    cols=['tier','mode','exit_model','horizon','trades','unique_signal_dates','avg_net_pct','win_pct','hit10_before_stop_pct','profit_factor','approval']
    dscore=scorecard([{'tier':'CHART_ONLY_DIAGNOSTIC','mode':x['entry_mode'],'exit_model':x['exit_model'],'horizon':x['horizon'],
                      'net_pct':x['net_pct'],'signal_date':x['signal_date'],'hit10_before_stop':x['hit10_before_stop']} for x in diag])
    sscore=scorecard(trades)
    # Chronological split is only a robustness diagnostic, not truly unseen OOS: the rule was developed on prior results.
    split_date=sorted(set(s['signal_date'] for _,_,s in signals))
    split_date=split_date[int(len(split_date)*0.7)] if split_date else '9999-12-31'
    split_rows=[]
    for tier,items in [('CHART_ONLY_DIAGNOSTIC',diag),('STRICT_PIT',trades)]:
        for phase in ('EARLY','LATE'):
            it=[r for r in items if (r['signal_date']<split_date)==(phase=='EARLY')]
            for row in it:
                x={'tier':tier,'mode':row.get('mode',row.get('entry_mode')),'exit_model':row['exit_model'],
                   'horizon':row['horizon'],'net_pct':row['net_pct'],'signal_date':row['signal_date'],
                   'hit10_before_stop':row['hit10_before_stop']}
                x['phase']=phase
                split_rows.append(x)
    split_score=[]
    for phase in ('EARLY','LATE'):
        for c in scorecard([r for r in split_rows if r['phase']==phase]):
            split_score.append({'split_date':split_date,'phase':phase,**c})
    write_csv(dest/'v90_pit_candidate_audit.csv',candidates,CAND_COLS)
    write_csv(dest/'v90_strict_trades.csv',trades,TRADES_COLS)
    write_csv(dest/'v90_chart_only_diagnostics.csv',diag,DIAG_COLS)
    write_csv(dest/'v90_mode_comparison.csv',sscore+dscore,cols)
    write_csv(dest/'v90_chronological_split.csv',split_score,['split_date','phase']+cols)
    write_csv(dest/'v90_paired_20d_comparison.csv',scorecard(paired),cols)
    write_csv(dest/'v90_paired_20d_trades.csv',paired,TRADES_COLS)
    diag_dates=sorted(set(x['signal_date'] for x in diag))
    has_verified_inputs=bool(members) and bool(fin)
    strict_status=('EXPLORATORY_PIT_SAMPLED_NOT_CERTIFIED' if trades else ('WAIT_NO_VALID_COMPLETE_TRADES' if has_verified_inputs else 'BLOCKED_MISSING_POINT_IN_TIME_DATA'))
    status={'version':VERSION,'research_only':True,'buy_approval':False,'strict_integrated_status':strict_status,
            'source_files':sources,'valid_bars':len(bars),'data_quality':dict(quality),'last_dates':dict(Counter(b[-1]['date'] for b in bars.values())),
            'mapping_file_status':map_status,'financial_file_status':fin_status,'verified_membership_rows':sum(map(len,members.values())),
            'verified_filing_rows':sum(map(len,fin.values())),'rejected_map_rows':dict(mapreject),'rejected_finance_rows':dict(finreject),
            'split_boundary_exploratory':split_date,'chart_only_signals':len(signals),'clean_prebreakout_signals':sum(not any(x['h']>=s['resistance'] for x in bars[t][i-3:i+1]) for t,i,s in signals),'distinct_chart_signal_dates':len(set(s['signal_date'] for _,_,s in signals)),
            'strict_gate_pass':len(bykey),'strict_failure_reasons':dict(block),'strict_strategy_trades_including_variants':len(trades),
            'chart_only_diagnostic_trades_including_variants':len(diag),'paired_20d_variants':len(paired),'paired_skips':dict(paired_skips),'chart_only_unique_days':len(diag_dates),
            'strict_execution_rejections':dict(strict_reject),'diagnostic_execution_rejections':dict(diag_block),
            'limitations':['Chart-only diagnostic explicitly omits fundamentals and sector money flow; it is not the target strategy.',
                           'Available OHLC cache is short or stale for many tickers and not a historical full KRX universe.',
                           'Sector membership must be dated and verified; current 2026 mappings cannot be retroactively applied.',
                           'Financial values must have DART receipt and next-session available_date, no future restatements.',
                           'Close*volume is turnover proxy; not verified exchange traded value.',
                           'One-slot portfolio is modeled separately per entry/exit/horizon, no actual position sync.',
                           'E3 next-close is UNCONDITIONAL, non-executable research proxy; strict PIT trading excludes it until pre-auction quotes are available.',
                           'Daily bars cannot certify same-session path, limit queue or closing-auction fills.',
                           'No verified delisted stocks/price adjustments in source; sensitivity and walk-forward needed.',
                           'Exit target +10% is hypothetical, no guarantee of overhead-resistance clearance.']}
    (dest/'v90_research_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'strict_status':status['strict_integrated_status'],'price_signals':len(signals),'strict_pass':len(bykey),'strict_trades':len(trades),'chart_diag_trades':len(diag),'valid':len(bars)},ensure_ascii=False))

if __name__=='__main__':main()
