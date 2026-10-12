#!/usr/bin/env python3
"""v7.7: conservative forward-only paper-entry audit for v7.6 WAIT candidates.
Research only. No real trading. No same-day lookahead. Never invent future bars.
"""
import argparse
import csv
import json
import math
import time
from datetime import date, datetime, timedelta
from pathlib import Path


def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader(); w.writerows(rows)


def valid_bars(path):
    if not path.exists(): return []
    try:
        rows = read_csv(path)
        out = []
        for r in rows:
            d = (r.get('Date') or r.get('date') or '').strip()[:10]
            date.fromisoformat(d)
            o,h,l,c = [float(r[k]) for k in ('Open','High','Low','Close')]
            v = float(r['Volume'])
            if not all(map(math.isfinite, (o,h,l,c,v))) or min(o,h,l,c)<=0 or v<0 or h<max(o,c,l) or l>min(o,c,h):
                return []
            out.append(dict(date=d,open=o,high=h,low=l,close=c,volume=v))
        if len({r['date'] for r in out}) != len(out): return []
        return sorted(out,key=lambda r:r['date'])
    except (ValueError,KeyError,TypeError,OverflowError): return []


def fetch_forward(ticker, start, end, source, output):
    import FinanceDataReader as fdr
    frame=fdr.DataReader(ticker,start,end)
    if frame is None or frame.empty: return False
    frame=frame.reset_index()
    frame['Date']=frame['Date'].dt.strftime('%Y-%m-%d')
    cols=['Date','Open','High','Low','Close','Volume']
    frame[cols].to_csv(output,index=False,encoding='utf-8-sig')
    return True


def fnum(v):
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError): return None


def process(signal, bars, asof, max_entry_sessions, fee_bps, slip_bps):
    ticker=(signal.get('ticker') or '').zfill(6)
    name=signal.get('name','')
    base=dict(ticker=ticker,name=name,signal_asof=asof,entry_low=signal.get('entry_low',''),entry_high=signal.get('entry_high',''),stop_reference=signal.get('stop_reference',''),target_reference=signal.get('target_reference',''),fill_date='',fill_price='',exit_date='',exit_price='',exit_reason='',net_return_pct='',bars_after_signal=0,post_fill_bars=0,status='')
    low,high,stop,target=(fnum(signal.get(k)) for k in ('entry_low','entry_high','stop_reference','target_reference'))
    if any(v is None for v in (low,high,stop,target)) or not 0<stop<low<=high<target:
        base['status']='INVALID_SIGNAL_LEVELS';return base,[]
    forward=[r for r in bars if r['date']>asof]
    base['bars_after_signal']=len(forward)
    if not forward:
        base['status']='NO_FORWARD_DATA';return base,[]
    entry_index=None;entry=None
    for i,r in enumerate(forward[:max_entry_sessions]):
        # Entry order only becomes active the session after signal.
        # Open in range => open fill; gap below range => no fill; high/low touch => at high limit.
        if low<=r['open']<=high: entry=r['open']
        elif r['open']>high and r['low']<=high and r['high']>=high: entry=high
        elif r['open']<low and r['high']>=low and r['low']<=high: entry=low
        if entry is not None:
            entry_index=i;break
    if entry_index is None:
        base['status']='NO_ENTRY_TOUCH' if len(forward)>=max_entry_sessions else 'ENTRY_WINDOW_INCOMPLETE'
        return base,[]
    # Model adverse entry slippage; no order book/market impact claim.
    entry=entry*(1+slip_bps/10000)
    base['fill_date']=forward[entry_index]['date'];base['fill_price']=round(entry,4)
    after=forward[entry_index:]
    base['post_fill_bars']=len(after)
    # Conservative: if entry-day low <= stop, treat stop as hit even if order of events unknown.
    # Same-session target never credited if stop also touched.
    outcomes=[];exit_idx=None;exit_price=None;reason=None
    for j,r in enumerate(after):
        if r['low']<=stop:
            exit_idx=j;exit_price=min(stop,r['open']) if j>0 else stop;reason='STOP_CONSERVATIVE_INTRADAY';break
        if r['high']>=target:
            exit_idx=j;exit_price=target;reason='TARGET_INTRADAY';break
    for horizon in (1,3,5,10):
        if exit_idx is not None and exit_idx < horizon:
            px=exit_price;day=after[exit_idx]['date'];status='CLOSED_'+reason
        elif len(after)>=horizon:
            px=after[horizon-1]['close'];day=after[horizon-1]['date'];status='MARK_TO_CLOSE'
        else:
            px=None;day='';status='PENDING_FUTURE_SESSIONS'
        # Cost: entry fee + exit fee, and exit slippage; conservative simplified gross not trade accounting.
        net=100*((px*(1-slip_bps/10000)*(1-fee_bps/10000))/(entry*(1+fee_bps/10000))-1) if px is not None else None
        outcomes.append(dict(ticker=ticker,name=name,fill_date=base['fill_date'],horizon_sessions=horizon,valuation_date=day,valuation_price=round(px,4) if px is not None else '',net_return_pct=round(net,4) if net is not None else '',status=status))
    if exit_idx is not None:
        base.update(exit_date=after[exit_idx]['date'],exit_price=round(exit_price,4),exit_reason=reason,net_return_pct=outcomes[-1]['net_return_pct'],status='PAPER_EXIT')
    else: base['status']='PAPER_OPEN_OR_HORIZON_PENDING'
    return base,outcomes


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--queue',default='reports/v76_paper_trade_queue.csv')
    p.add_argument('--cache',default='reports/v36_ohlcv_cache')
    p.add_argument('--forward-cache',default='reports/v77_forward_cache')
    p.add_argument('--outdir',default='reports')
    p.add_argument('--fetch',action='store_true',help='Attempt network forward OHLCV collection, without altering old cache')
    p.add_argument('--source',default='NAVER')
    p.add_argument('--end',default=date.today().isoformat())
    p.add_argument('--max-entry-sessions',type=int,default=3)
    p.add_argument('--fee-bps',type=float,default=15)
    p.add_argument('--slip-bps',type=float,default=10)
    a=p.parse_args()
    if a.max_entry_sessions<1 or a.fee_bps<0 or a.slip_bps<0: p.error('Invalid assumptions')
    outdir=Path(a.outdir);outdir.mkdir(parents=True,exist_ok=True)
    fw=Path(a.forward_cache);fw.mkdir(parents=True,exist_ok=True)
    queue=read_csv(a.queue)
    if not queue: raise SystemExit('Empty v7.6 paper trade queue')
    entries=[];outcomes=[];fetch_log=[]
    for sig in queue:
        ticker=(sig.get('ticker') or '').zfill(6);asof=sig.get('signal_asof','')
        date.fromisoformat(asof)
        original=valid_bars(Path(a.cache)/(ticker+'.csv'))
        extra=valid_bars(fw/(ticker+'.csv'))
        if a.fetch and not any(r['date']>asof for r in extra+original):
            try:
                fetched=fetch_forward(ticker,(date.fromisoformat(asof)+timedelta(days=1)).isoformat(),(date.fromisoformat(a.end)+timedelta(days=1)).isoformat(),a.source,fw/(ticker+'.csv'))
                fetch_log.append(dict(ticker=ticker,fetch='SUCCESS' if fetched else 'EMPTY'))
                extra=valid_bars(fw/(ticker+'.csv'))
            except Exception as e:
                fetch_log.append(dict(ticker=ticker,fetch='ERROR_'+type(e).__name__))
            time.sleep(.5)
        # Keep the original history authoritative through signal date; newer forward bars from dedicated cache.
        merged={r['date']:r for r in original}
        merged.update({r['date']:r for r in extra if r['date']>asof})
        entry,horizons=process(sig,sorted(merged.values(),key=lambda r:r['date']),asof,a.max_entry_sessions,a.fee_bps,a.slip_bps)
        entries.append(entry);outcomes.extend(horizons)
    entry_fields=['ticker','name','signal_asof','entry_low','entry_high','stop_reference','target_reference','fill_date','fill_price','exit_date','exit_price','exit_reason','net_return_pct','bars_after_signal','post_fill_bars','status']
    horizon_fields=['ticker','name','fill_date','horizon_sessions','valuation_date','valuation_price','net_return_pct','status']
    write_csv(outdir/'v77_paper_entries.csv',entries,entry_fields)
    write_csv(outdir/'v77_forward_outcomes.csv',outcomes,horizon_fields)
    audit=dict(version='7.7',source='v7.6 historical WAIT queue',signals=len(queue),paper_fills=sum(bool(r['fill_date']) for r in entries),paper_exits=sum(r['status']=='PAPER_EXIT' for r in entries),no_forward_data=sum(r['status']=='NO_FORWARD_DATA' for r in entries),forward_horizons_evaluated=sum(isinstance(r['net_return_pct'],float) for r in outcomes),fetch_attempted=a.fetch,fetch_log=fetch_log,fee_bps=a.fee_bps,slippage_bps=a.slip_bps,max_entry_sessions=a.max_entry_sessions,real_trading_authorized=False,limitations=['OHLCV bars do not reveal intraday execution sequence; same-day stop conservatively prioritized','No liquidity, spread, queue priority, taxes or exchange-specific tick rounding verified','Historical signal cohort selected with hindsight; not a walk-forward unbiased performance estimate','Insufficient future bars are PENDING, never assigned invented returns','Entry/exit fill and fees/slippage are modeled assumptions, not actual fills'])
    (outdir/'v77_paper_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False))

if __name__=='__main__':main()
