#!/usr/bin/env python3
"""Research only: dated KRX issuer metadata pairs on adjacent-session >50%/33% moves.
This identifies possible par-value/share-count change, not official action filing.
Historical API re-query alone is NOT original point-in-time issuance proof.
"""
import argparse,csv,hashlib,json,os,re,time,urllib.request,urllib.error
from collections import Counter,defaultdict
from pathlib import Path

ENDPOINTS={"KOSPI":"sto/stk_isu_base_info","KOSDAQ":"sto/ksq_isu_base_info"}

def digest(b):return hashlib.sha256(b).hexdigest()
def num(v):
    s=str(v or "").replace(",","")
    if re.fullmatch(r"\d+(\.\d+)?",s):return float(s)
    return None

def read_adjacent(root):
    days=[];by=defaultdict(list)
    for d in sorted(root.iterdir()):
        if not d.is_dir():continue
        status=d/"krx_v65_collect_status.json"
        if not status.exists():continue
        mf=json.loads(status.read_text())
        if not mf.get("official_dataset_usable"):continue
        if mf.get("asof")!=d.name:raise ValueError("MANIFEST_DATE_MISMATCH")
        days.append(d.name)
        for market in ENDPOINTS:
            file=d/(market+"_official.csv")
            if digest(file.read_bytes())!=mf.get("market_file_sha256",{}).get(market):
                raise ValueError("PRICE_MANIFEST_SHA_MISMATCH")
            with file.open(encoding="utf-8-sig",newline="") as f:
                for row in csv.DictReader(f):
                    if row.get("valid_daily_bar")=="True":
                        by[row["ticker"]].append({"date":d.name,"market":market,
                              "close":float(row["close"])})
    idx={d:i for i,d in enumerate(days)}
    events=[];gaps=0
    for ticker,series in by.items():
        series.sort(key=lambda x:x["date"])
        for a,b in zip(series,series[1:]):
            if b["close"]>=a["close"]*1.5 or b["close"]<=a["close"]*(2/3):
                if idx[b["date"]]-idx[a["date"]]==1:
                    if a["market"]!=b["market"]:raise ValueError("CHANGED_MARKET_UNVERIFIED")
                    events.append({"ticker":ticker,"market":b["market"],
                        "prev_date":a["date"],"date":b["date"],
                        "close_ratio":round(b["close"]/a["close"],7)})
                else:gaps+=1
    return events,gaps

def fetch_basics(day,market,key):
    if not key:return {"status":"BLOCKED_AUTH","digest":None,"rows":{}}
    url=("https://data-dbg.krx.co.kr/svc/apis/"+ENDPOINTS[market]+
         "?basDd="+day.replace("-",""))
    request=urllib.request.Request(url,headers={"AUTH_KEY":key,"Accept":"application/json"})
    try:
        with urllib.request.urlopen(request,timeout=20) as response:
            raw=response.read(6*1024*1024+1)
        if len(raw)>6*1024*1024:raise ValueError("OVERLIMIT")
        payload=json.loads(raw.decode("utf-8"))
        rows=payload.get("OutBlock_1")
        if not isinstance(rows,list) or not rows:raise ValueError("EMPTY_OR_INVALID")
        keyed={}
        for x in rows:
            code=str(x.get("ISU_SRT_CD",""))
            if code in keyed:raise ValueError("DUPLICATE_TICKER")
            keyed[code]=x
        return {"status":"HISTORICAL_API_REQUERY_UNCERTIFIED_VINTAGE",
                "digest":digest(raw),"rows":keyed}
    except urllib.error.HTTPError as e:
        return {"status":"BLOCKED_HTTP_"+str(e.code),"digest":None,"rows":{}}
    except (urllib.error.URLError,TimeoutError,OSError,ValueError):
        return {"status":"BLOCKED_NETWORK_OR_INVALID","digest":None,"rows":{}}

def paired_compare(prev,cur):
    if prev is None or cur is None:return "BLOCKED_MISSING_ISSUER_ON_ONE_DATE"
    pf,cf=num(prev.get("PARVAL")),num(cur.get("PARVAL"))
    ps,cs=num(prev.get("LIST_SHRS")),num(cur.get("LIST_SHRS"))
    if pf is None or cf is None or ps is None or cs is None:
        return "UNVERIFIED_NUMERIC_METADATA_MISSING"
    if (pf!=cf and ps!=cs):return "BOTH_PARVAL_AND_SHARES_CHANGED_UNVERIFIED_CAUSE"
    if pf!=cf:return "PARVAL_CHANGED_UNVERIFIED_CAUSE"
    if ps!=cs:return "SHARES_CHANGED_UNVERIFIED_CAUSE"
    return "NO_PARVAL_OR_SHARES_CHANGE_OBSERVED"

def evaluate(root,key,limit=110):
    anomal,gap=read_adjacent(root)
    if len(anomal)!=73 or gap!=337:
        raise ValueError("FROZEN_410_DISCONTINUITY_CHANGED")
    pairs=sorted({(e["prev_date"],e["market"]) for e in anomal}|
                 {(e["date"],e["market"]) for e in anomal})
    if len(pairs)>limit:return {"status":"BLOCKED_API_REQUEST_LIMIT","planned":len(pairs),"decision":"CASH"}
    docs={}
    for day,market in pairs:
        docs[(day,market)]=fetch_basics(day,market,key)
        time.sleep(.08)
    classes=Counter();events=[]
    for e in anomal:
        a=docs[e["prev_date"],e["market"]]
        b=docs[e["date"],e["market"]]
        prev=a["rows"].get(e["ticker"])
        cur=b["rows"].get(e["ticker"])
        cls=paired_compare(prev,cur)
        classes[cls]+=1
        events.append({**e,"classification":cls,
             "previous_issuer_response_sha256":a["digest"],
             "current_issuer_response_sha256":b["digest"],
             "previous_parval":prev.get("PARVAL") if prev else None,
             "current_parval":cur.get("PARVAL") if cur else None,
             "previous_listed_shares":prev.get("LIST_SHRS") if prev else None,
             "current_listed_shares":cur.get("LIST_SHRS") if cur else None,
             "issuer_kind":cur.get("KIND_STKCERT_TP_NM") if cur else None})
    return {"schema":"C3_KRX_ADJACENT_ANOMALY_ISSUER_V11",
        "source":"KRX_ISSUER_BASIC_HISTORICAL_REQUERY_NOT_ORIGINAL_VINTAGE",
        "price_anomalies":410,"adjacent_market_session_events":len(anomal),
        "ticker_gap_events_awaiting_separate_review":gap,
        "unique_api_requests":len(pairs),
        "api_status":dict(Counter(x["status"] for x in docs.values())),
        "classification_counts":dict(classes),
        "raw_api_date_file_sha256":[
            {"date":d,"market":m,"status":v["status"],"sha256":v["digest"]}
            for (d,m),v in sorted(docs.items())],
        "corporate_action_original_notice_verified":False,
        "regular_1530_price_verified":False,
        "selected_signal_validity_automatically_changed":False,
        "production_changed":False,"trade_approved":False,"decision":"CASH","events":events}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    d=evaluate(a.root,os.environ.get("KRX_AUTH_KEY"))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n")
    print("C3_ADJACENT_ANOMALY_V11",json.dumps({k:v for k,v in d.items()
        if k not in ("events","raw_api_date_file_sha256")},ensure_ascii=False))
if __name__=="__main__":main()
