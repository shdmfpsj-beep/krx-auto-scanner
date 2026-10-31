#!/usr/bin/env python3
"""C3 smartphone portrait TOP2 poster: dated daily bars, real price map and close-up.

Research only. The full-price overview and zoomed candle panel have separate
axis labels; never pretend distant T1/T2 are inside the candle zoom.
No price/revenue/flow backfilling, no brokerage orders, no fabricated targets.
"""
from __future__ import annotations
import argparse,gzip,hashlib,io,json,math,zipfile
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter,MaxNLocator
from matplotlib import font_manager
import pandas as pd
from c3_confirmed_target_ladder_v2 import target_ladder

SCHEMA="C3_TOP2_PORTRAIT_LARGE_V2_RESEARCH_NO_ORDERS"
COLORS=dict(stop="#B9353C",entry="#007E73",t1="#B57412",t2="#7645A5",
            close="#263A55",positive="#D64A4A",negative="#237AAB")
BG="#FFFFFF";INK="#152437";MUTED="#546579"

def korean_font():
    available={f.name for f in font_manager.fontManager.ttflist}
    for name in ("NanumSquare","NanumGothic","Noto Sans CJK KR","UnDotum"):
        if name in available:
            plt.rcParams["font.family"]=name
            break
    plt.rcParams["axes.unicode_minus"]=False
    plt.rcParams["savefig.facecolor"]="white"

def source_data(source,ranked):
    with zipfile.ZipFile(source) as z:
        raw=z.read("c3_premove_history_v1.csv.gz")
        metadata=json.loads(z.read("status.json"))
    if metadata.get("scan_complete") is not True or metadata.get("universe",0)<2000:
        raise ValueError("ORIGINAL_FULL_MARKET_SCAN_NOT_COMPLETE")
    bar=pd.read_csv(io.BytesIO(gzip.decompress(raw)),dtype={"ticker":str,"date":str})
    ranked=pd.read_csv(ranked,dtype={"ticker":str,"asof":str})
    asof=str(metadata["market_data_date"])
    if ranked.empty or ranked.ticker.duplicated().any() or not ranked.asof.eq(asof).all():
        raise ValueError("RANK_DATE_OR_DUPLICATES_INVALID")
    return metadata,bar,ranked,hashlib.sha256(raw).hexdigest()

def choose(ranked):
    good=ranked[
       ranked.priority_class.isin(["PRIORITY_PULLBACK","SECONDARY_WATCH"]) &
       ranked.watch_low.notna() & ranked.watch_high.notna() &
       ranked.first_obstacle_krw.notna()]
    rows=good.head(2).to_dict("records")
    if len(rows)!=2:raise ValueError("FEWER_THAN_TWO_MEASURED_TOP2")
    return rows

def as_int(v):
    if not math.isfinite(float(v)) or float(v)<=0:raise ValueError("INVALID_LEVEL")
    return int(round(float(v)))

def plan(row,hist,asof):
    t=row["ticker"]
    b=hist[hist.ticker==t].sort_values("date").reset_index(drop=True)
    if b.empty or b.date.iloc[-1]!=asof or b.date.duplicated().any():
        raise ValueError("CANDLE_ASOF_OR_UNIQUE_DATES_INVALID")
    close=as_int(row["close"])
    if as_int(b.close.iloc[-1])!=close:raise ValueError("SOURCE_CLOSE_MISMATCH")
    lo,hi=as_int(row["watch_low"]),as_int(row["watch_high"])
    stop=as_int(row["structure_stop"])
    first=as_int(row["first_obstacle_krw"])
    measured=target_ladder(b,asof=asof,close=close,entry_low=lo,
       entry_high=hi,stop=stop,first_observed=first)
    second=measured["second_target"]["price_krw"] if measured["second_target"] else None
    return b,dict(ticker=t,name=row["name"],asof=asof,
       source_close=close,entry_low=lo,entry_high=hi,stop=stop,t1=first,t2=second,
       t1_pivot_date=measured["first_target"]["pivot_date"],
       t2_pivot_date=(measured["second_target"]["pivot_date"]
         if measured["second_target"] else None),
       selection_label=str(row["priority_class"]),
       source_price_regular_only_certified=False,
       trade_approved=False,orders_enabled=False)

def card(fig,x,y,w,h,caption,value,color):
    fig.patches.append(Rectangle((x,y),w,h,transform=fig.transFigure,
        facecolor="#F4F6F8",edgecolor="#D9E0E8",linewidth=1.3))
    fig.text(x+.026,y+h*.66,caption,color=color,fontsize=17,weight="bold",
        va="center",transform=fig.transFigure)
    fig.text(x+.026,y+h*.28,value,color=INK,fontsize=22,weight="bold",
        va="center",transform=fig.transFigure)

def render(b,info,out,bars=35,reference_regular_close=None):
    korean_font()
    price=info["source_close"];lo=info["entry_low"];hi=info["entry_high"]
    stop=info["stop"];t1=info["t1"];t2=info["t2"]
    items=[stop,lo,hi,price,t1]+([t2] if t2 else [])
    if not stop<lo<=hi<price<t1:raise ValueError("STRATEGY_LEVEL_SEQUENCE_INVALID")
    b=b.tail(bars).reset_index(drop=True)
    if len(b)!=bars:raise ValueError("NOT_ENOUGH_RECENT_BARS")
    fig=plt.figure(figsize=(10.3,15.4),dpi=170,facecolor=BG)
    fig.text(.065,.963,f"{info['name']}  |  {info['ticker']}",
             fontsize=33,weight="bold",color=INK)
    fig.text(.065,.938,f"강현AI C3 · {info['asof']} 일봉 · TOP2 전략",
             fontsize=18,color=MUTED)
    if reference_regular_close is None:
        notice=f"스캐너 종가 {price:,}원  |  정규장 전용 종가 미검증"
    else:
        regular=as_int(reference_regular_close)
        notice=f"스캐너 {price:,}원 / 정규장 확인 {regular:,}원  |  불일치 · 매수승인 대기" if regular!=price else \
            f"스캐너·정규장 종가 {regular:,}원 일치 확인"
    fig.text(.065,.910,notice,fontsize=16,
             color=(COLORS["stop"] if reference_regular_close is not None and reference_regular_close!=price else MUTED))
    card(fig,.065,.822,.418,.072,"① 구조손절 연구선",f"{stop:,}원",COLORS["stop"])
    card(fig,.517,.822,.418,.072,"② 매수 관찰범위",f"{lo:,}~{hi:,}원",COLORS["entry"])
    card(fig,.065,.738,.418,.072,"③ 1차 목표 · 과거 저항",f"{t1:,}원",COLORS["t1"])
    card(fig,.517,.738,.418,.072,"④ 2차 목표 · 과거 저항",
         f"{t2:,}원" if t2 else "검증된 상단 저항 없음",COLORS["t2"])
    # Entire strategy's true KRW price axis, independent from zoomed daily candles.
    axmap=fig.add_axes([.115,.645,.82,.058])
    low=min(items);high=max(items);pad=(high-low)*.05
    axmap.set_xlim(low-pad,high+pad);axmap.set_ylim(0,1)
    axmap.hlines(.52,low,high,color="#CFD7E0",linewidth=8,zorder=0)
    axmap.axvspan(lo,hi,ymin=.26,ymax=.76,color=COLORS["entry"],alpha=.23)
    for key,level in [("stop",stop),("close",price),("t1",t1),("t2",t2)]:
        if level is not None:
            axmap.vlines(level,.20,.84,color=COLORS[key],linewidth=5)
    axmap.set_yticks([])
    axmap.xaxis.set_major_locator(MaxNLocator(5))
    axmap.xaxis.set_major_formatter(FuncFormatter(lambda value,_:f"{value:,.0f}"))
    axmap.tick_params(axis="x",labelsize=12,colors=MUTED)
    for side in ("left","right","top"):axmap.spines[side].set_visible(False)
    axmap.spines["bottom"].set_color("#E2E6EC")
    fig.text(.115,.714,"전략 가격 지도 · 전체 가격대 동일 원화 축",
             fontsize=17,weight="bold",color=INK)
    fig.text(.115,.599,"일봉 확대 · 최근 "+str(bars)+"거래일 (위 가격 지도와 축 범위가 다름)",
             fontsize=17,weight="bold",color=INK)
    # Zoom: large candles around current trading levels; distant targets map above.
    ax=fig.add_axes([.11,.265,.83,.320])
    n=len(b);days=range(n)
    for j,z in enumerate(b.itertuples(index=False)):
        o,h,l,c=map(float,(z.open,z.high,z.low,z.close))
        rise=c>=o
        color=COLORS["positive"] if rise else COLORS["negative"]
        ax.vlines(j,l,h,linewidth=1.3,color=color)
        ax.add_patch(Rectangle((j-.35,min(o,c)),.70,
                 max(abs(c-o),1),linewidth=.7,edgecolor=color,
                 facecolor=color,alpha=.84))
    cl=b.close.astype(float)
    ax.plot(days,cl.rolling(5,min_periods=5).mean(),
            color="#D0901E",linewidth=2.4,label="MA5")
    ax.plot(days,cl.rolling(20,min_periods=20).mean(),
            color="#8B59C8",linewidth=2.4,label="MA20")
    ax.axhspan(lo,hi,color=COLORS["entry"],alpha=.15)
    ax.axhline(stop,linestyle="--",linewidth=2,color=COLORS["stop"])
    ax.axhline(price,linestyle=":",linewidth=1.7,color=COLORS["close"])
    ax.axhline(lo,linewidth=1,color=COLORS["entry"],alpha=.75)
    ax.axhline(hi,linewidth=1,color=COLORS["entry"],alpha=.75)
    candle_min=float(b.low.min());candle_max=float(b.high.max())
    ylo=min(stop,lo,candle_min);yhi=max(hi,price,candle_max)
    yp=(yhi-ylo)*.075
    ax.set_ylim(ylo-yp,yhi+yp)
    ax.set_xlim(-1,n)
    ax.grid(axis="y",alpha=.20)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x,_:f"{x:,.0f}"))
    ax.yaxis.set_major_locator(MaxNLocator(7))
    ax.tick_params(axis="y",labelsize=15,colors=MUTED)
    ax.tick_params(axis="x",bottom=False,labelbottom=False)
    ax.legend(loc="upper left",fontsize=13,ncol=2)
    vol=fig.add_axes([.11,.165,.83,.082],sharex=ax)
    candle_colors=[COLORS["positive"] if float(z.close)>=float(z.open)
                   else COLORS["negative"] for z in b.itertuples(index=False)]
    vol.bar(days,b.volume.astype(float),width=.72,color=candle_colors,alpha=.62)
    vol.plot(days,b.volume.astype(float).rolling(20,min_periods=20).mean(),
             color="#4B5968",linewidth=2)
    vol.grid(axis="y",alpha=.15)
    vol.tick_params(axis="y",labelsize=12,colors=MUTED)
    ticks=sorted(set(list(range(0,n,max(1,n//5)))+[n-1]))
    vol.set_xticks(ticks)
    vol.set_xticklabels([str(b.date.iloc[i])[5:] for i in ticks],fontsize=13)
    fig.text(.11,.253,"거래량 · 20일 평균선",fontsize=13,color=MUTED)
    fig.text(.065,.120,
      "기준일의 과거 일봉에서 산정된 연구전략이며 새로운 거래·매수승인이 아닙니다.",
      fontsize=13.8,weight="bold",color=COLORS["stop"])
    fig.text(.065,.096,
      "첫 저항까지의 거리와 매수가 지지 여부를 확인하세요. 주말에는 새로운 주가가 없습니다.",
      fontsize=12.8,color=MUTED)
    fig.text(.065,.071,
      "정규장 종가·실제 수급·뉴스 근거가 불완전하면 CASH / 관찰 우선.",
      fontsize=12.8,color=MUTED)
    fig.text(.065,.047,
      "가격 지도와 확대 캔들 축은 별도입니다. 두 목표가는 과거 저항이며 실현 보장이 아닙니다.",
      fontsize=11.8,color=MUTED)
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(out,dpi=170,facecolor=BG)
    plt.close(fig)
    return dict(**info,file=out.name,sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
        pixel_width=1751,pixel_height=2618,
        candle_bars=bars,reference_regular_close=reference_regular_close,
        published_target2=bool(t2),regular_close_match=(
           reference_regular_close==price if reference_regular_close is not None else None))

def run(source,ranked,outdir,bars=35,external_close_map=None):
    meta,hist,ranking,sha=source_data(source,ranked)
    output=Path(outdir);output.mkdir(parents=True,exist_ok=True)
    info=[]
    for row in choose(ranking):
        b,p=plan(row,hist,str(meta["market_data_date"]))
        reference=(external_close_map or {}).get(p["ticker"])
        info.append(render(b,p,output/f"c3_large_{p['ticker']}_portrait.png",
                           bars=bars,reference_regular_close=reference))
    manifest=dict(schema=SCHEMA,asof=meta["market_data_date"],scanned=meta["universe"],
       source_run_kst=meta.get("run_kst"),original_history_sha256=sha,
       candidates=info,no_new_session_inferred=True,
       regular_only_source_certified=False,orders_enabled=False,buy_approved=False)
    (output/"c3_large_portrait_manifest.json").write_text(
       json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False)+"\n",
       encoding="utf-8")
    return manifest

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True)
    p.add_argument("--ranked",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--bars",type=int,choices=(30,35,45),default=35)
    p.add_argument("--regular-close-json",help="Optional separately checked date-matched closes: {ticker:price}")
    a=p.parse_args()
    external=json.loads(Path(a.regular_close_json).read_text()) if a.regular_close_json else None
    output=run(a.source,a.ranked,a.output,a.bars,external)
    print(json.dumps(dict(asof=output["asof"],charts=[z["file"] for z in output["candidates"]],
        buy_approved=output["buy_approved"]),ensure_ascii=False))
