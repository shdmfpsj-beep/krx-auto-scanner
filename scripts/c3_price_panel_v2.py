"""Dated official KOSPI/KOSDAQ research panel; never a trading approval.

Uses the existing read-only KRX connection. Retains contemporaneous daily
membership, halts, share counts and implied reference-price changes instead
of filtering the universe by today's winners. Session scope stays unknown.
"""
import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import date,datetime,timezone,timedelta
from pathlib import Path

from krx_official_eod_v65 import fetch_official,MARKETS,price

FIELDS=("date","market","ticker","name","open","high","low","close","volume",
        "turnover_krw","change","change_pct","listed_shares","market_cap","tradable",
        "halt_like","ohlc_valid","source_response_sha256")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalized_rows(payload,day,market,response_sha):
    if not isinstance(payload,dict) or not isinstance(payload.get("OutBlock_1"),list):
        raise ValueError("INVALID_OFFICIAL_PAYLOAD")
    if not payload["OutBlock_1"]:
        raise ValueError("EMPTY_OFFICIAL_RESPONSE_UNRESOLVED")
    rows=[];seen=set()
    for raw in payload["OutBlock_1"]:
        if not isinstance(raw,dict):
            raise ValueError("INVALID_OFFICIAL_RECORD")
        code=str(raw.get("ISU_CD","")).strip()
        if not re.fullmatch(r"[A-Z0-9]{6}",code):
            raise ValueError("UNSUPPORTED_SECURITY_ID_NOT_SILENTLY_DROPPED")
        if code in seen:
            raise ValueError("DUPLICATE_SECURITY_DATE")
        seen.add(code)
        if str(raw.get("BAS_DD","")).replace("-","")!=day.replace("-",""):
            raise ValueError("OFFICIAL_DATE_MISMATCH")
        names={"open":"TDD_OPNPRC","high":"TDD_HGPRC","low":"TDD_LWPRC","close":"TDD_CLSPRC",
               "volume":"ACC_TRDVOL","turnover_krw":"ACC_TRDVAL","listed_shares":"LIST_SHRS","market_cap":"MKTCAP"}
        row={k:price(raw.get(v)) for k,v in names.items()}
        # Delta and return may be negative. The legacy nonnegative parser
        # must not turn negative changes into missing corporate-action evidence.
        for key,col in (("change","CMPPREVDD_PRC"),("change_pct","FLUC_RT")):
            try:
                value=float(str(raw.get(col,"")).replace(",",""))
                row[key]=value if math.isfinite(value) else None
            except (ValueError,TypeError):
                row[key]=None
        o,h,l,c,v=(row[k] for k in ("open","high","low","close","volume"))
        valid=all(x is not None and math.isfinite(x) for x in (o,h,l,c,v)) and (
            0<l<=min(o,c)<=max(o,c)<=h and v>=0)
        halted=(c is not None and c>0 and v==0 and all(x is not None and x>=0 for x in (o,h,l)))
        row.update(date=day,market=market,ticker=code,name=str(raw.get("ISU_NM","")),
                   ohlc_valid=valid,halt_like=halted,tradable=bool(valid and v>0),
                   source_response_sha256=response_sha)
        rows.append(row)
    return rows


def reference_event(previous,current,tolerance=.000001):
    """A dated rebase candidate, not a verified split/bonus/dividend label."""
    if current.get("change") is None or not previous.get("close") or not current.get("close"):
        return None
    implied=current["close"]-current["change"]
    if implied<=0:
        return dict(date=current["date"],ticker=current["ticker"],kind="INVALID_REFERENCE_PRICE")
    factor=implied/previous["close"]
    if abs(factor-1)<=tolerance:
        return None
    shares_before=previous.get("listed_shares");shares_after=current.get("listed_shares")
    shares_ratio=shares_after/shares_before if shares_before and shares_after else None
    candidate=("SHARE_COUNT_REBASE_CANDIDATE" if shares_ratio and abs(shares_ratio-1)>.01 and abs(factor*shares_ratio-1)<.02
               else "REFERENCE_PRICE_REBASE_UNRESOLVED")
    return dict(date=current["date"],ticker=current["ticker"],kind=candidate,
                previous_close=previous["close"],implied_previous_reference=implied,
                factor_known_on_event_date=factor,share_count_ratio=shares_ratio,
                corporate_action_confirmed=False,
                event_must_not_adjust_earlier_decisions=True)


def audit_panel(rows,sessions,responses):
    if sessions!=sorted(set(sessions)) or not sessions:
        raise ValueError("INVALID_EXPECTED_SESSION_GRID")
    expected={(d,m) for d in sessions for m in MARKETS}
    success={(r["date"],r["market"]) for r in responses if r["status"]=="OK"}
    missing=sorted(expected-success)
    seen=set();invalid=[];halted=0;by_ticker={};membership={}
    for row in rows:
        key=(row["date"],row["ticker"])
        if key in seen:
            raise ValueError("DUPLICATE_PANEL_BAR_OR_CROSS_MARKET_SECURITY")
        seen.add(key)
        if row["date"] not in sessions:
            raise ValueError("UNEXPECTED_PRICE_DATE")
        membership.setdefault(row["date"],set()).add(row["ticker"])
        if not row["ohlc_valid"] and not row["halt_like"]:
            invalid.append(dict(date=row["date"],ticker=row["ticker"],reason="INVALID_OHLCV"))
        halted+=int(row["halt_like"])
        by_ticker.setdefault(row["ticker"],[]).append(row)
    rebases=[];name_changes=[];gaps=[];transitions=[]
    complete_dates=[d for d in sessions if all((d,m) in success for m in MARKETS)]
    grid_index={d:i for i,d in enumerate(sessions)}
    for ticker,bars in sorted(by_ticker.items()):
        bars.sort(key=lambda r:r["date"])
        for prev,cur in zip(bars,bars[1:]):
            event=reference_event(prev,cur)
            if event:rebases.append(event)
            if cur["name"]!=prev["name"]:
                name_changes.append(dict(ticker=ticker,date=cur["date"],previous=prev["name"],current=cur["name"]))
            absent=sessions[grid_index[prev["date"]]+1:grid_index[cur["date"]]]
            if absent:gaps.append(dict(ticker=ticker,before=prev["date"],after=cur["date"],missing_dates=absent))
    for before,after in zip(complete_dates,complete_dates[1:]):
        a,b=membership.get(before,set()),membership.get(after,set())
        if a!=b:
            transitions.append(dict(date=after,newly_observed=sorted(b-a),no_longer_observed=sorted(a-b),
                                    listing_or_delisting_cause_verified=False))
    return dict(schema="C3_OFFICIAL_PRICE_PANEL_AUDIT_V2",rows=len(rows),tickers=len(by_ticker),
                expected_sessions=len(sessions),complete_market_dates=len(complete_dates),
                missing_market_dates=[dict(date=d,market=m) for d,m in missing],
                invalid_rows=invalid,halt_like_rows=halted,
                reference_rebase_candidates=rebases,name_changes=name_changes,
                internal_security_gaps=gaps,membership_transitions=transitions,
                daily_membership_from_dated_official_responses=True,
                historical_industry_classification_verified=False,
                delisting_and_code_change_causes_verified=False,
                candidate_session_grid_is_official_calendar=False,
                regular_only_certified=False,corporate_actions_fully_verified=False,
                dated_eod_consistency_passed=not missing and not invalid,
                dataset_usable_for_strict_backtest=False,
                source_basis="OFFICIAL_DATED_EOD_UNADJUSTED_DECLARATION_NOT_SESSION_CERTIFICATION",
                orders_enabled=False,trade_approved=False)


class RequestPacer:
    def __init__(self,interval=1.):
        self.interval=interval;self.next_time=0.;self.lock=threading.Lock()
    def wait(self):
        with self.lock:
            now=time.monotonic();delay=max(0.,self.next_time-now)
            self.next_time=max(now,self.next_time)+self.interval
        if delay:time.sleep(delay)


def collect_panel(sessions,outdir,auth_key,*,workers=2,interval=1.,fetcher=fetch_official):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    if not auth_key:
        raise ValueError("AUTH_KEY_NOT_CONNECTED")
    pacer=RequestPacer(interval);all_rows=[];responses=[];stop=threading.Event()
    def request(task):
        day,market=task;started=utc_now()
        if stop.is_set():
            return [],dict(date=day,market=market,started_at=started,received_at=utc_now(),status="NOT_REQUESTED_AFTER_CIRCUIT_BREAK",rows=0)
        try:
            pacer.wait()
            payload,digest=fetcher(MARKETS[market],day,auth_key)
            normalized=normalized_rows(payload,day,market,digest)
            meta=dict(date=day,market=market,endpoint=MARKETS[market],started_at=started,
                      received_at=utc_now(),source_response_sha256=digest,status="OK",rows=len(normalized))
            return normalized,meta
        except ValueError as exc:
            # Only allowlisted machine labels; never echo HTTP/proxy content.
            label=str(exc)
            if not re.fullmatch(r"[A-Z0-9_]{1,100}",label):label="UNCLASSIFIED_SOURCE_ERROR"
            if label in ("KRX_AUTH_OR_SERVICE_APPROVAL_MISSING","KRX_SERVICE_HTTP_ERROR","KRX_SERVICE_NETWORK_UNAVAILABLE"):
                stop.set()
            return [],dict(date=day,market=market,started_at=started,received_at=utc_now(),status=label,rows=0)
        except Exception:
            return [],dict(date=day,market=market,started_at=started,received_at=utc_now(),status="UNCLASSIFIED_SOURCE_ERROR",rows=0)
    tasks=[(d,m) for d in sessions for m in MARKETS]
    if len(tasks)>800:
        raise ValueError("REQUEST_BUDGET_EXCEEDED")
    # Confirm representative old/recent dates before launching a large batch.
    seed=list(dict.fromkeys([(sessions[0],m) for m in MARKETS]+[(sessions[-1],m) for m in MARKETS]))
    completed=set()
    for task in seed:
        rows,meta=request(task);all_rows.extend(rows);responses.append(meta);completed.add(task)
        if meta["status"] not in ("OK","EMPTY_OFFICIAL_RESPONSE_UNRESOLVED"):
            break
    if not any(r["status"]=="OK" for r in responses):
        (root/"responses.json").write_text(json.dumps(responses,indent=2))
        raise ValueError("NO_OFFICIAL_SEED_RESPONSE")
    fatal=stop.is_set() or any(r["status"]=="UNCLASSIFIED_SOURCE_ERROR" for r in responses)
    remaining=[] if fatal else [t for t in tasks if t not in completed]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(request,t):t for t in remaining}
        for n,future in enumerate(as_completed(futures),start=len(completed)+1):
            rows,meta=future.result();all_rows.extend(rows);responses.append(meta)
            if n%40==0:
                print(json.dumps(dict(completed_requests=n,total_requests=len(tasks),rows=len(all_rows))),flush=True)
    all_rows.sort(key=lambda r:(r["date"],r["market"],r["ticker"]))
    responses.sort(key=lambda r:(r["date"],r["market"]))
    path=root/"official_panel.csv.gz"
    with gzip.open(path,"wt",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,lineterminator="\n");w.writeheader();w.writerows(all_rows)
    (root/"responses.json").write_text(json.dumps(responses,indent=2)+"\n")
    audit=audit_panel(all_rows,sessions,responses)
    audit.update(panel_sha256=fingerprint(path),start=sessions[0],requested_end=sessions[-1],
                 received_at=utc_now(),request_count=len(responses),max_request_budget=800,
                 checkpoint_source_code_sha256=fingerprint(__file__))
    (root/"quality_audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:audit[k] for k in ("rows","tickers","complete_market_dates","request_count","dated_eod_consistency_passed","dataset_usable_for_strict_backtest")}),flush=True)
    return audit


def main():
    p=argparse.ArgumentParser();p.add_argument("--sessions",required=True)
    p.add_argument("--start",default="2025-05-02");p.add_argument("--end",required=True)
    p.add_argument("--outdir",required=True);p.add_argument("--interval",type=float,default=1.)
    a=p.parse_args()
    today=datetime.now(timezone(timedelta(hours=9))).date()
    if date.fromisoformat(a.end)>=today:
        raise ValueError("END_MUST_PRECEDE_KST_TODAY")
    source=json.loads(Path(a.sessions).read_text());days=[d for d in source["dates"] if a.start<=d<=a.end]
    if a.end not in days:days.append(a.end)
    if days!=sorted(set(days)):raise ValueError("INVALID_SESSION_GRID")
    audit=collect_panel(days,a.outdir,os.environ.get("KRX_AUTH_KEY"),interval=a.interval)
    if not audit["dataset_usable_for_strict_backtest"]:
        print("DATA_QUALITY_BLOCKED_STRICT_BACKTEST",flush=True)


if __name__=="__main__":
    main()
