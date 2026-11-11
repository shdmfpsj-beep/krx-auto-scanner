#!/usr/bin/env python3
"""Read-only official KRX daily history builder, no live orders or ledger writes."""
import argparse,csv,json,os,time,hashlib
from collections import defaultdict
from datetime import date,timedelta
from pathlib import Path
from krx_official_eod_v65 import collect
from c3_three_entry_replay import replay,HORIZONS,MODELS

def weekdays(end,n):
    days=[];d=date.fromisoformat(end)
    while len(days)<n:
        if d.weekday()<5:days.append(d.isoformat())
        d-=timedelta(days=1)
    return list(reversed(days))
def history(root,days):
    rows=[];availability=[];seen=set()
    for day in days:
        folder=root/day
        m=folder/"krx_v65_collect_status.json"
        if not m.exists():availability.append(day);continue
        status=json.loads(m.read_text())
        if not status.get("official_dataset_usable") or status.get("asof")!=day:
            availability.append(day);continue
        for market in ("KOSPI","KOSDAQ"):
            fp=folder/(market+"_official.csv")
            assert fp.is_file() and hashlib.sha256(fp.read_bytes()).hexdigest()==status["market_file_sha256"][market], "RESTORED_OFFICIAL_FILE_HASH_MISMATCH"
            with fp.open(encoding="utf-8-sig",newline="") as f:
                for r in csv.DictReader(f):
                    if r["valid_daily_bar"]!="True":continue
                    key=(day,r["ticker"])
                    if key in seen:raise ValueError("DUPLICATE_DATE_TICKER_IN_OFFICIAL_HISTORY")
                    seen.add(key)
                    if r["asof"]!=day or r["market"]!=market:raise ValueError("OFFICIAL_ROW_DATE_OR_MARKET_MISMATCH")
                    rows.append(dict(ticker=r["ticker"],date=day,
                        **{k:r[k] for k in ("open","high","low","close","volume")}))
    return rows,availability
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--end",required=True)
    p.add_argument("--sessions",type=int,default=160)
    p.add_argument("--root",type=Path,default=Path("output/official_history"))
    p.add_argument("--out",type=Path,default=Path("output/replay"))
    p.add_argument("--collect",action="store_true")
    p.add_argument("--max-requests",type=int,default=12)
    a=p.parse_args()
    if a.sessions<120:raise ValueError("MINIMUM_120_SESSIONS")
    days=weekdays(a.end,a.sessions)
    a.root.mkdir(parents=True,exist_ok=True);a.out.mkdir(parents=True,exist_ok=True)
    fetched=0
    if a.collect:
        for day in days:
            existing=a.root/day/"krx_v65_collect_status.json"
            if existing.exists():
                old=json.loads(existing.read_text())
                if old.get("official_dataset_usable") and old.get("asof")==day:continue
                # Keep failed/holiday response as evidence, but do not retry every batch.
                if old.get("status") in ("OFFICIAL_RESPONSE_MISSING_OR_EMPTY_OUTBLOCK","OFFICIAL_NO_SHORT_SECURITY_IDS_TO_JOIN"):continue
            if fetched>=a.max_requests:break
            collect(day,a.root/day,os.environ.get("KRX_AUTH_KEY"))
            fetched+=1
            time.sleep(.3)
    rows,missing=history(a.root,days)
    counts=defaultdict(int)
    for r in rows:counts[r["ticker"]]+=1
    # Require 120 actual observations per ticker and 120 distinct market dates.
    usable={t for t,n in counts.items() if n>=120}
    actual_dates={r["date"] for r in rows}
    qualified=[r for r in rows if r["ticker"] in usable]
    quality={"min_120_distinct_market_days":len(actual_dates)>=120,
             "all_tickers_120_observations":bool(usable),
             "file_sha256_and_date_checked":True,
             "duplicate_date_ticker_checked":True,
             "official_holiday_calendar_verified":False,
             "corporate_actions_adjusted_verified":False,
             "delisted_issuers_included_verified":False,
             "historical_point_in_time_universe_verified":False,
             "regular_1530_session_verified":False}
    performance_publication_allowed=all(quality.values())
    # Fail closed: never compute or publish model P&L until every quality gate passes.
    events=replay(qualified) if performance_publication_allowed else []
    empty_responses=[];not_attempted=[];failed_responses=[]
    for day in missing:
        status_path=a.root/day/"krx_v65_collect_status.json"
        if not status_path.exists():not_attempted.append(day)
        else:
            state=json.loads(status_path.read_text())
            if state.get("status") in ("OFFICIAL_RESPONSE_MISSING_OR_EMPTY_OUTBLOCK","OFFICIAL_NO_SHORT_SECURITY_IDS_TO_JOIN"):
                empty_responses.append(day)  # holiday CANDIDATE, not certified holiday
            else:failed_responses.append({"date":day,"status":state.get("status")})
    summary={"quality_gates":quality,"performance_publication_allowed":performance_publication_allowed,
             "performance_blockers":[k for k,v in quality.items() if not v],
             "requested_weekdays":len(days),"observed_market_dates":len(actual_dates),
             "unattempted_days":not_attempted,"empty_response_holiday_candidates":empty_responses,
             "failed_response_days":failed_responses,
             "missing_or_unusable_days":missing,"qualified_tickers":len(usable),
             "historical_rows":len(rows),"research_events":len(events),
             "source":"OFFICIAL_KRX_EOD_SESSION_SCOPE_UNCERTIFIED",
             "survivorship_bias_resolved":False,"corporate_actions_adjusted":False,
             "net_cost_assumption_pct":0.65,"overlap_lockout_sessions":20,
             "vintage_pit_verified":False,"regular_1530_certified":False,
             "trade_approved":False,"orders_enabled":False,"decision":"CASH",
             "status":"RESEARCH_HISTORY_INCOMPLETE" if len(actual_dates)<120 else "PERFORMANCE_BLOCKED_UNCERTIFIED_QUALITY"}
    (a.out/"official_120d_replay_status.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    (a.out/"official_120d_replay_events.json").write_text(json.dumps(events,ensure_ascii=False))
    print("OFFICIAL_120D_REPLAY",json.dumps({k:v for k,v in summary.items() if k!="missing_or_unusable_days"},ensure_ascii=False))
if __name__=="__main__":main()
