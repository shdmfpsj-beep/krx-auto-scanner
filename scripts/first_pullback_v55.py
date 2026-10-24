#!/usr/bin/env python3
"""Free, causal HMA60 first-pullback scanner. ALL outcomes research-only.

Replays completed daily bars; no future fills, order endpoints, guessed sector
money flow, or price-session certifications. Never convert a watch to BUY.
"""
import argparse,csv,json,math
from collections import defaultdict,Counter
from datetime import date
from pathlib import Path
from free_structural_v52 import history_check,atr14,last_confirmed_pivot

VERSION="FREE_FIRST_PULLBACK_V55"
HMA_PERIOD=60
COST_PCT=0.5
FIELDS=("asof","ticker","name","setup","turn_date","daily_stop","entry1","entry2",
        "nearest_resistance","rr_net","risk_pct","source","warnings","buy_approval")

def read_csv(path):
    if not path.is_file():return []
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def wma(values,n):
    if n<1:raise ValueError("INVALID_WMA_PERIOD")
    a=[None]*len(values);den=n*(n+1)/2
    for i in range(n-1,len(values)):
        segment=values[i-n+1:i+1]
        if all(x is not None and math.isfinite(x) for x in segment):
            a[i]=sum((k+1)*x for k,x in enumerate(segment))/den
    return a

def hma60(closes):
    fast=wma(closes,30);slow=wma(closes,60)
    mixed=[2*x-y if x is not None and y is not None else None
           for x,y in zip(fast,slow)]
    return wma(mixed,math.isqrt(60))

def confirmed_turn(h):
    # Two completed positive HMA slopes after earlier declining slopes.
    for i in range(len(h)-1,max(65,len(h)-19),-1):
        if any(x is None for x in h[i-8:i+1]):continue
        if h[i]>h[i-1]>h[i-2] and h[i-2]<h[i-3] and h[i-3]<h[i-6]:
            return i
    return None

def phase(b,h,atr,turn):
    if turn is None:return "NO_TURN_CONFIRMED"
    age=len(b)-1-turn
    if not 2<=age<=14:return "EARLY_TURN_WATCH"
    prior=b[turn:-1];peak=max(x["close"] for x in prior)
    if peak<b[turn]["close"]+1.1*atr:return "TURN_CONFIRMED"
    if b[-1]["close"]<=h[-1]:return "PULLBACK_WATCH"
    dips=[j for j in range(turn+1,len(b)-1)
          if b[j]["close"]<b[j-1]["close"] and b[j]["low"]<=peak-0.25*atr]
    if not dips:return "PULLBACK_WATCH"
    d=dips[-1]
    if len(b)-1-d>5:return "PULLBACK_WATCH"
    avgvol=sum(x["volume"] for x in b[-21:-1])/20
    if avgvol<=0 or b[d]["volume"]>1.5*avgvol:return "PULLBACK_WATCH"
    if b[-1]["close"]<=b[-2]["high"]:return "PULLBACK_WATCH"
    if b[-1]["close"]>peak+0.8*atr:return "EXTENDED_RECLAIM"
    return "FIRST_PULLBACK_RECLAIM"

def tick(v):
    return (1 if v<2000 else 5 if v<5000 else 10 if v<20000 else
            50 if v<50000 else 100 if v<200000 else
            500 if v<500000 else 1000)

def down(v):
    return int(math.floor(v/tick(v))*tick(v)) if v and v>0 else None

def up(v):
    if not v or v<=0:return None
    n=int(math.ceil(v/tick(v))*tick(v))
    return n if tick(n)==tick(v) else up(n)

def inspect(candidate,history,asof,rank=None,conflicted=None):
    ticker=str(candidate.get("ticker","")).strip()
    r=dict(asof=asof.isoformat(),ticker=ticker,name=candidate.get("name") or ticker,
           setup="DATA_PENDING",turn_date=None,daily_stop=None,entry1=None,
           entry2=None,nearest_resistance=None,rr_net=None,risk_pct=None,
           source=None,warnings=[],buy_approval="NO")
    warnings=[]
    if candidate.get("latest_date")!=str(asof):warnings.append("CANDIDATE_DATE_MISMATCH")
    if candidate.get("instrument_type")=="NON_COMMON_OR_SPECIAL":
        warnings.append("SPECIAL_SECURITY_EXCLUDED")
    elif candidate.get("instrument_type") not in ("COMMON","COMMON_STOCK"):
        warnings.append("COMMON_SHARE_TYPE_UNVERIFIED")
    if candidate.get("turnover_source")!="SOURCE_REPORTED":
        warnings.append("TRADED_VALUE_ESTIMATED_NOT_VERIFIED")
    if ticker in (conflicted or set()):warnings.append("KNOWN_CROSS_SOURCE_CLOSE_CONFLICT")
    bars,problem=history_check(history,ticker,asof)
    if problem:
        r["warnings"]=warnings+[problem];return r
    r["source"]=bars[-1]["source"]
    close=bars[-1]["close"]
    try: candclose=float(candidate["close"])
    except (KeyError,TypeError,ValueError):candclose=None
    if candclose is None or candclose<=0 or abs(close/candclose-1)>0.005:
        r["warnings"]=warnings+["CANDIDATE_HISTORY_CLOSE_CONFLICT"];return r
    if bars[-1]["source"]!=candidate.get("data_source"):
        r["warnings"]=warnings+["HISTORY_SOURCE_MISMATCH"];return r
    h=hma60([b["close"] for b in bars])
    atr=atr14(bars)
    if h[-1] is None or atr is None or atr<=0:
        r["warnings"]=warnings+["NO_RELIABLE_HMA_ATR"];return r
    turn=confirmed_turn(h)
    if turn is not None:r["turn_date"]=bars[turn]["date"].isoformat()
    r["setup"]=phase(bars,h,atr,turn)
    if r["setup"]!="FIRST_PULLBACK_RECLAIM":warnings.append("RECLAIM_NOT_CONFIRMED")
    pivot,low=last_confirmed_pivot(bars)
    if low is None:
        warnings.append("NO_TWO_BAR_CONFIRMED_DAILY_PIVOT")
    else:
        stop=down(low-max(0.25*atr,0.003*close))
        if stop and 0<stop<close:
            r["daily_stop"]=stop
            r["risk_pct"]=round(100*(close-stop)/close,3)
            if not 2<=r["risk_pct"]<=12:warnings.append("STRUCTURAL_RISK_NOT_2_TO_12_PCT")
            first=up(close);second=down(sum(x["close"] for x in bars[-20:])/20)
            r["entry1"]=first
            if second and stop<second<=first-0.50*atr:r["entry2"]=second
            else:warnings.append("SECOND_SUPPORT_NOT_SEPARATED_0_5_ATR")
            resist=sorted({b["high"] for b in bars[-21:-1] if b["high"]>first})
            if resist:
                ceiling=resist[0];r["nearest_resistance"]=down(ceiling)
                risk=first-stop
                # Worse-case first entry and explicit roundtrip transaction cost.
                rr=(ceiling*(1-COST_PCT/200)-first*(1+COST_PCT/200))/risk
                r["rr_net"]=round(rr,3)
                if rr<2:warnings.append("NEAREST_RESISTANCE_NET_RR_BELOW_2")
            else:warnings.append("NO_UPSIDE_NEARBY_RESISTANCE")
        else:warnings.append("INVALID_STRUCTURAL_STOP")
    warnings+=["REGULAR_PRICE_SOURCE_UNCERTIFIED","SECTOR_EVIDENCE_UNVERIFIED",
               "FINAL_80_SCORE_UNVERIFIED","ACCOUNT_EXECUTION_NOT_VERIFIED"]
    r["warnings"]=list(dict.fromkeys(warnings))
    return r

def analyze(status,candidates,histories,prelims,asof,parity=None):
    p=parity if isinstance(parity,dict) else {}
    errors=[]
    if status.get("market_data_date")!=str(asof):errors.append("SCAN_DATE_MISMATCH")
    if status.get("scan_complete") is not True or status.get("data_date_verified") is not True:
        errors.append("SCAN_NOT_VERIFIED")
    try:coverage=float(status.get("coverage_ratio"))
    except (ValueError,TypeError):coverage=0.0
    if not math.isfinite(coverage) or coverage<0.95:
        errors.append("LOW_MARKET_COVERAGE")
    if p.get("asof")!=str(asof):errors.append("PRICE_PARITY_DATE_OR_FILE_MISSING")
    elif p.get("close_mismatches")!=0 or p.get("status")!="CANDIDATE_CLOSES_MATCH_RESEARCH_ONLY":
        errors.append("CROSS_SOURCE_PRICE_CONFLICT")
    conflicts={str(v.get("ticker")) for v in p.get("mismatch_examples",[])
               if isinstance(v,dict)}
    group=defaultdict(list)
    for b in histories:group[str(b.get("ticker","")).zfill(6)].append(b)
    ranks={v.get("ticker"):v for v in prelims}
    rows=[inspect(c,group.get(c.get("ticker"),[]),asof,ranks.get(c.get("ticker")),conflicts)
          for c in candidates]
    counts=dict(Counter(x["setup"] for x in rows))
    # Eligible WATCH (not BUY): never force 5 low-quality stocks into TOP5.
    eligible=[x for x in rows if x["setup"] in ("PULLBACK_WATCH","FIRST_PULLBACK_RECLAIM")
       and x["daily_stop"] is not None and x["entry2"] is not None
       and x["rr_net"] is not None and x["rr_net"]>=2
       and "KNOWN_CROSS_SOURCE_CLOSE_CONFLICT" not in x["warnings"]
       and "SPECIAL_SECURITY_EXCLUDED" not in x["warnings"]
       and "COMMON_SHARE_TYPE_UNVERIFIED" not in x["warnings"]
       and "TRADED_VALUE_ESTIMATED_NOT_VERIFIED" not in x["warnings"]
       and not any(t in str(x["name"]).upper()
                   for t in ("바이오","제약","PHARMA","BIOTECH"))]
    eligible=sorted(eligible,key=lambda x:(-x["rr_net"],x["ticker"]))[:5] if not errors else []
    # Show rejection diagnostics separately; never promote them to approved TOP5.
    rejected=sorted((x for x in rows if x["setup"]=="PULLBACK_WATCH"),
                    key=lambda x:(
                        -(x["rr_net"] if isinstance(x["rr_net"],(int,float)) else -999),
                        x["ticker"]))[:5]
    rejected_summary=[dict(ticker=x["ticker"],name=x["name"],
        research_entry=x["entry1"],research_stop=x["daily_stop"],
        cost_adjusted_near_rr=x["rr_net"],blocked_by=x["warnings"],
        trade_approved=False) for x in rejected]
    report=dict(schema=VERSION,asof=str(asof),scanned_count=len(rows),
      source_errors=errors,setup_counts=counts,
      parity_overlapping=p.get("overlap_tickers"),
      parity_mismatches=p.get("close_mismatches"),
      listed_parity_conflict_examples=len(conflicts),
      watch_tickers=[x["ticker"] for x in eligible],
      rejected_pullback_diagnostics=rejected_summary,
      first_reclaims=counts.get("FIRST_PULLBACK_RECLAIM",0),
      market_session_certified=False,final_80_score_verified=False,
      manual_review_final_score_threshold=80,
      excluded_chem_bio_stock_names_without_sector_master=True,
      roundtrip_cost_assumption_pct=COST_PCT,
      foreign_institution_netflows_optional=True,
      trade_approved=False,orders_enabled=False,decision="CASH",
      note="Source OHLC is not exchange-attested regular-only; never trade research levels.")
    return rows,report

def markdown(rows,report):
    counts=report["setup_counts"]
    lines=["# C3·K100 HMA60 첫 눌림 무료 연구 v5.5","",
      "**기준일:** "+report["asof"],
      "**최종 신규매수: CASH (승인 0건)**",
      f"분석 {report['scanned_count']}종목 · 첫 눌림 재돌파 {report['first_reclaims']}건",
      f"출처 간 종가 불일치 {report['parity_mismatches']} / {report['parity_overlapping']} 공통종목",
      "출처가 동일하거나 날짜가 일치해도 KRX 정규장 인증이 되지는 않습니다.","",
      "| 일봉 연구단계 | 종목수 |","|---|---:|"]
    for key,n in sorted(counts.items()):lines.append(f"| {key} | {n} |")
    lines+=["","## 비용 반영 2R 충족 연구 관찰 (최대 5개, 억지 선발 없음)","",
     "| 종목 | 상태 | 1차 연구가 | 2차 연구가 | 일봉 구조손절 | 비용후 R:R |",
     "|---|---|---:|---:|---:|---:|"]
    lookup={x["ticker"]:x for x in rows}
    for t in report["watch_tickers"]:
        x=lookup[t]
        lines.append(f"| {x['name']} ({t}) | {x['setup']} | {x['entry1']} | {x['entry2']} | {x['daily_stop']} | {x['rr_net']} |")
    if not report["watch_tickers"]:lines.append("| 충족 후보 없음 | CASH | — | — | — | — |")
    lines+=["","## 눌림 감시 중 제외된 종목 (매수 금지, 최대 5개)","",
       "| 종목 | 구조손절 참고 | 1차 참고 | 비용후 R:R | 제외사유 |",
       "|---|---:|---:|---:|---|"]
    for x in report.get("rejected_pullback_diagnostics",[]):
        reasons=[y for y in x["blocked_by"] if y in (
             "KNOWN_CROSS_SOURCE_CLOSE_CONFLICT",
             "NEAREST_RESISTANCE_NET_RR_BELOW_2",
             "SECOND_SUPPORT_NOT_SEPARATED_0_5_ATR",
             "RECLAIM_NOT_CONFIRMED")]
        reason=", ".join(reasons) or "미검증"
        lines.append(f"| {x['name']} ({x['ticker']}) | {x['research_stop'] or '미확인'} | {x['research_entry'] or '미확인'} | {x['cost_adjusted_near_rr'] if x['cost_adjusted_near_rr'] is not None else '미확인'} | {reason} |")
    if not report.get("rejected_pullback_diagnostics"):
        lines.append("| 없음 | — | — | — | — |")
    lines+=["","수급·재무·섹터 확산·정규장 가격 인증·계좌가 확인되기 전",
      "매수가와 구조손절은 참고값이며 주문 지시가 아닙니다.",
      "**Required Next Data:** 65일 정규장 인증 이력, 종가 대조, 실측 거래대금, 공시·실적, 계좌 잔고.",""]
    return "\n".join(lines)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--asof",required=True)
    args=parser.parse_args()
    try:asof=date.fromisoformat(args.asof)
    except ValueError:raise SystemExit("INVALID_ASOF")
    try:status=json.loads((args.input/"status.json").read_text())
    except (OSError,ValueError):status={}
    try:parity=json.loads((args.input/"source_price_parity.json").read_text())
    except (OSError,ValueError):parity={}
    rows,report=analyze(status,read_csv(args.input/"candidates.csv"),
       read_csv(args.input/"candidate_daily_history_v52.csv"),
       read_csv(args.input/"c3_preliminary.csv"),asof,parity)
    args.out.mkdir(parents=True,exist_ok=True)
    with (args.out/"first_pullback_v55_all.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader()
        w.writerows([{**r,"warnings":";".join(r["warnings"])} for r in rows])
    (args.out/"first_pullback_v55_status.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    (args.out/"first_pullback_v55_mobile.md").write_text(markdown(rows,report))
    print(json.dumps({"asof":args.asof,"scanned":len(rows),"counts":report["setup_counts"],
          "watch":report["watch_tickers"],"decision":"CASH"},ensure_ascii=False))

if __name__=="__main__":main()
