#!/usr/bin/env python3
"""v9.5 conservative, point-in-time *company guidance* revision research.

Inputs are company filings/explicitly reviewed figures, not analyst-consensus data.
Output NEVER approves strict PIT, generates orders, or claims investment success.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
from collections import defaultdict, Counter
from datetime import date
from pathlib import Path
from decimal import Decimal, InvalidOperation
import exchange_calendars as xcals

CANDIDATE_COLS = ['ticker', 'signal_date', 'signal_score', 'selection_status',
                  'forward_event_count', 'fresh_nonamend_event_count', 'forecast_title_count',
                  'title_only', 'quantitative_revision_count', 'best_guidance_change_pct',
                  'guidance_direction', 'evidence_level', 'reason', 'strict_pit_approved']
REVISION_COLS = ['ticker', 'signal_date', 'metric', 'fiscal_period', 'fs_div', 'entity_scope',
                 'previous_receipt', 'new_receipt', 'previous_first_usable_session',
                 'new_first_usable_session', 'previous_value_krw', 'new_value_krw',
                 'change_krw', 'change_pct', 'direction', 'new_age_sessions',
                 'source_type', 'evidence_level', 'strict_pit_approved']
EVENT_AUDIT_COLS = ['ticker', 'signal_date', 'receipt_no', 'report_name', 'event_type',
                    'filing_date', 'usable_session', 'event_age_sessions', 'is_amendment',
                    'is_subsidiary', 'asof_eligible', 'fresh_0_10', 'evidence_level', 'source_url']
QUEUE_COLS = ['ticker', 'signal_date', 'receipt_no', 'event_type', 'metric', 'period',
              'value_krw', 'evidence_status', 'action_needed']
FORECAST_COLS = ['ticker', 'receipt_no', 'filing_date', 'metric', 'fiscal_period',
                 'fs_div', 'entity_scope', 'value_krw', 'original_archive_sha256',
                 'evidence_status', 'is_amendment', 'source_url']
REJECT_COLS = ['ticker', 'receipt_no', 'reason']
SUPPORTED_METRICS = {'FORECAST_REVENUE_KRW', 'FORECAST_OPERATING_PROFIT_KRW'}
PERIOD_RE = re.compile(r'^(FY(?:20\d{2})|(20\d{2})Q[1-4]|(20\d{2})H[12])$')
RECEIPT_RE = re.compile(r'^20\d{12}$')
SHA_RE = re.compile(r'^[a-fA-F0-9]{64}$')
TICKER_RE = re.compile(r'^\d{6}$')
GOOD_EVIDENCE = 'ORIGINAL_AMOUNT_PERIOD_VERIFIED'


def load_csv(path):
    if not path or not Path(path).is_file():
        return []
    with open(path, encoding='utf-8-sig', newline='') as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows, cols):
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_suffix(p.suffix + '.tmp')
    with temp.open('w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore')
        w.writeheader(); w.writerows(rows)
    temp.replace(p)


def date_str(x):
    try:
        if not x or len(x) != 10:
            return ''
        return date.fromisoformat(str(x)).isoformat()
    except ValueError:
        return ''


def next_krx_session(filing, cal):
    """Conservative: data from filing date usable only on a subsequent KRX session."""
    d = date_str(filing)
    if not d: return ''
    try:
        x = cal.date_to_session(d, direction='next')
        # strictly after filing calendar date, including when filing date is a market session
        if x.date().isoformat() <= d:
            x = cal.next_session(x)
        return x.date().isoformat()
    except (ValueError, OverflowError, KeyError):
        return ''


def is_session(d, cal):
    try: return cal.is_session(d)
    except (TypeError, ValueError, OverflowError): return False


def age_sessions(first, signal, cal):
    if not date_str(first) or not date_str(signal) or first > signal:
        return -1
    try:
        if not is_session(first, cal) or not is_session(signal, cal):
            return -1
        return max(0, len(cal.sessions_in_range(first, signal))-1)
    except (ValueError, OverflowError):
        return -1


def event_type(row):
    # Correct legacy v9.4 forecast misclassification based on original title.
    name = re.sub(r'\s+', '', row.get('report_name', ''))
    if '전망' in name and ('영업실적' in name or '매출액' in name or '영업이익' in name):
        return 'FORECAST_DISCLOSURE'
    if any(x in name for x in ('매출액또는손익구조','잠정실적','영업(잠정)실적')):
        return 'EARNINGS_ACTUAL'
    if '수시공시의무관련사항' in name:
        return 'OTHER_FAIR_DISCLOSURE'
    return row.get('event_type', '') or 'UNKNOWN'


def truthy(s): return str(s).strip().lower() in ('true','1','yes')


def inspect_events(events, signals, cal):
    allowed = set(signals)
    # dedupe only identical chart/receipt; do not treat another signal as a different filing.
    out = []; seen = set()
    for r in events:
        ticker = str(r.get('ticker','')).zfill(6)
        signal = date_str(r.get('signal_date',''))
        receipt = str(r.get('receipt_no',''))
        key = (ticker,signal,receipt)
        if key in seen or (ticker,signal) not in allowed: continue
        seen.add(key)
        if not RECEIPT_RE.fullmatch(receipt): continue
        filing = date_str(r.get('filing_date', ''))
        if receipt[:8] != filing.replace('-',''): continue
        earliest = next_krx_session(filing, cal)
        supplied = date_str(r.get('first_usable_session',''))
        if not earliest: continue
        # Do not accept a supplied earlier eligible date. If later, be conservative.
        usable = max(earliest, supplied) if supplied and is_session(supplied, cal) else earliest
        days = age_sessions(usable,signal,cal)
        amendment = truthy(r.get('is_amendment')) or ('정정' in r.get('report_name',''))
        fresh = days >= 0 and days <= 10 and not amendment
        out.append(dict(ticker=ticker,signal_date=signal,receipt_no=receipt,
            report_name=r.get('report_name',''),event_type=event_type(r),filing_date=filing,
            usable_session=usable,event_age_sessions=days if days>=0 else '',
            is_amendment=str(amendment),is_subsidiary=str(truthy(r.get('is_subsidiary')) or '자회사의주요경영사항' in re.sub(r'\s+', '', r.get('report_name',''))),
            asof_eligible=str(days>=0),fresh_0_10=str(fresh),
            evidence_level='TITLE_ONLY',source_url=r.get('source_url','')))
    return sorted(out,key=lambda r:(r['ticker'],r['signal_date'],r['receipt_no']))


def period_end(s):
    if not PERIOD_RE.fullmatch(s): return ''
    if s.startswith('FY'): return s[2:]+'-12-31'
    year = s[:4]
    if 'Q' in s:
        return {'1':'-03-31','2':'-06-30','3':'-09-30','4':'-12-31'}[s[-1]].join([year,''])
    return (year+'-06-30') if s.endswith('H1') else (year+'-12-31')


def parse_value(x):
    try:
        raw = str(x).strip()
        if not re.fullmatch(r'-?(0|[1-9]\d*)',raw): return None
        return int(raw)
    except (ValueError,TypeError): return None


def inspect_forecasts(rows, cal):
    """Treat explicit evidence rows as user-asserted/provisional; never as PIT-certified."""
    accepted=[];rejected=[];seen={}
    for r in rows:
        tk = str(r.get('ticker','')).zfill(6);rcp=str(r.get('receipt_no',''))
        filing = date_str(r.get('filing_date',''));period=str(r.get('fiscal_period',''))
        k=(tk,rcp,str(r.get('metric','')),period,str(r.get('fs_div','')),str(r.get('entity_scope','')))
        why = []
        if not TICKER_RE.fullmatch(tk):why.append('BAD_TICKER')
        if not RECEIPT_RE.fullmatch(rcp) or rcp[:8]!=filing.replace('-',''):why.append('RECEIPT_DATE_MISMATCH')
        if str(r.get('metric','')) not in SUPPORTED_METRICS:why.append('METRIC_NOT_SUPPORTED')
        if not period_end(period):why.append('PERIOD_UNKNOWN')
        if r.get('fs_div','') not in ('CFS','OFS'):why.append('FS_DIV_UNKNOWN')
        if r.get('entity_scope','') not in ('ISSUER','SUBSIDIARY'):why.append('ENTITY_SCOPE_UNKNOWN')
        val=parse_value(r.get('value_krw',''))
        if val is None:why.append('VALUE_NOT_EXACT_INTEGER_KRW')
        if r.get('evidence_status','') != GOOD_EVIDENCE or not SHA_RE.fullmatch(r.get('original_archive_sha256','')):
            why.append('ORIGINAL_PERIOD_AMOUNT_NOT_EVIDENCED')
        if r.get('is_amendment','') not in ('True','False'):why.append('AMENDMENT_FLAG_MISSING')
        usable=next_krx_session(filing,cal)
        if not usable:why.append('NO_KRX_SESSION')
        if k in seen:
            if seen[k] != val:why.append('CONFLICTING_DUPLICATE')
            else:why.append('DUPLICATE_RECEIPT_METRIC_PERIOD')
        if why:
            rejected.append({'ticker':tk,'receipt_no':rcp,'reason':'|'.join(why)})
            continue
        seen[k]=val
        accepted.append(dict(ticker=tk,receipt_no=rcp,filing_date=filing,
             usable_session=usable,metric=r['metric'],fiscal_period=period,
             fs_div=r['fs_div'],entity_scope=r['entity_scope'],value_krw=val,
             is_amendment=truthy(r['is_amendment']),evidence_status=r['evidence_status'],
             source_url=r.get('source_url',''),original_archive_sha256=r['original_archive_sha256']))
    return accepted,rejected


def direction_change(old,new,metric):
    delta=new-old
    if metric=='FORECAST_REVENUE_KRW':
        if old <= 0 or new < 0: return 'UNCOMPARABLE_REVENUE',None
        return ('UP' if delta>0 else 'DOWN' if delta<0 else 'FLAT'),round(100*delta/old,4)
    if old<0 and new>=0:return 'LOSS_TO_PROFIT',None
    if old<0 and new<0:return ('LOSS_NARROWING' if delta>0 else 'LOSS_WIDENING' if delta<0 else 'FLAT'),None
    if old>=0 and new<0:return 'PROFIT_TO_LOSS',None
    if old==0:return ('FROM_ZERO' if new>0 else 'FLAT'),None
    return ('UP' if delta>0 else 'DOWN' if delta<0 else 'FLAT'),round(100*delta/old,4)


def compute_revisions(accepted, signals, cal):
    # For EACH historical signal, use only original-vintage guidance available at that signal.
    grouped=defaultdict(list)
    for r in accepted:
        key=(r['ticker'],r['metric'],r['fiscal_period'],r['fs_div'],r['entity_scope'])
        grouped[key].append(r)
    out=[]
    for tk,signal in sorted(set(signals)):
        for (ticker,metric,period,fs,entity), rows in grouped.items():
            if ticker!=tk or period_end(period)<signal: continue
            usable=[r for r in rows if r['usable_session']<=signal]
            usable.sort(key=lambda r:(r['usable_session'],r['receipt_no']))
            # Only compare strictly ordered distinct *report dates*. Same-session original/adjustment ambiguous.
            if len(usable)<2:continue
            new=usable[-1]
            if new['is_amendment']:continue  # Correction not a fresh positive catalyst.
            previous=[r for r in usable[:-1] if r['usable_session']<new['usable_session']]
            if not previous:continue
            prev=previous[-1]
            old_value,new_value=prev['value_krw'],new['value_krw']
            direction,change_pct=direction_change(old_value,new_value,metric)
            if direction=='UNCOMPARABLE_REVENUE':continue
            days=age_sessions(new['usable_session'],signal,cal)
            out.append(dict(ticker=tk,signal_date=signal,metric=metric,fiscal_period=period,
                 fs_div=fs,entity_scope=entity,previous_receipt=prev['receipt_no'],new_receipt=new['receipt_no'],
                 previous_first_usable_session=prev['usable_session'],new_first_usable_session=new['usable_session'],
                 previous_value_krw=old_value,new_value_krw=new_value,change_krw=new_value-old_value,
                 change_pct=change_pct if change_pct is not None else '',direction=direction,
                 new_age_sessions=days,source_type='COMPANY_GUIDANCE_NOT_ANALYST_CONSENSUS',
                 evidence_level='ASSERTED_ORIGINAL_MATCH_PROVISIONAL',strict_pit_approved='False'))
    return sorted(out,key=lambda r:(r['ticker'],r['signal_date'],r['metric'],r['fiscal_period']))


def link_queues(candidates, events, raw_amounts, revisions):
    event_map=defaultdict(list);rev_map=defaultdict(list)
    for e in events:
        if e['asof_eligible']=='True':event_map[(e['ticker'],e['signal_date'])].append(e)
    for r in revisions:rev_map[(r['ticker'],r['signal_date'])].append(r)
    audit=[];seen=set()
    for row in candidates:
        ticker=str(row.get('ticker','')).zfill(6);sig=date_str(row.get('signal_date',''))
        if not TICKER_RE.fullmatch(ticker) or not sig:continue
        k=(ticker,sig)
        if k in seen:continue
        seen.add(k)
        es=event_map[k];rs=rev_map[k]
        fresh=sum(e['fresh_0_10']=='True' for e in es)
        forecast_titles=sum(e['event_type']=='FORECAST_DISCLOSURE' for e in es)
        up=[r for r in rs if r['direction'] in ('UP','LOSS_NARROWING','LOSS_TO_PROFIT','FROM_ZERO')]
        down=[r for r in rs if r['direction'] in ('DOWN','LOSS_WIDENING','PROFIT_TO_LOSS')]
        recent_up=[r for r in up if r['new_age_sessions']<=10]
        direction='MIXED' if up and down else 'UP_ONLY' if up else 'DOWN_ONLY' if down else 'NO_COMPARABLE_REVISION'
        evidence='PROVISIONAL_COMPANY_GUIDANCE' if rs else 'TITLE_ONLY' if es else 'NO_EVIDENCE'
        best=[r['change_pct'] for r in up if isinstance(r['change_pct'],(float,int))]
        reason=('REVISION_IS_PROVISIONAL_NO_SECTOR_PIT' if rs else
                'OLD_OR_NONQUANTIFIED_DISCLOSURE' if es else 'NO_MATCHING_EVENT')
        if rs and not recent_up: reason='NO_FRESH_UPWARD_REVISION'
        audit.append(dict(ticker=ticker,signal_date=sig,signal_score=row.get('signal_score',''),
          selection_status=row.get('selection_status',''),forward_event_count=len(es),
          fresh_nonamend_event_count=fresh,forecast_title_count=forecast_titles,title_only=str(bool(es and not rs)),
          quantitative_revision_count=len(rs),best_guidance_change_pct=max(best) if best else '',
          guidance_direction=direction,evidence_level=evidence,reason=reason,strict_pit_approved='False'))
    event_keys={(e['ticker'],e['signal_date'],e['receipt_no']) for e in events if e['asof_eligible']=='True'}
    queue=[]
    for r in raw_amounts:
        k=(str(r.get('ticker','')).zfill(6),date_str(r.get('signal_date','')),str(r.get('receipt_no','')))
        if k not in event_keys:continue
        queue.append(dict(ticker=k[0],signal_date=k[1],receipt_no=k[2],event_type=r.get('event_type',''),
          metric=r.get('metric',''),period=r.get('period',''),value_krw=r.get('value_krw',''),
          evidence_status=r.get('evidence_status',''),
          action_needed='VERIFY_FILING_ORIGINAL_PERIOD_SCOPE_AND_PREVIOUS_GUIDANCE'))
    return audit,queue


def run(candidate_file, event_file, amount_file, forecasts_file, outdir):
    cal=xcals.get_calendar('XKRX')
    cands=load_csv(candidate_file)
    if not cands: raise ValueError('Candidate signal CSV missing/empty; refusing to synthesize a universe')
    signals={(str(x.get('ticker','')).zfill(6),date_str(x.get('signal_date',''))) for x in cands}
    signals={x for x in signals if TICKER_RE.fullmatch(x[0]) and x[1]}
    ev_source=load_csv(event_file); events=inspect_events(ev_source,signals,cal)
    raw=load_csv(amount_file)
    ledger=load_csv(forecasts_file)
    verified,rejections=inspect_forecasts(ledger,cal)
    rev=compute_revisions(verified,signals,cal)
    candidate_rows,queue=link_queues(cands,events,raw,rev)
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    write_csv(out/'v95_candidate_expectation_audit.csv',candidate_rows,CANDIDATE_COLS)
    write_csv(out/'v95_guidance_revisions_provisional.csv',rev,REVISION_COLS)
    write_csv(out/'v95_event_quality_audit.csv',events,EVENT_AUDIT_COLS)
    write_csv(out/'v95_unverified_amount_queue.csv',queue,QUEUE_COLS)
    write_csv(out/'v95_forecast_rejections.csv',rejections,REJECT_COLS)
    status={'version':'v9.5-company-guidance-revision-audit',
            'strict_pit_approved':False,'backtest_ready':False,'live_trading_enabled':False,
            'analyst_consensus_available':False,'sector_pit_available':False,
            'candidate_signals':len(candidate_rows),'event_rows_input':len(ev_source),
            'events_with_usable_asof':sum(e['asof_eligible']=='True' for e in events),
            'fresh_nonamend_events':sum(e['fresh_0_10']=='True' for e in events),
            'verified_forecast_rows_asserted':len(verified),'rejected_forecast_rows':len(rejections),
            'company_guidance_revision_pairs_provisional':len(rev),
            'upward_revision_pairs_provisional':sum(r['direction'] in ('UP','LOSS_NARROWING','LOSS_TO_PROFIT','FROM_ZERO') for r in rev),
            'raw_numeric_candidates_needing_review':len(queue),
            'coverage_warning':'The pre-selected 258-stock OHLC research cache is NOT all of historical KRX',
            'critical_limitations':[
             'Company guidance is not analyst-consensus change; evidence file requires source verification',
             'Forecast ledger is empty unless original numbers, period, vintage and scope are verified',
             'Current historical universe and PIT sector membership incomplete',
             'Same-day filings are conservatively usable next KRX session, intraday timestamps unknown',
             'No backtest or BUY decision authorized by these files']}
    (out/'v95_research_summary.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    return status


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate-file',default='config/v94_signal_candidates_reference.csv')
    p.add_argument('--event-file',default='reports/v941_forward_event_leads.csv')
    p.add_argument('--fallback-event-file',default='reports/v94_forward_event_leads.csv')
    p.add_argument('--amount-file',default='reports/v941_event_numeric_candidates.csv')
    p.add_argument('--forecasts-file',default='config/v95_verified_forecasts.csv')
    p.add_argument('--outdir',default='reports')
    args=p.parse_args(argv)
    evfile=args.event_file if Path(args.event_file).is_file() else args.fallback_event_file
    status=run(args.candidate_file,evfile,args.amount_file,args.forecasts_file,args.outdir)
    print(json.dumps(status,ensure_ascii=False,indent=2))
    return status

if __name__=='__main__':main()
