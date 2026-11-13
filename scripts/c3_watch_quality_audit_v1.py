"""Descriptive audit of unchanged WATCH/ENTRY_FIT ranks. No trading rules."""
import hashlib,json,math,statistics
from collections import Counter
from pathlib import Path

SORT_FIELDS=('original_pit_confirmed','growth_observed','sector_proxy_positive','turnover20','own_rs20','ticker')

def digest(obj):
    return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def price_metrics(bars,day):
    """Every observation ends at the requested completed bar, never at render time."""
    if len(bars)<65 or bars[-1]['date']!=day or any(b['date']>day for b in bars):
        raise ValueError('QUALITY_AUDIT_HISTORY_OR_ASOF_MISMATCH')
    if [b['date'] for b in bars]!=sorted({b['date'] for b in bars}):raise ValueError('QUALITY_AUDIT_DUPLICATE_OR_UNSORTED_BARS')
    c=bars[-1]['close'];ma={str(n):statistics.mean(b['close'] for b in bars[-n:]) for n in (5,10,20,60)}
    tr=[max(bars[i]['high']-bars[i]['low'],abs(bars[i]['high']-bars[i-1]['close']),abs(bars[i]['low']-bars[i-1]['close'])) for i in range(len(bars)-14,len(bars))]
    atr=statistics.mean(tr);v=statistics.mean(b['volume'] for b in bars[-21:-1])
    gaps=[100*(bars[i]['open']/bars[i-1]['close']-1) for i in range(len(bars)-5,len(bars))]
    return dict(asof=day,close=c,returns_pct={str(n):100*(c/bars[-n-1]['close']-1) for n in (5,10,20)},ma=ma,
        ma5_above_ma20_above_ma60=ma['5']>ma['20']>ma['60'],ma20_extension_pct=100*(c/ma['20']-1),
        ma20_extension_atr=(c-ma['20'])/atr if atr else None,atr14=atr,atr14_pct=100*atr/c,
        latest_rvol_vs_prior20=bars[-1]['volume']/v if v else None,
        max_abs_open_gap5_pct=max(map(abs,gaps)),max_positive_open_gap5_pct=max(0,max(gaps)),
        drawdown_from_high20_pct=100*(c/max(b['high'] for b in bars[-20:])-1),
        latest_turnover_krw=bars[-1]['turnover_krw'],risk_use='DESCRIPTIVE_NOT_VALIDATED_OVERHEAT_FILTER',
        actual_intraday_sequence_verified=False)

def finance_metrics(row):
    f=row.get('financial',{});s=f.get('statement') or {}
    def ratio(a,b):
        x,y=s.get(a),s.get(b)
        return 100*x/y if isinstance(x,(int,float)) and isinstance(y,(int,float)) and y>0 else None
    return dict(core_observed_positive=f.get('observed_positive',False),core_required_complete=f.get('required_metrics_complete',False),
        original_pit_confirmed=f.get('confirmed',False),quality_certified=False,
        basis=s.get('basis','UNAVAILABLE'),published_on=s.get('published_on'),receipt_no=s.get('receipt_no'),
        fs_div=s.get('fs_div'),income_period_basis=s.get('income_period_basis'),cashflow_period_basis=s.get('cashflow_period_basis'),
        operating_margin_pct=ratio('operating_profit_krw','revenue_krw'),debt_to_equity_pct=ratio('liabilities_krw','equity_krw'),
        liabilities_to_assets_pct=ratio('liabilities_krw','assets_krw'),
        revenue_growth_pct=ratio('revenue_krw','previous_comparable_revenue_krw')-100 if ratio('revenue_krw','previous_comparable_revenue_krw') is not None else None,
        operating_profit_growth_pct=ratio('operating_profit_krw','previous_comparable_operating_profit_krw')-100 if ratio('operating_profit_krw','previous_comparable_operating_profit_krw') is not None else None,
        revenue_increased=s.get('revenue_increased'),operating_profit_increased=s.get('operating_profit_increased'),
        net_income_status='UNAVAILABLE_IN_EXISTING_EXTRACT',interest_coverage_status='UNAVAILABLE_IN_EXISTING_EXTRACT',
        exact_publication_time_status='DATE_ONLY_NOT_INTRADAY_ATTESTATION',
        missing_quality_evidence=['NET_INCOME','INTEREST_COVERAGE','ORIGINAL_DOCUMENT_PIT','BUSINESS_COMPETITIVENESS'],
        selection_use='CURRENT_API_CORE_FACTS_NOT_CERTIFIED_HIGH_QUALITY_COMPANY')

def sort_key(row):
    f=row['financial']
    return (not f['confirmed'],not f['growth_observed'],not row['sector_proxy_positive'],-row['turnover20'],-row['own_rs20'],row['ticker'])

def prior_reviews(state,day):
    """Use preserved prior reports only, not reconstructed historical selections."""
    result=[]
    for p in sorted((Path(state)/'reports/c3_new_session_v1/reviews').glob('*/*.json')):
        r=json.loads(p.read_text());body=dict(r);expected=body.pop('report_payload_sha256',None)
        if r.get('source_date','9999')>=day or r.get('selection_status')!='RESEARCH_ANALYSIS_COMPLETE':continue
        if expected!=digest(body):raise ValueError('PRIOR_WATCH_REVIEW_HASH_MISMATCH')
        result.append(r)
    return result

def audit(rows,current,pool,fit,day,prior=()):
    """Pool and fit are computed by the pinned original functions before auditing."""
    if any(r.get('source_date','9999')>=day for r in prior):raise ValueError('FUTURE_OR_SAME_DAY_PRIOR_WATCH_REVIEW')
    if [r['ticker'] for r in sorted(pool,key=sort_key)]!=[r['ticker'] for r in pool]:
        raise ValueError('WATCH_SORT_AUDIT_DIVERGED_FROM_PINNED_ENGINE')
    pool_rank={r['ticker']:i for i,r in enumerate(pool,1)};fit_set={r['ticker'] for r in fit}
    previous=max(prior,key=lambda r:(r['source_date'],r['generated_at']),default=None)
    previous_rank={r['ticker']:r.get('rank',i) for i,r in enumerate(previous.get('watch_top2',[]),1)} if previous else {}
    by_pool={r['ticker']:r for r in pool};observations={};reasons=Counter()
    for row in rows:
        t=row['ticker'];q=row['financial'];why=[]
        if not q.get('observed_positive'):why.append('FINANCIAL_UNKNOWN' if not q.get('required_metrics_complete') else 'CORE_FINANCIAL_METRICS_FAIL')
        if not row['momentum_pass']:why.append('RS_OR_ACCELERATION_NOT_POSITIVE')
        if not row['liquidity_pass']:why.append('EXISTING_LIQUIDITY_GATE_FAIL')
        plans=row['range_review']['plans'];best=row['range_review']['best']
        entry_reasons=[]
        if not best:entry_reasons=sorted({p.get('range',{}).get('reason') or p.get('practicality',{}).get('status') or p.get('stop_reliability',{}).get('status') or 'NO_VALID_PLAN' for p in plans}) or ['NO_STRUCTURAL_PLAN']
        if len(current[t])<119:entry_reasons.append('FULL_VISIBLE_MA60_HISTORY_LT_119')
        reasons.update(why+entry_reasons)
        prior_rank=previous_rank.get(t);rank=pool_rank.get(t)
        repeat=bool(prior_rank is not None and rank is not None and rank<=2)
        peer=pool[rank] if rank is not None and rank<len(pool) else None
        key=sort_key(by_pool[t]) if t in by_pool else None
        peer_key=sort_key(peer) if peer else None
        deciding=next((SORT_FIELDS[i] for i in range(6) if key[i]!=peer_key[i]),None) if peer else None
        o=dict(ticker=t,name=row['name'],price=price_metrics(current[t],day),financial=finance_metrics(row),
            score=None,score_basis='DETERMINISTIC_LEXICOGRAPHIC_NO_WEIGHTED_TOTAL',quality_pool_rank=rank,
            previous_watch_day=previous['source_date'] if previous else None,previous_watch_rank=prior_rank,
            watch_rank_change=prior_rank-rank if prior_rank is not None and rank is not None and rank<=2 else None,
            repeated_watch=repeat,deciding_sort_field=deciding,
            repeat_reason=('CURRENT_DAY_'+deciding.upper()+'_PRIORITY_WITHOUT_RETENTION_BONUS') if repeat and deciding else 'CURRENT_DAY_RECOMPUTED_RANK',
            rank_inputs=dict(original_pit_confirmed=q.get('confirmed',False),growth_observed=q.get('growth_observed',False),
                sector_proxy_positive=by_pool[t]['sector_proxy_positive'] if t in by_pool else None,
                turnover20=row['turnover20'],own_rs20=row['own_rs20']),
            watch_eligible=t in by_pool,entry_fit_selected=t in fit_set,watch_fail_reasons=why,entry_fail_reasons=entry_reasons,
            entry_range=[best['range']['low'],best['range']['high']] if best else None,
            original_entry_prices_changed=False,overheat_filter_applied=False,buy_approved=False)
        observations[t]=o
    leaders=[observations[r['ticker']] for r in pool[:10]]
    differences=[]
    for ahead,behind in zip(pool[:9],pool[1:10]):
        a,b=sort_key(ahead),sort_key(behind);first=next((SORT_FIELDS[i] for i in range(6) if a[i]!=b[i]),None)
        differences.append(dict(ahead=ahead['ticker'],behind=behind['ticker'],first_deciding_sort_field=first))
    summaries={}
    for report in prior:
        d=report['source_date']
        if d in summaries and summaries[d]['generated_at']>=report['generated_at']:continue
        entries=[]
        for i,r in enumerate(report.get('watch_top2',[]),1):
            bs=[b for b in current.get(r['ticker'],[]) if b['date']<=d]
            metrics=price_metrics(bs,d) if len(bs)>=65 and bs[-1]['date']==d else None
            if metrics and metrics['close']!=r['close']:raise ValueError('PRIOR_WATCH_CLOSE_DOES_NOT_MATCH_PRESERVED_HISTORY')
            entries.append(dict(ticker=r['ticker'],name=r['name'],rank=r.get('rank',i),close=r['close'],own_rs20=r.get('own_rs20'),
                rs_accel5=r.get('rs_accel5'),turnover20=r.get('turnover20'),price_metrics=metrics,
                original_financial_context_not_backfilled=True))
        summaries[d]=dict(asof=d,generated_at=report['generated_at'],source_run_id=report['source_run_id'],report_hash=report['report_payload_sha256'],watch=entries)
    result=dict(schema='C3_WATCH_QUALITY_AUDIT_V1',asof=day,reviewed_technical=len(rows),quality_pool_count=len(pool),
        original_weighted_score_exists=False,sort_priority=list(SORT_FIELDS),entry_scope='ALL_QUALITY_MOMENTUM_LIQUIDITY_CANDIDATES_NOT_WATCH_TOP2',
        watch_top2=[r['ticker'] for r in pool[:2]],entry_fit_top2=[r['ticker'] for r in fit],
        top10=leaders,adjacent_rank_decisions=differences,observations=observations,prior_dated_watch_reports=list(summaries.values()),
        financial_summary=dict(core_observed_positive=sum(r['financial']['observed_positive'] for r in rows),
            original_pit_confirmed=sum(r['financial']['confirmed'] for r in rows),comprehensive_quality_certified=0,
            missing_net_income=len(rows),missing_interest_coverage=len(rows)),
        failure_reason_counts=dict(reasons),reused_previous_candidates=False,selection_rules_changed=False,
        overheat_thresholds_optimized=False,independent_performance_superiority_proven=False,buy_approved=False)
    result['audit_payload_sha256']=digest(result)
    return result
