#!/usr/bin/env python3
"""Free global industry & macro news discovery via GDELT DOC 2.0.

Research-only. A GDELT seen timestamp is not guaranteed to be the original
publication time. No automatic positive-catalyst score or trade signal.
No API secret or paid services. Safe to run on GitHub-hosted Actions.
"""
import argparse
import csv
import json
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

API="https://api.gdeltproject.org/api/v2/doc/doc"
# IDs deliberately match config/sector_evidence_v18.json embedded in workflow.
# Multi-country English queries: GDELT searches machine-translated global content.
SECTORS={
 "SEMICON":'"semiconductor equipment" OR "chip export controls" OR "advanced packaging"',
 "AUTO":'"electric vehicle production" OR "auto tariffs" OR "automotive supply chain"',
 "BANK":'"bank capital" OR "bank earnings" OR "central bank rates"',
 "SECURITIES":'"equity trading volumes" OR "stock exchange reforms" OR "brokerage earnings"',
 "INSURANCE":'"insurance capital" OR "reinsurance prices" OR "insurance earnings"',
 "CONSTRUCTION":'"infrastructure investment" OR "construction contracts" OR "building materials"',
 "IT":'"AI data center" OR "cloud infrastructure" OR "artificial intelligence spending"',
 "CONTENT":'"gaming industry" OR "streaming content" OR "music exports"',
 "ENERGY_CHEM":'"crude oil supply" OR "petrochemical margins" OR "LNG investment"',
 "STEEL":'"steel tariffs" OR "steel demand" OR "steel exports"',
 "RENEWABLE":'"solar power contracts" OR "wind power investment" OR "energy storage"',
 "SHIP":'"shipbuilding orders" OR "LNG carrier orders" OR "shipyard investment"',
 "ROBOT":'"industrial robotics orders" OR "humanoid robots" OR "factory automation"',
 "BATTERY":'"battery manufacturing" OR "lithium supply" OR "EV battery orders"',
 "POWER":'"power grid investment" OR "transformer orders" OR "electricity transmission"',
 "DEFENSE":'"defense procurement" OR "missile contract" OR "military exports"'
}
MACRO={
 "GLOBAL_AI":'"AI infrastructure investment" OR "GPU capital expenditure"',
 "GLOBAL_RATES":'"Federal Reserve policy" OR "US Treasury yields"',
 "GLOBAL_TRADE":'"semiconductor export restrictions" OR "global tariff policy"',
 "GLOBAL_ENERGY":'"crude oil supply disruption" OR "global LNG prices"'
}
COLS=("sector_id","market_scope","seen_at_utc","title","url","publisher_domain",
      "source_country","language","query","source","evidence_status",
      "positive_catalyst_verified","korean_stock_impact_verified")

def seen_time(s):
    s=str(s or "").strip()
    for fmt in ("%Y%m%dT%H%M%SZ","%Y%m%d%H%M%S","%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt=datetime.strptime(s,fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        except ValueError:
            pass
    return None

def safe_url(s):
    s=str(s or "").strip()
    if len(s)>1200 or any(x in s for x in " \r\n<>[]()\\"):
        return ""
    try:
        u=urlsplit(s)
    except ValueError:
        return ""
    if u.scheme!="https" or not u.hostname or u.username or u.password:
        return ""
    host=u.hostname.lower()
    if (host=="localhost" or host.endswith(".local") or host.startswith("127.")
        or host.startswith("10.") or host.startswith("192.168.")
        or host.startswith("172.16.")):
        return ""
    return s

def title_text(s):
    return re.sub(r"\s+"," ",str(s or "").replace("|","/").replace("[","(").replace("]",")")).strip()[:150]

def headline_signature(title):
    """Exact-normalized headline fingerprint to discount newswire syndication."""
    words=re.findall(r"[a-z0-9가-힣]+",str(title or "").casefold())
    return " ".join(words[:24])

def build_url(query,start,end):
    params={
       "query":"("+query+")",
       "mode":"artlist","format":"json","sort":"datedesc","maxrecords":"30",
       "startdatetime":start.strftime("%Y%m%d%H%M%S"),
       "enddatetime":end.strftime("%Y%m%d%H%M%S")
    }
    return API+"?"+urlencode(params)

def unpack(payload,sector,query,end,days=3):
    if not isinstance(payload,dict) or not isinstance(payload.get("articles",[]),list):
        raise ValueError("GLOBAL_NEWS_SCHEMA_MISMATCH")
    fresh=[]
    floor=end-timedelta(days=days)
    for a in payload.get("articles",[]):
        if not isinstance(a,dict):
            continue
        seen=seen_time(a.get("seendate"))
        if seen is None or not floor<=seen<=end:
            continue
        country=str(a.get("sourcecountry","")).strip()
        # Explicit non-Korean origins only; don't invent country from language.
        if not country or country.casefold() in ("south korea","republic of korea","korea, republic of"):
            continue
        url=safe_url(a.get("url"))
        title=title_text(a.get("title"))
        if not url or len(title)<12:
            continue
        domain=(urlsplit(url).hostname or "").lower()
        fresh.append(dict(
          sector_id=sector,market_scope="GLOBAL_MACRO" if sector.startswith("GLOBAL_") else "GLOBAL_SECTOR",
          seen_at_utc=seen.isoformat(timespec="seconds"),title=title,url=url,
          publisher_domain=domain,source_country=country,
          language=str(a.get("language",""))[:32],query=query,
          source="GDELT_DOC_2_ARTLIST",evidence_status="FOREIGN_NEWS_DISCOVERY_NOT_CONTENT_VERIFIED",
          positive_catalyst_verified="NO",korean_stock_impact_verified="NO"))
    # Deduplicate URL across this query, prefer most recently seen.
    uniq={r["url"]:r for r in fresh}
    return sorted(uniq.values(),key=lambda r:(r["seen_at_utc"],r["url"]),reverse=True)[:12]

def retrieve(url,timeout=18):
    request=Request(url,headers={"User-Agent":"C3-K100-FreeGlobalEvidence/1.0 (research only)",
                                 "Accept":"application/json"})
    with urlopen(request,timeout=timeout) as response:
        blob=response.read(1500000)
    return json.loads(blob.decode("utf-8-sig"))

def collect(end,fetch=retrieve,limit=None,sleep_seconds=1.5):
    start=end-timedelta(hours=72)
    # For completed historical PIT backtests this collector cannot be
    # substituted for archived snapshots: historical downloads unsupported.
    queries={**SECTORS,**MACRO}
    if limit is not None:
        queries=dict(list(queries.items())[:limit])
    rows=[]
    errors={}
    states={}
    for sector,query in queries.items():
        url=build_url(query,start,end)
        try:
            got=unpack(fetch(url),sector,query,end)
            states[sector]={"status":"OK","rows":len(got)}
            rows.extend(got)
        except Exception as err:
            # Do not put response bodies or URLs into the audit file.
            states[sector]={"status":"FAILED","rows":0}
            errors[sector]=type(err).__name__
        if sleep_seconds:
            time.sleep(sleep_seconds)
    bysector=defaultdict(list)
    for r in rows:bysector[r["sector_id"]].append(r)
    counts={}
    for sid in queries:
        arr=bysector.get(sid,[])
        recent=[x for x in arr if (end-seen_time(x["seen_at_utc"])).total_seconds()<=48*3600]
        publishers={x["publisher_domain"] for x in recent}
        countries={x["source_country"] for x in recent}
        unique_headlines={headline_signature(x["title"]) for x in recent}
        counts[sid]={"articles_observed":len(arr),
            "recent_48h_observed":len(recent),
            "independent_domains_48h":len(publishers),
            "distinct_headlines_48h":len(unique_headlines),
            "source_countries_48h":len(countries),
            "early_watch":len(publishers)>=2 and len(unique_headlines)>=2,
            "positive_catalyst_verified":False,
            "relevance_to_korean_equities_verified":False}
    audit={"schema":"global_sector_discovery_v1","collected_at_utc":end.isoformat(timespec="seconds"),
      "search_window_hours":72,"publisher_timestamp_semantics":"GDELT_FIRST_SEEN_NOT_ORIGINAL_PUBLICATION",
      "no_keys_required":True,"requests_attempted":len(queries),
      "queries_succeeded":sum(x["status"]=="OK" for x in states.values()),
      "articles_observed":len(rows),"query_states":states,
      "errors":errors,"sector_observations":counts,
      "trade_approved":False,"sector_100_score_verified":False,"decision":"CASH",
      "note":"Counts are sampled search results, not the total global press volume; early_watch is an investigation priority, NOT a positive catalyst or buy signal."}
    return rows,audit

def save(out,rows,audit):
    out.mkdir(parents=True,exist_ok=True)
    with (out/"global_sector_articles.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    (out/"global_sector_news_status.json").write_text(
       json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("output"))
    p.add_argument("--limit",type=int,default=None)
    p.add_argument("--sleep",type=float,default=1.5)
    a=p.parse_args()
    now=datetime.now(timezone.utc)
    rows,audit=collect(now,limit=a.limit,sleep_seconds=max(0,a.sleep))
    save(a.out,rows,audit)
    print(json.dumps({k:audit[k] for k in ("collected_at_utc","queries_succeeded",
        "requests_attempted","articles_observed","decision")},ensure_ascii=False))
    # Failed source queries do not fail the workflow: report preserves errors + CASH.
if __name__=="__main__":
    main()
