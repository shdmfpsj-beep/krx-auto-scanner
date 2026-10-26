#!/usr/bin/env python3
"""Exploratory stop-only sensitivity on fixed D-ranked choices; no new alpha claim."""
import argparse
import itertools
from pathlib import Path
from c3_event_replay_v637 import Policy,BASE_COST,STRESS_COST,confirmed_daily_stop,replay
from c3_research_v637 import load_data,select_D,metrics,csv,dump,RANKS


def run(source,candidates,eligibility,out):
    rows,prices,hist,sessions,bench,hashes=load_data(source,candidates,eligibility)
    stats=[];evidence=[]
    for rank in RANKS:
        chosen=select_D(rows,rank)
        for r in chosen:
            d=r['asof'];h=[b for b in hist[r['ticker']] if b['date']<=d]
            stop=confirmed_daily_stop(h,r['atr14'])
            evidence.append(dict(rank=rank,asof=d,ticker=r['ticker'],original_stop=r['stopD'],
                                 confirmed_stop=stop['stop'] if stop else None,
                                 pivot_date=stop['pivot_date'] if stop else None,
                                 confirmation_date=stop['confirmation_date'] if stop else None))
            r['requires_confirmed_pivot']=True;r['confirmed_pivot_evidence']=stop
            if stop:r['stopD']=stop['stop']
        for en,ex,costs in itertools.product(('OPEN_CAPPED','RETEST_2D'),
                          ('LEGACY_TRAIL7_D12','STRUCT_ATR_D12'),(BASE_COST,STRESS_COST)):
            p=Policy(entry=en,exit=ex)
            rr=replay(sessions,prices,chosen,p,costs)
            stats.append(dict(rank=rank,**metrics(rr)))
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    csv(out/'confirmed_pivot_stop_sensitivity_16.csv',stats)
    csv(out/'confirmed_pivot_D_evidence.csv',evidence)
    dump(out/'structure_experiment_disclosure.json',dict(
        adaptation_after_initial_1404_replays=True,
        purpose='Test whether the rolling-3-day low proxy drives apparent performance.',
        selection_D_rank_kept_fixed=True,stop_only_changed=True,
        confirmed_pivot_2_left_2_right=True,independent_forward_evidence=False,
        does_not_validate_chart_context_or_actual_fills=True,
        trade_approved=False,orders_enabled=False))
    return stats


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source-zip','candidates','eligibility-csv','out'):p.add_argument('--'+n,required=True)
    a=p.parse_args();r=run(a.source_zip,a.candidates,a.eligibility_csv,a.out)
    import pandas as pd
    print(pd.DataFrame(r)[['rank','entry','exit','cost_pct','closed_trades','account_roi_pct','daily_liquidation_mdd_pct']].to_string(index=False))
