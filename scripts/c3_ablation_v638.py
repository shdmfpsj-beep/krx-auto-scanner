#!/usr/bin/env python3
"""Controlled old-cohort ablation; keep exact D choices, capital and exit fixed."""
import argparse,itertools
from pathlib import Path
import c3_event_replay_v637 as old
import c3_execution_v638 as new
from c3_research_v637 import load_data,select_D,metrics,csv,dump


def run(source,candidates,eligibility,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    dump(out/'ablation_registry.json',dict(
        fixed_source='v633 NEAR60 snapshot-cleaned 169 signals / 68 D groups',
        D_choices_fixed=True,capital_fixed=1e6,account_risk_fixed=.01,
        entry_cap_fixed='D close minus .25 D ATR',exit_fixed='profit-activated ATR to day12',
        stop_definitions=['ROLLING3','V637_CONFIRMED_D_ATR','V638_UNBROKEN_FROZEN_BUFFER'],
        execution_definitions=['V637_POST_OPEN_GAP_PROXY','V638_PRECOMMITTED_RESTING'],
        cost_scenarios=[.65,.95],design_count=24,not_independent_forward_evidence=True))
    pool,prices,hist,sessions,bench,hashes=load_data(source,candidates,eligibility)
    rows=[]
    for rank in ('V632_BASE','BALANCED_LEADER'):
        fixed=select_D(pool,rank)
        for definition in ('ROLLING3','V637_CONFIRMED_D_ATR','V638_UNBROKEN_FROZEN_BUFFER'):
            selected=[]
            for source_row in fixed:
                r=dict(source_row)
                if definition!='ROLLING3':
                    h=[b for b in hist[r['ticker']] if b['date']<=r['asof']]
                    pivot=(old.confirmed_daily_stop(h,r['atr14']) if definition=='V637_CONFIRMED_D_ATR'
                           else new.unbroken_daily_stop(h))
                    r['requires_confirmed_pivot']=True;r['confirmed_pivot_evidence']=pivot
                    if pivot:r['stopD']=pivot['stop']
                selected.append(r)
            for style,costs in itertools.product(('V637_POST_OPEN_GAP_PROXY','V638_PRECOMMITTED_RESTING'),
                                                 (old.BASE_COST,old.STRESS_COST)):
                if style=='V637_POST_OPEN_GAP_PROXY':
                    rr=old.replay(sessions,prices,selected,old.Policy(entry='RETEST_2D'),costs)
                else:rr=new.replay(sessions,prices,selected,new.Policy(),costs)
                rows.append(dict(rank=rank,stop_definition=definition,execution_style=style,**metrics(rr)))
    csv(out/'controlled_old_cohort_ablation_24.csv',rows)
    return rows


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source-zip','candidates','eligibility-csv','out'):p.add_argument('--'+n,required=True)
    a=p.parse_args();r=run(a.source_zip,a.candidates,a.eligibility_csv,a.out)
    import pandas as pd
    print(pd.DataFrame(r)[['rank','stop_definition','execution_style','cost_pct','closed_trades','account_roi_pct']].to_string(index=False))
