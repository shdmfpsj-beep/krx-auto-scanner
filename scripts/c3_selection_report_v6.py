"""Mobile research results and archived price geometry; current action is CASH."""
import argparse,csv,gzip,html,json,statistics
from pathlib import Path


def render(study,panel,outdir,probe=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import FuncFormatter
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True);study=Path(study)
    report=json.loads((study/"factor_report.json").read_text());ledger=json.load(gzip.open(study/"ledger.json.gz","rt"))
    fig,ax=plt.subplots(figsize=(7,4.5))
    for name in ("A_DAILY_PULLBACK","B_DAILY_PULLBACK"):
        rows=ledger["papers"][name]["HOLDOUT"]["20"]["equity"]
        ax.plot([r["date"] for r in rows],[100*(r["equity"]/10_000_000-1) for r in rows],label=name)
    ticks=list(range(0,len(rows),max(1,len(rows)//5)));ax.set_xticks(ticks,[rows[i]["date"] for i in ticks],rotation=25)
    ax.set_title("Same pullback and stop | selection A vs B | 20 sessions");ax.set_ylabel("Model equity / %");ax.grid(alpha=.2);ax.legend(fontsize=9)
    fig.tight_layout();fig.savefig(root/"selection_equity.png",dpi=150);fig.savefig(root/"selection_equity.svg",metadata={"Date":None});plt.close(fig)
    p=ledger["chart_example"];caption="과거 구조 예시 없음"
    if p:
        bars=[]
        with gzip.open(panel,"rt") as f:
            for r in csv.DictReader(f):
                if r["ticker"]==p["ticker"]:bars.append(dict(date=r["date"],name=r["name"],**{k:float(r[k]) for k in ("open","high","low","close")}))
        i=next(i for i,b in enumerate(bars) if b["date"]==p["decision_date"]);a=max(0,i-40);window=bars[a:i+22]
        fig,ax=plt.subplots(figsize=(6.3,8))
        for j,b in enumerate(window):
            c="#c84f59" if b["close"]>=b["open"] else "#477eb2";ax.vlines(j,b["low"],b["high"],color=c,linewidth=.8)
            ax.add_patch(Rectangle((j-.28,min(b["open"],b["close"])),.56,max(abs(b["close"]-b["open"]),b["close"]*.0002),color=c))
        for n,color in ((5,"#bd9729"),(10,"#68a06b"),(20,"#8170aa")):
            ax.plot(range(len(window)),[statistics.mean(b["close"] for b in bars[max(0,j-n+1):j+1]) for j in range(a,a+len(window))],color=color,label=f"MA{n}",linewidth=1)
        ax.axhspan(p["low"],p["high"],color="#3b9f8b",alpha=.18,label=f"Entry {p['low']:,}-{p['high']:,}")
        for level,label,color in ((p["reference_close"],"Decision close","#354657"),(p["support"],"Support","#6b8195"),(p["stop"],"Structure stop","#bb4051"),(p.get("resistance"),"R1","#a57b31"),(p.get("resistance2"),"R2","#c1a446")):
            if level is not None:ax.axhline(level,ls="--",color=color,label=f"{label} {level:,.0f}")
        ax.axvspan(i-a+.5,len(window)-.5,color="#96a9b9",alpha=.08)
        ticks=list(range(0,len(window),max(1,len(window)//5)));ax.set_xticks(ticks,[window[j]["date"][5:] for j in ticks],rotation=25)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x,pos:f"{x:,.0f}"));ax.set_title(f"ARCHIVED {p['ticker']} | {p['decision_date']}\nFirst planned case; not selected by return",fontsize=10)
        ax.grid(alpha=.15);ax.legend(fontsize=8);fig.tight_layout()
        fig.savefig(root/"archived_structure.png",dpi=150);fig.savefig(root/"archived_structure.svg",metadata={"Date":None});plt.close(fig)
        caption=bars[i]["name"]+" "+p["ticker"]+" · "+p["decision_date"]+" 과거 최초 구조 예시. 현재 추천 아님."
    def number(v,unit="%"):
        return "미검증" if v is None else f"{v:+.2f}"+unit
    table=[]
    for model,label in (("A","A 기존 선정"),("B","B 시장 상대강도·개선")):
        m=report["selection"][model]["DAILY"]["HOLDOUT"]
        table.append("<tr><th>"+label+"</th><td>"+"/".join(str(m[str(h)]["completed"]) for h in (5,10,20))+"</td>"+"".join("<td>"+number(m[str(h)]["mean_excess_pct"],"%p")+"</td>" for h in (5,10,20))+"</tr>")
    images=[]
    for name in ("selection_equity.svg","archived_structure.svg"):
        path=root/name
        if path.exists():
            s="\n".join(line.rstrip() for line in path.read_text().splitlines())+"\n";path.write_text(s);images.append(s[s.index("<svg"):])
    current_probe=json.loads(Path(probe).read_text()) if probe and Path(probe).exists() else None
    price_note="11월 5일 공식 가격 조회 결과 없음"
    if current_probe:price_note="; ".join(r["asof"]+" 공식 조회 "+r["status"]+" · "+str(r["official_market_rows"])+"코드" for r in current_probe["dates"])
    doc='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>C3 선정 능력 6차</title><style>body{font:16px/1.65 system-ui;max-width:780px;margin:auto;padding:18px;background:#f2f5f9;color:#1c293c}section,figure{background:white;border-radius:12px;padding:16px;margin:16px 0}h1{font-size:25px}.cash{color:#ad4051;font-size:25px;font-weight:bold}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:9px;border-bottom:1px solid #ddd;text-align:right}th:first-child{text-align:left}svg{width:100%;height:auto}</style><h1>C3 · 종목 선정 능력 검증</h1><section><div class="cash">현재 행동: CASH</div><p>승인한 TOP2가 없으므로 현재 종목·종가·매수 범위·손절·저항·전망은 제시하지 않았습니다.</p><p>'''+html.escape(price_note)+'''</p><p>현재 분석 가능 1,983종목과 과거 검증 95종목을 구분합니다. 새 업종·재무·뉴스를 과거 신호에 소급하지 않았습니다.</p></section><section><h2>A/B 선정 비교</h2><p>재사용 비교 기간 2026년 5월~11월 3일. 같은 종목의 관찰 구간이 겹치지 않도록 20거래일 간격으로 평가했습니다. 평균은 실제 계좌 수익률이 아닙니다.</p><div class="scroll"><table><tr><th>방식</th><th>완료 5/10/20</th><th>5일 지수 대비</th><th>10일</th><th>20일</th></tr>'''+"".join(table)+'''</table></div><p>KOSPI·KOSDAQ 지수값은 네이버 제공 자료로 날짜·OHLC·중복을 검사했습니다. KRX 직접 원본과의 독립 대조는 미완료입니다. 과거에 이미 본 기간의 결과를 새 기간 외 검증으로 취급하지 않습니다.</p></section><section><h2>AI 추가 검토 C</h2><p>공개 TradingAgents·AI Hedge Fund의 역할 분리와 시점 기록 구조를 검토했습니다. 과거 결과를 가린 입력·해시·시각·근거 필드 검증 인터페이스만 구현했습니다. 실제 AI 응답 실험은 미실행이고 유료 API 호출·결제는 0입니다.</p><p>11월 6일 이후의 신규 결정은 아직 성과가 완성되지 않았습니다. 완료 표본 0은 0% 수익의 성공을 뜻하지 않습니다.</p></section><section><h2>같은 진입·같은 손절의 참고 자산 곡선</h2><p>기존 두 자리·지정가 체결 가정·확인 저점과 ATR 고정·종가 이탈 후 다음 거래 시가·거래비용을 유지했습니다. 장중 최대낙폭과 실제 체결 인증은 아닙니다.</p></section>'''+"".join('<figure>'+s+'</figure>' for s in images)+'''<p>'''+html.escape(caption)+'''</p><p>실전 주문·알림·예약·기본 브랜치 변경 없음.</p></html>'''
    (root/"mobile_report.html").write_text(doc)
    (root/"chart_provenance.json").write_text(json.dumps(dict(selection="FIRST_PLANNED_CASE_NOT_BEST_RETURN",plan=p,current_action="CASH"),ensure_ascii=False,indent=2)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for k in ("study","panel","outdir"):p.add_argument("--"+k,required=True)
    p.add_argument("--probe",default="");a=p.parse_args();render(a.study,a.panel,a.outdir,a.probe)
