"""Read-only C3 entry-geometry gate; never changes scores, registrations or orders."""
import math

MAX_ENTRY_PREMIUM_PCT=5.0  # research hypothesis, not backtested
MIN_R1_REWARD_RISK=1.5     # research hypothesis, not backtested
HOT_5D_RETURN_PCT=25.0     # review flag only
HOT_10D_RETURN_PCT=40.0    # review flag only

def assess(row, bars=None):
    p=((row.get('entry_plans') or {}).get('A_SUPPORT_LIMIT') or {}).get('plan')
    close=row.get('reference_close',row.get('close'))
    reasons=[];metrics={}
    if not isinstance(close,(int,float)) or not math.isfinite(close) or close<=0:
        return {'status':'CASH','eligible':False,'reasons':['REFERENCE_CLOSE_MISSING'],'metrics':metrics}
    if not p or not all(isinstance(p.get(k),(int,float)) for k in ('low','high','stop')):
        return {'status':'CASH','eligible':False,'reasons':['ENTRY_PLAN_INCOMPLETE'],'metrics':metrics}
    low,high,stop=map(float,(p['low'],p['high'],p['stop']))
    if not 0<stop<low<=high:
        reasons.append('INVALID_ENTRY_GEOMETRY')
    premium=100*(close/high-1)
    metrics['premium_over_entry_high_pct']=round(premium,2)
    if premium>MAX_ENTRY_PREMIUM_PCT:reasons.append('CHASE_ENTRY_PREMIUM_OVER_5PCT')
    if p.get('resistance') is None:
        reasons.append('FIRST_RESISTANCE_UNVERIFIED')
    else:
        resistance=float(p['resistance'])
        if resistance<=high:reasons.append('FIRST_RESISTANCE_NOT_ABOVE_ENTRY')
        else:
            rr=(resistance-high)/(high-stop)
            metrics['entry_high_r1_reward_risk']=round(rr,3)
            if rr<MIN_R1_REWARD_RISK:reasons.append('ENTRY_REWARD_RISK_BELOW_1_5')
    if bars:
        closes=[float(x['close']) for x in bars]
        if len(closes)>=11 and closes[-1]==close:
            ret5=100*(close/closes[-6]-1)
            ret10=100*(close/closes[-11]-1)
            metrics.update(return5_pct=round(ret5,2),return10_pct=round(ret10,2))
            if ret5>HOT_5D_RETURN_PCT or ret10>HOT_10D_RETURN_PCT:
                reasons.append('RAPID_RISE_REVIEW_REQUIRED')
        else:reasons.append('MOMENTUM_HISTORY_NOT_VERIFIED')
    return {'status':'CASH' if reasons else 'ENTRY_WATCH_ONLY','eligible':not reasons,'reasons':reasons,'metrics':metrics,
            'thresholds_status':'RESEARCH_PROVISIONAL_NOT_BACKTESTED'}

def annotate(report):
    for r in report.get('research_top2',[]):
        r['entry_geometry_review']=assess(r,r.get('chart_bars'))
    return report
