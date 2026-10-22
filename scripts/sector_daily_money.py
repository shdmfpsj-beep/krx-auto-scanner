#!/usr/bin/env python3
"""Daily sector money-flow evidence from dated v18 raw KRX snapshots.

Uses completed-stock OHLCV and actual foreign/institution investor net-buy data;
never treats ETF cash-like lines as missing stock data, and never double-counts
the same stock as incremental money when selecting multiple ETFs.
This is a PROVISIONAL sector research screen, not trade approval.
"""
import argparse,csv,io,json,math,zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

SCHEMA="sector_daily_money_v1"
CORE=("prices","flows","holdings","normalization")
EXCLUDE={"HEALTH","PHARMA","BIOTECH"}

class Evidence:
    def __init__(self,path):
        self.path=Path(path)
        self.zip=zipfile.ZipFile(path) if self.path.is_file() else None
    def read(self,rel):
        if self.zip:
            try:return self.zip.read(rel).decode("utf-8-sig")
            except KeyError:return ""
        file=self.path/rel
        return file.read_text(encoding="utf-8-sig") if file.is_file() else ""
    def csv(self,rel):
        txt=self.read(rel)
        return list(csv.DictReader(io.StringIO(txt))) if txt else []
    def close(self):
        if self.zip:self.zip.close()

def num(v):
    try:
        v=float(v)
        return v if math.isfinite(v) else None
    except (ValueError,TypeError):return None

def day(v):
    try:return date.fromisoformat(str(v)[:10])
    except (ValueError,TypeError):return None

def daily_evidence(evidence,asof,expected_sectors=None):
    status_txt=evidence.read("diagnostics/collection_status.json")
    if not status_txt:raise ValueError("MISSING_EVIDENCE_STATUS")
    status=json.loads(status_txt)
    if status.get("asof")!=asof:
        raise ValueError("ASOF_MISMATCH")
    for key in CORE:
        if status.get("datasets",{}).get(key,{}).get("status")!="OK":
            raise ValueError("CORE_DATA_UNVERIFIED_"+key.upper())
    prices={}
    flows=defaultdict(dict)
    raw_tradable_count=0
    raw_ohlc_conflicts=0
    raw_nontrading_count=0
    for market in ("KOSPI","KOSDAQ"):
        for r in evidence.csv("market/daily_prices/"+market+"/"+asof+".csv"):
            t=r.get("ticker")
            close=num(r.get("Close"));turnover=num(r.get("TurnoverKRW"))
            op=num(r.get("Open"));hi=num(r.get("High"));lo=num(r.get("Low"))
            if not (t and len(t)==6 and t.isdigit() and close and close>0
                    and turnover is not None and turnover>=0):
                continue
            # Some suspended stocks have 0/0/0 OHLC but a last known close.
            # They are not completed trading bars and cannot confirm breadth.
            if op==0 and hi==0 and lo==0:
                raw_nontrading_count+=1
                continue
            raw_tradable_count+=1
            if (op is None or hi is None or lo is None or
                not (0<lo<=min(op,close)<=max(op,close)<=hi)):
                raw_ohlc_conflicts+=1
                continue
            if t in prices:raise ValueError("DUPLICATE_TICKER_MARKET")
            prices[t]=r
        for who in ("foreign","institution"):
            for r in evidence.csv("market/daily_flows/"+market+"/"+asof+"_"+who+".csv"):
                t=r.get("ticker");flow=num(r.get("net_buy_krw"))
                if not (t and len(t)==6 and t.isdigit() and flow is not None):
                    continue
                if who in flows[t]:raise ValueError("DUPLICATE_INVESTOR_FLOW")
                flows[t][who]=flow
    if not prices or not flows:raise ValueError("EMPTY_COMPLETED_MARKET_DATA")
    features=[r for r in evidence.csv("research/sector_evidence_latest.csv")
              if r.get("date")==asof and r.get("sector_id") not in EXCLUDE]
    if not features:raise ValueError("NO_ASOF_SECTOR_FEATURES")
    seen_ids=set()
    sector_data=[]
    ticker_cache={}
    for feat in features:
        sid=feat.get("sector_id","")
        if not sid or sid in seen_ids:raise ValueError("DUPLICATE_SECTOR_FEATURE")
        seen_ids.add(sid)
        snapshot=day(feat.get("snapshot_date"))
        target=day(asof)
        if snapshot is None or target is None or not 0<=(target-snapshot).days<=10:
            continue
        holders=evidence.csv("market/raw_holdings/"+feat["etf"]+"/"+str(snapshot)+".csv")
        if not holders:continue
        all_valid={}
        nonstock=[]
        for r in holders:
            t=r.get("티커","").strip()
            name=r.get("구성종목명","")
            # Cash positions are not tradable shares. Never silently discard
            # a real stock whose OHLC/flows are missing.
            if "원화현금" in name or name in ("현금","KRW CASH"):
                nonstock.append(t)
                continue
            if t and len(t)==6 and t.isdigit():
                all_valid[t]=name
        if len(all_valid)<5:continue
        included={}
        unavailable=[]
        for t,name in all_valid.items():
            if t not in prices or len(flows[t])!=2:
                unavailable.append(t)
                continue
            included[t]=name
        coverage=len(included)/len(all_valid)
        by_company={}
        for t in included:
            if t not in ticker_cache:
                series=evidence.csv("market/prices/"+t+".csv")
                tail=[r for r in series if (d:=day(r.get("Date"))) is not None and d<=target]
                if len(tail)<2 or day(tail[-1].get("Date"))!=target:
                    ticker_cache[t]=None
                else:
                    prev=day(tail[-2].get("Date"))
                    now_close=num(tail[-1].get("Close"))
                    prev_close=num(tail[-2].get("Close"))
                    # The dated stock history must agree with the valid
                    # one-day market snapshot. Do not use revised closes
                    # or malformed daily candles as a breadth signal.
                    market_close=num(prices[t].get("Close"))
                    same_close=(now_close is not None and market_close is not None
                                and abs(now_close-market_close)<=0.00001)
                    ticker_cache[t]=(now_close>prev_close) if (
                        prev and 0<(target-prev).days<=10 and same_close
                        and prev_close is not None and prev_close>0) else None
            up=ticker_cache[t]
            if up is not None:
                by_company[t]=up
        breadth_coverage=len(by_company)/len(all_valid)
        daily_flow={t:flows[t]["foreign"]+flows[t]["institution"] for t in included}
        rolling5=sum((num(feat.get(k)) or 0) for k in (
            "foreign_net_buy_5d_krw","institution_net_buy_5d_krw"))
        # v18 price_flow_proxy_ready describes multi-day indicator availability.
        # It must NOT veto a fully observed one-day KRX flow/breadth comparison:
        # POWER was falsely excluded on 2026-10-21 despite 100% valid 1D OHLC/flow.
        eligible=(coverage>=0.95 and breadth_coverage>=0.95 and
            len(included)>=5 and len(by_company)>=5)
        sector_data.append(dict(
            sector_id=sid,name=feat.get("sector_name",sid),
            etf=feat["etf"],snapshot_date=str(snapshot),
            member_count=len(all_valid),cash_lines_excluded=len(nonstock),
            price_flow_coverage=round(coverage,4),
            breadth_coverage=round(breadth_coverage,4),
            missing_stock_tickers=sorted(set(unavailable)|(
                set(included)-set(by_company))),
            day_net_flow_krw=round(sum(daily_flow.values())),
            day_turnover_krw=round(sum(num(prices[t].get("TurnoverKRW")) or 0 for t in included)),
            day_breadth_pct=round(100*sum(by_company.values())/len(by_company),2)
               if by_company else None,
            rolling_5d_net_flow_krw=round(rolling5),
            base_eligible=eligible,positive_catalyst_verified=False,
            investor_flow_by_ticker=daily_flow,
            included_tickers=sorted(included),rank_kind="ETF_CONSTITUENT_DAILY_FLOW_PROXY"))
    # If many traded OHLC candles violate Low <= Open,Close <= High,
    # do not rank seemingly attractive sectors from a corrupt market slice.
    conflict_rate=(raw_ohlc_conflicts/raw_tradable_count
                   if raw_tradable_count else 1.0)
    market_ohlc_quality_verified=bool(conflict_rate<=0.01)
    used=set()
    remaining=[x for x in sector_data if market_ohlc_quality_verified
               and x["base_eligible"] and
               x["day_net_flow_krw"]>0 and x["day_breadth_pct"] is not None]
    chosen=[]
    while len(chosen)<3 and remaining:
        candidates=[]
        for s in remaining:
            new=set(s["included_tickers"])-used
            incremental_net=sum(s["investor_flow_by_ticker"][t] for t in new)
            incremental_turn=sum(num(prices[t].get("TurnoverKRW")) or 0 for t in new)
            candidates.append((incremental_net,incremental_turn,s["sector_id"],s,new))
        winner=max(candidates,key=lambda x:(x[0],x[1],x[2]))
        if winner[0]<=0:break
        s=winner[3]
        chosen.append(dict(rank=len(chosen)+1,sector_id=s["sector_id"],
            name=s["name"],member_count=s["member_count"],
            cash_lines_excluded=s["cash_lines_excluded"],
            day_breadth_pct=s["day_breadth_pct"],
            flow_phase=("EXPANDING" if s["day_breadth_pct"]>=60 else
                        "NARROW_POSITIVE" if s["day_breadth_pct"]>0 else
                        "DIVERGENT_ALL_DOWN"),
            raw_day_net_flow_krw=s["day_net_flow_krw"],
            incremental_day_net_flow_krw=round(winner[0]),
            day_turnover_krw=s["day_turnover_krw"],
            incremental_turnover_krw=round(winner[1]),
            rolling_5d_net_flow_krw=s["rolling_5d_net_flow_krw"],
            overlap_with_prior_sector_count=len(set(s["included_tickers"])&used),
            flow_coverage=s["price_flow_coverage"],
            nonoverlap_tickers=sorted(winner[4]),
            final_100_score=None,trade_approval="NO"))
        used.update(s["included_tickers"])
        remaining=[x for x in remaining if x["sector_id"]!=s["sector_id"]]
    # Additional money-inflow candidates outside TOP3. Breadth under 60%
    # is an EARLY/WARNING classification, never a reason to conceal the flow.
    selected_ids={x["sector_id"] for x in chosen}
    watch_pool=[x for x in sector_data if market_ohlc_quality_verified
                and x["base_eligible"]
                and x["day_net_flow_krw"]>0 and
                x["day_breadth_pct"] is not None and
                x["sector_id"] not in selected_ids]
    watch_used=set()
    watch=[]
    while len(watch)<3 and watch_pool:
        options=[]
        for row in watch_pool:
            new=set(row["included_tickers"])-watch_used
            added=sum(row["investor_flow_by_ticker"][t] for t in new)
            options.append((added,row["day_turnover_krw"],row["sector_id"],row,new))
        best=max(options,key=lambda item:(item[0],item[1],item[2]))
        if best[0]<=0:break
        row=best[3]
        watch.append(dict(rank=len(watch)+1,sector_id=row["sector_id"],
             name=row["name"],member_count=row["member_count"],
             day_breadth_pct=row["day_breadth_pct"],
             raw_day_net_flow_krw=row["day_net_flow_krw"],
             incremental_day_net_flow_krw=round(best[0]),
             day_turnover_krw=row["day_turnover_krw"],
             price_flow_coverage=row["price_flow_coverage"],
             breadth_coverage=row["breadth_coverage"],
             watch_only=True,trade_approval="NO",
             exclusion_reason=("BREADTH_LT_60_WATCH" if row["day_breadth_pct"]<60
                               else "FLOW_RANK_OUTSIDE_TOP3")))
        watch_used.update(row["included_tickers"])
        watch_pool=[x for x in watch_pool if x["sector_id"]!=row["sector_id"]]
    compact=[]
    for s in sector_data:
        compact.append({k:v for k,v in s.items()
                        if k not in ("included_tickers","investor_flow_by_ticker")})
    return dict(schema=SCHEMA,asof=asof,source="KRX via PyKrx v18 raw dated ETF members",
      market_price_stock_count=len(prices),
      raw_tradable_ohlc_checked=raw_tradable_count,
      raw_ohlc_conflict_count=raw_ohlc_conflicts,
      raw_nontrading_count=raw_nontrading_count,
      raw_ohlc_conflict_pct=round(100*conflict_rate,2),
      market_ohlc_quality_verified=market_ohlc_quality_verified,
      market_source_status=("OK" if market_ohlc_quality_verified else
                            "RAW_MARKET_OHLC_CONFLICT_HIGH"),
      sector_samples=compact,selected_top3=chosen,
      watch_only_positive_flow_top3=watch,
      complete_three=len(chosen)==3,
      early_flow_research_only=True,
      expanding_sector_count=sum(x["day_breadth_pct"]>=60 for x in chosen),
      pre_expansion_sector_count=sum(x["day_breadth_pct"]<60 for x in chosen),
      overlaps_removed=True,
      five_day_flow_separate_from_day=True,
      independent_stock_closes_crosschecked=False,
      final_sector_100_score_verified=False,
      decision="CASH",trade_approved=False,
      caveat="One-day constituent sum is not a whole-sector industry money flow. Ranks exclude reused stock flow from previously selected sectors.")

def render(data):
    lines=["# KRX 당일 실측 수급 중심 섹터 TOP3","",
      "**CASH · 실측 수급 순위는 최종 매수 승인과 다릅니다.**","",
      "데이터 기준일: "+data["asof"],"",
      "시장 OHLC 품질: "+data["market_source_status"]+
      " / 거래일봉 모순 "+str(data["raw_ohlc_conflict_count"])+
      "건 ("+str(data["raw_ohlc_conflict_pct"])+"%)","",
      "| 연구 순위 | 섹터 | 중복제거 순매수(억) | 전체 구성종목 순매수(억) | 거래대금(억) | 상승확산 | 단계 | 5일 합산 순매수(억) |",
      "|---|---|---:|---:|---:|---:|---|---:|"]
    def eok(x):return f"{x/1e8:,.0f}"
    for x in data["selected_top3"]:
        lines.append(f"| {x['rank']} | {x['name']} | {eok(x['incremental_day_net_flow_krw'])} | "+
          f"{eok(x['raw_day_net_flow_krw'])} | {eok(x['day_turnover_krw'])} | "+
          f"{x['day_breadth_pct']}% | {x['flow_phase']} | {eok(x['rolling_5d_net_flow_krw'])} |")
    if not data["selected_top3"]:
        lines.append("| 자금유입 적격 섹터 없음 | — | — | — | — | — | — | — |")
    watch=data.get("watch_only_positive_flow_top3") or []
    if watch:
            lines.extend(["","## 추가 자금유입 관찰 섹터 (TOP3 외)","",
              "| 관찰 | 섹터 | 중복제거 순매수(억) | 상승종목 비율 | 제외 사유 |",
              "|---|---|---:|---:|---|"])
            for row in watch:
                lines.append(f"| {row['rank']} | {row['name']} | "
                  f"{eok(row['incremental_day_net_flow_krw'])} | "
                  f"{row['day_breadth_pct']}% | {row['exclusion_reason']} |")
            lines.append("이 목록은 ETF 구성종목 수급의 잠정 관찰순위로 BUY 추천이 아닙니다.")
    if not data["market_ohlc_quality_verified"]:
        lines+=["","**가격·고가·저가가 서로 모순되는 당일 일봉이 많아 섹터 선정 보류(CASH).**"]
    lines+=["","*상승확산 60%는 관찰 단계 분류 기준입니다. 매수 승인이 아닙니다.",
        "*상승 종목 0% 상태의 순매수는 하락 종목 흡수/집중 매수 가능성도 있으므로 추세 확정 금지.",
        "*ETF 현금성 항목 제외·가격/매매주체 정보 누락 종목 점검 완료.",
        "*반도체와 IT·로봇 등 중복 구성종목의 돈은 추가 유입으로 재계산하지 않습니다.",
        "*주간 수급이 음수이면 하루 순매수만으로 추세전환을 확정하지 않습니다.",
        "*미검증 호재·실적·가격 품질 때문에 신규매수 CASH.",""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--asof",required=True)
    p.add_argument("--out",type=Path,default=Path("output"))
    a=p.parse_args()
    root=Evidence(a.evidence)
    try:res=daily_evidence(root,a.asof)
    finally:root.close()
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/"sector_daily_money.json").write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding="utf-8")
    (a.out/"sector_daily_money_mobile.md").write_text(render(res),encoding="utf-8")
    print(json.dumps(dict(asof=res["asof"],top3=[x["sector_id"] for x in res["selected_top3"]],
        completeness=res["complete_three"],decision=res["decision"]),ensure_ascii=False))

if __name__=="__main__":main()
