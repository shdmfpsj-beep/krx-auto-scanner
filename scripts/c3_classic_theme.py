"""One white/gold C3 card per stock. Frozen KRX data only; no network/sender."""
import functools,hashlib,json,math,os
from datetime import date
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

W,H=1400,2120
INK,SUB,GOLD,PAPER='#292B2C','#6C7073','#AC8848','#FAF9F5'
GREEN,BLUE,RED,PURPLE='#297756','#367CAF','#B84B48','#8568A0'
TRADE_COLORS={'first':GREEN,'second':BLUE,'stop':RED,'r1':GOLD,'r2':PURPLE}
MA_COLORS={5:'#596475',20:'#A18A66',60:'#738B80'}

@functools.lru_cache(maxsize=40)
def font(size,bold=False):
    root=Path(os.environ.get('C3_FONT_DIR','/usr/share/fonts/truetype/nanum'))
    names=['NanumGothic-Bold.ttf','NanumGothicBold.ttf'] if bold else ['NanumGothic-Regular.ttf','NanumGothic.ttf']
    p=next((root/n for n in names if (root/n).is_file()),None)
    if p is None:raise ValueError('KOREAN_FONT_REQUIRED')
    return ImageFont.truetype(str(p),size)

def text(d,x,y,value,size=32,color=INK,bold=False,anchor=None):d.text((x,y),str(value),font=font(size,bold),fill=color,anchor=anchor)
def won(v):return f'{v:,.0f}원' if v is not None else '미확정'

def validate_bars(rows,asof,close):
    if len(rows)<60:raise ValueError('INSUFFICIENT_60_SESSION_HISTORY')
    dates=[]
    for r in rows:
        date.fromisoformat(r['date']);dates.append(r['date'])
        o,h,l,c,v=[float(r[k]) for k in ('open','high','low','close','volume')]
        if not all(math.isfinite(x) for x in (o,h,l,c,v)) or not 0<l<=min(o,c)<=max(o,c)<=h or v<0:raise ValueError('INVALID_CHART_OHLCV')
    if dates!=sorted(set(dates)) or dates[-1]!=asof or any(d>asof for d in dates):raise ValueError('CHART_DATE_OR_ORDER_MISMATCH')
    if float(rows[-1]['close'])!=float(close):raise ValueError('CHART_REFERENCE_CLOSE_MISMATCH')
    return rows

def moving_average(rows,n):
    c=[float(r['close']) for r in rows]
    return [sum(c[i-n+1:i+1])/n if i+1>=n else None for i in range(len(c))]

def notes(r,p):
    industry=r.get('industry') or '미확인';market=r.get('market') or '미확인'
    money=r.get('turnover20');rs=r.get('own_rs20',r.get('rs20'));accel=r.get('rs_accel5');rr=p.get('net_r1_rr') if p else None
    cash=f'20일 평균 거래대금 {money/1e8:,.0f}억원.' if isinstance(money,(int,float)) else '검증된 거래대금 요약은 미확인입니다.'
    strength=f'시장 대비 RS20 {rs:+.2f}%p' if isinstance(rs,(int,float)) else '시장 대비 상대강도 미확인'
    strength+=f', 5일 개선 {accel:+.2f}%p.' if isinstance(accel,(int,float)) else '.'
    risk=f'첫 저항 손익비 {rr:.2f}배' if isinstance(rr,(int,float)) else '첫 저항 손익비 미확인'
    risk+=', 시장은 약세입니다.' if r.get('market_regime')=='DOWN' else '. 수익 지속성은 검증 중입니다.'
    return [('섹터 및 재료',f'확인 업종: {industry} · {market}. 최근 섹터 강세·수주·신사업 재료는 미확인입니다.'),
        ('재무 및 실적','최근 분기 매출·영업이익 자료가 미수집 상태입니다. 실적 개선 여부는 판단을 보류합니다.'),
        ('이슈 및 수급',cash+' 최근 공시·뉴스와 외국인·기관 수급은 미확인입니다.'),('펀더멘털 및\n선정 근거',strength+' '+risk)]

def wrap(d,value,width,size=31):
    lines=[];line=''
    for c in value:
        if d.textlength(line+c,font=font(size))>width:lines.append(line);line=c
        else:line+=c
    if line:lines.append(line)
    if len(lines)>3:raise ValueError('VERIFIED_NOTE_TOO_LONG_FOR_CARD')
    return lines

def plot(d,bars,row,plan):
    left,right,top,bottom=158,1110,384,1015;show=bars[-30:];offset=len(bars)-len(show)
    levels=[('종가',float(row.get('reference_close',row['close'])),INK)]
    if plan:
        levels+=[('매수 상단',plan['high'],GREEN),('매수 하단',plan['low'],GREEN),('손절가',plan['stop'],RED)]
        levels+=[(label,plan[k],color) for label,k,color in [('1차 저항','resistance',GOLD),('2차 저항','resistance2',PURPLE)] if plan.get(k) is not None]
    av={n:moving_average(bars,n) for n in (5,20,60)}
    values=[r[k] for r in show for k in ('high','low')]+[v for _,v,_ in levels]+[v for seq in av.values() for v in seq[offset:] if v is not None]
    lo,hi=min(values)*.965,max(values)*1.035;y=lambda v:bottom-(v-lo)/(hi-lo)*(bottom-top);step=(right-left)/(len(show)-1)
    for i in range(6):
        v=lo+(hi-lo)*i/5;yy=y(v);d.line((left,yy,right,yy),fill='#E7E5DE',width=1);text(d,left-18,yy,f'{v:,.0f}',26,SUB,anchor='rm')
    if plan:d.rectangle((left,y(plan['high']),right,y(plan['low'])),fill='#ECF4ED')
    for name,v,c in levels:d.line((left,y(v),right,y(v)),fill=c,width=3 if name=='종가' else 2)
    vtop,vbottom=1050,1137;vmax=max(max(r['volume'] for r in show),1)
    for i,r in enumerate(show):
        xx=left+i*step;c=RED if r['close']>=r['open'] else BLUE;d.line((xx,y(r['high']),xx,y(r['low'])),fill=c,width=3)
        a,b=sorted((y(r['open']),y(r['close'])));d.rectangle((xx-8,a,xx+8,max(a+2,b)),fill=c)
        d.rectangle((xx-8,vbottom-r['volume']/vmax*(vbottom-vtop),xx+8,vbottom),fill=c)
        if i%6==0 or i==len(show)-1:text(d,xx,1150,r['date'][5:].replace('-','/'),25,SUB,anchor='ma')
    for n,seq in av.items():
        pts=[(left+i*step,y(seq[offset+i])) for i in range(len(show)) if seq[offset+i] is not None]
        if len(pts)>1:d.line(pts,fill=MA_COLORS[n],width=4,joint='curve')
    text(d,left,1020,'거래량',24,SUB);text(d,right,1020,f'최대 {vmax/1e6:,.2f}백만주',24,SUB,anchor='ra')
    ordered=sorted((y(v),name,v,c) for name,v,c in levels);positions=[]
    for yy,_,_,_ in ordered:positions.append(max(yy,positions[-1]+48 if positions else top+12))
    if positions[-1]>bottom-10:
        positions[-1]=bottom-10
        for i in range(len(positions)-2,-1,-1):positions[i]=min(positions[i],positions[i+1]-48)
    for (actual,name,v,c),yy in zip(ordered,positions):
        d.line((right,actual,right+18,actual,right+28,yy,1138,yy),fill=c,width=2);text(d,1332,yy-15,f'{name} {v:,.0f}',24,c,True,anchor='ra')
    return av

def create_cards(report,outdir='/tmp/c3-integrated-cards'):
    picks=report.get('research_top2') or []
    if len(picks)!=2 or len({r['ticker'] for r in picks})!=2:raise ValueError('EXACTLY_TWO_UNIQUE_CANDIDATES_REQUIRED')
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True);files=[];diagnostics=[]
    for rank,r in enumerate(picks,1):
        asof=report['source_price_asof'];close=float(r.get('reference_close',r['close']));bars=validate_bars(r.get('chart_bars',[]),asof,close)
        if r.get('chart_price_basis')!='KRX_UNADJUSTED_AS_TRADED':raise ValueError('CHART_PRICE_BASIS_NOT_VERIFIED')
        p=((r.get('entry_plans') or {}).get('A_SUPPORT_LIMIT') or {}).get('plan');im=Image.new('RGB',(W,H),PAPER);d=ImageDraw.Draw(im)
        d.rectangle((0,0,W,98),fill=INK);d.rectangle((0,94,W,99),fill=GOLD)
        text(d,52,26,'강현AI PRO | C3 TOP2',46,'#F3E6CD',True);text(d,1345,37,asof.replace('-','.'),31,'#EEEAE2',anchor='ra')
        text(d,54,123,r['name'],65,INK,True);text(d,54,205,f"{r['ticker']} · {r.get('industry','업종 미확인')} · TOP{rank}",30,SUB)
        text(d,1345,125,won(close),61,INK,True,anchor='ra');previous=float(bars[-2]['close']);change=close-previous;pct=100*change/previous
        text(d,1345,204,f'{change:+,.0f}원 ({pct:+.2f}%)',31,RED if change>0 else BLUE if change<0 else SUB,True,anchor='ra')
        banner='과거 연구 예시 · '+asof+' 미등록 후보' if report.get('example_only') else asof+' 정규장 기준 · 연구 관찰용'
        d.rectangle((48,252,1352,294),fill='#F0EBDD');text(d,700,258,banner,27,GOLD,True,anchor='ma')
        d.rounded_rectangle((48,316,1352,1192),radius=12,fill='white',outline='#DEDAD1',width=2);text(d,74,333,'일봉 · 가격과 거래량',31,INK,True)
        for i,n in enumerate((5,20,60)):
            xx=800+i*164;d.line((xx,353,xx+33,353),fill=MA_COLORS[n],width=4);text(d,xx+43,338,f'{n}일선',25,SUB)
        av=plot(d,bars,r,p);text(d,54,1218,'매매 관찰 구간',33,INK,True)
        cells=[('1차 매수 범위',won(p['low'])+' ~\n'+won(p['high']) if p else '미성립',GREEN),('2차 매수 범위','미확정',BLUE),('손절가',won(p.get('stop')) if p else '미확정',RED),('1차 저항',won(p.get('resistance')) if p else '미확정',GOLD),('2차 저항',won(p.get('resistance2')) if p else '미확정',PURPLE)]
        for i,(label,value,c) in enumerate(cells):
            x=48+i*261;d.rectangle((x,1270,x+252,1398),fill='white');d.line((x,1270,x+252,1270),fill=c,width=4);text(d,x+126,1286,label,28,c,True,anchor='ma')
            for k,line in enumerate(value.split('\n')):text(d,x+126,1330+k*33,line,31,c,True,anchor='ma')
        text(d,54,1428,'종목 선정 이유',35,INK,True);rendered=[]
        for i,(label,value) in enumerate(notes(r,p)):
            yy=1482+i*132;d.rectangle((48,yy,1352,yy+122),fill='white');d.line((48,yy,48,yy+122),fill=GOLD,width=5);text(d,70,yy+22,f'{i+1:02}',22,GOLD,True)
            for k,line in enumerate(label.split('\n')):text(d,116,yy+20+k*36,line,29,INK,True)
            for k,line in enumerate(wrap(d,value,1004)):text(d,321,yy+14+k*35,line,31,INK)
            rendered.append(value)
        text(d,700,2030,'출처: 한국거래소 통계정보 · 정규장 범위 독립 확인 미완료',25,SUB,anchor='ma');text(d,700,2071,'연구 관찰용 정보 · 실제 매수 승인이 아닙니다.',27,SUB,anchor='ma')
        path=root/(r['ticker']+'_integrated.png');im.save(path,optimize=True);files.append(path)
        diagnostics.append(dict(ticker=r['ticker'],asof=asof,source_rows=len(bars),visible_rows=min(30,len(bars)),source_basis=r['chart_price_basis'],previous_close=previous,close=close,change=change,change_pct=pct,
            ma_last={str(n):seq[-1] for n,seq in av.items()},ma_valid_points={str(n):sum(v is not None for v in seq) for n,seq in av.items()},second_entry='NO_VALIDATED_SECOND_ENTRY_PLAN',financials_news='NOT_COLLECTED_NO_POSITIVE_INFERENCE',notes=rendered,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (root/'render_diagnostics.json').write_text(json.dumps(dict(example_only=bool(report.get('example_only')),cards=diagnostics),ensure_ascii=False,indent=2)+'\n')
    return files
