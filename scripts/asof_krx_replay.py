#!/usr/bin/env python3
"""Strict as-of historical KRX v18 ZIP replay, no retroactive paper fills.

Checks actual daily foreign/institution stock flows and KRX OHLC within the
dated ETF constituent universe. Removes misleading overlapping IT/robot
sector inflows, reports independently computed daily pivot stop references,
and fails closed when old provider data conflicts with independent prices.
"""
import argparse,csv,io,json,math,zipfile
from pathlib import Path

EXCLUDE={"HEALTH","PHARMA","BIOTECH"}
FOCUS=("005930","036930","010120","229640","028050")
def csvread(z,path):
    try:return list(csv.DictReader(io.StringIO(z.read(path).decode("utf-8-sig"))))
    except KeyError:return []
def val(x):
    try:
        v=float(x)
        return v if math.isfinite(v) else 0.
    except (ValueError,TypeError):return 0.
def quote_step(value):
    """KRX-listed ordinary share price bands, excludes ETF/ETN special rules."""
    v=val(value)
    if v<2000:return 1
    if v<5000:return 5
    if v<20000:return 10
    if v<50000:return 50
    if v<200000:return 100
    if v<500000:return 500
    return 1000

def floor_quote(value):
    if value is None:return None
    step=quote_step(value)
    return int(math.floor(val(value)/step)*step)

def study(seq,asof):
    seq=[x for x in seq if x.get("Date","")<=asof]
    if len(seq)<65 or seq[-1].get("Date")!=asof:
        return {"status":"MISSING_65_ASOF_BARS"}
    c=lambda i,k:val(seq[i].get(k))
    n=len(seq);close=c(-1,"Close")
    true_ranges=[max(c(i,"High")-c(i,"Low"),
                     abs(c(i,"High")-c(i-1,"Close")),
                     abs(c(i,"Low")-c(i-1,"Close")))
                 for i in range(n-14,n)]
    atr=sum(true_ranges)/14
    pivots=[]
    for i in range(max(2,n-41),n-2):
        low=c(i,"Low")
        if (low<min(c(i-2,"Low"),c(i-1,"Low")) and
            low<=min(c(i+1,"Low"),c(i+2,"Low")) and
            all(c(j,"Close")>=low for j in range(i+1,n))):
            pivots.append((low,i))
    result={"status":"DAILY_RESEARCH_ONLY","close":int(round(close)),
       "atr14":round(atr,2),
       "ma20":round(sum(c(i,"Close") for i in range(n-20,n))/20),
       "entry1_study":[int(round(close-.22*atr)),int(round(close+.12*atr))],
       "stop_reference":None,"pivot_date":None,"entry2_retest":None}
    if pivots:
        low,index=max(pivots,key=lambda x:(x[0],x[1]))
        stop=low-max(.25*atr,.003*close)
        if 0<stop<close:
            result.update(stop_reference=int(round(stop)),
                 pivot_date=seq[index]["Date"],
                 entry2_retest=[int(round(low)),int(round(low+.25*atr))],
                 status="STRUCTURAL_STOP_REFERENCE_ONLY")
    return result

def eligible_research(groups):
    # Deliberately no positive-news or final 85-point scores.
    return sorted((s for s in groups if s["day_net_bn"]>0 and
                   s["day_breadth_pct"] is not None and s["day_breadth_pct"]>60 and
                   not s.get("duplicate_inflow",False)),
                  key=lambda s:(-s["day_net_bn"],-s["day_turn_bn"]))[:3]

def replay(archive,asof,external_closes=None):
    with zipfile.ZipFile(archive) as z:
        status=json.loads(z.read("diagnostics/collection_status.json"))
        if status.get("asof")!=asof:raise ValueError("ASOF_MISMATCH")
        for k in ("prices","flows","holdings","normalization"):
            if status.get("datasets",{}).get(k,{}).get("status")!="OK":
                raise ValueError("MISSING_CORE_"+k.upper())
        features=[x for x in csvread(z,"research/sector_evidence_latest.csv")
                  if x.get("date")==asof and x.get("sector_id") not in EXCLUDE]
        prices={x["ticker"]:x for m in ("KOSPI","KOSDAQ")
                 for x in csvread(z,"market/daily_prices/"+m+"/"+asof+".csv")}
        flows={}
        for m in ("KOSPI","KOSDAQ"):
            for who in ("foreign","institution"):
                for r in csvread(z,"market/daily_flows/"+m+"/"+asof+"_"+who+".csv"):
                    flows[r["ticker"],who]=flows.get((r["ticker"],who),0)+val(r.get("net_buy_krw"))
        def money(t):return sum(flows.get((t,who),0) for who in ("foreign","institution"))
        histories={}
        def history(t):
            if t not in histories:histories[t]=csvread(z,"market/prices/"+t+".csv")
            return histories[t]
        sectors=[]
        members={}
        company_names={}
        for s in features:
            holdings=csvread(z,"market/raw_holdings/"+s["etf"]+"/"+s["snapshot_date"]+".csv")
            group={r["티커"]:r["구성종목명"] for r in holdings
                   if r.get("티커") in prices and r.get("티커","").isdigit()}
            members[s["sector_id"]]=group
            company_names.update(group)
            up=total=0
            for t in group:
                series=history(t)
                if len(series)>1 and series[-1].get("Date")==asof:
                    total+=1;up+=val(series[-1]["Close"])>val(series[-2]["Close"])
            sectors.append({"sector_id":s["sector_id"],"name":s["sector_name"],
               "membership_date":s["snapshot_date"],
               "member_count":len(group),"day_breadth_pct":round(up/total*100,1) if total else None,
               "day_net_bn":round(sum(money(t) for t in group)/1e9,2),
               "day_turn_bn":round(sum(val(prices[t]["TurnoverKRW"]) for t in group)/1e9,2),
               "net_5d_bn":round((val(s.get("foreign_net_buy_5d_krw"))+
                                   val(s.get("institution_net_buy_5d_krw")))/1e9,2)})
        chips=set(members.get("SEMICON",{}))
        overlap={}
        for s in sectors:
            if s["sector_id"] in ("IT","ROBOT"):
                raw=set(members.get(s["sector_id"],{}))
                incremental=sum(money(t) for t in raw-chips)/1e9
                s["duplicate_inflow"]=incremental<=0
                overlap[s["sector_id"]]={"overlap_tickers":len(raw&chips),
                     "incremental_ex_chips_net_bn":round(incremental,2)}
        chosen=eligible_research(sectors)
        focus=[]
        references=external_closes or {}
        for t in FOCUS:
            if t not in prices:continue
            raw=prices[t]
            technical=study(history(t),asof)
            external=references.get(asof,{}).get(t)
            discrepancy=external is not None and val(raw.get("Close"))!=val(external.get("close"))
            focus.append({"ticker":t,"name":company_names.get(t,t),
              "close_archive":int(round(val(raw["Close"]))),
              "day_net_bn":round(money(t)/1e9,2),
              "technical":technical,
              "external_close":external.get("close") if external else None,
              "cross_source_conflict":discrepancy,
              "execution_prices_allowed":False})
        return {"schema":"krx_asof_replay_v1","asof":asof,
          "source":"dated KRX via PyKrx v18 GitHub artifact",
          "source_run_id":39581006851,"top3":chosen,
          "sectors":sectors,"overlap":overlap,
          "focus":focus,"decision":"CASH","trade_approved":False,
          "is_live_signal":False,"forward_paper_trades_created":0,
          "news_status":status["datasets"].get("news",{}).get("status"),
          "dart_status":status["datasets"].get("dart",{}).get("status")}

def render(data):
    fmt=lambda x:f"{x:,.0f}" if isinstance(x,(int,float)) else "—"
    lines=["# 10월 21일 실제 KRX 데이터 리플레이","",
      "**신규 매수 승인: CASH — 과거자료 연구 결과, 소급 모의체결 없음**","",
      "## 당일 자금·상승확산 기준 섹터 TOP3 (ETF 구성종목 표본)","",
      "| 섹터 | 외국인+기관 1일 순매수(억원) | 거래대금(억원) | 상승 비율 | 최근5일 순매수(억원) |",
      "|---|---:|---:|---:|---:|"]
    for x in data["top3"]:
        lines.append(f"| {x['name']} | {fmt(x['day_net_bn']*10)} | "
          f"{fmt(x['day_turn_bn']*10)} | {x['day_breadth_pct']}% | {fmt(x['net_5d_bn']*10)} |")
    lines+=["","## 실제 일봉 가격·구조적 손절 참고","",
       "| 종목 | 수집 종가 | 피벗 손절 참고 | 1차 가격 연구 | 2차 지지 연구 |",
       "|---|---:|---:|---|---|"]
    for x in data["focus"]:
        t=x["technical"];zone=lambda a:("~".join(fmt(floor_quote(v)) for v in a) if a else "—")
        if x["cross_source_conflict"]:
            lines.append("| "+x["name"]+"† | "+fmt(x["close_archive"])+
                " / 외부 "+fmt(x.get("external_close"))+" | 주문 사용 금지 |"+
                " 출처 불일치 | 출처 불일치 |")
        else:
            lines.append("| "+x["name"]+" | "+fmt(x["close_archive"])+" | "+
               fmt(floor_quote(t.get("stop_reference")))+" | "+
               zone(t.get("entry1_study"))+" | "+zone(t.get("entry2_retest"))+" |")
    lines+=["","*표시한 가격대는 한국거래소 일반주식 가격대별 호가단위로 내림한 **연구 참고값**이며 실제 지정가 주문 승인이 아닙니다.",
      "*IT·로봇 ETF에는 반도체 대표주가 중복되므로 중복 제외 순매수가 음수면 TOP3에서 배제합니다.",
      "*뉴스·DART 수집이 누락돼 80점 최종 투자평가는 수행하지 않았습니다.",
      "*† 외부 확인 종가와 수집본 불일치: 해당 종목의 매매가격 사용 금지.",""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence-zip",type=Path,required=True)
    p.add_argument("--asof",default="2026-10-21")
    p.add_argument("--references",type=Path)
    p.add_argument("--out",type=Path,default=Path("output"))
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    refs=json.loads(a.references.read_text(encoding="utf-8")) if a.references and a.references.is_file() else {}
    data=replay(a.evidence_zip,a.asof,refs)
    (a.out/"asof_krx_replay.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    (a.out/"asof_krx_replay_mobile.md").write_text(render(data),encoding="utf-8")
    print(json.dumps({"asof":a.asof,"top3":[x["name"] for x in data["top3"]],
      "quote_conflicts":[x["ticker"] for x in data["focus"] if x["cross_source_conflict"]],
      "forward_paper_trades_created":0,"decision":"CASH"},ensure_ascii=False))
if __name__=="__main__":main()
