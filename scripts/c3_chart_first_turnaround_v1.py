"""Chart-first earnings-turnaround research overlay; never a trading approval."""
import argparse,json,math
from pathlib import Path
def num(x):return isinstance(x,(int,float)) and math.isfinite(x)
def classify(r,day):
    p=r['observation_audit']['price'];f=r.get('financial') or {};s=f.get('statement') or {};m=p['ma'];c=r['close'];atr=p['atr14'];w=r['entry_window']
    out=dict(ticker=r['ticker'],name=r['name'],close=c,status='REJECT',reason='UNQUALIFIED',chart_score=0,earnings_score=0,buy_approved=False,entry_range=None,stop=None,target=None,research_only=True)
    if not r.get('liquidity_pass') or r.get('history_rows',0)<119:return out
    if not num(atr) or atr<=0 or any(not num(m.get(str(n))) for n in (5,10,20,60)):return out
    if not num(r.get('own_rs20')) or not num(r.get('rs_accel5')):return out
    if r['own_rs20']<=0 or r['rs_accel5']<=0 or c<=m['20'] or m['20']<=m['60']:out['reason']='CHART_TREND_FAIL';return out
    ext=(c-m['20'])/atr
    if ext>2.5:out['reason']='PRICE_OVEREXTENDED';return out
    score=30+min(20,r['own_rs20']/4)+min(15,r['rs_accel5']*2)+(10 if m['5']>m['20'] else 0)+(10 if p.get('latest_rvol_vs_prior20') is not None and p['latest_rvol_vs_prior20']>=1.2 else 0)+15*max(0,1-ext/2.5)
    out['chart_score']=round(min(100,score),2)
    if s.get('published_on') and s['published_on']>day:out['reason']='FUTURE_FINANCIAL_REPORT';return out
    equity=s.get('equity_krw');assets=s.get('assets_krw');liabilities=s.get('liabilities_krw')
    if not all(num(x) for x in (equity,assets,liabilities)) or equity<=0 or assets<=0 or liabilities<0:
        out.update(status='RESEARCH_HOLD',reason='BALANCE_SHEET_UNKNOWN');return out
    if liabilities/equity>3:out['reason']='HIGH_LEVERAGE';return out
    rev=s.get('revenue_krw');prev_rev=s.get('previous_comparable_revenue_krw')
    op=s.get('operating_profit_krw');prev_op=s.get('previous_comparable_operating_profit_krw')
    bonus=(8 if num(rev) and num(prev_rev) and prev_rev>0 and rev>prev_rev else 0)+(12 if num(op) and num(prev_op) and op>prev_op else 0)
    out.update(earnings_score=bonus,combined_score=round(.8*out['chart_score']+bonus,2),
        turnaround_loss_making=bool(num(op) and num(prev_op) and op<0 and op>prev_op),
        financial_risk='BALANCE_SHEET_ONLY_AUDIT_AND_LISTING_NOT_CHECKED',
        baseline_entry_status=w['status'],reason='NEW_STRUCTURE_AND_STOP_NOT_CONFIRMED',
        status='CHART_FIRST_WATCH')
    if w['status'] in ('ENTRY_READY','NEAR_ENTRY') and w.get('research_fit_eligible'):
        out.update(status='V4_ENTRY_RESEARCH_REVIEW',reason='EXISTING_V4_GEOMETRY_ONLY')
    return out
def evaluate(doc):
    day=doc['asof'];rows=[classify(r,day) for r in doc['rows']]
    watch=sorted((r for r in rows if r['status'] in ('CHART_FIRST_WATCH','V4_ENTRY_RESEARCH_REVIEW')),key=lambda r:(-r['combined_score'],r['ticker']))
    return dict(schema='C3_CHART_FIRST_TURNAROUND_SHADOW_V1',asof=day,technical_universe=len(rows),
        chart_first_watch_count=len(watch),ranked_watch=watch,all_diagnostics=rows,
        financial_safety_scope='BALANCE_SHEET_ONLY_NOT_AUDIT_OR_LISTING_CERTIFIED',
        earnings_scope='OBSERVED_DISCLOSURES_NOT_FORECAST',buy_approved=False,orders_enabled=False,telegram_requests=0)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    result=evaluate(json.loads(Path(a.input).read_text()));Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'asof':result['asof'],'watch_count':result['chart_first_watch_count']},ensure_ascii=False))
