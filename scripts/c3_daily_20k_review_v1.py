#!/usr/bin/env python3
"""Read-only 20:00 KST C3 whole-market rescreen + fresh domestic news.

At 20:00 today's official-final price source may not yet be available (existing
collector waits until after 20:15). Use last verified completed scan, preserve
data dates, and never claim a new same-day scan on weekends/holidays.
"""
from __future__ import annotations
import argparse,csv,datetime,email.utils,hashlib,json,urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

FEEDS={
 'HK_FINANCE':'https://www.hankyung.com/feed/finance',
 'MK_MARKET':'https://www.mk.co.kr/rss/30100041/',
}

def kst_now():return datetime.datetime.now(ZoneInfo('Asia/Seoul'))

def read_rss(url,now,fetch=None):
    if fetch is None:
        def fetch(address):
            req=urllib.request.Request(address,headers={'User-Agent':'Mozilla/5.0 C3-News-Research/1.0'})
            with urllib.request.urlopen(req,timeout=15) as reply:return reply.read(900000)
    xml=ET.fromstring(fetch(url))
    rows=[]
    for item in xml.findall('.//item'):
        title=' '.join((item.findtext('title') or '').split()).strip()[:180]
        link=(item.findtext('link') or '').strip()
        raw=(item.findtext('pubDate') or '').strip()
        if not title or not link.startswith('https://'):continue
        published=None
        if raw:
            try:
                published=email.utils.parsedate_to_datetime(raw)
                if published.tzinfo is None:published=published.replace(tzinfo=datetime.timezone.utc)
            except (ValueError,TypeError):pass
        if published and (published>now or (now-published).total_seconds()>72*3600):continue
        rows.append(dict(title=title,url=link,
            published_at=published.isoformat() if published else None,
            original_pubtime_present=bool(published)))
    return rows

def inspect_scan(source):
    source=Path(source)
    if not (source/'status.json').is_file():
        return dict(source_state='NO_FULL_MARKET_SCAN_ARCHIVE',universe=None,source_date=None,
                    total_observations=None,early_candidate_count=None),[]
    status=json.loads((source/'status.json').read_text(encoding='utf-8'))
    day=status.get('market_data_date');universe=status.get('universe')
    f=source/'c3_premove_observations_v1.csv'
    if not day or not isinstance(universe,int) or universe<2000 or not f.is_file():
        return dict(source_state='INCOMPLETE_FULL_MARKET_SCAN',universe=universe,source_date=day,
                    total_observations=None,early_candidate_count=None),[]
    with f.open(encoding='utf-8-sig',newline='') as stream:obs=list(csv.DictReader(stream))
    codes=[r.get('ticker') for r in obs]
    if len(obs)!=universe or len(set(codes))!=universe:
        return dict(source_state='OBSERVATION_UNIVERSE_COUNT_MISMATCH',universe=universe,
                    source_date=day,total_observations=len(obs),early_candidate_count=None),[]
    early=[x for x in obs if x.get('price_stage_pass')=='True'
           and x.get('observation_status')=='PRICE_ONLY_OBSERVED' and x.get('asof')==day]
    return dict(source_state='COMPLETED_ARCHIVE_RESCREENED' if status.get('scan_complete')
                else 'SCAN_COMPLETENESS_UNVERIFIED_RESCREENED',source_date=day,
          universe=universe,total_observations=len(obs),early_candidate_count=len(early),
          original_run_kst=status.get('run_kst'),original_source_session_scope_certified=
          bool(status.get('source_session_scope_certified',False)),
          full_status_sha256=hashlib.sha256((source/'status.json').read_bytes()).hexdigest()),early

def run(source,output,now=None,fetch=None):
    now=(now or kst_now()).astimezone(ZoneInfo('Asia/Seoul'))
    market,early=inspect_scan(source)
    day=market['source_date']
    try:age=(now.date()-datetime.date.fromisoformat(day)).days if day else None
    except ValueError:age=None
    weekend=now.weekday()>=5
    mode=('WEEKEND_NEWS_OVER_LAST_COMPLETED_DAY' if weekend else
        'WEEKDAY_20K_NOT_YET_2015_SOURCE_FINAL' if now.hour==20 and now.minute<15
        else 'LAST_COMPLETED_SCAN_AND_NEWS_REVIEW')
    if age is None:mode='NO_FULL_MARKET_SOURCE_NEWS_ONLY'
    elif age<0:mode='FUTURE_SOURCE_REJECTED_NEWS_ONLY';early=[]
    elif age>7:mode='STALE_SOURCE_NEWS_ONLY'
    news=[];feed_states={}
    for name,url in FEEDS.items():
        try:
            rows=read_rss(url,now,fetch)
            news.extend(dict(source=name,**x) for x in rows)
            feed_states[name]=dict(status='OK',articles_72h=len(rows))
        except Exception as exc:
            feed_states[name]=dict(status='FAILED',error_type=type(exc).__name__,articles_72h=0)
    news=sorted({r['url']:r for r in news}.values(),key=lambda x:x['published_at'] or '',reverse=True)
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    meta=dict(schema='C3_DAILY_20K_FULL_MARKET_AND_NEWS_V1',run_kst=now.isoformat(),
        price_data_asof=day,source_age_calendar_days=age,weekend=weekend,
        mode=mode,full_market_scanned_fresh_now=False,
        completed_market_universe_rescreened=(market['total_observations']==market['universe']
          and market['universe'] is not None and age is not None and 0<=age<=7),
        source_market=market,news_window_hours=72,
        domestic_news_count=len(news),domestic_rss_sources=feed_states,
        global_news_separate_file='global/global_sector_news_status.json',
        weekend_news_not_weekend_prices=True,disclosed_news_not_a_required_buy_gate=True,
        price_source_regular_only_certified=False,actual_investor_flows_verified=False,
        trade_approved=False,orders_enabled=False)
    # Store one read-only dated screening observation for EVERY source ticker.
    # These are original per-stock price-stage findings, not newly traded
    # 20:00 prices, and never trade permissions.
    obsfile=Path(source)/'c3_premove_observations_v1.csv'
    audit_fields=['ticker','source_price_asof','observation_status','early_stage_pass',
        'observed_5d_return_pct','observed_20d_return_pct','rsi14',
        'fresh_price_at_20k','trade_approved']
    if meta['completed_market_universe_rescreened'] and obsfile.is_file():
        with obsfile.open(encoding='utf-8-sig',newline='') as f:
            original=list(csv.DictReader(f))
        with (root/'c3_20k_all_market_rescreen.csv').open(
             'w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=audit_fields);writer.writeheader()
            for v in original:
                writer.writerow(dict(ticker=v['ticker'],source_price_asof=v['asof'],
                    observation_status=v.get('observation_status',''),
                    early_stage_pass=v.get('price_stage_pass',''),
                    observed_5d_return_pct=v.get('ret5',''),
                    observed_20d_return_pct=v.get('ret20',''),
                    rsi14=v.get('rsi14',''),
                    fresh_price_at_20k=False,trade_approved=False))
        meta['all_market_rescreen_rows_written']=len(original)
    else:
        meta['all_market_rescreen_rows_written']=0
    (root/'c3_20k_full_market_status.json').write_text(
        json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (root/'c3_20k_domestic_news.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=['source','title','url','published_at','original_pubtime_present'])
        w.writeheader();w.writerows(news)
    report=['# C3 20:00 KST 전 종목 및 뉴스 점검',
        f"- 실행시각: {now.isoformat()}",
        f"- 가격 기준거래일: {day or '원본 미확보'} (주말에도 새 일봉을 만들지 않음)",
        f"- 진행 상태: {mode}",
        f"- 원본 전체 관측 종목: {market['total_observations'] or 0:,} / 상승 초기 후보: {market['early_candidate_count'] or 0:,}",
        f"- 새로운 국내 뉴스(72시간 제목 검색): {len(news)}건 / 국외 뉴스: 별도 수집",
        '- 가격·거래량 원본의 정규장 전용 인증, 외국인/기관 순매수는 아직 미완료',
        '- TOP2 손절·매수가·1차·2차 목표는 원본 새 완료 일봉 확인 후 별도 계산',
        '- 새 20:00 가격수집 완료/자동주문/매수승인을 주장하지 않음']
    (root/'c3_20k_mobile.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    return meta

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--scan-source',required=True);ap.add_argument('--output',required=True)
    args=ap.parse_args()
    x=run(args.scan_source,args.output)
    print(json.dumps({k:x[k] for k in ('mode','completed_market_universe_rescreened',
       'domestic_news_count','trade_approved')},ensure_ascii=False))
