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
    for market in ("KOSPI","KOSDAQ"):
        for r in evidence.csv("market/daily_prices/"+market+"/"+asof+".csv"):
            t=r.get("ticker")
            close=num(r.get("Close"));turnover=num(r.get("TurnoverKRW"))
            if not (t and len(t)==6 and t.isdigit() and close and turnover is not None and turnover>=0):
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
                    ticker_cache[t]=(now_close>prev_close) if (
                        prev and 0<(target-prev).days<=10 and
                        now_close is not None and prev_close and prev_close>0) else None
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
    used=set()
    remaining=[x for x in sector_data if x["base_eligible"] and
               x["day_net_flow_krw"]>0 and x["day_breadth_pct"]>=60]
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
    # Separate watch-only ranking for positive-flow sectors that did NOT
    # satisfy broad advancing-stock participation. Never upgrade these
    # into the independently validated selected_top3 set.
    watch_pool=[x for x in sector_data if x["base_eligible"]
                and x["day_net_flow_krw"]>0 and
                (x["day_breadth_pct"] is None or x["day_breadth_pct"]<60)]
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
             exclusion_reason="RISING_BREADTH_BELOW_60_PERCENT"))
        watch_used.update(row["included_tickers"])
        watch_pool=[x for x in watch_pool if x["sector_id"]!=row["sector_id"]]
    compact=[]
    for s in sector_data:
        compact.append({k:v for k,v in s.items()
                        if k not in ("included_tickers","investor_flow_by_ticker")})
    return dict(schema=SCHEMA,asof=asof,source="KRX via PyKrx v18 raw dated ETF members",
      market_price_stock_count=len(prices),
      sector_samples=compact,selected_top3=chosen,
      watch_only_positive_flow_top3=watch,
      complete_three=len(chosen)==3,
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
      "| 연구 순위 | 섹터 | 중복제거 순매수(억) | 전체 구성종목 순매수(억) | 거래대금(억) | 상승확산 | 5일 합산 순매수(억) |",
      "|---|---|---:|---:|---:|---:|---:|"]
    def eok(x):return f"{x/1e8:,.0f}"
    for x in data["selected_top3"]:
        lines.append(f"| {x['rank']} | {x['name']} | {eok(x['incremental_day_net_flow_krw'])} | "+
          f"{eok(x['raw_day_net_flow_krw'])} | {eok(x['day_turnover_krw'])} | "+
          f"{x['day_breadth_pct']}% | {eok(x['rolling_5d_net_flow_krw'])} |")
    if not data["selected_top3"]:
        lines.append("| 적격 섹터 없음 | — | — | — | — | — | — |")
        watch=data.get("watch_only_positive_flow_top3") or []
        if watch:
            lines.extend(["","## 매수 제외된 수급 관찰 섹터 (강세 TOP3 아님)","",
              "| 관찰 | 섹터 | 중복제거 순매수(억) | 상승종목 비율 | 제외 사유 |",
              "|---|---|---:|---:|---|"])
            for row in watch:
                lines.append(f"| {row['rank']} | {row['name']} | "
                  f"{eok(row['incremental_day_net_flow_krw'])} | "
                  f"{row['day_breadth_pct']}% | 상승확산 60% 미달 |")
            lines.append("이 목록은 ETF 구성종목 수급의 잠정 관찰순위로 BUY 추천이 아닙니다.")
    lines+=["","*ETF 현금성 항목 제외·가격/매매주체 정보 누락 종목 점검 완료.",
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
