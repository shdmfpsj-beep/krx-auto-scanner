"""Read-only TOP2 eligibility reranker; never promotes an unverified substitute."""
from copy import deepcopy
from c3_entry_geometry_gate import assess

def select(pool, *, asof, maximum=2, require_market_certification=True):
    """pool must be an independently preserved as-of full-market shortlist.

    Do not infer a substitute from the two already-selected research candidates.
    Return empty slots and CASH if candidate coverage cannot be certified.
    """
    if maximum!=2:raise ValueError('TOP2_ONLY')
    if not isinstance(pool,list):raise ValueError('POOL_MUST_BE_LIST')
    seen=set();audited=[];eligible=[]
    for rank,item in enumerate(pool,1):
        row=deepcopy(item)
        ticker=row.get('ticker')
        if not isinstance(ticker,str) or len(ticker)!=6 or not ticker.isdigit() or ticker in seen:
            raise ValueError('INVALID_OR_DUPLICATE_TICKER')
        seen.add(ticker)
        reasons=[]
        if row.get('source_price_asof')!=asof:reasons.append('ASOF_NOT_CERTIFIED')
        if require_market_certification and row.get('source_regular_only_certified') is not True:
            reasons.append('REGULAR_SESSION_NOT_CERTIFIED')
        if row.get('trade_approved') is not True:
            reasons.append('TRADE_APPROVAL_NOT_VERIFIED')
        review=assess(row,row.get('chart_bars'))
        reasons+=review['reasons']
        record={'ticker':ticker,'name':row.get('name'),'original_rank':rank,
                'eligible':not reasons,'reasons':list(dict.fromkeys(reasons)),
                'geometry':review}
        audited.append(record)
        if not reasons:eligible.append(record)
    # Only preserve input order, which must be the existing verified scoring order.
    selected=eligible[:maximum]
    return {'asof':asof,'selected':selected,'vacancies':maximum-len(selected),
            'audited':audited,'action':'CASH' if len(selected)<maximum else 'ENTRY_WATCH_ONLY',
            'read_only':True,'substitutes_invented':False,
            'pool_coverage_certified':False}  # caller must separately certify full-universe coverage

def review_report(report):
    """Current forward report contains only TOP2; cannot discover other market candidates."""
    rows=report.get('research_top2',[])
    result=select(rows,asof=report['source_price_asof'])
    result['pool_coverage_certified']=False
    result['scope']='EXISTING_TOP2_ONLY_NO_FULL_MARKET_REPLACEMENT'
    result['action']='CASH'
    return result
