#!/usr/bin/env python3
"""Add foreign press and global-macro early watch to the sector-first mobile report.

Not a model claiming causation. No headlines counted as positive catalysts,
no unseen article contents summarized, no stock price or BUY manufactured.
"""
import argparse
import csv
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from global_sector_news import MACRO,SECTORS,safe_url,seen_time,title_text

def read_csv(path):
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def render_time(s):
    dt=seen_time(s)
    return dt.astimezone(ZoneInfo("Asia/Seoul")).strftime("%m-%d %H:%M KST") if dt else "시각 불명"

def status_gate(audit,now):
    if audit.get("schema")!="global_sector_discovery_v1":
        return "NO_GLOBAL_SOURCE"
    dt=seen_time(audit.get("collected_at_utc"))
    if dt is None or not timedelta(0)<=now-dt<=timedelta(hours=4):
        return "STALE_GLOBAL_DISCOVERY"
    successes=audit.get("queries_succeeded",0)
    if not isinstance(successes,int) or successes<4:
        return "INSUFFICIENT_GLOBAL_DISCOVERY"
    total=audit.get("requests_attempted",0)
    if successes<total:
        return "PARTIAL_GLOBAL_DISCOVERY"
    return "GLOBAL_DISCOVERY_OK"

def combine(base,audit,articles,now):
    out=dict(base)
    gate=status_gate(audit,now)
    allowed=gate in ("GLOBAL_DISCOVERY_OK","PARTIAL_GLOBAL_DISCOVERY")
    sector_list=[dict(x) for x in base.get("sector_top3",[])]
    sector_ids={str(x.get("sector_id","")) for x in sector_list}
    valid=[]
    if allowed:
        for r in articles:
            dt=seen_time(r.get("seen_at_utc"))
            sid=str(r.get("sector_id",""))
            if (sid not in SECTORS and sid not in MACRO) or dt is None or (
               not now-timedelta(hours=73)<=dt<=now):
                continue
            if r.get("source")!="GDELT_DOC_2_ARTLIST":
                continue
            url=safe_url(r.get("url"))
            name=title_text(r.get("title"))
            country=str(r.get("source_country","")).strip()
            if not url or not name or not country or country.casefold() in ("south korea","republic of korea"):
                continue
            valid.append({
              "sector_id":sid,"title":name,"url":url,
              "source_country":country,"language":str(r.get("language",""))[:30],
              "seen_at_utc":dt.isoformat(timespec="seconds"),
              "publisher_domain":str(r.get("publisher_domain",""))[:130],
              "impact_status":"FOREIGN_NEWS_OBSERVATION_NOT_CONTENT_VERIFIED",
              "positive_catalyst_verified":False})
    # Keep source links with per-sector TOP3, but no artificial score boost.
    for sector in sector_list:
        related=[r for r in valid if r["sector_id"]==sector.get("sector_id")]
        sector["global_news_observations"]=related[:3]
        sector["global_catalyst_confirmed"]=False
        sector["global_news_rank_adjusted"]=False
    # Other sectors with independent overseas publishing domains receive an
    # early-watch label, not an investment recommendation or sector TOP3 rank.
    emerging=[]
    for sid in SECTORS:
        if sid in sector_ids:continue
        relevant=[x for x in valid if x["sector_id"]==sid and
                  seen_time(x["seen_at_utc"])>=now-timedelta(hours=48)]
        domains={x["publisher_domain"] for x in relevant}
        if len(domains)>=2:
            emerging.append(dict(sector_id=sid,foreign_article_sample=len(relevant),
              independent_publishers=len(domains),sources=relevant[:2],
              status="WORLD_NEWS_EARLY_REVIEW_ONLY",
              trade_approval="NO"))
    emerging.sort(key=lambda r:(-r["independent_publishers"],
                                -r["foreign_article_sample"],r["sector_id"]))
    macro=[x for x in valid if x["sector_id"] in MACRO][:4]
    out["sector_top3"]=sector_list
    out["foreign_news_source_status"]=gate
    out["foreign_news_collected_at_utc"]=audit.get("collected_at_utc") if allowed else None
    out["global_early_watch_outside_top3"]=emerging[:3]
    out["global_macro_observations"]=macro
    out["global_news_sector_rank_adjusted"]=False
    out["global_positive_catalysts_verified"]=0
    out["report_not_real_time_after_close"]=True
    out["decision"]="CASH"
    out["trade_approved"]=False
    out["orders_enabled"]=False
    return out

def render(report,existing):
    lines=["","## ④ 해외 선행 뉴스 및 글로벌 환경",
           "","GDELT는 해외 언론의 기사를 검색한 시각을 기록합니다. 원문 최초 보도 시각, 기사 진위, 한국 종목 영향은 아직 검증하지 않았습니다.",
           "해외 뉴스는 섹터 연구 및 장전 주목 후보를 발굴하는 용도입니다. 기사 수만으로 상승 호재 점수나 매수 승인을 부여하지 않습니다.",
           "","해외 수집 상태: "+str(report.get("foreign_news_source_status","UNKNOWN")),""]
    for s in report.get("sector_top3",[]):
        lines.append("### "+str(s.get("name",s.get("sector_id",""))) + " — 해외")
        articles=s.get("global_news_observations") or []
        if not articles:lines.append("- 해당 섹터 해외 뉴스 근거 미확보")
        for a in articles:
            lines.append("- "+render_time(a["seen_at_utc"])+" / "+a["source_country"]+
              " / ["+a["title"].replace("]","）")+"]("+a["url"]+")")
        lines.append("")
    early=report.get("global_early_watch_outside_top3") or []
    lines += ["### TOP3 밖 해외 선행 관찰 (매수 후보 아님)",""]
    if not early:lines.append("- 서로 다른 해외 매체에서 포착한 충분한 최신 단서 없음")
    for r in early:
        lines.append("- "+r["sector_id"]+" : 해외 언론 출처 "+
                     str(r["independent_publishers"])+"곳의 검색 결과. 본문 검증 필요")
        for a in r["sources"]:
            lines.append("  - ["+a["title"].replace("]","）")+"]("+a["url"]+")")
    lines+=["","### 금리·무역·AI·에너지 글로벌 단서",""]
    macro=report.get("global_macro_observations") or []
    if not macro:lines.append("- 확보된 글로벌 거시 뉴스 근거 없음")
    for a in macro:
        lines.append("- "+a["sector_id"]+": "+render_time(a["seen_at_utc"])+" / ["+
                     a["title"].replace("]","）")+"]("+a["url"]+")")
    lines += ["","**해외 기사 최초 보도 여부·국내 선반영 여부·실질 수혜 기업은 미확정입니다. 최종 신규매수: CASH.**",""]
    return existing.rstrip()+"\n"+"\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--report-root",type=Path,default=Path("output"))
    p.add_argument("--news-root",type=Path,default=Path("output"))
    args=p.parse_args()
    source=args.report_root/"sector_first_with_catalysts.json"
    if not source.is_file():
        source=args.report_root/"sector_first_daily_status.json"
    if not source.is_file():
        raise SystemExit("MISSING_SECTOR_FIRST_REPORT")
    base=json.loads(source.read_text(encoding="utf-8"))
    status_file=args.news_root/"global_sector_news_status.json"
    try:
        audit=json.loads(status_file.read_text(encoding="utf-8")) if status_file.is_file() else {}
    except (ValueError,OSError):
        audit={}
    now=datetime.now(timezone.utc)
    merged=combine(base,audit,read_csv(args.news_root/"global_sector_articles.csv"),now)
    args.report_root.mkdir(parents=True,exist_ok=True)
    (args.report_root/"sector_first_global.json").write_text(
        json.dumps(merged,ensure_ascii=False,indent=2),encoding="utf-8")
    old=args.report_root/"sector_first_with_catalysts_mobile.md"
    if not old.is_file():
        old=args.report_root/"sector_first_daily_mobile.md"
    previous=old.read_text(encoding="utf-8") if old.is_file() else "# C3 K100 섹터 분석\n"
    (args.report_root/"sector_first_global_mobile.md").write_text(
        render(merged,previous),encoding="utf-8")
    print(json.dumps(dict(decision=merged["decision"],
      global_status=merged["foreign_news_source_status"],
      overseas_early_watch=len(merged["global_early_watch_outside_top3"]),
      trade_approved=False),ensure_ascii=False))

if __name__=="__main__":
    main()
