"""C3 sector/opportunity research shadow. No orders, no Telegram, no approval."""
import argparse,json,math
from collections import defaultdict
from pathlib import Path

def num(x):
 return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def pct(a,b):
 return 100*(a/b-1) if num(a) and num(b) and b>0 else None
def clamp(v,a=0,b=1): return max(a,min(b,v))
def sector_snapshot(market_rows,diagnostics):
 names={r['ticker']:r.get('sector') for r in diagnostics}
 groups=defaultdict(list)
 for r in market_rows:
  s=names.get(r.get('ticker'))
  if s and num(r.get('turnover_krw')) and num(r.get('open')) and num(r.get('close')) and r['open']>0:
   groups[s].append(r)
 out={}
 for s,rs in groups.items():
  total=sum(r['turnover_krw'] for r in rs)
  breadth=sum(r['close']>r['open'] for r in rs)/len(rs)
  out[s]={'matched_count':len(rs),'turnover_krw':total,'intraday_up_share':round(breadth,4),
    'status':'ONE_DAY_CROSS_SECTION_ONLY_NOT_FUND_FLOW',
    'turnover_share_change_5_10_20':'UNAVAILABLE','investor_net_flow':'UNAVAILABLE'}
 return out
def entry_modes(bars,close,atr):
 if len(bars)<65 or not num(atr) or atr<=0:return []
 bars=sorted(bars,key=lambda x:x['date'])
 if any(not all(num(b.get(k)) and b[k]>0 for k in ('open','high','low','close','volume')) for b in bars):return []
 if pct(bars[-1]['close'],close) is None or abs(pct(bars[-1]['close'],close))>.1:return []
 prev=bars[-21:-1];recent=bars[-6:-1]
 highs=[b['high'] for b in prev];lows=[b['low'] for b in recent]
 ma5=sum(b['close'] for b in bars[-5:])/5
 ma10=sum(b['close'] for b in bars[-10:])/10
 ma20=sum(b['close'] for b in bars[-20:])/20
 volume20=sum(b['volume'] for b in prev)/len(prev)
 support_candidates=[
  ('BREAKOUT_RETEST',max(b['high'] for b in bars[-31:-6]),close>=max(b['high'] for b in bars[-31:-6])*.985),
  ('FIRST_FAST_PULLBACK',ma5,ma5>=ma10>=ma20 and min(lows)<=ma5*1.025),
  ('COMPRESSION_REBREAK',max(b['high'] for b in bars[-11:-1]),(max(highs[-10:])-min(lows))/close<.12 and bars[-1]['volume']>=volume20),
  ('EARLY_TREND_TURN',ma20,ma5>=ma10>=ma20 and bars[-21]['close']<ma20),
  ('NEAR_PRICE_BASE',sorted(lows)[2],sum(abs(x/sorted(lows)[2]-1)<.025 for x in lows)>=2)]
 candidates=[]
 for mode,s,condition in support_candidates:
  if not condition or not num(s) or s<=0 or pct(close,s)>9 or pct(close,s)<-4:continue
  lo=s-.15*atr;hi=s+.3*atr
  stop=min(min(lows),s)-.5*atr
  if stop<=0 or stop>=lo:continue
  risk=pct(hi,stop)
  if risk is None or risk>7:continue
  resist=sorted(set(b['high'] for b in bars[-65:-1] if b['high']>hi*1.02))
  if not resist:continue
  r1=next((x for x in resist if (x-hi)/(hi-stop)>=1.5),None)
  if r1 is None:continue
  rr=(r1-hi)/(hi-stop)
  candidates.append({'mode':mode,'entry_range':[round(lo),round(hi)],'stop':round(stop),
   'resistance1':round(r1),'resistance2':round(resist[-1]),'rr':round(rr,2),
   'risk_pct':round(risk,2),'distance_to_entry_upper_pct':round(max(0,pct(close,hi)),2),
   'second_entry':'NOT_PROPOSED_WITHOUT_INDEPENDENT_SUPPORT'})
 return sorted(candidates,key=lambda x:(x['distance_to_entry_upper_pct'],-x['rr']))
def run(diag,market,histories=None):
 histories=histories or {}
 assert diag['asof']==market['asof']
 sectors=sector_snapshot(market['rows'],diag['rows'])
 results=[]
 for r in diag['rows']:
  p=r.get('observation_audit',{}).get('price',{})
  fin=r.get('financial',{});s=fin.get('statement') or {}
  op=s.get('operating_profit_krw');prev=s.get('previous_comparable_operating_profit_krw')
  rev=s.get('revenue_krw');pr=s.get('previous_comparable_revenue_krw')
  debt=pct(s.get('liabilities_krw'),s.get('equity_krw'))
  fin_score=30*(.4*bool(num(op) and num(prev) and op>prev)+.3*bool(num(rev) and num(pr) and rev>pr)+.3*bool(num(debt) and debt<=200))
  rs=r.get('own_rs20');acc=r.get('rs_accel5')
  tech=20*(.65*clamp(rs/30) if num(rs) else 0)+20*(.35*clamp(acc/8) if num(acc) else 0)
  sec=sectors.get(r.get('sector'),{})
  # Cross-sectional same-day proxy only; missing historical flow gets no invented points.
  sector_score=10*clamp(sec.get('intraday_up_share',0)) + 5*clamp(sec.get('matched_count',0)/10)
  modes=entry_modes(histories.get(r['ticker'],[]),r['close'],p.get('atr14'))
  best=modes[0] if modes else None
  opp=25*(.6*clamp(1-best['distance_to_entry_upper_pct']/8)+.4*clamp(best['rr']/3)) if best else 0
  score=round(fin_score+tech+sector_score+opp,2)
  reasons=[]
  if not best:reasons.append('ENTRY_STRUCTURE_NOT_VERIFIED')
  if fin.get('status')!='VERIFIED':reasons.append('FINANCIAL_PIT_NOT_CERTIFIED')
  if not r.get('liquidity_pass'):reasons.append('LIQUIDITY_FAIL')
  if num(p.get('returns_pct',{}).get('20')) and p['returns_pct']['20']>45:reasons.append('SHORT_TERM_EXTENSION_REVIEW')
  results.append({'ticker':r['ticker'],'name':r['name'],'close':r['close'],'sector':r.get('sector'),
   'score':score,'financial_points':round(fin_score,2),'technical_points':round(tech,2),
   'sector_proxy_points':round(sector_score,2),'opportunity_points':round(opp,2),
   'entry':best,'entry_modes':modes,'flags':reasons,
   'eligible_for_verified_top2':bool(best and r.get('liquidity_pass') and fin.get('status')=='VERIFIED')})
 ranked=sorted(results,key=lambda x:(-x['score'],x['ticker']))
 verified=[x for x in ranked if x['eligible_for_verified_top2']]
 return {'schema':'C3_SECTOR_OPPORTUNITY_SHADOW_V1','asof':diag['asof'],'diagnostic_scope':len(diag['rows']),
 'market_snapshot_scope':len(market['rows']),'sector_proxy':sectors,'ranked_research':ranked,
 'verified_top2':verified[:2],'research_watch_top2':ranked[:2],
 'stage_gate':'HOLD' if len(verified)<2 else 'RESEARCH_ONLY',
 'limits':['134_DIAGNOSTICS_NOT_WHOLE_MARKET','ONE_DAY_SECTOR_PROXY_NOT_FUND_FLOW','PIT_FINANCIAL_UNVERIFIED','REGULAR_PRICE_NOT_CERTIFIED'],
 'current_action':'CASH','buy_approved':False,'orders_enabled':False,'telegram_requests':0}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--diagnostics',required=True);ap.add_argument('--market',required=True);ap.add_argument('--histories');ap.add_argument('--output',required=True)
 a=ap.parse_args();h=json.loads(Path(a.histories).read_text()) if a.histories else {}
 result=run(json.loads(Path(a.diagnostics).read_text()),json.loads(Path(a.market).read_text()),h)
 Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'watch_top2':[x['name'] for x in result['research_watch_top2']],'verified_top2':[x['name'] for x in result['verified_top2']],'gate':result['stage_gate']},ensure_ascii=False))
