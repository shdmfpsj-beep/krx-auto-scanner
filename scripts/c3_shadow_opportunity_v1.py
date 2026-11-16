"""Research-only shadow opportunities from the Nov16 134-stock diagnostics.

WATCH is never an executable entry: original V4 pivot, stop and RR must pass
before any candidate can be promoted. This module never edits the ledger.
"""
import argparse,json,math
from collections import Counter
from pathlib import Path

def classify(row):
    p=row['observation_audit']['price'];w=row['entry_window'];f=row['financial']
    close=float(row['close']);atr=float(p['atr14']);ma=p['ma']
    result=dict(ticker=row['ticker'],name=row['name'],asof=w['asof'],
        baseline_status=w['status'],status='NO_SHADOW_SETUP',reason='NOT_QUALIFIED',
        buy_approved=False,research_only=True,entry_range=None,stop=None,target=None,rr=None)
    if not (f.get('required_metrics_complete') and f.get('observed_positive')
            and row['momentum_pass'] and row['liquidity_pass']):return result
    if w['status'] not in ('MISSED_ENTRY','WAIT_PULLBACK','OVEREXTENDED'):return result
    if not (math.isfinite(atr) and atr>0 and all(math.isfinite(float(ma[str(n)])) for n in (5,10,20,60))):return result
    if not (ma['5']>ma['20']>ma['60'] and close>ma['20']):
        result['reason']='TREND_NOT_CONFIRMED';return result
    if (close-ma['20'])/atr>1.6:
        result['reason']='MA20_EXTENSION_TOO_LARGE';return result
    distances={str(n):abs(close-ma[str(n)])/atr for n in (5,10)}
    support=min(distances,key=distances.get)
    if distances[support]>.45 or close<ma[support]:
        result['reason']='NO_NEAR_MA_SUPPORT';return result
    result.update(status='WATCH_NEW_SUPPORT_CONFIRMATION',
        reason='MA_SUPPORT_PROXIMITY_NEEDS_NEXT_CONFIRMED_PIVOT',
        support_reference='MA'+support,reference_ma=round(ma[support],4),
        proximity_atr=round(distances[support],4),
        ma20_extension_atr=round((close-ma['20'])/atr,4),
        required_next_steps=['CONFIRM_NEW_PIVOT_AFTER_PRIOR_SETUP','V4_STRUCTURAL_STOP',
                             'V4_NET_RR','NO_CHASE_IF_PRICE_LEAVES_RANGE'])
    return result

def evaluate(doc):
    rows=doc['rows'];out=[classify(r) for r in rows]
    return dict(schema='C3_SHADOW_OPPORTUNITY_V1',
        asof=rows[0]['entry_window']['asof'] if rows else None,
        reviewed=len(rows),
        baseline_entry_fit=sum(r['entry_window']['research_fit_eligible'] for r in rows),
        statuses=dict(Counter(x['status'] for x in out)),
        watch=[x for x in out if x['status']=='WATCH_NEW_SUPPORT_CONFIRMATION'],
        shadow_trade_eligible=0,buy_approved=False,orders_enabled=False,
        policy='RESEARCH_WATCH_ONLY_NO_AUTO_PROMOTION_NO_UNVALIDATED_STOP')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
    result=evaluate(json.loads(Path(a.input).read_text()))
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'asof':result['asof'],'watch':[x['name'] for x in result['watch']]},ensure_ascii=False))
