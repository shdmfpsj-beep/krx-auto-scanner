#!/usr/bin/env python3
"""Objective C3/K100 daily research readiness, not promised software completion.

Each gate is backed by the dated evidence itself. A weak market can pass source
integrity while correctly yielding CASH at the candidate gate. Never convert
source-test completion into expected investment return or an 80-point score.
"""
import argparse,json
from pathlib import Path
from datetime import date

VERSION="daily_readiness_gates_v1"

def dated(v):
    try:return date.fromisoformat(str(v)[:10]).isoformat()
    except (ValueError,TypeError):return None

def build(source,sector,summary,entry,shadow,proof):
    asof=dated(source.get("asof"))
    aligned=(asof is not None and all(dated(r.get("asof"))==asof for r in
             (sector,summary,entry)))
    samples=source.get("sector_samples",[])
    samples=samples if isinstance(samples,list) else []
    stock_count=source.get("market_price_stock_count")
    price_and_flow=bool(aligned and isinstance(stock_count,int) and
        stock_count>=100 and samples and source.get("overlaps_removed") is True)
    cover=bool(price_and_flow and len(samples)>=3 and
        all(isinstance(s,dict) and
            s.get("price_flow_coverage",0)>=0.95 and
            s.get("breadth_coverage",0)>=0.95 and
            isinstance(s.get("day_breadth_pct"),(int,float)) and
            isinstance(s.get("day_net_flow_krw"),(int,float))
            for s in samples))
    ranked=source.get("selected_top3") or []
    qualified=bool(cover and len(ranked)==3 and
        source.get("complete_three") is True and
        sector.get("daily_money_rank_applied") is True and
        sector.get("daily_money_gate")=="VERIFIED_1D_EARLY_FLOW_RESEARCH_ONLY" and
        [s.get("sector_id") for s in ranked] ==
          [s.get("sector_id") for s in summary.get("sector_top3",[])] and
        all(isinstance(s,dict) and
            isinstance(s.get("day_breadth_pct"),(int,float)) and
            0<=s["day_breadth_pct"]<=100 and
            s.get("incremental_day_net_flow_krw",0)>0 and
            s.get("flow_coverage",0)>=0.95
            for s in ranked))
    expanding=bool(qualified and all(s["day_breadth_pct"]>=60 for s in ranked))
    candidates=summary.get("stock_research_top5") or []
    top5=bool(qualified and len(candidates)==5)
    geometry=entry.get("candidates") or []
    validated=sum(bool(x.get("geometry_pass")) for x in geometry
                  if isinstance(x,dict))
    entry_ok=bool(top5 and entry.get("stock_count",0)>=5 and
                  entry.get("technical_geometry_pass_count",0)>=1)
    signals=shadow.get("signal_count",0)
    closes=shadow.get("closed_count",0)
    paper_observed=bool(isinstance(signals,int) and signals>0 and
                        isinstance(closes,int) and closes>0)
    proof_ok=bool(paper_observed and proof.get("sample_sufficiency_met") is True
                  and proof.get("integrity_pass") is True and
                  proof.get("profit_proof_status")==
                     "PROVISIONAL_PAPER_EDGE_NOT_LIVE_OR_OOS_PROVEN")
    gate_rows=[
      ("KRX_DATE_PRICE_FLOW",price_and_flow,
       "당일 증시 가격과 종목 수급 확보"),
      ("SECTOR_BREADTH_MEASURED",cover,
       "섹터별 상승확산·수급 검증"),
      ("THREE_FLOW_RESEARCH_SECTORS",qualified,
       "검증된 수급 선행 섹터 3개 (확산·매수 별도)"),
      ("STOCK_TOP5",top5,
       "섹터에서 후보 TOP5 선별"),
      ("STRUCTURAL_ENTRY",entry_ok,
       "실제 일봉 구조손절·진입 타점"),
      ("PROSPECTIVE_OUTCOMES",paper_observed,
       "사전 기록된 모의매매 종료 사례"),
      ("ROBUST_PAPER_EVIDENCE",proof_ok,
       "충분한 표본과 비용 스트레스 검증"),
    ]
    done=sum(x[1] for x in gate_rows)
    weak=bool(cover and not ranked and
              not any(s.get("base_eligible") is True and
                      s.get("day_net_flow_krw",0)>0 for s in samples))
    if not aligned:
        market_status="SOURCE_ASOF_MISMATCH"
    elif not price_and_flow or not cover:
        market_status="DATA_MISSING_OR_LOW_COVERAGE"
    elif weak:
        market_status="VERIFIED_NO_POSITIVE_FLOW_SECTOR"
    elif not qualified:
        market_status="FLOW_RANKING_MISSING_OR_PARTIAL"
    elif not expanding:
        market_status="PRE_EXPANSION_FLOW_WATCH"
    else:
        market_status="SECTOR_RESEARCH_TOP3_AVAILABLE"
    result=dict(schema=VERSION,asof=asof,
       checked_gates=len(gate_rows),passed_gates=done,
       evidence_progress_pct=round(100*done/len(gate_rows)),
       metric_definition="PASSED_OBSERVABLE_RESEARCH_GATES_NOT_PROGRAM_PERCENT",
       gates=[dict(id=a,passed=b,label=c) for a,b,c in gate_rows],
       market_source_status=market_status,
       verified_price_stock_count=stock_count if price_and_flow else None,
       sector_samples_checked=len(samples) if cover else 0,
       selected_sectors=len(ranked) if qualified else 0,
       expanding_sector_count=sum(s["day_breadth_pct"]>=60 for s in ranked)
           if qualified else 0,
       flow_research_only=True,
       research_top5_count=len(candidates) if top5 else 0,
       geometry_research_pass_count=entry.get("technical_geometry_pass_count",0),
       prospective_signals=signals if isinstance(signals,int) else 0,
       completed_paper_trades=closes if isinstance(closes,int) else 0,
       profit_proof_status=proof.get("profit_proof_status","UNAVAILABLE"),
       source_research_not_investment_score=True,
       success_on_cautious_cash_day=weak,
       conditional_trade_risk_not_guaranteed=True,
       final_80_trade_score_verified=False,
       trade_approved=False,orders_enabled=False,decision="CASH")
    return result

def markdown(r):
    lines=["## ⑧ 오늘 분석 검증 진행률","",
      "**시장 신규매수: CASH**",
      "분석 증거 충족: **"+str(r["passed_gates"])+"/"+
          str(r["checked_gates"])+"관문 ("+str(r["evidence_progress_pct"])+"%)**",
      "이 숫자는 프로그램 개발 완료율·수익확률·종목 점수가 아닙니다.","",
      "| 관문 | 상태 |","|---|---|"]
    for g in r["gates"]:
        lines.append("| "+g["label"]+" | "+
                     ("자료확인" if g["passed"] else "미충족/추후 검증")+" |")
    lines+=["","시장 판정: **"+r["market_source_status"]+"**",
        "가격 데이터 종목 수: "+str(r["verified_price_stock_count"] or "미검증"),
        "사전 기록 신호: "+str(r["prospective_signals"])+
         "건 / 5거래일 종료: "+str(r["completed_paper_trades"])+"건",
        "수익 실증 판정: "+r["profit_proof_status"],
        "돈 유입이 먼저 나타난 섹터도 TOP3 관찰대상입니다. 60% 확산 미달은 경고이지 삭제조건이 아닙니다.",
        "수급 연구 TOP3를 매수 승인이나 수익 검증으로 혼동하지 않습니다.",""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("output"))
    a=p.parse_args()
    def read(file):
        path=a.root/file
        if not path.is_file():return {}
        try:v=json.loads(path.read_text(encoding="utf-8"))
        except (ValueError,OSError):return {}
        return v if isinstance(v,dict) else {}
    progress=build(read("sector_daily_money.json"),
                   read("sector_bridge_status.json"),
                   read("sector_first_daily_status.json"),
                   read("entry_setup_audit.json"),
                   read("shadow_scorecard.json"),
                   read("profit_proof_gate.json"))
    a.root.mkdir(parents=True,exist_ok=True)
    (a.root/"daily_readiness_progress.json").write_text(
        json.dumps(progress,ensure_ascii=False,indent=2),encoding="utf-8")
    msg=markdown(progress)
    (a.root/"daily_readiness_progress_mobile.md").write_text(msg,encoding="utf-8")
    compact=a.root/"sector_first_compact_mobile.md"
    if compact.is_file():
        old=compact.read_text(encoding="utf-8").split("\n## ⑧ 오늘 분석 검증 진행률")[0].rstrip()
        compact.write_text(old+"\n\n"+msg,encoding="utf-8")
    print(json.dumps({k:progress[k] for k in (
        "asof","passed_gates","checked_gates","evidence_progress_pct",
        "market_source_status","decision")},ensure_ascii=False))

if __name__=="__main__":main()
