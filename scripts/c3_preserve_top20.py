"""C3 read-only shortlist preservation. Input is a dated whole-market research snapshot, not TOP2."""
import hashlib,json
from pathlib import Path
from c3_eligible_top2_rerank import select

def preserve(snapshot,*,top_n=20):
    if top_n not in (10,20):raise ValueError('TOP_N_MUST_BE_10_OR_20')
    if snapshot.get('schema')!='C3_CURRENT_CANDIDATES_V7':raise ValueError('UNSUPPORTED_SOURCE_SCHEMA')
    asof=snapshot.get('price_asof')
    pool=snapshot.get('candidate_pool')
    if not isinstance(pool,list) or not isinstance(asof,str):raise ValueError('SOURCE_POOL_MISSING')
    if snapshot.get('orders_enabled') is not False or snapshot.get('current_action')!='CASH':
        raise ValueError('RESEARCH_ONLY_SOURCE_REQUIRED')
    if snapshot.get('b_native_index_candidates')!=len(pool):raise ValueError('POOL_COUNT_MISMATCH')
    if not isinstance(snapshot.get('currently_analyzable'),int) or snapshot['currently_analyzable']<len(pool):
        raise ValueError('UNIVERSE_COVERAGE_MISSING')
    if any(r.get('price_asof')!=asof for r in pool):raise ValueError('MIXED_PRICE_DATES')
    ranked=pool[:top_n]
    seen=set();out=[]
    for i,r in enumerate(ranked,1):
        t=r.get('ticker')
        if not isinstance(t,str) or len(t)!=6 or not t.isdigit() or t in seen:raise ValueError('DUPLICATE_OR_INVALID_TICKER')
        seen.add(t)
        out.append({'rank':i,'ticker':t,'name':r.get('name'),'price_asof':asof,
                    'close':r.get('close'),'rs20':r.get('rs20'),'turnover20':r.get('turnover20'),
                    'market':r.get('market'),'industry':r.get('industry'),
                    'entry_plan_status':'NOT_EVALUATED_NO_HISTORICAL_BARS',
                    'buy_approved':False,'trade_approved':False})
    digest=hashlib.sha256(json.dumps(snapshot,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return {'schema':'C3_PRESERVED_SHORTLIST_V1','asof':asof,'source_schema':snapshot['schema'],
            'source_sha256':digest,'source_pool_count':len(pool),'analyzable_count':snapshot['currently_analyzable'],
            'top_n':top_n,'candidates':out,'approval_state':'RESEARCH_ONLY','orders_enabled':False,
            'full_market_certified':False,'reason':'SOURCE_HAS_NO_INDEPENDENT_REGULAR_SESSION_CERTIFICATION',
            'selected_top2':[],'current_action':'CASH'}

def from_file(source,destination,top_n=20):
    obj=json.loads(Path(source).read_text(encoding='utf-8'))
    result=preserve(obj,top_n=top_n)
    target=Path(destination);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True);p.add_argument('--top-n',type=int,default=20)
    a=p.parse_args();print(json.dumps(from_file(a.source,a.out,a.top_n),ensure_ascii=False))
