#!/usr/bin/env python3
"""Paired EOD-stop vs intraday-stop diagnostic using identical hypothetical D+2 entries.

Source cohort was selected 2026-10-29 (survivorship bias). No brokerage fills,
official regular-only scope, forward profit proof or trade approval.
"""
import argparse,csv,hashlib,json
from pathlib import Path
import pandas as pd
from c3_historical_reclaim_diagnostic_v1 import read_artifact

SCHEMA='C3_PAIRED_CLOSE_STOP_DIAGNOSTIC_V1_RESEARCH_NO_BUY'
COST=.0065

def closing_stop_return(opens,highs,lows,closes,entry_i,entry,stop,target,hold):
    # Price <= 0 indicates no executable session, e.g. a suspended symbol.
    if any(opens[j]<=0 or highs[j]<=0 or lows[j]<=0 or closes[j]<=0
        for j in range(entry_i,entry_i+hold)):
        raise ValueError('UNTRADEABLE_ZERO_OHLC_IN_HOLD')
    for j in range(entry_i,entry_i+hold):
        # On a candle with both target touch and closing stop breach, assign
        # the adverse exit (cannot reconstruct intraday order from daily data).
        if closes[j]<stop:
            if j==entry_i+hold-1:
                exit_price=closes[j];reason='FINAL_DAY_CLOSE_STOP'
            else:
                if opens[j+1]<=0:raise ValueError('NEXT_OPEN_UNTRADEABLE')
                exit_price=opens[j+1];reason='CLOSE_STOP_NEXT_OPEN_GAP'
            break
        if highs[j]>=target:
            exit_price=target;reason='TARGET_WHILE_CLOSE_HOLDS'
            break
    else:
        exit_price=closes[entry_i+hold-1];reason='TIME_EXIT'
    pct=100*(exit_price/entry-1-COST)
    return dict(close_stop_net_pct=round(pct,4),
      close_stop_exit_reason=reason,close_stop_win=pct>0)

def run(source,diagnostic_csv,diagnostic_status,output):
    panel,meta,_=read_artifact(source)
    info=json.loads(Path(diagnostic_status).read_text(encoding='utf-8'))
    raw=Path(diagnostic_csv).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=info['csv_sha256']:
        raise ValueError('PRIOR_DIAGNOSTIC_DIGEST_MISMATCH')
    if (info['schema']!='C3_SELECTED_36_HISTORICAL_RECLAIM_DIAGNOSTIC_V1_NO_BUY'
        or str(info['source_run_id'])!=str(meta['run_context']['run_id'])
        or not info['major_bias']):
        raise ValueError('HISTORICAL_SOURCE_OR_BIAS_STATUS_INVALID')
    prior=pd.read_csv(diagnostic_csv,dtype={'ticker':str})
    by={t:g.sort_values('date').reset_index(drop=True)
        for t,g in panel.groupby('ticker')}
    rows=[]
    for x in prior.itertuples(index=False):
        g=by[x.ticker]
        matches=g.index[g.date==x.d2_date].tolist()
        if len(matches)!=1:raise ValueError('D2_DATE_MISSING_OR_DUPLICATED')
        j=matches[0];hold=int(x.hold)
        if j+hold>len(g):raise ValueError('FUTURE_HORIZON_UNAVAILABLE')
        entry=float(x.entry_open_d2)
        if entry!=float(g.loc[j,'open']):
            raise ValueError('ENTRY_OPEN_SOURCE_CHANGED')
        result=closing_stop_return(
          g.open.to_numpy(float),g.high.to_numpy(float),
          g.low.to_numpy(float),g.close.to_numpy(float),
          j,entry,float(x.stop),float(x.first_resistance),hold)
        rows.append(dict(ticker=x.ticker,name=x.name,
          signal_date=x.signal_date,entry_date=x.d2_date,
          partition=x.market_partition,policy=x.policy,
          holding_sessions=hold,stop=float(x.stop),
          first_resistance=float(x.first_resistance),entry_open=entry,
          intraday_stop_net_pct=float(x.net_pct),
          intraday_exit_reason=x.exit_reason,**result,
          assumed_transaction_cost_pct=100*COST,
          source_regular_only_certified=False,broker_fill=False,
          trade_approved=False,orders_enabled=False))
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    dest=out/'c3_close_stop_comparison_v1.csv'
    with dest.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summaries=[]
    for policy in ('CONTACT_ONLY','MODERATE_RECOVERY','STRICT_RECOVERY'):
        for hold in (5,10):
            for part in ('EARLY','LATE','ALL'):
                xs=[x for x in rows if x['policy']==policy
                  and x['holding_sessions']==hold
                  and (part=='ALL' or x['partition']==part)]
                n=len(xs)
                a=[x['intraday_stop_net_pct'] for x in xs]
                b=[x['close_stop_net_pct'] for x in xs]
                summaries.append(dict(policy=policy,hold=hold,partition=part,
                  paired_cases=n,
                  intraday_stop_mean_pct=round(sum(a)/n,3) if n else None,
                  close_stop_mean_pct=round(sum(b)/n,3) if n else None,
                  close_minus_intraday_pct_points=round((sum(b)-sum(a))/n,3) if n else None,
                  close_stop_win_pct=round(100*sum(v>0 for v in b)/n,2) if n else None,
                  close_stop_worst_pct=round(min(b),3) if n else None,
                  close_stop_overnight_gap_exit_count=sum(
                    x['close_stop_exit_reason']=='CLOSE_STOP_NEXT_OPEN_GAP' for x in xs)))
    status=dict(schema=SCHEMA,asof_original='2026-10-30',
      source_run_id=meta['run_context']['run_id'],
      identical_paper_entries=True,simulated_stops_only=True,
      hindsight_selected_universe_bias=True,source_regular_only_certified=False,
      actual_fills=0,trade_approved=False,orders_enabled=False,
      total_rows=len(rows),results=summaries,
      csv_sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
    (out/'c3_close_stop_comparison_v1_status.json').write_text(
      json.dumps(status,ensure_ascii=False,indent=2,allow_nan=False)+'\n',
      encoding='utf-8')
    return status

if __name__=='__main__':
    a=argparse.ArgumentParser()
    a.add_argument('--input',required=True)
    a.add_argument('--diagnostic-csv',required=True)
    a.add_argument('--diagnostic-status',required=True)
    a.add_argument('--output',required=True)
    x=a.parse_args();z=run(x.input,x.diagnostic_csv,x.diagnostic_status,x.output)
    print(json.dumps([r for r in z['results'] if r['partition']=='ALL'],
      ensure_ascii=False,indent=2))
