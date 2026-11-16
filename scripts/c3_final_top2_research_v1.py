"""Final C3 research decision overlay. No unverified entry, orders or Telegram."""
import argparse,json,math
from pathlib import Path
def ok(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def pct(a,b):return 100*(a/b-1) if ok(a) and ok(b) and b>0 else None
def evaluate_one(r,history=None):
 p=r['observation_audit']['price'];c=r['close'];a=p.get('atr14');m=p.get('ma',{})
 o=dict(ticker=r['ticker'],name=r['name'],close=c,stage='DATA_HOLD',reason='LONG_HISTORY_REQUIRED',entry_range=None,stop=None,target1=None,target2=None,rr=None,entry_mode=None,score=None,buy_approved=False,research_only=True)
 if not r.get('liquidity_pass') or not ok(c) or not ok(a) or a<=0:return o
 if not history or len(history)<201:return o
 bars=sorted(history,key=lambda b:b['date'])
 if len({b['date'] for b in bars})!=len(bars) or bars[-1]['date']!=p['asof'] or any(not all(ok(b.get(k)) and b[k]>0 for k in ('high','low','close')) or b['low']>b['close'] or b['close']>b['high'] for b in bars):return o
 closes=[b['close'] for b in bars]
 if abs(closes[-1]/c-1)>0.001:return o
 r60=pct(c,closes[-61]);r120=pct(c,closes[-121]);r200=pct(c,closes[-201]);from_low=pct(c,min(closes[-201:]))
 o.update(return60_pct=r60,return120_pct=r120,return200_pct=r200,rise_from_200day_low_pct=from_low)
 # Long-run gate precedes short-term momentum: prevents Tiger Electric-type misclassification.
 if r120>65 or r200>100 or from_low>120:
  o.update(stage='MATURE_RUN',reason='LONG_RUN_EXTENSION');return o
 if not all(ok(m.get(k)) for k in ('20','60')) or c<=m['20'] or c<=m['60'] or r.get('own_rs20',0)<=0 or r.get('rs_accel5',0)<=0:
  o.update(stage='NOT_UPTREND',reason='TREND_NOT_CONFIRMED');return o
 if r60>45 or r120>50:
  o.update(stage='TREND_IN_PROGRESS',reason='EARLY_STAGE_NOT_CONFIRMED');return o
 s=(r.get('financial') or {}).get('statement') or {}
 if s.get('published_on') and s['published_on']>p['asof']:
  o.update(stage='FINANCIAL_HOLD',reason='FUTURE_DISCLOSURE');return o
 eq,assets,liab=(s.get(k) for k in ('equity_krw','assets_krw','liabilities_krw'))
 if not all(ok(x) for x in (eq,assets,liab)) or eq<=0 or assets<=0 or liab<0 or liab/eq>3:
  o.update(stage='FINANCIAL_HOLD',reason='BALANCE_SHEET_NOT_CLEARED');return o
 o.update(stage='EARLY_TREND_RESEARCH',reason='NEAR_PRICE_STRUCTURE_NOT_VALIDATED')
 # Use only completed as-of bars. A fresh base needs at least 3 recent independent touches.
 recent=bars[-11:];lows=sorted(b['low'] for b in recent[:-1]);support=lows[2]
 touches=sum(abs(b['low']/support-1)<=.025 for b in recent[:-1])
 if touches<3:return o
 # Reject a price level too far below close; do not manufacture a deep pullback.
 if pct(c,support)>7:return o
 # Low of observed base; conservative stop, below support by >=0.5 ATR.
 stop=min(b['low'] for b in recent[:-1])-.5*a
 if stop<=0:return o
 entry_lo=max(support,c-.4*a);entry_hi=min(c+.15*a,support+.5*a)
 if not 0<stop<entry_lo<=entry_hi:return o
 # Resistance must be an observed high BEFORE as-of, above proposed entry.
 resist=sorted({b['high'] for b in bars[-61:-1] if b['high']>entry_hi*1.02})
 if not resist:return o
 t1=resist[0];t2=resist[-1]
 risk=(entry_hi-stop)/entry_hi
 rr=(t1-entry_hi)/(entry_hi-stop)
 if risk>.055 or rr<1.8:
  o.update(reason='RISK_OR_REWARD_FAIL',risk_pct=round(100*risk,2),rr=round(rr,2));return o
 op=s.get('operating_profit_krw');prev=s.get('previous_comparable_operating_profit_krw')
 bonus=10 if ok(op) and ok(prev) and op>prev else 0
 score=max(0,70-0.3*max(0,r120)-0.15*max(0,from_low))+bonus+min(10,rr)
 o.update(stage='RESEARCH_ENTRY_READY',reason='ASOF_BASE_RESEARCH_ONLY',entry_range=[round(entry_lo),round(entry_hi)],stop=round(stop),target1=round(t1),target2=round(t2),rr=round(rr,2),risk_pct=round(100*risk,2),entry_mode='CURRENT_PRICE_BASE',score=round(score,2))
 return o
def evaluate(doc,histories):
 rows=[evaluate_one(r,histories.get(r['ticker'])) for r in doc['rows']]
 ranked=sorted((r for r in rows if r['stage']=='RESEARCH_ENTRY_READY'),key=lambda r:(-r['score'],r['ticker']))
 return dict(schema='C3_FINAL_TOP2_RESEARCH_V1',asof=doc['asof'],top2=ranked[:2],candidate_count=len(ranked),all_rows=rows,current_action='CASH',buy_approved=False,orders_enabled=False,telegram_requests=0,warning='Historical bars must be adjusted consistently and authenticated; observed base heuristic is not V4-certified.')
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--histories',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
 d=json.loads(Path(a.input).read_text());h=json.loads(Path(a.histories).read_text());o=evaluate(d,h);Path(a.output).write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'asof':o['asof'],'research_top2':[x['name'] for x in o['top2']],'candidate_count':o['candidate_count']},ensure_ascii=False))
