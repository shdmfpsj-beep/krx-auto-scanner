#!/usr/bin/env python3
"""v7.6: conservative historical entry eligibility and forward-paper-trade queue.
No live orders. No look-ahead. No claim of exchange tick validation.
"""
import argparse
import csv
import json
import math
from datetime import date
from pathlib import Path

FIELDS = ['ticker','name','candidate_class','asof','setup','close','stock_5d_pct','stock_20d_pct','rvol20','technical_score','ideal_buy_low','ideal_buy_high','max_buy','no_chase_above','structural_stop','target_1','target_2','entry_low','entry_high','stop_reference','target_reference','risk_pct','reward_risk','decision','reason','trade_authorized']

def num(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None

def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def write_csv(path, rows, fields):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
        w.writeheader();w.writerows(rows)

def evaluate(src, args):
    r=dict(src)
    close=num(r.get('close')); lo=num(r.get('ideal_buy_low')); hi=num(r.get('ideal_buy_high'))
    cap=num(r.get('max_buy')); chase=num(r.get('no_chase_above'))
    stop=num(r.get('structural_stop')); target=num(r.get('target_1'))
    p5=num(r.get('stock_5d_pct')); p20=num(r.get('stock_20d_pct'))
    reasons=[]
    if r.get('setup') not in ('FIRST_PULLBACK','BREAKOUT'):
        reasons.append('UNKNOWN_SETUP')
    if any(v is None or v <= 0 for v in (close,lo,hi,cap,chase,stop,target)):
        reasons.append('INVALID_PRICE')
    if p5 is None or p20 is None:
        reasons.append('MISSING_RETURN')
    if reasons:
        r.update(entry_low='',entry_high='',stop_reference='',target_reference='',risk_pct='',reward_risk='',decision='DATA_REJECT',reason=';'.join(reasons),trade_authorized='NO')
        return r
    upper=min(hi,cap,chase)
    if lo > upper or stop >= lo or target <= upper:
        reasons.append('INVALID_ENTRY_GEOMETRY')
    if p5 > args.max_5d_pct or p20 > args.max_20d_pct:
        reasons.append('OVERHEATED_RETURN')
    if close > upper * (1+args.max_chase_pct/100):
        reasons.append('ABOVE_ENTRY_CEILING')
    if close < stop:
        reasons.append('BELOW_STRUCTURAL_STOP')
    risk_pct=(upper-stop)/upper*100 if upper > stop else None
    rr=(target-upper)/(upper-stop) if upper > stop else None
    if risk_pct is not None and risk_pct > args.max_risk_pct:
        reasons.append('EXCESSIVE_STOP_DISTANCE')
    if rr is not None and rr < args.min_rr:
        reasons.append('LOW_REWARD_RISK')
    # Do not infer tick size from unverified market segment / historical tick rules.
    if not reasons:
        reasons.append('HISTORICAL_PRICE_ONLY_NO_LIVE_GATE')
    r.update(entry_low=round(lo,2),entry_high=round(upper,2),stop_reference=round(stop,2),target_reference=round(target,2),risk_pct=round(risk_pct,3) if risk_pct is not None else '',reward_risk=round(rr,3) if rr is not None else '',decision='WAIT' if reasons == ['HISTORICAL_PRICE_ONLY_NO_LIVE_GATE'] else 'BLOCK',reason=';'.join(reasons),trade_authorized='NO')
    return r

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',default='reports/v75_common_technical_watchlist.csv')
    p.add_argument('--outdir',default='reports')
    p.add_argument('--max-5d-pct',type=float,default=25)
    p.add_argument('--max-20d-pct',type=float,default=70)
    p.add_argument('--max-chase-pct',type=float,default=0)
    p.add_argument('--max-risk-pct',type=float,default=12)
    p.add_argument('--min-rr',type=float,default=1.5)
    a=p.parse_args()
    if not (0 <= a.max_chase_pct <= 5 and a.max_risk_pct>0 and a.min_rr>0):
        p.error('Invalid gate parameters')
    src=read_csv(Path(a.input))
    if not src: raise SystemExit('Input watchlist is empty')
    asofs={r.get('asof','') for r in src}
    if len(asofs)!=1 or not next(iter(asofs)):
        raise SystemExit('Mixed or missing historical asof dates')
    seen=set(); rows=[]
    for r in src:
        t=r.get('ticker','').zfill(6)
        if not t.isdigit() or len(t)!=6 or t in seen:
            raise SystemExit('Duplicate or invalid ticker: '+t)
        seen.add(t)
        rows.append(evaluate(r,a))
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    write_csv(out/'v76_entry_eligibility.csv',rows,FIELDS)
    wait=sorted((r for r in rows if r['decision']=='WAIT'),key=lambda r:float(r.get('technical_score') or 0),reverse=True)
    write_csv(out/'v76_conditional_research_top3.csv',wait[:3],FIELDS)
    # Future outcomes cannot be computed from as-of data; explicitly track pending status.
    ledger=[]
    for r in wait[:3]:
        ledger.append({'ticker':r['ticker'],'name':r['name'],'signal_asof':r['asof'],'entry_condition':'NEXT_SESSION_OR_LATER_TOUCH_WITH_LIVE_CONFIRMATION','entry_low':r['entry_low'],'entry_high':r['entry_high'],'stop_reference':r['stop_reference'],'target_reference':r['target_reference'],'entry_fill_date':'','entry_fill_price':'','horizon_1d':'PENDING_FUTURE_DATA','horizon_3d':'PENDING_FUTURE_DATA','horizon_5d':'PENDING_FUTURE_DATA','horizon_10d':'PENDING_FUTURE_DATA','fees_bps':'NOT_APPLIED_NO_FILL','slippage_bps':'NOT_APPLIED_NO_FILL','status':'NO_EXECUTED_PAPER_TRADE'})
    write_csv(out/'v76_paper_trade_queue.csv',ledger,['ticker','name','signal_asof','entry_condition','entry_low','entry_high','stop_reference','target_reference','entry_fill_date','entry_fill_price','horizon_1d','horizon_3d','horizon_5d','horizon_10d','fees_bps','slippage_bps','status'])
    audit={'version':'7.6','asof':next(iter(asofs)),'scope':'v7.5 preselected 51 historical candidates, not unbiased full-market backtest','total':len(rows),'wait_count':len(wait),'blocked_count':sum(r['decision']=='BLOCK' for r in rows),'data_reject_count':sum(r['decision']=='DATA_REJECT' for r in rows),'conditional_top3':[{'ticker':r['ticker'],'name':r['name'],'decision':r['decision']} for r in wait[:3]],'gate_parameters':{'max_5d_pct':a.max_5d_pct,'max_20d_pct':a.max_20d_pct,'max_chase_pct':a.max_chase_pct,'max_risk_pct':a.max_risk_pct,'min_rr':a.min_rr},'trade_authorized':False,'filled_paper_trades':0,'forward_returns_available':False,'limitations':['Historical-only snapshot; no future bars to confirm entries or returns','Exchange-specific historical tick sizes, live liquidity, fees and slippage not validated','Technical target values are model projections, not demonstrated probabilities','Research WAIT is not BUY; conditional TOP3 may contain fewer than 3 names','Sample selected using same-day data; no unbiased full-market historical performance claim']}
    (out/'v76_entry_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False))
if __name__=='__main__':main()
