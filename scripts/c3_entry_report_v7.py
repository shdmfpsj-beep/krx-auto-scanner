"""Render existing ledgers and dated candidates without rerunning selection."""
import argparse,csv,gzip,html,json,statistics
from pathlib import Path

LABELS={"A_SUPPORT_LIMIT":"지지 지정가","B_CONFIRMED_PULLBACK":"눌림 확인 다음 시가","C_LIMITED_BREAKOUT":"돌파 확인 제한 매수"}


def stop_diagnostics(ledger,panel_path):
    tickers={t["ticker"] for x in ledger["papers"].values() for t in x["HOLDOUT"]["20"]["trades"] if t["mature"]}
    bars={t:{} for t in tickers}
    with gzip.open(panel_path,"rt") as f:
        for r in csv.DictReader(f):
            if r["ticker"] in bars:bars[r["ticker"]][r["date"]]={k:float(r[k]) for k in ("open","high","low","close")}
    result={}
    for variant,folds in ledger["papers"].items():
        p=folds["HOLDOUT"]["20"];plans={(o["plan"]["ticker"],o["plan"]["decision_date"]):o["plan"] for o in p["orders"]};rows=[]
        for t in p["trades"]:
            if not t["mature"]:continue
            plan=plans[t["ticker"],t["decision_date"]];by=bars[t["ticker"]];opening=by[t["entry_date"]]["open"]
            price=min(opening,plan["high"]) if plan["method"]=="PULLBACK" else opening
            breaches=[(d,b) for d,b in sorted(by.items()) if t["entry_date"]<=d<t["exit_date"] and b["close"]>0 and b["close"]<plan["stop"]]
            breach=breaches[0] if breaches and t["reason"]=="CLOSE_STOP_NEXT_OPEN" else None
            exit_price=by[t["exit_date"]]["open"]
            rows.append(dict(ticker=t["ticker"],decision_date=t["decision_date"],entry_date=t["entry_date"],exit_date=t["exit_date"],entry_price=price,
                structural_stop=plan["stop"],distance_pct=100*(price-plan["stop"])/price,distance_frozen_ATR=(price-plan["stop"])/plan["atr"],
                first_resistance=plan["resistance"],gross_room_to_r1_pct=100*(plan["resistance"]/price-1) if plan["resistance"] is not None else None,
                exit_reason=t["reason"],net_pct=t["net_pct"],close_breach_date=breach[0] if breach else None,
                exit_open_vs_stop_pct=100*(exit_price/plan["stop"]-1) if breach else None,
                next_open_vs_breach_close_pct=100*(exit_price/breach[1]["close"]-1) if breach else None))
        avg=lambda values:round(statistics.mean(values),6) if values else None
        stopped=[r for r in rows if r["close_breach_date"]]
        result[variant]=dict(completed=len(rows),mean_distance_pct=avg([r["distance_pct"] for r in rows]),
            min_distance_pct=min((r["distance_pct"] for r in rows),default=None),max_distance_pct=max((r["distance_pct"] for r in rows),default=None),
            close_stop_exits=len(stopped),mean_exit_open_vs_stop_pct=avg([r["exit_open_vs_stop_pct"] for r in stopped]),
            mean_next_open_vs_breach_close_pct=avg([r["next_open_vs_breach_close_pct"] for r in stopped]),trades=rows)
    return result


def render(study,current,panel,outdir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import FuncFormatter
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    study=Path(study);report=json.loads((study/"entry_report.json").read_text());ledger=json.load(gzip.open(study/"entry_ledger.json.gz","rt"))
    current=json.loads(Path(current).read_text());diagnostics=stop_diagnostics(ledger,panel)
    (root/"stop_diagnostics.json").write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2)+"\n")
    fig,ax=plt.subplots(figsize=(6.3,4.8))
    for variant,folds in ledger["papers"].items():
        rows=folds["HOLDOUT"]["20"]["equity"]
        ax.plot(range(len(rows)),[100*(r["equity"]/10_000_000-1) for r in rows],label=variant.split("_")[0]+" "+variant.split("_",1)[1],lw=1.5)
    ticks=list(range(0,len(rows),max(1,len(rows)//5)));ax.set_xticks(ticks,[rows[i]["date"][5:] for i in ticks])
    ax.set_title("Frozen B selection | 20-session model equity\nReused 95-stock cohort; NOT new out-of-sample",fontsize=10)
    ax.set_ylabel("Costed model equity (%)");ax.grid(alpha=.2);ax.legend(fontsize=8);fig.tight_layout()
    fig.savefig(root/"entry_equity.png",dpi=150);plt.close(fig)
    for item in current["research_top2"]:
        bars=current.get("chart_bars",{}).get(item["ticker"],[])
        if not bars:continue
        fig,(ax,vol)=plt.subplots(2,1,figsize=(6.3,9),sharex=True,gridspec_kw={"height_ratios":[4,1]})
        for i,b in enumerate(bars):
            color="#c94e5c" if b["close"]>=b["open"] else "#437cae"
            ax.vlines(i,b["low"],b["high"],color=color,linewidth=.8)
            ax.add_patch(Rectangle((i-.28,min(b["open"],b["close"])),.56,max(abs(b["close"]-b["open"]),b["close"]*.0002),color=color))
            vol.bar(i,b["volume"]/1_000_000,color=color,width=.65)
        for n,color in ((5,"#c4952f"),(10,"#6a9d6e"),(20,"#8a71a5")):
            ax.plot(range(n-1,len(bars)),[statistics.mean(b["close"] for b in bars[i-n+1:i+1]) for i in range(n-1,len(bars))],color=color,label=f"MA{n}",lw=1)
        p=item["entry_plans"].get("A_SUPPORT_LIMIT",{}).get("plan")
        if p:
            ax.axhspan(p["low"],p["high"],color="#388e84",alpha=.18,label=f"Research limit {p['low']:,}-{p['high']:,}")
            for level,label,color in ((p["support"],"Support","#687e92"),(p["stop"],"Structure stop","#b73b52"),(p.get("resistance"),"R1","#9c7729"),(p.get("resistance2"),"R2","#bc9d43")):
                if level is not None:ax.axhline(level,ls="--",color=color,lw=1,label=f"{label} {level:,.0f}")
        ax.axhline(item["close"],color="#324659",ls=":",label=f"Dated close {item['close']:,.0f}")
        ax.set_title(f"RESEARCH ONLY | {item['ticker']} | {current['price_asof']}\nCASH: no approved trade / no verified current-day quote",fontsize=10)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x,pos:f"{x:,.0f}"));ax.grid(alpha=.15);ax.legend(fontsize=8,loc="upper left")
        vol.set_ylabel("Vol / million",fontsize=8);vol.grid(axis="y",alpha=.1)
        ticks=list(range(0,len(bars),max(1,len(bars)//5)));vol.set_xticks(ticks,[bars[i]["date"][5:] for i in ticks],rotation=25)
        fig.tight_layout();fig.savefig(root/(item["ticker"]+"_structure.png"),dpi=160);plt.close(fig)
    fmt=lambda v,unit="%":"미확정" if v is None else f"{v:+.2f}{unit}"
    entryrows=[]
    for variant,label in LABELS.items():
        m=report["entry_metrics"][variant]["HOLDOUT"];h=m["20"];o=h["opportunity"]
        entryrows.append("<tr><th>"+label+"</th>"+"".join("<td>"+fmt(m[str(n)]["mean_net_pct"])+"</td>" for n in (5,10,20))+f"<td>{h['model_entries']}/{h['orders']} ({h['fill_rate_pct']:.1f}%)</td><td>{h['completed']}</td><td>{h['stop_rate_pct']:.1f}%</td><td>{o['profitable_reference_unfilled']} / {o['profitable_reference_no_setup']}</td><td>"+fmt(h["max_drawdown_close_pct"])+"</td></tr>")
    cards=[]
    for r in current["research_top2"]:
        p=r["entry_plans"].get("A_SUPPORT_LIMIT",{}).get("plan");price=lambda x:"미확인" if x is None else f"{x:,.0f}원"
        text=f"<h2>{html.escape(r['name'])} · {r['ticker']}</h2><p>연구 순위 {r['rank']} · {current['price_asof']} 종가 {price(r['close'])}. 정규장 원천 인증과 기업행위 전수 검증은 미완료입니다.</p><p>자기 시장 대비 20일 상대강도 {r['own_rs20']:+.2f}%p, 5일간 상대강도 개선 {r['rs_accel5']:+.2f}%p. 업종 {html.escape(r['industry'])}은 표시만 했으며 순위에 새 조건을 추가하지 않았습니다.</p>"
        if p:text+=f"<p>과거 기준 연구 지정가 {price(p['low'])}~{price(p['high'])}, 구조손절 {price(p['stop'])}, 지지 {price(p['support'])}, 첫 저항 {price(p['resistance'])}, 둘째 저항 {price(p['resistance2'])}. 상단 매수 대비 손절 거리 {p['risk_pct']:.2f}%.</p>"
        text+="<p>다음 시가 눌림·돌파 확인 신호는 미성립입니다. 매수 승인 없음. 현재 실행 가격이나 5·10·20일 상승 예측으로 사용하지 않습니다.</p>"
        image=root/(r["ticker"]+"_structure.png")
        if image.exists():text+=f'<img src="{image.name}" alt="{html.escape(r["name"])} dated structure chart">'
        cards.append("<section>"+text+"</section>")
    doc='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>C3 7차 종목 선정·매수 타점</title><style>body{font:16px/1.65 system-ui;max-width:800px;margin:auto;padding:16px;background:#f1f4f8;color:#203047}h1{font-size:25px}h2{font-size:20px}section{background:white;border-radius:12px;padding:16px;margin:16px 0}.cash{font-size:26px;font-weight:bold;color:#aa3e52}.scroll{overflow-x:auto}table{border-collapse:collapse;white-space:nowrap;font-size:13px}th,td{padding:9px;border-bottom:1px solid #ddd;text-align:right}th:first-child{text-align:left}img{width:100%;height:auto}</style><h1>C3 7차 · 좋은 종목과 실제 매수 타점</h1><section><div class="cash">최종 행동: CASH</div><p>새 모델을 채택하지 않았습니다. 체결률 상승이 손익 개선으로 이어지지 않았습니다. 새 미사용 기간의 완료 표본은 0입니다.</p><p>현재 전체 분석 가능 '''+str(current["currently_analyzable"])+'''종목, A 후보 '''+str(current["a_native_index_candidates"])+'''개, B 후보 '''+str(current["b_native_index_candidates"])+'''개. 후보 가격 기준 '''+current["price_asof"]+'''이며, 최신 공식 종가를 확보하지 못해 이전에 검증한 날짜를 표시했습니다. 이는 과거 95종목의 성과와 별개입니다.</p></section><section><h2>같은 B 선정 · 세 진입 방식 비교</h2><p>2026-05-01~11-03 재사용 기간, 같은 결정일·후보·비용·구조손절·2개 자금 슬롯. 체결률 분모는 제출된 모형 주문이며 신호 없는 150개 전체 결정을 분모로 삼지 않습니다. 손익은 완료 거래 평균입니다.</p><div class="scroll"><table><tr><th>방식</th><th>5일 순손익</th><th>10일</th><th>20일</th><th>20일 진입/주문</th><th>완료</th><th>손절률</th><th>수익기회 미체결/신호없음</th><th>종가 최대낙폭</th></tr>'''+"".join(entryrows)+'''</table></div><p>미체결·신호 없음의 수익 기회는 다음 시가 기준 비용 차감 수익이 양수인 경우이며, 실제 주문 또는 독립 거래 수가 아닙니다. 같은 종목의 연속 결정과 자금 제약을 분리한 진단값입니다. 장중 최대낙폭·실제 주문 체결은 인증하지 않았습니다.</p><img src="entry_equity.png" alt="Costed entry model equity"></section><section><h2>선정과 손절 해석</h2><p>B의 하락장 20일 시장 대비 +6.71%p에도 비용 차감 기준가격 손익은 -6.35%였습니다. 같은 결정일·같은 시장끼리 맞춘 비교에서 B-A는 상승장 -0.71%p(4개), 횡보장 -1.08%p(6개), 하락장은 대응 표본이 없습니다. 서로 다른 종목·날짜의 평균 손실 축소를 같은 날 선정 개선으로 해석하지 않습니다.</p><p>구조저점과 확인 시점의 ATR은 유지했습니다. 시가 진입 시 그 저점과 너무 멀어지는 사례가 확인됐습니다. 손절 범위를 사후 최적화하지 않았으며, 종가 이탈 뒤 다음 거래 시가와 갭·비용을 반영했습니다. 자세한 사례는 stop_diagnostics.json에 저장했습니다.</p></section><section><h2>GPT 보조 선정 C</h2><p>해시로 고정한 입력과 상승 근거·위험 반론을 함께 요구하는 출력 검증을 구현했습니다. 실제 모델 응답 0회, 유료 API 0회로 성과는 미검증입니다. 11월 6일 이후 신규 결정과 5·10·20일 결과는 아직 없습니다.</p></section>'''+"".join(cards)+'''<p>연구 브랜치 전용. 실전 주문·기존 알림·예약·기본 브랜치 변경 없음.</p></html>'''
    (root/"mobile_report.html").write_text(doc)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for k in ("study","current","panel","outdir"):p.add_argument("--"+k,required=True)
    a=p.parse_args();render(a.study,a.current,a.panel,a.outdir)
