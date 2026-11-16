"""Early trend overlay using only as-of daily diagnostic observations; research only."""
import argparse,json,math
from collections import Counter
from pathlib import Path
def finite(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def classify(r):
 p=r['observation_audit']['price'];m=p['ma'];c=r['close'];a=p['atr14'];s=(r.get('financial') or {}).get('statement') or {}
 out=dict(ticker=r['ticker'],name=r['name'],close=c,stage='INSUFFICIENT',score=None,entry_status='WATCH_ONLY',buy_approved=False)
 if not (r.get('liquidity_pass') and r.get('history_rows',0)>=119 and all(finite(x) for x in (c,a,m['20'],m['60'],r.get('own_rs20'),r.get('rs_accel5')))) or a<=0:return out
 ret=p['returns_pct'];r20=ret.get('20');r5=ret.get('5');ext=p['ma20_extension_atr'];ma60ext=100*(c/m['60']-1)
 if not all(finite(x) for x in (r20,r5,ext,ma60ext)):return out
 out.update(return20_pct=round(r20,2),return5_pct=round(r5,2),ma20_extension_atr=round(ext,2),ma60_extension_pct=round(ma60ext,2))
 if c<=m['20'] or c<=m['60'] or r['own_rs20']<=0 or r['rs_accel5']<=0:stage='NOT_UPTREND'
 elif r20>35 and ma60ext<=25 and ext<=1.8:stage='EARLY_BURST_WAIT'
 elif r20>35 or ma60ext>35 or ext>2.2:stage='EXTENDED_OR_LATE'
 elif r5>25 and ma60ext<=25:stage='EARLY_BURST_WAIT'
 elif 0<r20<=25 and ma60ext<=25 and ext<=1.8:stage='EARLY_TREND_CANDIDATE'
 else:stage='TREND_IN_PROGRESS'
 out['stage']=stage
 if stage not in ('EARLY_TREND_CANDIDATE','TREND_IN_PROGRESS'):return out
 eq=s.get('equity_krw');liab=s.get('liabilities_krw');assets=s.get('assets_krw')
 if not all(finite(x) for x in (eq,liab,assets)) or eq<=0 or assets<=0 or liab<0:out['stage']='FINANCIAL_HOLD';return out
 if liab/eq>3:out['stage']='FINANCIAL_RISK';return out
 if s.get('published_on') and s['published_on']>p['asof']:out['stage']='FUTURE_DISCLOSURE_HOLD';return out
 op=s.get('operating_profit_krw');prev=s.get('previous_comparable_operating_profit_krw');rev=s.get('revenue_krw');prevrev=s.get('previous_comparable_revenue_krw')
 bonus=(12 if finite(op) and finite(prev) and op>prev else 0)+(8 if finite(rev) and finite(prevrev) and prevrev>0 and rev>prevrev else 0)
 early=stage=='EARLY_TREND_CANDIDATE'
 score=(35 if early else 15)+min(15,max(0,r['own_rs20'])/5)+min(10,max(0,r['rs_accel5']))+max(0,15-7*max(0,ext))+max(0,10-0.3*max(0,r20))+bonus
 out.update(score=round(score,2),earnings_bonus=bonus,early_priority=early,financial_scope='BALANCE_SHEET_ONLY',entry_status='NEEDS_NEW_PIVOT_AND_V4_STOP',buy_approved=False)
 return out
def evaluate(doc):
 rows=[classify(r) for r in doc['rows']];ranked=sorted((x for x in rows if x['score'] is not None),key=lambda x:(not x['early_priority'],-x['score'],x['ticker']))
 return dict(schema='C3_EARLY_TREND_SHADOW_V1',asof=doc['asof'],total=len(rows),stages=dict(Counter(x['stage'] for x in rows)),ranked=ranked,all_rows=rows,buy_approved=False,orders_enabled=False,telegram_requests=0,warning='Single-day descriptive classification; cannot certify first trend transition without historical prior MA slopes/crossing dates.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args();o=evaluate(json.loads(Path(a.input).read_text()));Path(a.output).write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'stages':o['stages'],'top10':[(x['name'],x['stage']) for x in o['ranked'][:10]]},ensure_ascii=False))
