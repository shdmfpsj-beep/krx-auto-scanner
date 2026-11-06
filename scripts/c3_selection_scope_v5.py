"""Dated common-share/industry coverage and selection-only forward records.

Research only: sector descriptions are provider classifications, not an audit of
every subsidiary. Current classifications are NEVER applied to historical signals.
No broker, notification, schedule, or model-promotion calls.
"""
import argparse,csv,gzip,hashlib,json,math,re,statistics
from collections import Counter,defaultdict,deque
from datetime import datetime,timezone
from pathlib import Path

from c3_daily_report_v4 import known_by,digest
from c3_daily_top2_v4 import features,make_plan

FORWARD_START="2026-11-06"
BIO_INDUSTRIES={"제약","생물공학","생명과학도구및서비스"}
BIO_PRODUCTS=("의약","치료제","항암","유전자","진단시약","백신","세포치료",
              "바이오시밀러","항체","임상시험","혈액제제")


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))


def write_csv(path,rows):
    if not rows:raise ValueError("EMPTY_AUDIT_NOT_SUCCESS")
    with Path(path).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)


def unique_index(rows):
    out={}
    for r in rows:
        t=r["ticker"]
        if not re.fullmatch(r"[0-9A-Z]{6}",t):raise ValueError("INVALID_SECURITY_CODE")
        if t in out:raise ValueError("DUPLICATE_SECURITY_CODE")
        out[t]=r
    return out


def classify(price,basic,kind,industry_rows):
    """Require official common proof AND two dated industry sources; never name-guess."""
    if not basic or basic.get("security_group")!="주권" or basic.get("share_kind")!="보통주":
        return "COMMON_SHARE_UNCONFIRMED_OR_SPECIAL"
    if basic["market"]!=price["market"]:return "SECURITY_MARKET_CONFLICT"
    if not kind or not kind.get("industry") or not kind.get("products"):return "KIND_INDUSTRY_OR_BUSINESS_UNVERIFIED"
    if kind["market"]!=price["market"] or kind["listed_date"]>price["asof"]:return "KIND_IDENTITY_OR_LISTING_CONFLICT"
    bio_kind="의약" in kind["industry"] or "생물" in kind["industry"]
    text=kind["products"].upper()
    bio_product=any(s in text for s in BIO_PRODUCTS) or re.search(r"(?<![A-Z])(?:CRO|CDMO)(?![A-Z])",text) is not None
    if bio_kind or bio_product or any(r["sector"] in BIO_INDUSTRIES for r in industry_rows):
        return "PHARMA_BIOTECH_EXCLUDED"
    if "금융 지원" in kind["industry"] and any(s in kind["products"] for s in ("기업인수","합병")):
        return "SPAC_WITHOUT_OPERATING_BUSINESS"
    sectors={r["sector"] for r in industry_rows}
    if len(sectors)!=1:return "SECONDARY_INDUSTRY_MISSING_OR_CONFLICT"
    if any(r["market"]!=price["market"] for r in industry_rows):return "SECONDARY_MARKET_CONFLICT"
    statuses={r.get("krx_tradable_status","") for r in industry_rows}
    if statuses!={"tradable"}:return "CURRENT_KRX_TRADABILITY_UNCONFIRMED"
    return "VERIFIED_NONBIO_COMMON_AS_REPORTED"


def load_sources(latest,basic,scope,known_at):
    latest,basic,scope=map(Path,(latest,basic,scope))
    pm=json.loads((latest/"krx_v65_collect_status.json").read_text())
    bm=json.loads((basic/"krx_basic_v610_status.json").read_text())
    sm=json.loads((scope/"classification_sources.json").read_text())
    receipts=[pm["retrieval_utc"],bm["received_utc"],sm["frozen_at"]]+[r["received_at"] for r in sm["receipts"]]
    for receipt in receipts:
        if not known_by(receipt,known_at):raise ValueError("SOURCE_NOT_YET_KNOWN")
    from c3_market_supply_v11 import source_usable,price_path
    if not source_usable(pm) or not bm["official_base_usable"]:raise ValueError("OFFICIAL_SOURCE_UNAVAILABLE")
    prices=[];basics=[]
    for market in ("KOSPI","KOSDAQ"):
        p=price_path(latest,pm,market);b=basic/(market+"_basic_v610.csv")
        if digest(p)!=pm["market_file_sha256"][market] or digest(b)!=bm["source_file_sha256"][market]:raise ValueError("OFFICIAL_HASH_MISMATCH")
        prices+=read_csv(p);basics+=read_csv(b)
    for name,h in sm["file_sha256"].items():
        if digest(scope/name)!=h:raise ValueError("CLASSIFICATION_HASH_MISMATCH")
    price_index=unique_index(prices);basic_index=unique_index(basics)
    if len(prices)!=pm["official_market_rows"] or any(r["asof"]!=pm["asof"] for r in prices):raise ValueError("PRICE_DATE_OR_COUNT_MISMATCH")
    kind=unique_index(read_csv(scope/"kind_companies.csv"));secondary=defaultdict(list)
    for r in read_csv(scope/"secondary_industries.csv"):secondary[r["ticker"]].append(r)
    return price_index,basic_index,kind,secondary,dict(price=pm,basic=bm,classification=sm)


def current_histories(panel_path,audit_path,prices):
    audit=json.loads(Path(audit_path).read_text())
    if digest(panel_path)!=audit["panel_sha256"]:raise ValueError("PANEL_HASH_MISMATCH")
    day=next(iter(prices.values()))["asof"]
    if day>audit["requested_end"]:raise ValueError("LATEST_WITHOUT_CONTINUOUS_PANEL")
    if any(r["date"]<day for r in audit["missing_market_dates"]):raise ValueError("INTERIOR_MARKET_GAP")
    events={(r["ticker"],r["date"]) for r in audit["reference_rebase_candidates"]}
    tails=defaultdict(lambda:deque(maxlen=90));days=set()
    with gzip.open(panel_path,"rt") as f:
        for r in csv.DictReader(f):
            days.add(r["date"])
            if r["ticker"] in prices and r["date"]<day:tails[r["ticker"]].append(r)
    days=sorted(days|{day});grid={d:i for i,d in enumerate(days)};out={};reasons={}
    for t,p in prices.items():
        rows=list(tails[t])+[dict(p,date=day,tradable=p["valid_daily_bar"],ohlc_valid=p["valid_daily_bar"])];past=[];prev=None
        for r in rows:
            valid=str(r["tradable"])=="True" and str(r["ohlc_valid"])=="True"
            gap=prev is not None and grid[r["date"]]!=grid[prev["date"]]+1
            reset=gap or (t,r["date"]) in events or (prev is not None and r["name"]!=prev["name"])
            values={k:float(r[k]) if r[k] not in (None,"","None") else None for k in ("open","high","low","close","volume","turnover_krw")}
            if prev and values["close"] and prev.get("close") not in (None,"","None","0","0.0"):
                # The latest added day has no old audit's reference-price proof.
                # Never splice a large unresolved price-unit jump into a trend.
                reset=reset or abs(values["close"]/float(prev["close"])-1)>.35
            valid=valid and all(v is not None and math.isfinite(v) for v in values.values())
            valid=valid and 0<values["low"]<=min(values["open"],values["close"])<=max(values["open"],values["close"])<=values["high"] and values["volume"]>0 and values["turnover_krw"]>0
            if reset or not valid:past=[]
            if valid:past.append(dict(values,date=r["date"],name=r["name"],segment=0))
            prev=r
        if len(past)>=65:out[t]=past
        else:reasons[t]="CONTINUOUS_VALID_HISTORY_LT_65"
    return out,reasons


def selection_features(past,market20):
    """Evaluate stock quality BEFORE a pivot, limit, breakout, or stop is required."""
    if len(past)<65:return None
    close=past[-1]["close"];ma20=statistics.mean(b["close"] for b in past[-20:]);ma50=statistics.mean(b["close"] for b in past[-50:])
    r20=100*(close/past[-21]["close"]-1);rs=r20-market20
    if not close>ma20>ma50 or rs<=0:return None
    return dict(return20=r20,rs20=rs,turnover20=statistics.mean(b["turnover_krw"] for b in past[-20:]),close=close)


def rank_stocks(pool,sector_gate=False):
    rows=[r for r in pool if not sector_gate or (r.get("sector_excess20") is not None and r["sector_excess20"]>0)]
    return sorted(rows,key=lambda r:(-r["turnover20"],-r["rs20"],r["ticker"]))[:2]


def freeze_forward(folder,record,registered_at):
    """Exclusive create: future or backdated decisions cannot manufacture PIT proof."""
    now=datetime.fromisoformat(registered_at.replace("Z","+00:00"))
    if now.tzinfo is None:raise ValueError("TIMEZONE_REQUIRED")
    from datetime import timedelta
    day=now.astimezone(timezone(timedelta(hours=9))).date().isoformat()
    if record["decision_date"]!=day:raise ValueError("DECISION_MUST_BE_REGISTERED_TODAY")
    if day<FORWARD_START:raise ValueError("FORWARD_NOT_STARTED")
    if record["price_asof"]>day:raise ValueError("FUTURE_PRICE_SESSION")
    local=now.astimezone(timezone(timedelta(hours=9)))
    if record["price_asof"]==day and (local.hour,local.minute)<(15,30):raise ValueError("SAME_DAY_SOURCE_NOT_YET_COMPLETE")
    if record.get("expected_last_completed_session")!=record["price_asof"]:raise ValueError("STALE_OR_UNVERIFIED_LAST_SESSION")
    if not known_by(record["known_at"],registered_at):raise ValueError("FUTURE_KNOWLEDGE")
    if not record.get("execution_open_at"):raise ValueError("EXPLICIT_EXECUTION_OPEN_REQUIRED")
    opening=datetime.fromisoformat(record["execution_open_at"].replace("Z","+00:00"))
    if opening.tzinfo is None:raise ValueError("TIMEZONE_REQUIRED")
    if now>=opening or opening.astimezone(timezone(timedelta(hours=9))).date().isoformat()<=record["price_asof"]:
        raise ValueError("REGISTRATION_MUST_PRECEDE_NEXT_EXECUTION_OPEN")
    path=Path(folder)/(day+".json");path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x") as f:json.dump(dict(record,registered_at=registered_at),f,ensure_ascii=False,indent=2);f.write("\n")
    return path


def run(panel,audit,latest,basic,scope,known_at,outdir):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    prices,basics,kind,secondary,sources=load_sources(latest,basic,scope,known_at)
    histories,history_fail=current_histories(panel,audit,prices);counts=Counter();rows=[];eligible={};returns=[]
    for t,p in sorted(prices.items()):
        reason=classify(p,basics.get(t),kind.get(t),secondary[t]);counts[reason]+=1
        eligible_history=reason=="VERIFIED_NONBIO_COMMON_AS_REPORTED" and t in histories
        if eligible_history:eligible[t]=histories[t];returns.append(100*(histories[t][-1]["close"]/histories[t][-21]["close"]-1))
        rows.append(dict(ticker=t,name=p["name"],market=p["market"],price_asof=p["asof"],known_at=known_at,
            kind_industry=kind.get(t,{}).get("industry",""),kind_products=kind.get(t,{}).get("products",""),
            secondary_industry=";".join(sorted({r["sector"] for r in secondary[t]})),classification=reason,
            history_ready_65=t in histories,analysis_eligible=eligible_history,history_reason=history_fail.get(t,"")))
    market20=statistics.median(returns) if returns else None;groups=defaultdict(list);sector={}
    for t,bars in eligible.items():groups[secondary[t][0]["sector"]].append(100*(bars[-1]["close"]/bars[-21]["close"]-1))
    for s,values in groups.items():sector[s]=statistics.median(values)-market20 if len(values)>=5 else None
    pool=[]
    for t,bars in sorted(eligible.items()):
        f=selection_features(bars,market20)
        if f is None:continue
        s=secondary[t][0]["sector"]
        pool.append(dict(ticker=t,name=prices[t]["name"],industry=s,sector_members=len(groups[s]),sector_excess20=sector[s],**f))
    base_top=rank_stocks(pool);sector_top=rank_stocks(pool,True)
    for t in sorted({r["ticker"] for r in base_top+sector_top}):
        entry_features,error=features(eligible[t],market20);plans={}
        if entry_features:
            for method in ("PULLBACK","BREAKOUT"):
                p,why=make_plan(t,eligible[t],entry_features,method,"CURRENT_MEDIAN_PROXY_NOT_CERTIFIED_INDEX")
                plans[method]=dict(plan=p,reason=why)
        for row in base_top+sector_top:
            if row["ticker"]==t:row.update(entry_structure_reason=error,entry_plans=plans)
    write_csv(root/"universe_audit.csv",rows)
    result=dict(schema="C3_SELECTION_SCOPE_V5",price_asof=next(iter(prices.values()))["asof"],known_at=known_at,
        price_rows=len(prices),classified_nonbio_common=counts["VERIFIED_NONBIO_COMMON_AS_REPORTED"],analysis_eligible=len(eligible),
        history_excluded_after_classification=counts["VERIFIED_NONBIO_COMMON_AS_REPORTED"]-len(eligible),classification_counts=dict(counts),
        selection_candidates=len(pool),market_median20_pct=market20,sector_group_count=len(groups),
        research_base_top2=base_top,research_sector_gate_top2=sector_top,candidate_pool=pool,
        classification_known_at=sources["classification"]["frozen_at"],classification_historical_pit_verified=False,
        historical_sector_gate_tested=False,selection_profitability_improved=False,unseen_completed={str(h):0 for h in (5,10,20)},
        current_action="CASH",approved_top2=[],buy_prices=None,structural_stops=None,resistances=None,
        source_hashes=dict(panel=digest(panel),audit=digest(audit),classification=digest(Path(scope)/"classification_sources.json"),
            price_manifest=digest(Path(latest)/"krx_v65_collect_status.json"),basic_manifest=digest(Path(basic)/"krx_basic_v610_status.json"),
            selection_code=digest(__file__),entry_stop_code=digest(Path(__file__).with_name("c3_daily_top2_v4.py"))),
        caveats=["PRICE_SESSION_AND_SOURCE_RECEIPT_DATE_ARE_DISTINCT","PROVIDER_REPORTED_BUSINESS_NOT_ALL_SUBSIDIARIES_AUDITED","CURRENT_INDUSTRIES_NOT_BACKFILLED_TO_HISTORY",
                 "REGULAR_ONLY_PRICE_SCOPE_UNCERTIFIED","NO_COMPLETED_NEW_FORWARD_WINDOW"],orders_enabled=False)
    (root/"selection_report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    summary={k:v for k,v in result.items() if k!="candidate_pool"}
    summary["universe_audit_sha256"]=digest(root/"universe_audit.csv")
    (root/"scope_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    forward=dict(schema="C3_SELECTION_FORWARD_V5",first_decision_not_before=FORWARD_START,
        frozen_rules=dict(base_rank="UPTREND_POSITIVE_RS_THEN_TURNOVER20",sector_variant="SAME_RANK_AND_SECTOR_MEDIAN20_EXCESS_GT_0_MIN_5_MEMBERS",
            comparison_cadences=["FIXED26","DAILY"],entry_and_stop="UNCHANGED_C3_DAILY_V4",source_knowledge_must_precede_decision=True,
            registration_must_precede_explicit_execution_open=True),
        current_registration="ANALYSIS_ONLY_USE_EXPLICIT_APPEND_ONLY_REGISTRATION_AFTER_FORWARD_START",completed_horizons={str(h):0 for h in (5,10,20)},
        registered_snapshots=[],automatic_schedule_created=False,orders_enabled=False)
    (root/"forward_protocol.json").write_text(json.dumps(forward,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ("price_rows","classified_nonbio_common","analysis_eligible","classification_counts","selection_candidates","current_action")},ensure_ascii=False))
    return result


def main():
    p=argparse.ArgumentParser()
    for name in ("panel","audit","latest","basic","scope","known-at","outdir"):p.add_argument("--"+name,required=True)
    p.add_argument("--register-forward",default="");p.add_argument("--expected-last-session",default="");p.add_argument("--execution-open-at",default="")
    a=p.parse_args();record=run(a.panel,a.audit,a.latest,a.basic,a.scope,a.known_at,a.outdir)
    if a.register_forward:
        from datetime import timedelta
        now=datetime.now(timezone.utc);day=now.astimezone(timezone(timedelta(hours=9))).date().isoformat()
        freeze_forward(a.register_forward,dict(record,decision_date=day,expected_last_completed_session=a.expected_last_session,
            execution_open_at=a.execution_open_at),now.isoformat())


if __name__=="__main__":main()
