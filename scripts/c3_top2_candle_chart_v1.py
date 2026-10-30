#!/usr/bin/env python3
"""C3 TOP2 mobile-friendly 45-day candlestick + volume + decision lines.

Dated research-only OHLCV from the original frozen 2026-10-30 scan.
Does NOT certify regular-only prices or authorize any buy/order.
"""
from __future__ import annotations
import argparse,gzip,hashlib,io,json,zipfile
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter,MaxNLocator
import pandas as pd

SCHEMA='C3_TOP2_DAILY_CANDLES_WITH_VOLUME_V1_NO_BUY'
SOURCE_RUN='41051723762'
ASOF='2026-10-30'

def choose_font():
    fonts={x.name for x in font_manager.fontManager.ttflist}
    for name in ('NanumGothic','Noto Sans CJK KR','Noto Sans KR','Malgun Gothic'):
        if name in fonts:
            plt.rcParams['font.family']=name
            break
    plt.rcParams['axes.unicode_minus']=False

def load(source,ranked):
    with zipfile.ZipFile(source) as z:
        raw=z.read('c3_premove_history_v1.csv.gz')
        status=json.loads(z.read('status.json'))
    if (status['market_data_date']!=ASOF or status['universe']!=2625):
        raise ValueError('FROZEN_SCAN_DATE_OR_UNIVERSE_MISMATCH')
    history=pd.read_csv(io.BytesIO(gzip.decompress(raw)),dtype={'ticker':str})
    ranked=pd.read_csv(ranked,dtype={'ticker':str})
    if ranked.ticker.duplicated().any():
        raise ValueError('RANKED_DUPLICATE_TICKERS')
    required={'ticker','name','asof','close','watch_low','watch_high',
              'structure_stop','first_obstacle_krw','priority_class'}
    if not required<=set(ranked.columns):
        raise ValueError('V5_RANKED_COLUMNS_MISSING')
    return history,ranked.set_index('ticker'),hashlib.sha256(raw).hexdigest()

def assert_study_levels(row,b):
    required=('close','watch_low','watch_high','structure_stop','first_obstacle_krw')
    vals={k:float(row[k]) for k in required}
    if row['asof']!=ASOF or b.date.iloc[-1]!=ASOF:
        raise ValueError('CANDLE_PRICE_ASOF_MISMATCH')
    if not (0<vals['structure_stop']<vals['watch_low']<=vals['watch_high']
             <vals['close']<vals['first_obstacle_krw']):
        raise ValueError('UNUSABLE_STOP_ENTRY_RESISTANCE_GEOMETRY')
    if vals['close']!=float(b.close.iloc[-1]):
        raise ValueError('QUOTE_NOT_EQUAL_TO_ORIGINAL_OHLCV')
    if b.date.duplicated().any() or (b[['open','high','low','close','volume']]<=0).any().any():
        raise ValueError('INVALID_OR_HALTED_OHLCV')
    return vals

def render(history,ticker,row,path,bars=45):
    b=history[history.ticker==ticker].sort_values('date').tail(bars).reset_index(drop=True)
    if len(b)!=bars:
        raise ValueError('SHORT_CANDLE_HISTORY')
    p=assert_study_levels(row,b)
    fig=plt.figure(figsize=(13.4,7.9),dpi=145)
    ax=fig.add_axes([.075,.29,.83,.60])
    vol=fig.add_axes([.075,.115,.83,.148],sharex=ax)
    for j,z in enumerate(b.itertuples(index=False)):
        o,h,l,c=map(float,(z.open,z.high,z.low,z.close))
        ax.vlines(j,l,h,linewidth=1.2,alpha=.88)
        ax.add_patch(Rectangle((j-.31,min(o,c)),.62,max(abs(c-o),.6),
                               linewidth=1,fill=c<o,alpha=.92))
    close=b.close.astype(float)
    n=len(b)
    ax.plot(range(n),close.rolling(5,min_periods=5).mean(),linewidth=1.4,label='MA5')
    ax.plot(range(n),close.rolling(20,min_periods=20).mean(),linewidth=1.6,label='MA20')
    lo,hi,stop,res=(p['watch_low'],p['watch_high'],
                    p['structure_stop'],p['first_obstacle_krw'])
    ax.axhspan(lo,hi,alpha=.15,label='Pullback watch band')
    ax.axhline(lo,linewidth=.8,linestyle='--',alpha=.75)
    ax.axhline(hi,linewidth=.8,linestyle='--',alpha=.75)
    ax.axhline(stop,linewidth=1.9,linestyle='--',label='Structure stop (study)')
    extremes=[float(b.low.min()),float(b.high.max()),stop,lo,hi]
    if res<=max(extremes)*1.05:
        extremes.append(res)
    bot,top=min(extremes),max(extremes)
    pad=(top-bot)*.075
    ax.set_ylim(bot-pad,top+pad)
    if res<=ax.get_ylim()[1]:
        ax.axhline(res,linestyle=':',linewidth=2,label='First resistance')
        ax.text(n-.4,res,f'Resistance {int(res):,}',va='bottom',ha='right',fontsize=9)
    else:
        ax.text(.985,.96,f'First resistance ↑ {int(res):,} KRW (above chart)',
                ha='right',va='top',transform=ax.transAxes,fontsize=10)
    ax.scatter([n-1],[float(close.iloc[-1])],s=45,zorder=5)
    ax.text(n-1.8,float(close.iloc[-1]),f'Close {int(close.iloc[-1]):,}',
            ha='right',va='bottom',fontsize=10)
    ax.set_xlim(-.8,n+.5)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x,_:f'{x:,.0f}'))
    ax.yaxis.set_major_locator(MaxNLocator(7))
    ax.grid(axis='y',alpha=.23)
    vol.bar(range(n),b.volume.astype(float),width=.62,alpha=.45)
    vol.plot(range(n),b.volume.astype(float).rolling(20,min_periods=20).mean(),linewidth=1.5)
    vol.set_ylabel('Volume',fontsize=9)
    vol.grid(axis='y',alpha=.15)
    vol.yaxis.set_major_locator(MaxNLocator(3))
    stride=max(1,n//9)
    ticks=sorted(set(range(0,n,stride))|{n-1})
    vol.set_xticks(ticks)
    vol.set_xticklabels([str(b.date.iloc[i])[5:] for i in ticks],fontsize=9)
    ax.tick_params(axis='x',labelbottom=False)
    ax.legend(loc='lower left',fontsize=9,ncol=2)
    fig.text(.075,.95,f"{row['name']} ({ticker}) | Daily candles & volume",
             fontsize=18,weight='bold')
    fig.text(.075,.918,f"Source as-of {ASOF} · Close {int(p['close']):,} KRW · {bars} bars · Research only",fontsize=10)
    fig.text(.075,.04,f"Watch {int(lo):,}–{int(hi):,}  /  Stop {int(stop):,}  /  First resistance {int(res):,}  |  Regular-session-only not certified",fontsize=11)
    path=Path(path)
    fig.savefig(path,dpi=145,bbox_inches='tight')
    plt.close(fig)
    return dict(ticker=ticker,name=row['name'],chart_file=path.name,
       sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
       first_bar=str(b.date.iloc[0]),last_bar=str(b.date.iloc[-1]),
       last_close=int(close.iloc[-1]),last_volume=int(b.volume.iloc[-1]),
       candle_count=bars,entry_watch_low=int(lo),entry_watch_high=int(hi),
       study_stop=int(stop),first_resistance=int(res),
       buy_approved=False,orders_enabled=False)

def run(source,ranked,output,bars=45):
    choose_font()
    hist,ranked,source_sha=load(source,ranked)
    # Explicit current model Top2, not automatically arbitrary high score alone.
    tickers=['271560','026960']
    if not set(tickers)<=set(ranked.index):
        raise ValueError('EXPECTED_TWO_RESEARCH_STOCKS_NOT_PRESENT')
    root=Path(output)
    root.mkdir(parents=True,exist_ok=True)
    charts=[render(hist,t,ranked.loc[t],root/f'c3_top2_{t}_candlestick.png',bars)
        for t in tickers]
    status=dict(schema=SCHEMA,source_run=SOURCE_RUN,asof=ASOF,
       original_history_sha256=source_sha,charts=charts,
       chart_features=['OHLC','VOLUME','MA5','MA20','PULLBACK_BAND',
                       'STRUCTURAL_STOP','OBSERVED_FIRST_RESISTANCE'],
       real_investor_flows_present=False,regular_session_scope_certified=False,
       trade_approved=False,orders_enabled=False)
    (root/'c3_top2_chart_v1_manifest.json').write_text(
        json.dumps(status,ensure_ascii=False,indent=2,allow_nan=False)+'\n',
        encoding='utf-8')
    return status

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True)
    parser.add_argument('--ranked',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--bars',type=int,choices=(30,45,60),default=45)
    args=parser.parse_args()
    x=run(args.source,args.ranked,args.output,args.bars)
    print(json.dumps(dict(chart_count=len(x['charts']),asof=x['asof'],
       files=[r['chart_file'] for r in x['charts']],buy_approved=x['trade_approved']),
       ensure_ascii=False))
