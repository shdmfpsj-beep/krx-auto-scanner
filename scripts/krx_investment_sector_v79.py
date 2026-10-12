#!/usr/bin/env python3
"""v7.9: audited forward refresh, revision provenance and freshness safeguards.
Research-only continuation of the v7.6 paper queue; NEVER a live BUY engine.
"""
import argparse
import csv
import json
import math
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
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


def price_basis_ok(ticker, asof, original, anchor_close, tolerance_pct=2.0):
    asof_bars=[r for r in original if r['date']==asof]
    if not asof_bars:
        return False, 'MISSING_ASOF_BAR', None
    old_close=asof_bars[0]['close']
    if anchor_close is None or anchor_close<=0:
        return False, 'MISSING_SIGNAL_ANCHOR_CLOSE', old_close
    difference=abs(old_close/anchor_close-1)*100
    if difference>tolerance_pct:
        return False, 'SIGNAL_CLOSE_BASIS_MISMATCH', old_close
    return True,'MATCH',old_close


def save_forward_cache(path,bars):
    tmp=path.with_suffix('.tmp')
    with open(tmp,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['Date','Open','High','Low','Close','Volume'])
        w.writeheader()
        for r in sorted(bars,key=lambda t:t['date']):
            w.writerow(dict(Date=r['date'],Open=r['open'],High=r['high'],Low=r['low'],Close=r['close'],Volume=r['volume']))
    tmp.replace(path)


def refresh_forward(ticker,asof,end,source,path,existing):
    """Compare before/after OHLCV bars; retain any original cache on material revision.

    Source arg is a legacy hint ONLY. FDR selects its actual backend, which is not
    independently confirmed as NAVER or KRX. See audit provider disclosure.
    """
    temp=path.with_suffix('.fetch.tmp')
    old_map={r['date']:r for r in existing if asof<r['date']<=end}
    changes=[]
    rec=dict(ticker=ticker,status='FETCH_NOT_RUN',new_bars=0,
             revised_days=0,major_revision_days=0,max_revision_pct=0.0,
             missing_existing_days=0,revision_dates='',missing_dates='')
    try:
        ok=fetch_forward(ticker,(date.fromisoformat(asof)+timedelta(days=1)).isoformat(),
                         (date.fromisoformat(end)+timedelta(days=1)).isoformat(),source,temp)
        if not ok:
            rec['status']='EMPTY_KEEP_CACHE';return existing,rec,changes
        fetched=valid_bars(temp)
        if not fetched:
            rec['status']='INVALID_KEEP_CACHE';return existing,rec,changes
        fetched_map={r['date']:r for r in fetched if asof<r['date']<=end}
        if not fetched_map:
            rec['status']='NO_REQUESTED_DATES_KEEP_CACHE';return existing,rec,changes
        old_keys=set(old_map)
        new_keys=set(fetched_map)
        # Provider outages or short responses must not erase cached dates.
        missing=sorted(old_keys-new_keys)
        rec['missing_existing_days']=len(missing)
        rec['missing_dates']=';'.join(missing)
        max_revision=0.0
        for d in sorted(old_keys & new_keys):
            old,new=old_map[d],fetched_map[d]
            pct={k:100*(new[k]/old[k]-1) if old[k]>0 else 0.0
                 for k in ('open','high','low','close')}
            vol_pct=100*(new['volume']/old['volume']-1) if old['volume']>0 else (0 if new['volume']==0 else None)
            max_abs=max(abs(x) for x in pct.values())
            vol_changed=old['volume'] != new['volume']
            if max_abs>1e-8 or vol_changed:
                changes.append(dict(ticker=ticker,date=d,
                                    max_abs_ohlc_revision_pct=round(max_abs,6),
                                    close_revision_pct=round(pct['close'],6),
                                    volume_revision_pct=round(vol_pct,6) if vol_pct is not None else '',
                                    material_revision=max_abs>0.5,
                                    disposition='QUARANTINED' if max_abs>0.5 else 'ACCEPTED'))
                max_revision=max(max_revision,max_abs)
        major=[x for x in changes if x['material_revision']]
        rec['revised_days']=len(changes)
        rec['major_revision_days']=len(major)
        rec['max_revision_pct']=round(max_revision,6)
        rec['revision_dates']=';'.join(x['date'] for x in changes)
        rec['new_bars']=len(new_keys-old_keys)
        if major:
            rec['status']='CHANGED_PRICE_BASIS_QUARANTINE'
            rec['new_bars']=0
            return existing,rec,changes
        if missing:
            rec['status']='PARTIAL_FETCH_KEEP_CACHE'
            rec['new_bars']=0
            return existing,rec,changes
        merged={**old_map,**fetched_map}
        save_forward_cache(path,list(merged.values()))
        rec['status']='REFRESH_OK'
        return list(merged.values()),rec,changes
    except Exception as e:
        rec['status']='ERROR_KEEP_CACHE_'+type(e).__name__
        rec['new_bars']=0
        return existing,rec,changes
    finally:
        if temp.exists(): temp.unlink()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--queue',default='reports/v76_paper_trade_queue.csv')
    p.add_argument('--anchor',default='reports/v76_conditional_research_top3.csv')
    p.add_argument('--cache',default='reports/v36_ohlcv_cache')
    p.add_argument('--forward-cache',default='reports/v77_forward_cache')
    p.add_argument('--outdir',default='reports')
    p.add_argument('--fetch',action='store_true',help='Refresh all forward bars every run, not just first session')
    p.add_argument('--source',default='NAVER')
    p.add_argument('--end',default=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat())
    p.add_argument('--max-entry-sessions',type=int,default=3)
    p.add_argument('--fee-bps',type=float,default=15)
    p.add_argument('--slip-bps',type=float,default=10)
    a=p.parse_args()
    if a.max_entry_sessions<1 or a.fee_bps<0 or a.slip_bps<0: p.error('Invalid assumptions')
    date.fromisoformat(a.end)
    if a.end>datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat(): p.error('End date cannot be in the future (KST)')
    outdir=Path(a.outdir);outdir.mkdir(parents=True,exist_ok=True)
    fw=Path(a.forward_cache);fw.mkdir(parents=True,exist_ok=True)
    queue=read_csv(a.queue)
    anchor={r['ticker'].zfill(6):fnum(r.get('close')) for r in read_csv(a.anchor)}
    if not queue: raise SystemExit('Empty v7.6 paper trade queue')
    entries=[];outcomes=[];fetch_log=[];basis_log=[];risk_log=[];revision_log=[]
    for sig in queue:
        ticker=(sig.get('ticker') or '').zfill(6);asof=sig.get('signal_asof','')
        date.fromisoformat(asof)
        original=valid_bars(Path(a.cache)/(ticker+'.csv'))
        extra=valid_bars(fw/(ticker+'.csv'))
        basis_ok,basis_status,asof_close=price_basis_ok(ticker,asof,original,anchor.get(ticker))
        basis_log.append(dict(ticker=ticker,name=sig.get('name',''),asof=asof,reference_close=anchor.get(ticker),historical_close=asof_close,status=basis_status))
        fetch_status='FETCH_DISABLED'
        if a.fetch and basis_ok:
            extra,rec,changes=refresh_forward(ticker,asof,a.end,a.source,fw/(ticker+'.csv'),extra)
            fetch_log.append(rec)
            revision_log.extend(changes)
            fetch_status=rec['status']
            time.sleep(.5)
        else:
            fetch_log.append(dict(ticker=ticker,status=fetch_status,new_bars=0,revised_days=0,major_revision_days=0,max_revision_pct=0.0,missing_existing_days=0))
        merged={r['date']:r for r in original if r['date']<=asof}
        merged.update({r['date']:r for r in extra if asof<r['date']<=a.end})
        forward=sorted((r for r in merged.values() if r['date']>asof),key=lambda r:r['date'])
        quarantine=(not basis_ok or (a.fetch and fetch_status!='REFRESH_OK'))
        if quarantine:
            entry=dict(ticker=ticker,name=sig.get('name',''),signal_asof=asof,fill_date='',fill_price='',exit_date='',exit_price='',exit_reason='',net_return_pct='',bars_after_signal=len(forward),post_fill_bars=0,status='DATA_INTEGRITY_QUARANTINE')
            horizons=[]
        else:
            entry,horizons=process(sig,sorted(merged.values(),key=lambda r:r['date']),asof,a.max_entry_sessions,a.fee_bps,a.slip_bps)
        entries.append(entry);outcomes.extend(horizons)
        first=forward[0] if forward else None
        risk_log.append(dict(ticker=ticker,name=sig.get('name',''),signal_asof=asof,asof_close=asof_close or '',first_forward_date=first['date'] if first else '',gap_open_pct=round((first['open']/asof_close-1)*100,3) if first and asof_close else '',first_day_low_vs_entry_pct=round((first['low']/float(entry['fill_price'])-1)*100,3) if first and entry.get('fill_price') else '',first_day_close_vs_signal_pct=round((first['close']/asof_close-1)*100,3) if first and asof_close else '',latest_forward_date=forward[-1]['date'] if forward else '',forward_sessions=len(forward),fetch_status=fetch_status,entry_status=entry['status']))
    entry_fields=['ticker','name','signal_asof','entry_low','entry_high','stop_reference','target_reference','fill_date','fill_price','exit_date','exit_price','exit_reason','net_return_pct','bars_after_signal','post_fill_bars','status']
    horizon_fields=['ticker','name','fill_date','horizon_sessions','valuation_date','valuation_price','net_return_pct','status']
    write_csv(outdir/'v79_paper_entries.csv',entries,entry_fields)
    write_csv(outdir/'v79_forward_outcomes.csv',outcomes,horizon_fields)
    write_csv(outdir/'v79_forward_risk_audit.csv',risk_log,['ticker','name','signal_asof','asof_close','first_forward_date','gap_open_pct','first_day_low_vs_entry_pct','first_day_close_vs_signal_pct','latest_forward_date','forward_sessions','fetch_status','entry_status'])
    write_csv(outdir/'v79_price_basis_audit.csv',basis_log,['ticker','name','asof','reference_close','historical_close','status'])
    write_csv(outdir/'v79_revision_audit.csv',revision_log,
              ['ticker','date','max_abs_ohlc_revision_pct','close_revision_pct',
               'volume_revision_pct','material_revision','disposition'])
    audit=dict(version='7.9',source='same v7.6 historical WAIT cohort; NOT new market selections',run_kst=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds'),requested_end=a.end,provider='FINANCEDATAREADER_AUTO_BACKEND_UNVERIFIED',provider_request_hint=a.source,signals=len(queue),paper_fills=sum(bool(r['fill_date']) for r in entries),paper_exits=sum(r['status']=='PAPER_EXIT' for r in entries),pending_forward_outcomes=sum(r['status']=='PENDING_FUTURE_SESSIONS' for r in outcomes),quarantined=sum(r['status']=='DATA_INTEGRITY_QUARANTINE' for r in entries),fetch_attempted=a.fetch,fetch_log=fetch_log,revision_rows=len(revision_log),revised_days=sum(r['revised_days'] for r in fetch_log),major_revision_days=sum(r['major_revision_days'] for r in fetch_log),price_basis=basis_log,fee_bps=a.fee_bps,slippage_bps=a.slip_bps,max_entry_sessions=a.max_entry_sessions,real_trading_authorized=False,status='RESEARCH_ONLY_NEVER_TRADE',limitations=['Same historical cohort; not unbiased full-market predictive evaluation','OHLCV cannot establish within-bar touch order; conservative same-session stop model retained','Unverified exchange ticks, latency, liquidity, queue priority, taxation and broker fills','Every observed OHLCV revision is audited; >0.5% OHLC changes are quarantined','Failed, empty, partial or invalid fresh fetches quarantine results rather than present stale cache as fresh', 'Incomplete future sessions are PENDING; not zero-return or fabricated results'])
    (outdir/'v79_forward_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False))

if __name__=='__main__':main()
