#!/usr/bin/env python3
"""Phone-first overseas premarket sector watch, NOT a Korean sector TOP3 or BUY.

Uses existing free GDELT output. Its early-watch queue requires independent
publisher domains AND distinct headlines; syndicated copies are discounted.
"""
import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from global_sector_news import SECTORS,MACRO,seen_time,safe_url,title_text,headline_signature

def read_csv(path):
    if not path.is_file():return []
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def build(audit,articles,now):
    stamp=seen_time(audit.get("collected_at_utc"))
    source_fresh=bool(audit.get("schema")=="global_sector_discovery_v1" and
       stamp is not None and timedelta(0)<=now-stamp<=timedelta(hours=2))
    states=audit.get("query_states")
    if not isinstance(states,dict):states={}
    grouped=defaultdict(list)
    if source_fresh:
        for row in articles:
            sector=str(row.get("sector_id",""))
            if sector not in SECTORS and sector not in MACRO:continue
            if states.get(sector,{}).get("status")!="OK":continue
            seen=seen_time(row.get("seen_at_utc"))
            url=safe_url(row.get("url"))
            headline=title_text(row.get("title"))
            country=str(row.get("source_country","")).strip()
            if seen is None or not now-timedelta(hours=72)<=seen<=now:
                continue
            if not url or len(headline)<12 or not country or country.casefold() in (
                  "south korea","republic of korea","korea, republic of"):
                continue
            if row.get("source")!="GDELT_DOC_2_ARTLIST":continue
            grouped[sector].append(dict(
                title=headline,url=url,country=country,
                seen_at_utc=seen.isoformat(timespec="seconds"),
                publisher_domain=str(row.get("publisher_domain","")),
                headline_signature=headline_signature(headline)))
    sectors=[]
    for sector in SECTORS:
        current=[r for r in grouped[sector]
                 if seen_time(r["seen_at_utc"])>=now-timedelta(hours=48)]
        domains={x["publisher_domain"] for x in current if x["publisher_domain"]}
        signatures={x["headline_signature"] for x in current if x["headline_signature"]}
        if len(domains)<2 or len(signatures)<2:
            continue
        current.sort(key=lambda x:(x["seen_at_utc"],x["url"]),reverse=True)
        # Source-index only. No stock-price acceleration/earnings/positive news claimed.
        sectors.append(dict(sector_id=sector,
            independent_publisher_domains=len(domains),distinct_headlines=len(signatures),
            source_countries=len({r["country"] for r in current}),
            sample_articles=current[:3],
            news_validated_positive=False,domestic_flow_checked=False,
            status="FOREIGN_PREOPEN_WATCH_ONLY",trade_approval="NO"))
    sectors.sort(key=lambda r:(-r["independent_publisher_domains"],
      -r["distinct_headlines"],-r["source_countries"],r["sector_id"]))
    macro=[]
    for code in MACRO:
        current=sorted(grouped[code],key=lambda x:x["seen_at_utc"],reverse=True)
        macro.extend([dict(sector_id=code,**x) for x in current[:1]])
    macro.sort(key=lambda r:r["seen_at_utc"],reverse=True)
    if not source_fresh:status="MISSING_OR_STALE_GLOBAL_SOURCE"
    elif not any(states.get(s,{}).get("status")=="OK" for s in SECTORS):
        status="GLOBAL_SECTOR_QUERIES_FAILED"
    elif any(states.get(s,{}).get("status")!="OK" for s in SECTORS):
        status="PARTIAL_GLOBAL_SOURCE"
    else:status="GLOBAL_SOURCE_READ"
    return dict(schema="global_preopen_v1",generated_utc=now.isoformat(timespec="seconds"),
      source_status=status,search_completed_utc=stamp.isoformat(timespec="seconds") if stamp else None,
      global_early_watch=sectors[:3],
      global_macro_observations=macro[:4],
      domestic_sector_top3_verified=False,verified_positive_global_catalyst_count=0,
      is_korean_market_money_flow_confirmed=False,
      trade_approved=False,orders_enabled=False,decision="CASH",
      note="Global sample discovery only; confirm original source, direct beneficiaries, KRX turnover/net buying and daily chart before acting.")

def render(report):
    lines=["# C3·K100 08:35 세계 뉴스 선행 관찰","",
      "**신규매수: CASH / 해외 기사만으로 매수 판단하지 않음**","",
      "해외 자료 상태: "+report["source_status"],
      "이는 국내 거래대금·외국인/기관 수급까지 확인한 섹터 TOP3가 아닌 **장전 연구 대기열**입니다.",
      "기사 발견 시각은 원문 최초 보도 시각이 아닙니다.","",
      "## 해외 주목 섹터 (최대 3개)","",
      "| 섹터 | 언론 출처 수 | 서로 다른 제목 수 | 국내 수급 |",
      "|---|---:|---:|---|"]
    for r in report["global_early_watch"]:
        lines.append(f"| {r['sector_id']} | {r['independent_publisher_domains']} | "+
          f"{r['distinct_headlines']} | 미확인 |")
    if not report["global_early_watch"]:
        lines.append("| 검증된 해외 선행 관찰 없음 | — | — | 미확인 |")
    lines+=["","## 해외 기사 근거",""]
    for r in report["global_early_watch"]:
        lines.append("### "+r["sector_id"])
        for item in r["sample_articles"]:
            t=seen_time(item["seen_at_utc"]).astimezone(ZoneInfo("Asia/Seoul"))
            lines.append(f"- {t:%m-%d %H:%M} KST / {item['country']}: "+
             "["+item["title"].replace("]","）")+"]("+item["url"]+")")
    lines+=["","## 글로벌 거시경제 단서",""]
    if not report["global_macro_observations"]:
        lines.append("- 검증 가능한 최신 해외 거시 뉴스 없음")
    for item in report["global_macro_observations"]:
        lines.append("- "+item["sector_id"]+": ["+item["title"].replace("]","）")+
                     "]("+item["url"]+")")
    lines+=["","## 국내장 개장 후 확인할 항목",
     "- 해당 산업 내 KRX 거래대금·거래량 증가와 외국인/기관 순매수",
     "- 해외 소식의 실제 한국 상장기업 공급계약·수주·실적 연결 근거",
     "- 일봉 추세·실질 손절 지점·매수 타점 (검증된 종목점수 85점 이상만 매수 검토)",""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("output"))
    a=p.parse_args()
    status_file=a.root/"global_sector_news_status.json"
    try:
        audit=json.loads(status_file.read_text(encoding="utf-8")) if status_file.is_file() else {}
    except (ValueError,OSError):audit={}
    result=build(audit,read_csv(a.root/"global_sector_articles.csv"),datetime.now(timezone.utc))
    a.root.mkdir(parents=True,exist_ok=True)
    (a.root/"global_preopen_brief.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    (a.root/"global_preopen_brief_mobile.md").write_text(render(result),encoding="utf-8")
    print(json.dumps({"source_status":result["source_status"],
      "early_watch":len(result["global_early_watch"]),"decision":result["decision"]},ensure_ascii=False))

if __name__=="__main__":
    main()
