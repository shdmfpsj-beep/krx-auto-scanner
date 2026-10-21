#!/usr/bin/env python3
"""Join existing v18 Naver-news and OpenDART evidence to sector-first report.

Only an as-of evidence index: a headline or filing is NOT a verified positive catalyst.
No web calls, credentials, scores, trade actions or fabricated recommendations.
"""
import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit


def rows(path):
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def safe_text(value, limit=105):
    return (str(value or "").replace("|", "/").replace("\n", " ")
            .replace("\r", " ").replace("[", "(").replace("]", ")")[:limit])


def news_url(value):
    url=str(value or "").strip()
    if len(url)>1300 or any(x in url for x in " <>\r\n\\"):
        return ""
    try:
        parsed=urlsplit(url)
    except ValueError:
        return ""
    if parsed.scheme != "https" or not parsed.hostname:
        return ""
    host=parsed.hostname.lower()
    if (host=="localhost" or host.endswith(".local") or
            host.startswith("127.") or host.startswith("10.") or
            host.startswith("192.168.")):
        return ""
    # Prevent broken markdown links.
    if any(x in url for x in "()[]"):
        return ""
    return url


def official_dart_url(receipt):
    receipt=str(receipt or "")
    return ("https://dart.fss.or.kr/dsaf001/main.do?rcpNo="+receipt
            if re.fullmatch(r"[0-9]{14}", receipt) else "")


def index_evidence(base, news, filings, membership, source_status, asof):
    sectors=base.get("sector_top3") or []
    ids={str(x.get("sector_id","")) for x in sectors}
    metrics={x:{"news":[],"filings":[]} for x in ids}
    news_state=str(source_status.get("datasets",{}).get("news",{}).get("status","UNKNOWN"))
    dart_state=str(source_status.get("datasets",{}).get("dart",{}).get("status","UNKNOWN"))
    if asof is None:
        return metrics,{"news":"INVALID_ASOF","dart":"INVALID_ASOF","eligible_rows":0}
    # Dated ETF constituents are a research-only sector membership proxy.
    # No stale or unknown membership is silently promoted to today's universe.
    attached={}
    for r in membership:
        sector=str(r.get("sector_id",""))
        ticker=str(r.get("ticker","")).strip()
        snap=day(r.get("snapshot_date"))
        if (sector not in ids or not re.fullmatch(r"[0-9]{6}",ticker) or
                snap is None or not 0<=(asof-snap).days<=10):
            continue
        attached.setdefault(ticker,set()).add(sector)
    if news_state=="PARTIAL_SEARCH_ARCHIVE":
        for r in news:
            sector=str(r.get("sector_id",""))
            published=day(r.get("published_at"))
            url=news_url(r.get("url"))
            if (sector not in ids or published is None or url=="" or
                    not 0<=(asof-published).days<=5 or
                    not str(r.get("timestamp_basis","")).startswith("NAVER_pubDate")):
                continue
            title=safe_text(r.get("title"))
            if len(title)<8:
                continue
            entry=dict(sector_id=sector,kind="NEWS_HEADLINE_UNVERIFIED_IMPACT",
                date=str(published),title=title,url=url,ticker="",
                source="NAVER_NEWS_SEARCH",evidence="SEARCH_ARCHIVE_INCOMPLETE",
                positive_catalyst_verified=False)
            metrics[sector]["news"].append(entry)
    if dart_state=="DATE_ONLY_COMPLETE":
        for r in filings:
            filed=day(r.get("receipt_date"))
            ticker=str(r.get("ticker","")).strip()
            url=official_dart_url(r.get("receipt_no"))
            if (filed is None or not 0<=(asof-filed).days<=5 or
                    filed==asof or not url or
                    r.get("published_precision")!="DAY_ONLY_no_intraday_time"):
                continue
            for sector in attached.get(ticker,set()):
                metrics[sector]["filings"].append(dict(
                    sector_id=sector,kind="OFFICIAL_DART_FILING_UNVERIFIED_IMPACT",
                    date=str(filed),title=safe_text(r.get("report_name")),
                    url=url,ticker=ticker,source="OPENDART_LIST",
                    evidence="PUBLICATION_DAY_ONLY_NOT_EXACT_TIME",
                    positive_catalyst_verified=False))
    for group in metrics.values():
        for typ in ("news","filings"):
            dedup={}
            for item in group[typ]:
                dedup[(item["url"],item["sector_id"])]=item
            group[typ]=sorted(dedup.values(),
                key=lambda x:(x["date"],x["url"]),reverse=True)[:3]
    return metrics,dict(news=news_state,dart=dart_state,
        eligible_rows=sum(len(x["news"])+len(x["filings"]) for x in metrics.values()),
        caveat="News title and filing name are not independently verified positive catalysts; counts are incomplete and do not change sector rank.")


def enrich(report,metrics,audit):
    new=dict(report)
    new["catalyst_source_status"]=audit
    out=[]
    for original in report.get("sector_top3",[]):
        r=dict(original)
        group=metrics.get(str(r.get("sector_id","")),{})
        articles=group.get("news",[])
        filings=group.get("filings",[])
        r["recent_news_observations"]=articles
        r["prior_day_dart_observations"]=filings
        r["positive_catalyst_verified"]=False
        r["catalyst"]="DATED_SOURCE_OBSERVED_IMPACT_UNVERIFIED" if articles or filings else "NOT_VERIFIED"
        out.append(r)
    new["sector_top3"]=out
    new["decision"]="CASH"
    new["trade_approved"]=False
    new["orders_enabled"]=False
    new["source_note"]=(
        "Sector v18 price/flow breadth is an ETF-membership research proxy; "
        "Naver headlines and DART report names do not prove positive catalysts.")
    new["catalyst_rank_adjusted"]=False
    new["catalyst_positive_count_verified"]=0
    # Even fresh headlines do not authorize removal of catalyst verification blocker.
    return new


def markdown(report,previous=""):
    lines=["","## ③ 최근 뉴스·공시 근거 (호재 판정 전 검토)","",
       "수집된 기사 제목이나 공시명만으로 호재를 확정하거나 섹터 순위를 조정하지 않았습니다.",
       "뉴스는 불완전한 검색 목록이며 DART는 공시 시간 미확인으로 기준일 당일 공시를 제외했습니다.",""]
    status=report.get("catalyst_source_status",{})
    lines.append("자료 수집 상태: 뉴스 "+str(status.get("news","UNKNOWN"))+
                 " / DART "+str(status.get("dart","UNKNOWN")))
    lines.append("")
    for sector in report.get("sector_top3",[]):
        lines.append("### "+safe_text(sector.get("name")))
        items=sector.get("recent_news_observations",[])+sector.get("prior_day_dart_observations",[])
        if not items:
            lines.append("- 사용 가능한 해당 기간 뉴스·공시 근거 없음 (미수집일 수도 있음)")
        for item in items:
            marker="뉴스 단서" if item["kind"].startswith("NEWS") else "공식 공시 (호재 미확인)"
            lines.append("- "+item["date"]+" "+marker+": ["+
                         safe_text(item["title"])+"]("+item["url"]+")")
        lines.append("")
    lines.extend(["**최종 신규매수 판단: CASH** — 호재의 실질 내용·실적 영향·시점은 별도로 확인해야 합니다.",""])
    return previous.rstrip()+"\n"+"\n".join(lines)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--report-root",type=Path,default=Path("output"))
    p.add_argument("--evidence-root",type=Path,default=Path("inputs/evidence"))
    a=p.parse_args()
    source=a.report_root/"sector_first_daily_status.json"
    if not source.is_file():
        raise SystemExit("MISSING_SECTOR_FIRST_BASE_REPORT")
    base=json.loads(source.read_text(encoding="utf-8"))
    root=a.evidence_root
    matches=list(root.rglob("diagnostics/collection_status.json")) if root.is_dir() else []
    if len(matches)==1:
        evidence=matches[0].parent.parent
        try:
            status=json.loads(matches[0].read_text(encoding="utf-8"))
        except (OSError,ValueError):
            status={}
    else:
        evidence=root
        status={}
    asof=day(base.get("asof"))
    metrics,audit=index_evidence(base,rows(evidence/"catalysts/news.csv"),
       rows(evidence/"catalysts/disclosures.csv"),
       rows(a.report_root/"sector_stock_watchlist.csv"),
       status,asof)
    result=enrich(base,metrics,audit)
    a.report_root.mkdir(parents=True,exist_ok=True)
    (a.report_root/"sector_first_with_catalysts.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    old=a.report_root/"sector_first_daily_mobile.md"
    rendered=old.read_text(encoding="utf-8") if old.is_file() else "# 섹터 우선 보고서\n"
    (a.report_root/"sector_first_with_catalysts_mobile.md").write_text(
        markdown(result,rendered),encoding="utf-8")
    print(json.dumps(dict(decision=result["decision"],asof=result.get("asof"),
      sectors=len(result["sector_top3"]),evidence_rows=audit["eligible_rows"],
      news_status=audit["news"],dart_status=audit["dart"],
      positive_catalysts_verified=0),ensure_ascii=False))


if __name__=="__main__":
    main()
