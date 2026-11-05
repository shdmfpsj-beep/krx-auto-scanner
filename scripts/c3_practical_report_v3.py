"""Practical CASH/TOP2 contract and dated research charts; no trading approval."""
import argparse,csv,gzip,hashlib,html,json
from pathlib import Path
from datetime import date


def current_decision(broad,issuer,requested):
    if date.fromisoformat(requested).isoformat()!=requested:raise ValueError("BAD_REQUEST_DATE")
    if broad["asof"]!=issuer["asof"]:raise ValueError("CURRENT_ASOF_JOIN_MISMATCH")
    blockers=["NO_VALIDATED_PROFITABLE_TOP2_MODEL"]
    if broad["asof"]!=requested:blockers.append("SELECTION_DATA_NOT_AT_REQUESTED_COMPLETED_DATE")
    if not broad.get("regular_1530_session_certified"):blockers.append("REGULAR_SESSION_SCOPE_UNCERTIFIED")
    if not issuer.get("independent_PIT_issuer_vintage_verified"):blockers.append("INDUSTRY_AND_ISSUER_PIT_UNVERIFIED")
    if not issuer.get("asof_earnings_and_catalyst_verified"):blockers.append("EARNINGS_AND_CATALYST_UNVERIFIED")
    if broad.get("confirmed_research_trigger_rows",0)==0:blockers.append("NO_CONFIRMED_ENTRY_IN_CURRENT_SCAN")
    blank=dict(name=None,ticker=None,selection_reason="검증된 종목·타점 조합 없음",watch_price=None,
        first_buy=None,buy_range=None,structural_stop=None,stop_distance_pct=None,resistance1=None,resistance2=None,
        forecast5="미검증",forecast10="미검증",forecast20="미검증",action="CASH")
    return dict(schema="C3_PRACTICAL_CURRENT_DECISION_V3",requested_completed_date=requested,
        selection_data_asof=broad["asof"],source_run_is_not_price_date=True,decision="CASH",
        top2=[dict(blank),dict(blank)],blockers=blockers,full_market_codes=broad["full_market_universe"],
        liquid_common_shares=broad["official_common_120day_50e8_liquid"],
        positive_fi_5day=broad["official_common_120day_liquid_5d_positive_FI"],
        moderate_trend_watch_count=broad.get("moderate_trend_no_chase_research_count"),
        historical_investor_flow_effect_verified=False,score_out_of_100=None,
        live_strategy_adopted=None,orders_enabled=False)


def charts(study,panel,ledger,outdir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import FuncFormatter
    root=Path(outdir)
    models=json.load(gzip.open(Path(study)/"top2_replay_ledger.json.gz","rt"))
    keys=[("C3_STRUCTURE__TURNOVER20","C3 structure + turnover"),
          ("FRESH_COSTED_LIMIT__SECTOR_LEADER","Fresh structure + sector"),
          ("FRESH_COSTED_LIMIT__SECTOR_LEADER__CAUSAL_EDGE_GATE","Matured evidence gate")]
    fig,ax=plt.subplots(figsize=(7,4.5))
    for key,label in keys:
        rows=models[key]["HOLDOUT"]["20"]["equity"]
        ax.plot([r["date"] for r in rows],[100*(r["equity"]/10_000_000-1) for r in rows],label=label)
    ax.set_xticks(ax.get_xticks()[::max(1,len(ax.get_xticks())//5)])
    ax.set_ylabel("Model portfolio change / %");ax.set_title("Two reserved slots | May-Nov 2026 | not live performance")
    ax.legend(fontsize=8);ax.grid(alpha=.2);fig.autofmt_xdate();fig.tight_layout()
    fig.savefig(root/"equity.png",dpi=150);fig.savefig(root/"equity.svg",metadata={"Date":None});plt.close(fig)
    # First reserved plan, not the best winner or a hindsight-selected fill.
    order=models[keys[1][0]]["DEVELOPMENT"]["20"]["orders"][0];p=order["plan"]
    t=order["ticker"];d=order["decision_date"]
    original=next(r["plan"] for r in json.load(gzip.open(ledger,"rt"))["C3_BASELINE"] if r["ticker"]==t and r["decision_date"]==d)
    bars=[]
    with gzip.open(panel,"rt") as f:
        for r in csv.DictReader(f):
            if r["ticker"]==t:bars.append(dict(date=r["date"],**{k:float(r[k]) for k in ("open","high","low","close")}))
    i=next(i for i,b in enumerate(bars) if b["date"]==d);start=max(0,i-35);window=bars[start:i+26]
    fig,ax=plt.subplots(figsize=(6.5,8))
    for j,b in enumerate(window):
        color="#cc4a58" if b["close"]>=b["open"] else "#3e78bd"
        ax.vlines(j,b["low"],b["high"],color=color,linewidth=.8)
        ax.add_patch(Rectangle((j-.3,min(b["open"],b["close"])),.6,max(abs(b["close"]-b["open"]),b["close"]*.0002),color=color))
    for n,color in ((5,"#b48b17"),(10,"#608d5a"),(20,"#775da9")):
        means=[sum(b["close"] for b in bars[max(0,j-n+1):j+1])/min(n,j+1) for j in range(start,start+len(window))]
        ax.plot(range(len(window)),means,color=color,linewidth=1,label=f"MA{n}")
    ax.axhspan(original["low"],original["high"],color="#7e8895",alpha=.18,label="Original watch band")
    ax.axhspan(p["low"],p["high"],color="#268873",alpha=.25,label=f"New band {p['low']:,}-{p['high']:,}")
    ax.axhline(p["stop"],color="#be3446",linestyle="--",label=f"Structure stop {p['stop']:,}")
    ax.axhline(bars[i]["close"],color="#425268",linestyle=":",label=f"Decision close {bars[i]['close']:,.0f}")
    for k,color in (("resistance","#a77520"),("resistance2","#c2a05f")):
        if p.get(k):ax.axhline(p[k],color=color,linestyle="-.",label=f"{'R1' if k=='resistance' else 'R2'} {p[k]:,.0f}")
    ax.axvspan(i-start,len(window)-.5,color="#91a0af",alpha=.07)
    ticks=list(range(0,len(window),max(1,len(window)//5)));ax.set_xticks(ticks,[window[j]["date"][5:] for j in ticks],rotation=30)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x,pos:f"{x:,.0f}"));ax.grid(alpha=.15)
    ax.set_title(f"{t} | {d}\nFirst chronological reserved plan; not current TOP2",fontsize=11)
    ax.legend(loc="best",fontsize=8);ax.set_ylabel("Official archived EOD units / KRW")
    fig.text(.09,.015,"Grey dates are outcomes. Limit contact is not verified execution.",fontsize=8)
    fig.tight_layout(rect=(0,.04,1,1));fig.savefig(root/"entry_geometry.png",dpi=150)
    fig.savefig(root/"entry_geometry.svg",metadata={"Date":None});plt.close(fig)
    for name in ("equity.svg","entry_geometry.svg"):
        path=root/name;path.write_text("\n".join(x.rstrip() for x in path.read_text().splitlines())+"\n")
    return dict(ticker=t,decision_date=d,chosen_without_outcome_filter=True,order_status=order["status"])


def render(study,panel,ledger,broad_dir,issuer_dir,requested,outdir):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    broad_dir=Path(broad_dir);broad=json.loads((broad_dir/"broad_watch_v611_status.json").read_text())
    for name,digest in broad["artifact_file_sha256"].items():
        if hashlib.sha256((broad_dir/name).read_bytes()).hexdigest()!=digest:raise ValueError("CURRENT_SCAN_HASH_MISMATCH")
    issuer=json.loads((Path(issuer_dir)/"issuer_entry_v610_status.json").read_text())
    decision=current_decision(broad,issuer,requested)
    chart=charts(study,panel,ledger,root)
    (root/"current_decision.json").write_text(json.dumps(decision,ensure_ascii=False,indent=2)+"\n")
    (root/"chart_provenance.json").write_text(json.dumps(chart,indent=2)+"\n")
    images=[]
    for name in ("equity.svg","entry_geometry.svg"):
        s=(root/name).read_text();images.append(s[s.index("<svg"):])
    comparison=list(csv.DictReader((Path(study)/"top2_comparison.csv").open()))
    entry_names={"C3_STRUCTURE":"기존 구조","COSTED_LIMIT":"매수가 상한","FRESH_COSTED_LIMIT":"최근 지지·상한"}
    rank_names={"TURNOVER20":"거래대금순","STOCK_RS20":"종목 상대강도순","SECTOR_LEADER":"업종·주도주순"}
    def label(model):
        parts=model.split("__");return entry_names[parts[0]]+" · "+rank_names[parts[1]]+(" · 최근 성과 확인" if len(parts)>2 else "")
    rows="".join("<tr><th>"+html.escape(label(r['model']))+"</th><td>"+(f"{float(r['mean5']):+.2f}%" if r['mean5'] else '미검증')+"</td><td>"+(f"{float(r['mean10']):+.2f}%" if r['mean10'] else '미검증')+"</td><td>"+(f"{float(r['mean20']):+.2f}%" if r['mean20'] else '미검증')+"</td></tr>" for r in comparison)
    doc=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>C3 실용 TOP2 연구</title><style>body{{font:16px/1.65 system-ui;max-width:800px;margin:auto;padding:18px;background:#f3f5f9;color:#182334}}section,figure{{background:white;padding:16px;border-radius:12px;margin:16px 0}}h1{{font-size:25px}}h2{{font-size:20px}}.cash{{color:#a43a43;font-weight:bold;font-size:24px}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{text-align:right;padding:8px;border-bottom:1px solid #ddd}}th:first-child{{text-align:left;max-width:240px;overflow-wrap:anywhere}}svg{{width:100%;height:auto}}.scroll{{overflow-x:auto}}</style>
<h1>C3 · 좋은 종목 / 매수가 / 구조손절</h1><section><div class="cash">최종 판단: CASH</div><p>검증된 종목·타점 조합이 없어 현재 TOP2 가격을 제시하지 않습니다.</p><p>판단 요청 기준일 {requested}, 실제 전체 시장 선정 자료 {broad['asof']}. 오늘 실행된 작업도 과거 가격을 재사용할 수 있어 실행 날짜와 가격 날짜를 분리했습니다.</p><table><tr><th>구분</th><th>TOP1</th><th>TOP2</th></tr><tr><th>종목·매수가·범위·손절·저항</th><td>미제시</td><td>미제시</td></tr><tr><th>5·10·20일 전망</th><td>미검증</td><td>미검증</td></tr><tr><th>행동</th><td>CASH</td><td>CASH</td></tr></table></section>
<section><h2>이번에 바뀐 검증</h2><p>같은 과거 결정일에서 구조손절을 먼저 고정하고 호가 단위에 맞춘 매수가 상한을 비교했습니다. 실제로 두 자리만 예약하고 미체결 때도 자리를 점유합니다. 미래에 체결될 종목만 골라 빈자리를 채우지 않습니다. 1주 단위와 비용·슬리피지·정수 수량·청산가치 기준 일별 낙폭을 반영했습니다.</p><p>기존 12가지 타점 실험은 재실행하지 않았습니다. 이번에는 거래대금·상대강도·업종 주도 순위와 세 가지 매수 규칙을 결합해 실제 기회 감소를 확인했습니다.</p></section>
<section><h2>95종목의 TOP2 검증 구간 모형손익</h2><div class="scroll"><table><tr><th>모형</th><th>5일</th><th>10일</th><th>20일</th></tr>{rows}</table></div><p>기간별 완료 표본은 적고 서로 다릅니다. 가격·업종 선정 편향, 미인증 정규장 범위가 남습니다. 기존 C3의 실제 과거 순위 복원도 아닙니다. 이 결과를 실전 성과로 승인하지 않았습니다.</p></section>
<section><h2>체결 기회를 포함하면 개선이 사라짐</h2><p>개발 구간에서 양수였던 모형이 검증 구간에서 다시 음수였습니다. 더 좋은 손익비를 위해 지정가를 낮추면 체결 기회가 감소했습니다. 최근 성과 확인 장치는 검증 구간에서 거래가 0건이므로 수익성 개선으로 인정하지 않았습니다.</p><p>현재 전체 시장 {broad['full_market_universe']:,}개 코드 중 유동성 확인 보통주 {decision['liquid_common_shares']}개, 최근 5일 외국인·기관 합산 순매수 {decision['positive_fi_5day']}개입니다. 이 스냅샷으로 과거 수급의 예측력을 입증하지는 못했습니다. 재무·뉴스·수급이 미확인일 때 점수를 더하지 않습니다.</p></section>
<figure>{images[0]}<figcaption>동시에 최대 두 종목만 보유하는 가상 포트폴리오. 현금 0%는 거래 없음이며 수익 모델 성공이 아닙니다.</figcaption></figure><figure>{images[1]}<figcaption>가장 먼저 예약한 과거 계획. 현재 추천이 아니며 수익·체결 여부로 사례를 고르지 않았습니다.</figcaption></figure></html>'''
    (root/"mobile_report.html").write_text(doc);return decision


def main():
    p=argparse.ArgumentParser()
    for name in ("study","panel","ledger","broad","issuer","requested-date","outdir"):p.add_argument("--"+name,required=True)
    a=p.parse_args();r=render(a.study,a.panel,a.ledger,a.broad,a.issuer,a.requested_date,a.outdir)
    print(json.dumps(dict(decision=r["decision"],asof=r["selection_data_asof"],blockers=r["blockers"])))


if __name__=="__main__":main()
