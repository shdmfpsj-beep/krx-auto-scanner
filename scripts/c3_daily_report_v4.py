"""Whole-market dated forward audit and a concise research report. Never orders."""
import argparse,csv,gzip,hashlib,html,json,statistics
from collections import Counter,defaultdict,deque
from datetime import datetime,timezone,timedelta
from pathlib import Path

from c3_daily_top2_v4 import features,make_plan


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def known_by(received,known_at):
    a=datetime.fromisoformat(received.replace("Z","+00:00"));b=datetime.fromisoformat(known_at.replace("Z","+00:00"))
    if a.tzinfo is None or b.tzinfo is None:raise ValueError("TIMEZONE_REQUIRED")
    return a<=b


def forward_audit(panel_path,audit_path,latest_dir,basic_dir,members_path,known_at,outdir):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True);latest=Path(latest_dir);basic=Path(basic_dir)
    audit=json.loads(Path(audit_path).read_text());meta=json.loads((latest/"krx_v65_collect_status.json").read_text())
    registry=json.loads((basic/"krx_basic_v610_status.json").read_text())
    if not known_by(meta["retrieval_utc"],known_at) or not known_by(registry["received_utc"],known_at):raise ValueError("SOURCE_NOT_YET_KNOWN_AT_DECISION")
    if digest(panel_path)!=audit["panel_sha256"]:raise ValueError("PRICE_PANEL_HASH_MISMATCH")
    price_day=meta["asof"];known_day=datetime.fromisoformat(known_at.replace("Z","+00:00")).astimezone(timezone(timedelta(hours=9))).date().isoformat()
    if price_day>=known_day:raise ValueError("REQUIRES_PREVIOUS_COMPLETED_DAILY_SOURCE")
    if price_day>audit["requested_end"]:raise ValueError("LATEST_PRICE_WITHOUT_CONTINUOUS_HISTORY")
    if not meta["krx_eod_authenticated"]:raise ValueError("OFFICIAL_PRICE_SOURCE_UNAVAILABLE")
    common={};snapshots={}
    for market in ("KOSPI","KOSDAQ"):
        bp=basic/(market+"_basic_v610.csv");lp=latest/(market+"_official.csv")
        if digest(bp)!=registry["source_file_sha256"][market] or digest(lp)!=meta["market_file_sha256"][market]:raise ValueError("FORWARD_SOURCE_HASH_MISMATCH")
        with bp.open(encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):common[r["ticker"]]=r["security_group"]=="주권" and r["share_kind"]=="보통주"
        with lp.open(encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r["asof"]!=price_day or r["ticker"] in snapshots:raise ValueError("BAD_OR_DUPLICATE_FORWARD_PRICE")
                snapshots[r["ticker"]]=r
    if len(snapshots)!=meta["official_market_rows"]:raise ValueError("FORWARD_UNIVERSE_COUNT_MISMATCH")
    with open(members_path,encoding="utf-8-sig") as f:members=list(csv.DictReader(f))
    excluded={r["ticker"] for r in members if any(x in r["investment_sector"] for x in ("바이오","제약","헬스케어"))}
    study_scope={r["ticker"] for r in members}-excluded
    boundaries={(r["ticker"],r["date"]) for r in audit["reference_rebase_candidates"]}
    tails=defaultdict(lambda:deque(maxlen=90));segments=Counter()
    with gzip.open(panel_path,"rt",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t=r["ticker"]
            if t not in snapshots:continue
            if r["date"]>=price_day:continue
            tradable=r["tradable"]=="True"
            if (t,r["date"]) in boundaries or not tradable:segments[t]+=1
            b={k:float(r[k]) if r[k] not in ("","None") else None for k in ("open","high","low","close","volume","turnover_krw")}
            b.update(date=r["date"],name=r["name"],segment=segments[t],tradable=tradable,ohlc_valid=r["ohlc_valid"]=="True")
            tails[t].append(b)
            if not tradable:segments[t]+=1
    prepared={};returns={};counts=Counter();rows=[]
    for t,r in snapshots.items():
        b={k:float(r[k]) if r[k] not in ("","None") else None for k in ("open","high","low","close","volume","turnover_krw")}
        prev=tails[t][-1] if tails[t] else None
        reset=prev and (r["name"]!=prev["name"] or not b["close"] or not prev["close"] or abs(b["close"]/prev["close"]-1)>.35)
        if reset:segments[t]+=1
        tradable=r["valid_daily_bar"]=="True" and b["volume"] is not None and b["volume"]>0
        b.update(date=price_day,name=r["name"],segment=segments[t],tradable=tradable,ohlc_valid=r["valid_daily_bar"]=="True")
        tails[t].append(b);past=[b for b in tails[t] if b["segment"]==segments[t] and b["tradable"]]
        ready=tradable and len(past)>=65 and all(x["turnover_krw"] is not None and x["turnover_krw"]>0 for x in past[-20:])
        if ready:returns[t]=100*(past[-1]["close"]/past[-21]["close"]-1);prepared[t]=past
        counts["price_rows"]+=1;counts["history_ready_65"]+=int(ready)
    market20=statistics.median(returns.values()) if returns else None
    research=[]
    for t,r in sorted(snapshots.items()):
        reason="ELIGIBLE_RESEARCH_ONLY";plans=[]
        if not common.get(t):reason="COMMON_SHARE_UNCONFIRMED_OR_SPECIAL"
        elif t in excluded or any(x in r["name"] for x in ("바이오","제약","셀트리온","녹십자","약품")):reason="PHARMA_BIOTECH_EXCLUDED"
        elif t not in study_scope:reason="BUSINESS_SCOPE_UNVERIFIED_OUTSIDE_CURATED_COHORT"
        elif t not in prepared:reason="CONTINUOUS_HISTORY_OR_CORPORATE_BASIS_UNVERIFIED"
        else:
            f,error=features(prepared[t],market20)
            if f is None:reason=error
            else:
                for method in ("PULLBACK","BREAKOUT"):
                    p,error=make_plan(t,prepared[t],f,method,"FORWARD_PROXY_UNCERTIFIED")
                    if p:plans.append(method)
                if plans:research.append(dict(ticker=t,name=r["name"],setups=plans))
                else:reason="NO_ENTRY_BAND_OR_CONFIRMED_BREAKOUT"
        counts[reason]+=1;rows.append(dict(ticker=t,name=r["name"],price_asof=price_day,known_at=known_at,
            common_share=common.get(t),history_ready_65=t in prepared,reason=reason,setups=";".join(plans),action="CASH"))
    with (root/"full_market_forward_audit.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
    result=dict(schema="C3_FULL_MARKET_FORWARD_AUDIT_V4",known_at=known_at,price_asof=price_day,
        issuer_asof=registry["asof"],price_source_hashes=meta["market_file_sha256"],counts=dict(counts),
        research_scope_size=len(study_scope),research_setups=len(research),research_names=research,
        all_source_price_codes_audited=True,complete_nonbio_classification=False,
        full_market_historical_strategy_validation=False,regular_only_certified=False,
        historical_current_registry_not_used_as_past_signal=True,
        top2=[],current_action="CASH",buy_prices=None,structural_stops=None,resistances=None,
        blockers=["UNSEEN_PROFITABILITY_NOT_ESTABLISHED","REGULAR_SESSION_SCOPE_UNCERTIFIED","BUSINESS_CLASSIFICATION_COVERAGE_INCOMPLETE"],
        orders_enabled=False)
    (root/"current_decision.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    return result


def render(study,panel_path,outdir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import FuncFormatter
    root=Path(outdir);data=json.load(gzip.open(Path(study)/"daily_ledger.json.gz","rt"))
    fig,ax=plt.subplots(figsize=(7,4.5))
    for key,folds in data.items():
        rows=folds["HOLDOUT"]["20"]["equity"]
        ax.plot([r["date"] for r in rows],[100*(r["equity"]/10_000_000-1) for r in rows],label=key)
    ax.set_xticks(ax.get_xticks()[::max(1,len(ax.get_xticks())//5)]);ax.legend(fontsize=8);ax.grid(alpha=.2)
    ax.set_title("Fixed-26 vs daily | same next-session order validity");ax.set_ylabel("Model equity change / %")
    fig.autofmt_xdate();fig.tight_layout();fig.savefig(root/"equity.png",dpi=150);fig.savefig(root/"equity.svg",metadata={"Date":None});plt.close(fig)
    filled=[o for o in data["DAILY_BREAKOUT"]["DEVELOPMENT"]["20"]["orders"] if o["status"]=="MODEL_ENTRY"]
    if not filled:filled=[o for o in data["DAILY_PULLBACK"]["DEVELOPMENT"]["20"]["orders"] if o["status"]=="MODEL_ENTRY"]
    example=filled[0] if filled else None
    if example:
        p=example["plan"];bars=[]
        with gzip.open(panel_path,"rt") as f:
            for r in csv.DictReader(f):
                if r["ticker"]==p["ticker"]:bars.append(dict(date=r["date"],**{k:float(r[k]) for k in ("open","high","low","close")}))
        i=next(i for i,b in enumerate(bars) if b["date"]==p["decision_date"]);start=max(0,i-35);window=bars[start:i+26]
        fig,ax=plt.subplots(figsize=(6.5,8))
        for j,b in enumerate(window):
            c="#cf4c59" if b["close"]>=b["open"] else "#4079bd";ax.vlines(j,b["low"],b["high"],color=c,linewidth=.8)
            ax.add_patch(Rectangle((j-.3,min(b["open"],b["close"])),.6,max(abs(b["close"]-b["open"]),b["close"]*.0002),color=c))
        for n,c in ((5,"#ba8b24"),(10,"#669966"),(20,"#7b64a5")):
            ax.plot(range(len(window)),[statistics.mean(b["close"] for b in bars[max(0,j-n+1):j+1]) for j in range(start,start+len(window))],color=c,linewidth=1,label=f"MA{n}")
        ax.axhspan(p["low"],p["high"],color="#2b907c",alpha=.2,label=f"Entry {p['low']:,}-{p['high']:,}")
        for level,label,c in ((p["support"],"Confirmed support","#657a8a"),(p["stop"],"Structure stop","#bd3b4f"),(p["reference_close"],"Decision close","#354657"),(p.get("resistance"),"R1","#a87c25"),(p.get("resistance2"),"R2","#c5a660")):
            if level:ax.axhline(level,color=c,linestyle="--",label=f"{label} {level:,.0f}")
        ax.axvspan(i-start+.5,len(window)-.5,color="#99aabb",alpha=.07)
        ticks=list(range(0,len(window),max(1,len(window)//5)));ax.set_xticks(ticks,[window[j]["date"][5:] for j in ticks],rotation=30)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x,pos:f"{x:,.0f}"));ax.legend(fontsize=8);ax.grid(alpha=.15)
        ax.set_title(f"{p['ticker']} | {p['decision_date']} | archived {p['method']}\nFirst chronological fill, not selected by profit",fontsize=10)
        fig.tight_layout();fig.savefig(root/"entry_example.png",dpi=150);fig.savefig(root/"entry_example.svg",metadata={"Date":None});plt.close(fig)
    for path in root.glob('*.svg'):path.write_text("\n".join(x.rstrip() for x in path.read_text().splitlines())+"\n")
    current=json.loads((root/"current_decision.json").read_text());report=json.loads((Path(study)/"daily_report.json").read_text())
    rows=list(csv.DictReader((Path(study)/"daily_comparison.csv").open()))
    names={"FIXED26_PULLBACK":"26일 간격 · 눌림목","DAILY_PULLBACK":"매일 재평가 · 눌림목","FIXED26_BREAKOUT":"26일 간격 · 돌파 확인","DAILY_BREAKOUT":"매일 재평가 · 돌파 확인"}
    table="".join("<tr><th>"+names[r["model"]]+"</th><td>"+"/".join(r[k] for k in ("n5","n10","n20"))+"</td>"+"".join("<td>"+(f"{float(r[k]):+.2f}%" if r[k] else "미검증")+"</td>" for k in ("mean5","mean10","mean20","mdd20"))+"</tr>" for r in rows)
    images=[]
    for name in ("equity.svg","entry_example.svg"):
        path=root/name
        if path.exists():s=path.read_text();images.append(s[s.index('<svg'):])
    doc=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>C3 매일 선정·눌림목·돌파</title><style>body{{font:16px/1.65 system-ui;max-width:800px;margin:auto;padding:18px;background:#f3f5fa;color:#182333}}section,figure{{background:white;border-radius:12px;padding:16px;margin:16px 0}}h1{{font-size:25px}}.cash{{font-size:24px;color:#a43b48;font-weight:bold}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{border-bottom:1px solid #ddd;padding:8px;text-align:right}}th:first-child{{text-align:left}}svg{{width:100%;height:auto}}.scroll{{overflow-x:auto}}</style><h1>C3 · 매일 선정과 두 매수 방식</h1><section><div class="cash">현재 판단: CASH</div><p>현재 종목명·매수가·범위·손절·저항은 승인하지 않았습니다. 5·10·20일 전망은 미검증입니다.</p><p>확인한 공식 일봉 날짜 {current['price_asof']}, 전체 가격 코드 {current['counts']['price_rows']:,}개. 모든 코드를 검사했지만 비바이오 분류 범위는 불완전하여 미분류 종목을 유망 후보로 승격하지 않았습니다.</p></section><section><h2>고정 26일과 매일 재평가</h2><p>기존 관측 구간의 95종목 비교입니다. 같은 순위·비용·다음 거래일 유효 주문을 사용했고, 매일 갱신 모형은 미체결 다음 날 새 구조를 평가합니다. 체결된 같은 구조는 반복 매수하지 않습니다.</p><div class="scroll"><table><tr><th>모형</th><th>완료 5/10/20</th><th>5일</th><th>10일</th><th>20일</th><th>20일 MDD</th></tr>{table}</table></div><p>실제 계좌 성과가 아닌 비용 차감 가상 체결입니다. 정규장 전용 범위·역사적 업종 분류·생존자 편향이 완전히 검증되지 않았습니다.</p></section><section><h2>미사용 검증</h2><p>새 규칙 공개 이후인 2026-11-06 이후 결정부터 별도 검증합니다. 현재 자료에서 완료된 5·10·20일 표본은 없습니다. 이전에 본 기간의 양수 결과를 새 기간 검증 성공으로 취급하지 않았고 새 예약 작업도 만들지 않았습니다.</p></section><section><h2>손절과 체결</h2><p>두 개의 이후 일봉으로 확인된 최근 저점에서 손절을 먼저 정합니다. 완충 ATR은 저점 확인일 값으로 고정하고, 변동성이 커졌다고 과거 손절을 뒤로 내리지 않습니다. 눌림목은 지정가 한 번 접촉을 체결로 단정하지 않으며, 돌파 확인은 당일 종가가 아닌 다음 시가에서 가격 예산을 지킬 때만 진입합니다.</p></section>{''.join('<figure>'+s+'</figure>' for s in images)}<p>차트는 최초 과거 체결 예시이며 현재 추천이 아닙니다. 주문·알림·예약·기본 브랜치 변경 없음.</p></html>'''
    (root/"mobile_report.html").write_text(doc)
    (root/"chart_provenance.json").write_text(json.dumps(dict(example=example,selection="FIRST_CHRONOLOGICAL_FILL_NOT_BEST_RETURN"),ensure_ascii=False,indent=2)+"\n")


def main():
    p=argparse.ArgumentParser()
    for name in ("panel","audit","latest","basic","known-at","study","outdir"):p.add_argument('--'+name,required=True)
    p.add_argument('--members',default='reports/v68_investment_sector_members.csv');a=p.parse_args()
    result=forward_audit(a.panel,a.audit,a.latest,a.basic,a.members,a.known_at,a.outdir)
    render(a.study,a.panel,a.outdir)
    print(json.dumps(dict(price_codes=result['counts']['price_rows'],research_setups=result['research_setups'],action=result['current_action'])))


if __name__=='__main__':main()
