#!/usr/bin/env python3
"""C3 v1 immutable archive evidence: SHA, gaps, prior-day flow, entry coverage.
This module is RESEARCH ONLY; it cannot alter ranking, orders, ledger or approval.
Retrospectively re-collected flow is not independently verified PIT vintage.
"""
import argparse,csv,hashlib,io,json,zipfile
from collections import Counter,defaultdict
from pathlib import Path
from c3_selection_first_research import candidate

def sha(b):return hashlib.sha256(b).hexdigest()
def records(data):return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
class Archive:
    def __init__(self,path):
        self.path=Path(path)
        self.zip=zipfile.ZipFile(path) if self.path.is_file() else None
        self.names=set(self.zip.namelist()) if self.zip else None
    def get(self,name):
        if self.zip:
            return self.zip.read(name) if name in self.names else None
        f=self.path/name
        return f.read_bytes() if f.is_file() else None

def entry_touch(bar,low,high,stop,target):
    if bar is None:return "TICKER_SESSION_MISSING"
    if bar["low"]>high or bar["high"]<low:return "PASS_NOT_TOUCHED"
    if bar["open"]<stop:return "GAP_BELOW_STOP"
    if bar["low"]<=stop and bar["high"]>=target:return "STOP_TARGET_ORDER_UNCERTAIN"
    if bar["low"]<=stop:return "STOP_ENTRY_ORDER_UNCERTAIN"
    if bar["high"]>=target:return "TARGET_ENTRY_ORDER_UNCERTAIN"
    return "RANGE_OVERLAP_NOT_FILL"

def consecutive_breakdowns(by_ticker,calendar):
    idx={d:i for i,d in enumerate(calendar)}
    flags=[]
    for ticker,series in by_ticker.items():
        for prev,cur in zip(series,series[1:]):
            if cur["close"]>=1.5*prev["close"] or cur["close"]<=prev["close"]*2/3:
                flags.append((ticker,prev,cur,idx[cur["date"]]-idx[prev["date"]]))
    return flags

def evaluate(root,source,cohort,source_run_id=42914786449):
    root=Path(root);archive=Archive(source)
    st=archive.get("diagnostics/collection_status.json")
    if not st:raise ValueError("MISSING_V18_COLLECTION_PROVENANCE")
    evidence=json.loads(st)
    if evidence.get("asof")!="2026-11-10" or evidence.get("datasets",{}).get("flows",{}).get("status")!="OK":
        raise ValueError("V18_PROVENANCE_OR_FLOWS_NOT_VERIFIED")
    by=defaultdict(list);bydate={};daily_sha={};days=[]
    for folder in sorted(d for d in root.iterdir() if d.is_dir()):
        manifest_path=folder/"krx_v65_collect_status.json"
        if not manifest_path.exists():continue
        manifest=json.loads(manifest_path.read_text())
        if manifest.get("official_dataset_usable") is not True:continue
        date=folder.name
        if manifest.get("asof")!=date:raise ValueError("MANIFEST_DATE_MISMATCH")
        day_symbols=set()
        for market in ("KOSPI","KOSDAQ"):
            filename=folder/(market+"_official.csv")
            data=filename.read_bytes()
            digest=sha(data)
            if digest!=manifest.get("market_file_sha256",{}).get(market):
                raise ValueError("OFFICIAL_ORIGIN_HASH_MISMATCH")
            daily_sha[f"{market}/{date}"]=digest
            for r in records(data):
                if r.get("valid_daily_bar")!="True":continue
                ticker=r["ticker"]
                if ticker in day_symbols:raise ValueError("DUPLICATE_OR_CROSSMARKET_TICKER")
                day_symbols.add(ticker)
                x={"ticker":ticker,"date":date,"market":market}
                for key in ("open","high","low","close","volume","turnover_krw"):
                    x[key]=float(r[key])
                by[ticker].append(x)
                bydate[(ticker,date)]=x
        if day_symbols:days.append(date)
    if len(days)<120:raise ValueError("MINIMUM_HISTORY_NOT_YET_MET")
    for items in by.values():items.sort(key=lambda r:r["date"])
    dayidx={d:i for i,d in enumerate(days)}
    # Read only as-needed ticker/dates; each source copy is hashed, not substituted.
    pxcache={};flowcache={}
    def price_file(day,market):
        key=(day,market)
        if key not in pxcache:
            content=archive.get(f"market/daily_prices/{market}/{day}.csv")
            pxcache[key]=({r["ticker"]:r for r in records(content)},sha(content)) if content else ({},None)
        return pxcache[key]
    def flow_file(day,market,side):
        key=(day,market,side)
        if key not in flowcache:
            content=archive.get(f"market/daily_flows/{market}/{day}_{side}.csv")
            flowcache[key]=({r["ticker"]:r for r in records(content)},sha(content)) if content else ({},None)
        return flowcache[key]
    receipts=defaultdict(list)
    dbytes=archive.get("catalysts/disclosures.csv")
    if dbytes:
        for row in records(dbytes):
            if row.get("ticker") and row.get("receipt_date"):
                receipts[row["ticker"]].append(row)
    ekeys=set()
    selected_price=Counter()
    flow_count=Counter()
    entry=Counter()
    dart_count=0
    source_price_sha={}
    for e in cohort.get("events",[]):
        ticker,date=str(e["ticker"]),str(e["date"])
        if (ticker,date) in ekeys:raise ValueError("DUPLICATE_SELECTED_TICKER_DATE")
        ekeys.add((ticker,date))
        origin=bydate.get((ticker,date))
        if not origin:raise ValueError("MISSING_SELECTED_OFFICIAL_BAR")
        market=origin["market"]
        source_rows,source_digest=price_file(date,market)
        raw=source_rows.get(ticker)
        if raw is None:
            selected_price["MISSING_PYKRX_COMPARISON"]+=1
        else:
            cols=(("open","Open"),("high","High"),("low","Low"),("close","Close"),
                  ("volume","Volume"),("turnover_krw","TurnoverKRW"))
            if all(abs(origin[k]-float(raw[v]))<=0.00001 for k,v in cols):
                selected_price["ALL_SIX_FIELDS_MATCH"]+=1
            else:selected_price["FIELD_MISMATCH"]+=1
            source_price_sha[f"{market}/{date}"]=source_digest
        # The cash-flow data are collected ex post; NEVER use signal-day after-close flows.
        prior=days[max(0,dayidx[date]-5):dayidx[date]]
        for scope in (1,5):
            selected=prior[-scope:]
            if len(selected)!=scope:continue
            complete=True
            for prev_date in selected:
                for kind in ("foreign","institution"):
                    flows,fp=flow_file(prev_date,market,kind)
                    value=flows.get(ticker)
                    if not (value and value.get("date")==prev_date and
                            value.get("market")==market and value.get("unit")=="KRW"):
                        complete=False;break
                if not complete:break
            if complete:flow_count[f"PRIOR_{scope}D_TWO_INVESTORS"]+=1
        dart_count+=any(r["receipt_date"]<date for r in receipts.get(ticker,[]))
        if date<"2026-09-16":continue
        series=by[ticker]
        i=next((i for i,b in enumerate(series) if b["date"]==date),None)
        c=candidate(series,i,{},None) if i is not None else None
        if not c:
            entry["NO_ASOF_ENTRY_RECONSTRUCTION"]+=1
            continue
        entry["ENTRY1_REFERENCE_AVAILABLE"]+=1
        if c.get("entry2_range"):entry["ENTRY2_REFERENCE_AVAILABLE"]+=1
        for n in (1,2,3):
            onward=days[dayidx[date]+1:dayidx[date]+n+1]
            if len(onward)<n:
                entry[f"DAY_{n}_CENSORED"]+=1
                continue
            first=[]
            for d in onward:
                b=bydate.get((ticker,d))
                low,high=c["entry1_range"]
                first.append(entry_touch(b,low,high,c["stop"],c["target1"]))
            if any(a not in ("PASS_NOT_TOUCHED","TICKER_SESSION_MISSING") for a in first):
                entry[f"ENTRY1_OVERLAP_WITHIN_{n}D_NOT_FILL"]+=1
            elif any(a=="TICKER_SESSION_MISSING" for a in first):
                entry[f"ENTRY1_MISSING_BAR_WITHIN_{n}D"]+=1
            else:entry[f"ENTRY1_UNTOUCHED_WITHIN_{n}D"]+=1
            if n==1:entry["DAY1_"+first[0]]+=1
    flags=consecutive_breakdowns(by,days)
    anomal=Counter();source_anomaly_matches=0
    for ticker,prev,cur,market_gap in flags:
        anomal["PREVIOUS_MARKET_DAY" if market_gap==1 else "TICKER_SESSION_GAP"]+=1
        left,_=price_file(prev["date"],prev["market"])
        right,_=price_file(cur["date"],cur["market"])
        a=left.get(ticker);b=right.get(ticker)
        if a and b and abs(float(a["Close"])/float(prev["close"])-1)<1e-8 and abs(float(b["Close"])/float(cur["close"])-1)<1e-8:
            source_anomaly_matches+=1
    return {
        "schema":"C3_FIXED_V1_V18_SOURCE_ENTRY_AUDIT",
        "official_price_days":len(days),
        "official_source_rows":sum(len(v) for v in by.values()),
        "source_v18_run_id":source_run_id,
        "source_archive_asof":evidence["asof"],
        "selected_events":len(ekeys),
        "independent_method_price_comparison":dict(selected_price),
        "prior_market_day_foreign_institution_file_coverage":dict(flow_count),
        "dated_dart_prior_receipt_title_events":dart_count,
        "not_numeric_earnings_confirmation":True,
        "unadjusted_price_discontinuity_count":len(flags),
        "discontinuity_by_market_gap":dict(anomal),
        "cross_source_discontinuity_reproduced":source_anomaly_matches,
        "corporate_action_cause_verified":False,
        "post_sep16_entry_coverage":dict(entry),
        "source_manifest_aggregate_sha256":sha(json.dumps(daily_sha,sort_keys=True).encode()),
        "v18_consulted_price_sha_count":len(source_price_sha),
        "v18_consulted_price_sha_aggregate":sha(json.dumps(source_price_sha,sort_keys=True).encode()),
        "asof_investor_flow_PIT_original_vintage_verified":False,
        "asof_financial_numeric_PIT_verified":False,
        "regular_1530_price_certified":False,
        "volume_and_price_source_agreement_is_not_independent_session_certification":True,
        "same_date_flow_used_for_selection":False,
        "real_execution_or_cost_adjusted_trade_pnl_claimed":False,
        "feature_weights_changed":False,"operating_selection_changed":False,
        "ledger_changed":False,"orders_enabled":False,"trade_approved":False,"decision":"CASH"
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--v18",type=Path,required=True)
    p.add_argument("--cohort",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    result=evaluate(a.root,a.v18,json.loads(a.cohort.read_text()))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("C3_SOURCE_ENTRY_FIXED_V1",json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
