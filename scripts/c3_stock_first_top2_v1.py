"""C3 stock-first TOP2: selection independent of entry readiness. Research-only."""
import argparse,json
from pathlib import Path
from c3_final_top2_research_v1 import evaluate_one,ok
def choose(doc,histories):
 rows=[]
 for r in doc['rows']:
  timing=evaluate_one(r,histories.get(r['ticker']))
  p=r.get('observation_audit',{}).get('price',{})
  s=(r.get('financial') or {}).get('statement') or {}
  o=dict(timing,selection_score=None,selection_status='NOT_SELECTED',timing_status='UNVERIFIED',buy_approved=False)
  # The long-history and balance-sheet gates are required, but entry geometry is NOT.
  if timing['stage'] in ('DATA_HOLD','MATURE_RUN','NOT_UPTREND','TREND_IN_PROGRESS','FINANCIAL_HOLD'):
   o['selection_reason']=timing['reason'];rows.append(o);continue
  if timing['stage'] not in ('EARLY_TREND_RESEARCH','RESEARCH_ENTRY_READY'):
   rows.append(o);continue
  r120=timing['return120_pct'];from_low=timing['rise_from_200day_low_pct']
  op=s.get('operating_profit_krw');prev=s.get('previous_comparable_operating_profit_krw')
  rev=s.get('revenue_krw');prevrev=s.get('previous_comparable_revenue_krw')
  earnings=(12 if ok(op) and ok(prev) and op>prev else 0)+(8 if ok(rev) and ok(prevrev) and prevrev>0 and rev>prevrev else 0)
  rs=r.get('own_rs20',0);acc=r.get('rs_accel5',0)
  score=45+min(15,max(0,rs)/5)+min(10,max(0,acc))+earnings-max(0,r120-20)*.25-max(0,from_low-50)*.15
  o.update(selection_score=round(score,2),selection_status='QUALITY_CANDIDATE',selection_reason='TREND_AND_FINANCIAL_SCREEN_PASSED',earnings_bonus=earnings,
   timing_status='CURRENT_PRICE_RESEARCH_RANGE' if timing['stage']=='RESEARCH_ENTRY_READY' else 'WAIT_STRUCTURE_VALIDATION')
  rows.append(o)
 ranked=sorted((x for x in rows if x['selection_status']=='QUALITY_CANDIDATE'),key=lambda x:(-x['selection_score'],x['ticker']))
 for x in ranked[:2]:x['selection_status']='TOP2_STOCK'
 return dict(schema='C3_STOCK_FIRST_TOP2_SHADOW_V1',asof=doc['asof'],top2=ranked[:2],quality_candidate_count=len(ranked),all_rows=rows,
  selection_policy='QUALITY_FIRST_TIMING_SEPARATE',current_action='CASH',buy_approved=False,orders_enabled=False,telegram_requests=0)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--histories',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
 o=choose(json.loads(Path(a.input).read_text()),json.loads(Path(a.histories).read_text()))
 Path(a.output).write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'top2':[r['name'] for r in o['top2']],'quality_candidates':o['quality_candidate_count']},ensure_ascii=False))
