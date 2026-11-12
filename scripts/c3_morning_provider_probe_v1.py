"""One past-day Kiwoom quote diagnostic; no account/order APIs or certification."""
import argparse,json,os,re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from kiwoom_daily_readonly import fetch_daily


def probe(day,ticker='005930'):
    if not re.fullmatch(r'\d{8}',day) or day>=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d'):
        raise ValueError('PAST_COMPLETED_PROBE_DAY_REQUIRED')
    result=dict(schema='C3_PAST_DAY_FREE_PROVIDER_PROBE_V1',provider='KIWOOM_EXISTING_DAILY_ADAPTER',asof=day,ticker=ticker,
        source_scope='ADJUSTED_DAILY_CHART_NOT_REGULAR_ONLY',regular_only_certified=False,buy_approved=False,
        orders_enabled=False,registered_signals_modified=False,telegram_requests=0)
    if not (os.environ.get('KIWOOM_APP_KEY') and os.environ.get('KIWOOM_APP_SECRET')):
        return dict(result,status='PENDING_PROVIDER_CONNECTION',reason='EXISTING_CREDENTIAL_PAIR_NOT_CONFIGURED',request_attempted=False)
    try:
        rows=fetch_daily(ticker,day,max_pages=1)
        target=day[:4]+'-'+day[4:6]+'-'+day[6:]
        exact=[r for r in rows if r['Date']==target]
        return dict(result,status='DATED_DAILY_SAMPLE_UNCERTIFIED' if len(exact)==1 else 'EXACT_DAY_SAMPLE_UNAVAILABLE',request_attempted=True,dated_sample=exact[0] if len(exact)==1 else None)
    except Exception as exc:
        safe=str(exc)
        # The established adapter redacts credentials and provider messages.
        if not safe.startswith(('KIWOOM_HTTP_REJECTED ','KIWOOM_RESPONSE_NOT_SUCCESS ','KIWOOM_CREDENTIALS_NOT_CONFIGURED','KIWOOM_TOKEN_MISSING')):
            safe=type(exc).__name__
        return dict(result,status='PROVIDER_QUERY_FAILED',request_attempted=True,diagnostic=safe)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--day',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    result=probe(a.day);out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
