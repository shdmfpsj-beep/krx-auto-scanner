"""Archive the real scanner's top20 preliminary ranks; no substitute buy approval."""
import argparse,csv,hashlib,json
from pathlib import Path

def build(preliminary,ranking_status,*,top_n=20):
    if top_n not in (10,20):raise ValueError('TOP_N')
    if ranking_status.get('trade_approvals')!=0:raise ValueError('TRADING_STATUS_NOT_SAFE')
    if ranking_status.get('ranked_rows',0)<top_n:raise ValueError('INSUFFICIENT_RANKED_ROWS')
    if len(preliminary)!=ranking_status['ranked_rows']:raise ValueError('RANKING_COUNT_MISMATCH')
    if len({r['ticker'] for r in preliminary})!=len(preliminary):raise ValueError('DUPLICATE_TICKER')
    days={r['latest_date'] for r in preliminary}
    if len(days)!=1:raise ValueError('MIXED_DATES')
    asof=days.pop()
    if not asof or len(asof)!=10:raise ValueError('INVALID_ASOF')
    # Retain original rank order, even when preliminary instrument classification is UNKNOWN.
    candidates=[]
    for i,r in enumerate(preliminary[:top_n],1):
        if not (len(r['ticker'])==6 and r['ticker'].isdigit()):raise ValueError('BAD_TICKER')
        candidates.append({'rank':i,'ticker':r['ticker'],'name':r['name'],
            'price_asof':asof,'close_reference':r['close_reference'],
            'preliminary_score':r['c3_preliminary_score'],'instrument_type':r['instrument_type'],
            'eligibility':r['eligibility'],'warnings':r['warnings'],
            'turnover_source':r['turnover_source'],
            'entry_geometry_status':'NOT_COMPUTED',
            'fundamentals_status':'NOT_VERIFIED','trade_approved':False})
    return {'schema':'C3_REAL_SCAN_PRELIMINARY_TOP20_V1','asof':asof,
            'source_ranked_rows':len(preliminary),'top_n':top_n,
            'source_sha256':hashlib.sha256(json.dumps(preliminary,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
            'candidates':candidates,'candidate_coverage':'PRELIMINARY_RANKING_NOT_VERIFIED_FULL_MARKET',
            'entry_eligible_top2':[],'vacancies':2,'current_action':'CASH',
            'trade_approved':False,'orders_enabled':False}

def run(source,status,out):
    with Path(source).open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    result=build(rows,json.loads(Path(status).read_text(encoding='utf-8')))
    dest=Path(out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('C3_REAL_SCAN_TOP20 '+json.dumps({'asof':result['asof'],'rows':result['source_ranked_rows'],
         'preserved':len(result['candidates']),'trade_approved':False},ensure_ascii=False))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--status',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();run(a.source,a.status,a.out)
