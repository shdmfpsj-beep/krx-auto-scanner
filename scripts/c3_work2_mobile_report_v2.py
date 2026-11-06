"""Mobile research evidence, not today's TOP2 recommendation."""
import argparse
import csv
import gzip
import html
import json
from pathlib import Path


def render_chart(case,bars,path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import FuncFormatter
    selected=next(i for i,b in enumerate(bars) if b["date"]==case["decision_date"])
    last=next(i for i,b in enumerate(bars) if b["date"]==case["exit_date"])
    start=max(0,selected-35);window=bars[start:min(len(bars),max(selected+27,last+4))]
    fig,(ax,vol)=plt.subplots(2,1,figsize=(6.6,8.4),sharex=True,gridspec_kw=dict(height_ratios=[4,1]))
    fig.patch.set_facecolor("#f5f7fb")
    for i,b in enumerate(window):
        color="#d84e58" if b["close"]>=b["open"] else "#3978c5"
        ax.vlines(i,b["low"],b["high"],color=color,linewidth=1)
        ax.add_patch(Rectangle((i-.3,min(b["open"],b["close"])),.6,
                     max(abs(b["close"]-b["open"]),b["close"]*.0003),facecolor=color,edgecolor=color))
        vol.bar(i,b["volume"]/1e6,color=color,width=.65)
    for n,color in ((5,"#b78c19"),(20,"#624a9a")):
        values=[]
        for i in range(start,start+len(window)):
            values.append(sum(b["close"] for b in bars[max(0,i-n+1):i+1])/min(n,i+1))
        ax.plot(range(len(window)),values,color=color,linewidth=1,label=f"MA{n}")
    ax.axhline(case["entry_price"],color="#16846d",linewidth=1.5,label=f"Model entry {case['entry_price']:,.0f}")
    ax.axhline(case["structure_stop"],color="#b53645",linestyle="--",linewidth=1.5,label=f"Frozen stop {case['structure_stop']:,.0f}")
    if case["first_resistance"]:
        ax.axhline(case["first_resistance"],color="#9a7220",linestyle=":",label=f"Frozen R1 {case['first_resistance']:,.0f}")
    ax.axvspan(selected-start,len(window)-.5,color="#8b95a6",alpha=.09)
    for key,label,color in (("decision_date","Decision","#8c6820"),("entry_date","Model entry","#16846d"),("exit_date","Model exit","#b53645")):
        i=next(i for i,b in enumerate(window) if b["date"]==case[key])
        ax.axvline(i,color=color,linewidth=.8,alpha=.7)
        vol.axvline(i,color=color,linewidth=.8,alpha=.7)
    ax.set_title(f"{case['ticker']} | {case['decision_date']}\nLegacy model net {case['net_pct']:+.2f}% (not actual fills)",fontsize=12,loc="left")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x,p:f"{x:,.0f}"))
    ax.set_ylabel("Official dated EOD price / KRW")
    ax.legend(loc="best",fontsize=8,framealpha=.9)
    vol.set_ylabel("Vol / mn")
    ticks=list(range(0,len(window),max(1,len(window)//5)))
    vol.set_xticks(ticks,[window[i]["date"][5:] for i in ticks],rotation=30)
    for axis in (ax,vol):axis.grid(alpha=.15);axis.set_axisbelow(True)
    fig.text(.08,.02,"Archived model levels; source/session basis remains uncertified.\nShaded dates are outcomes unavailable at the decision.",fontsize=8,color="#505d72")
    fig.tight_layout(rect=(0,.055,1,1))
    fig.savefig(path.with_suffix(".png"),dpi=150)
    fig.savefig(path.with_suffix(".svg"),metadata={"Date":None})
    plt.close(fig)
    svg=path.with_suffix(".svg");svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines())+"\n")


def render(competition_dir,panel_path,outdir,cases_path):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    report=json.loads((Path(competition_dir)/"competition_report.json").read_text())
    cases=json.loads(Path(cases_path).read_text())["cases"]
    chosen=[next(c for c in cases if c["ticker"]==ticker and c["decision_date"]==day)
            for ticker,day in (("007810","2026-06-15"),("086280","2026-05-13"),("012330","2026-05-06"))]
    bars={c["ticker"]:[] for c in chosen}
    with gzip.open(panel_path,"rt",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["ticker"] in bars:
                bars[r["ticker"]].append(dict(date=r["date"],**{k:float(r[k]) for k in ("open","high","low","close","volume")}))
    images=[]
    for c in chosen:
        path=root/(c["ticker"]+"_"+c["decision_date"])
        render_chart(c,bars[c["ticker"]],path)
        svg=path.with_suffix(".svg").read_text();svg=svg[svg.index("<svg"):]
        images.append("<figure>"+svg+"<figcaption>과거 사례 "+html.escape(c["ticker"])+" · "+html.escape(c["decision_date"])+"</figcaption></figure>")
    names={"C3_BASELINE":"기존 C3 구조", "FIRST_RETEST":"돌파 후 첫 재시험", "MA5_PULLBACK":"5일선 눌림목",
           "MA10_PULLBACK":"10일선 눌림목","MA20_PULLBACK":"20일선 눌림목","VOLUME_REEXPANSION":"거래량 재확대",
           "VCP_PREBREAKOUT":"VCP·돌파 전","RS_FIRST_PULLBACK":"상대강도 첫 눌림","ICT_RETEST":"ICT 재시험",
           "C3_RISK_RR_GATE":"비용·위험 예산","FRESH_SUPPORT_LIMIT":"최근 확인 지지점","COMPOSITE_HYPOTHESIS":"복합 가설"}
    rows=[]
    for s,cohorts in report["summaries"].items():
        stats=cohorts["NEW_TICKER_CONFIRMATION"]["HOLDOUT"]
        cells=[]
        for h in ("5","10","20"):
            x=stats[h];cells.append(f"{x['mean_net_pct']:+.2f}%<small>n={x['completed']}</small>" if x["mean_net_pct"] is not None else "미검증")
        rows.append("<tr><th>"+html.escape(names[s])+"</th>"+"".join("<td>"+x+"</td>" for x in cells)+"</tr>")
    a=report["audit"]
    text=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>C3 2차 연구 결과</title><style>body{{font:16px/1.65 system-ui,sans-serif;background:#f2f5f9;color:#182334;max-width:760px;margin:0 auto;padding:18px}}h1{{font-size:26px}}h2{{font-size:21px}}section,figure{{background:white;border-radius:14px;padding:18px;margin:18px 0;box-shadow:0 2px 12px #1122330c}}.cash{{color:#92383e;font-size:22px;font-weight:700}}table{{border-collapse:collapse;font-size:14px;width:100%}}th,td{{border-bottom:1px solid #e0e5eb;padding:10px 5px;text-align:right}}th:first-child{{text-align:left}}small{{display:block;color:#687489}}svg{{width:100%;height:auto}}figure{{padding:6px}}figcaption{{padding:8px 12px;color:#59667a}}.scroll{{overflow-x:auto}}a{{color:#255bb2}}</style>
<h1>C3 TOP2 · 2차 연구 결과</h1><p>공식 일별 응답 원본을 사용한 연구 · 실전 매수 추천 아님</p>
<section><div class="cash">최종 행동: CASH · 새 전략 채택 보류</div><p>비용·슬리피지를 반영한 20일 모형손익은 비교한 매수 타점에서 모두 음수입니다. 손실 감소 탐색치는 있지만 수익성 개선을 확정할 근거는 부족합니다.</p></section>
<section><h2>데이터 범위</h2><p>{a['effective_start']}~{a['effective_end']} · {a['published_sessions']}개 조회 거래일<br>공식 응답 {a['raw_source_tickers']:,}개 코드 / {a['raw_source_rows']:,}개 일봉<br>비교 집단 {a['cohort_tickers']}개 / {a['cohort_bars']:,}개 일봉<br>기존 16개를 제외한 비교 집단 {len(a['confirmation_tickers'])}개</p><p>11월 4일은 양 시장 빈 응답으로 제외했습니다. 종목군·업종의 과거 시점 일치, 정규장 전용 가격, 기업행위 원인은 완전 인증되지 않았습니다. 현재 분류로 고른 비교 집단의 생존자·선정 편향이 남습니다.</p></section>
<section><h2>동일 비용으로 비교한 매수 타점</h2><p>2026-05-01 이후 · 기존 연구 16개 종목 제외. 관찰 창 완료 건수는 기간마다 다릅니다.</p><div class="scroll"><table><thead><tr><th>전략</th><th>5일</th><th>10일</th><th>20일</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div><p>매수비용 0.15%, 매도비용 0.50%, 슬리피지 양쪽 각 0.10%. 종가 신호는 다음 거래 가능 시가에 체결을 가정하며, 기간 청산도 다음 시가를 사용합니다. 모든 값은 미인증 가상 체결 모형입니다.</p></section>
<section><h2>해석과 다음 검증</h2><p>최근 확인 지지점을 쓰면 기준선보다 평균 손실이 줄어드는 탐색치가 나왔지만, 개발 기간과 검증 기간의 결과가 뒤집혔습니다. 상대강도 눌림 후 5일 청산의 작은 양수 평균도 신뢰구간에 0이 포함되어 채택하지 않았습니다.</p><p>손절 이후의 고가 도달은 실현 가능한 수익과 다릅니다. 동일 봉 손절·목표 접촉은 두 시나리오로 남겼고, 기업행위·공백·미완료 창은 구분해 기록했습니다. 실제 TOP2 순위·포트폴리오 최대낙폭은 이번에 재구성하지 못했습니다.</p></section>
<section><h2>기존 손실의 핵심</h2><p>기존 완료 14건 중 손실 13건. 손실 사례의 평균 구성은 구조손절 거리 -8.43%p, 종가 이탈 추가분 -1.97%p, 다음 시가 갭 순효과 -0.02%p, 비용 -0.58%p입니다. 변동성·먼 손절·가까운 저항은 사전 가설이며 인과 효과가 검증된 조건은 아닙니다.</p><p>아래는 과거 연구 사례입니다. 현재 매수·손절 가격으로 사용하지 마세요.</p></section>
{''.join(images)}<p><a href="https://github.com/shdmfpsj-beep/krx-auto-scanner/pull/30">초안 PR #30</a> · 주문·알림·예약 작업 변경 없음</p></html>'''
    (root/"mobile_report.html").write_text(text,encoding="utf-8")
    return dict(charts=len(chosen),decision="CASH",orders_enabled=False)


def main():
    p=argparse.ArgumentParser();p.add_argument("--competition",required=True);p.add_argument("--panel",required=True)
    p.add_argument("--outdir",required=True);p.add_argument("--cases",default="reports/c3_work2_20261105/legacy_loss_diagnostics.json")
    a=p.parse_args();print(json.dumps(render(a.competition,a.panel,a.outdir,a.cases)))


if __name__=="__main__":main()
