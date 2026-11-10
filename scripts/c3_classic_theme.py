"""One white/gold C3 card. True OHLCV paths and dated company context only."""
import functools, hashlib, json, math, os
from datetime import date
from decimal import Decimal
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from c3_entry_geometry_gate import assess

W,H=1400,2400
INK,SUB,GOLD,PAPER='#292B2C','#6C7073','#AC8848','#FAF9F5'
GREEN,BLUE,RED,PURPLE='#297756','#367CAF','#B84B48','#8568A0'
TRADE_COLORS={'first':GREEN,'second':BLUE,'stop':RED,'r1':GOLD,'r2':PURPLE}
MA_COLORS={5:'#405B81',20:'#B08739',60:'#738B80'}


@functools.lru_cache(maxsize=40)
def font(size,bold=False):
    root=Path(os.environ.get('C3_FONT_DIR','/usr/share/fonts/truetype/nanum'))
    names=['NanumGothic-Bold.ttf','NanumGothicBold.ttf'] if bold else ['NanumGothic-Regular.ttf','NanumGothic.ttf']
    p=next((root/n for n in names if (root/n).is_file()),None)
    if p is None:raise ValueError('KOREAN_FONT_REQUIRED')
    return ImageFont.truetype(str(p),size)


def text(d,x,y,value,size=32,color=INK,bold=False,anchor=None):
    d.text((x,y),str(value),font=font(size,bold),fill=color,anchor=anchor)


def won(v):return f'{v:,.0f}원' if v is not None else '미확정'


def validate_bars(rows,asof,close):
    if len(rows)<60:raise ValueError('INSUFFICIENT_60_SESSION_HISTORY')
    dates=[];segments=set()
    for r in rows:
        date.fromisoformat(r['date']);dates.append(r['date'])
        o,h,l,c,v=[float(r[k]) for k in ('open','high','low','close','volume')]
        if not all(math.isfinite(x) for x in (o,h,l,c,v)) or not 0<l<=min(o,c)<=max(o,c)<=h or v<0 or v!=int(v):raise ValueError('INVALID_CHART_OHLCV')
        if 'turnover_krw' in r and (not math.isfinite(float(r['turnover_krw'])) or float(r['turnover_krw'])<0):raise ValueError('INVALID_CHART_TURNOVER')
        if r.get('segment') is not None:segments.add(r['segment'])
        if r.get('price_basis','KRX_UNADJUSTED_AS_TRADED')!='KRX_UNADJUSTED_AS_TRADED' or r.get('corporate_action_unresolved'):raise ValueError('UNRESOLVED_CHART_PRICE_BASIS')
    if len(segments)>1:raise ValueError('UNRESOLVED_CHART_PRICE_SEGMENT_CHANGE')
    if dates!=sorted(set(dates)) or dates[-1]!=asof or any(d>asof for d in dates):raise ValueError('CHART_DATE_OR_ORDER_MISMATCH')
    if not math.isfinite(float(close)) or float(rows[-1]['close'])!=float(close):raise ValueError('CHART_REFERENCE_CLOSE_MISMATCH')
    return rows


def moving_average(rows,n):
    c=[float(r['close']) for r in rows]
    return [sum(c[i-n+1:i+1])/n if i+1>=n else None for i in range(len(c))]


def audit_averages(bars,av):
    """Independent decimal reference, including the complete warm-up mask."""
    result={}
    for n in (5,20,60):
        seq=av[n]
        if len(seq)!=len(bars):raise ValueError('CHART_MA_LENGTH_MISMATCH')
        errors=[]
        for i,value in enumerate(seq):
            if i<n-1:
                if value is not None:raise ValueError('CHART_MA_FAKE_WARMUP')
                continue
            expected=sum((Decimal(str(b['close'])) for b in bars[i-n+1:i+1]),Decimal(0))/n
            if value is None or not math.isfinite(value) or abs(float(expected)-value)>1e-7:raise ValueError('CHART_MA_INDEPENDENT_VALUE_MISMATCH')
            errors.append(abs(float(expected)-value))
        result[str(n)]={'max_decimal_error_krw':max(errors,default=0),'last5':seq[-5:]}
    return result


def quarter_note(q):
    basis='연결 잠정' if q.get('provisional') else '연결'
    def growth(key):
        v=q.get(key+'_yoy_pct')
        return f' (전년비 {v:+.1f}%)' if isinstance(v,(int,float)) else ''
    op=f"영업익 {q['operating_profit_krw']/1e8:,.0f}억원"+growth('operating_profit')
    if q.get('profit_transition')=='LOSS_TO_PROFIT':op+=' · 전년비 흑자전환'
    published=q.get('published_on','')[5:].replace('-','/')
    return f"{q['period']} {basis}"+(f' ({published} 발표)' if published else '')+f" · 매출 {q['revenue_krw']/1e8:,.0f}억원"+growth('revenue')+'. '+op+'.'


def notes(r,p):
    """Financial/news supplements are explicitly separate from selection inputs."""
    ctx=r.get('company_context') or {};business=ctx.get('business') or [];qs=ctx.get('quarters') or []
    sector=business[0]['text'] if business else f"{r.get('market','KRX')} · {r.get('industry','업종')} 가격·거래량 기반 연구 후보."
    eligible=[q for q in qs if q.get('fs_div')=='CFS' and q.get('revenue_krw') is not None and q.get('operating_profit_krw') is not None]
    financial=quarter_note(max(eligible,key=lambda q:q['period'])) if eligible else '실적 판단은 보류합니다. 가격·거래량 관찰에 한정하며 실적 개선을 전제로 하지 않습니다.'
    events=ctx.get('events') or []
    money=r.get('turnover20')
    liquidity=f'20일 평균 거래대금 {money/1e8:,.0f}억원.' if isinstance(money,(int,float)) else '거래대금 근거를 추가 점검해야 합니다.'
    if events:issue=events[0]['text']
    else:
        receipts=(ctx.get('dart') or {}).get('recent_disclosures') or []
        last=(r.get('chart_bars') or [{}])[-1]
        trade=f"당일 거래대금 {last['turnover_krw']/1e8:,.0f}억원 · 거래량 {last['volume']/1e4:,.1f}만주. " if isinstance(last.get('turnover_krw'),(int,float)) and isinstance(last.get('volume'),(int,float)) else ''
        issue=(f"{receipts[0]['published_on'][5:].replace('-','/')} 공시 제목: {receipts[0]['title'].strip()}. 내용 검토와 구분." if receipts else trade+liquidity)
    risk=ctx.get('business_risk') if business else None
    rr=p.get('net_r1_rr') if p else None
    risk=(risk or '가격 구조가 훼손되면 관찰 가설을 재점검합니다.')+(f' 첫 저항 손익비 {rr:.2f}배.' if isinstance(rr,(int,float)) else '')
    return [('섹터·재료',sector),('재무·실적',financial),('주요 이슈·수급',issue),('펀더멘털·위험',risk)]


def wrap(d,value,width,size=31,max_lines=3):
    lines=[];line=''
    for word in value.split():
        candidate=(line+' '+word).strip()
        if d.textlength(candidate,font=font(size))>width:
            if not line or d.textlength(word,font=font(size))>width:raise ValueError('VERIFIED_NOTE_TOKEN_TOO_LONG')
            lines.append(line);line=word
        else:line=candidate
    if line:lines.append(line)
    if len(lines)>max_lines:raise ValueError('VERIFIED_NOTE_TOO_LONG_FOR_CARD')
    return lines


def price_scale(values):
    if not values or any(not math.isfinite(float(v)) or v<=0 for v in values):raise ValueError('INVALID_CHART_PRICE_SCALE')
    low,high=min(values)*.97,max(values)*1.03
    target=(high-low)/5;unit=10**math.floor(math.log10(target))
    tick=next(v*unit for v in (1,2,2.5,5,10) if v*unit>=target)
    low=math.floor(low/tick)*tick;high=math.ceil(high/tick)*tick
    if low<=0:low=min(values)*.8
    return low,high,tick


def chart_geometry(bars,row,plan,av=None):
    left,right,top,bottom=158.,1104.,392.,1015.
    show=bars[-30:];offset=len(bars)-len(show);last_x=right-28
    step=(last_x-left)/(len(show)-1)
    av=av or {n:moving_average(bars,n) for n in (5,20,60)}
    audit=audit_averages(bars,av)
    levels=[('종가',float(row.get('reference_close',row['close'])),INK)]
    if plan:
        levels += [('매수 상단',plan['high'],GREEN),('매수 하단',plan['low'],GREEN),('손절가',plan['stop'],RED)]
        levels += [(label,plan[k],color) for label,k,color in [('1차 저항','resistance',GOLD),('2차 저항','resistance2',PURPLE)] if plan.get(k) is not None]
    values=[r[k] for r in show for k in ('high','low')]+[v for _,v,_ in levels]+[v for seq in av.values() for v in seq[offset:] if v is not None]
    lo,hi,tick=price_scale(values)
    y=lambda v:bottom-(v-lo)/(hi-lo)*(bottom-top)
    paths={str(n):[{'date':show[i]['date'],'x':left+i*step,'y':y(seq[offset+i]),'value':seq[offset+i]} for i in range(len(show)) if seq[offset+i] is not None] for n,seq in av.items()}
    if any(not left<=p['x']<=last_x or not top<=p['y']<=bottom for seq in paths.values() for p in seq):raise ValueError('CHART_PATH_OUTSIDE_REAL_PRICE_AXIS')
    for seq in paths.values():
        if seq and (seq[-1]['date']!=bars[-1]['date'] or seq[-1]['x']!=last_x):raise ValueError('CHART_PATH_ENDS_AFTER_LAST_CANDLE')
    return dict(left=left,right=right,last_candle_x=last_x,top=top,bottom=bottom,offset=offset,step=step,axis_min=lo,axis_max=hi,tick=tick,paths=paths,levels=levels,average_audit=audit,endpoint_label_style='STRAIGHT_PRICE_BADGE_NO_LEADER_POLYLINE'),av


def plot(d,bars,row,plan):
    g,av=chart_geometry(bars,row,plan);left,right,top,bottom=[g[k] for k in ('left','right','top','bottom')]
    show=bars[-30:];lo,hi=g['axis_min'],g['axis_max'];y=lambda v:bottom-(v-lo)/(hi-lo)*(bottom-top)
    v=lo
    while v<=hi+.01:
        yy=y(v);d.line((left,yy,right,yy),fill='#E7E5DE',width=1);text(d,left-18,yy,f'{v:,.0f}',26,SUB,anchor='rm');v+=g['tick']
    if plan:d.rectangle((left,y(plan['high']),right,y(plan['low'])),fill='#ECF4ED')
    for name,v,c in g['levels']:
        if name=='종가':
            for x in range(int(left),int(right),16):d.line((x,y(v),min(x+7,right),y(v)),fill='#6C7073',width=1)
        else:d.line((left,y(v),right,y(v)),fill=c,width=2)
    vtop,vbottom=1050,1137;vmax=max(max(r['volume'] for r in show),1)
    for i,r in enumerate(show):
        xx=left+i*g['step'];c=RED if r['close']>=r['open'] else BLUE
        d.line((xx,y(r['high']),xx,y(r['low'])),fill=c,width=3)
        a,b=sorted((y(r['open']),y(r['close'])));d.rectangle((xx-8,a,xx+8,max(a+2,b)),fill=c)
        if r['volume']>0:d.rectangle((xx-8,vbottom-r['volume']/vmax*(vbottom-vtop),xx+8,vbottom),fill=c)
        if i%6==0 or i==len(show)-1:text(d,xx,1150,r['date'][5:].replace('-','/'),25,SUB,anchor='ma')
    for n,path in g['paths'].items():
        pts=[(p['x'],p['y']) for p in path]
        if len(pts)>1:d.line(pts,fill=MA_COLORS[int(n)],width=4)
        if pts:
            xx,yy=pts[-1];d.ellipse((xx-4,yy-4,xx+4,yy+4),fill=MA_COLORS[int(n)])
    close=float(row.get('reference_close',row['close']));yy=y(close)
    # A flat badge at the true price, isolated from all MA paths. No diagonal or
    # displaced collision-avoidance leader can masquerade as a final price move.
    d.line((right,yy,right+18,yy),fill=INK,width=2)
    d.rounded_rectangle((right+20,yy-23,1340,yy+23),radius=5,fill=INK)
    text(d,1330,yy,'종가 '+f'{close:,.0f}',27,'white',True,anchor='rm')
    text(d,left,1020,'거래량',24,SUB);text(d,right,1020,f'최대 {vmax/1e6:,.2f}백만주',24,SUB,anchor='ra')
    return av,g


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
        text(d,54,123,r['name'],65,INK,True);text(d,54,205,f"{r['ticker']} · {r.get('industry','업종')} · TOP{rank}",30,SUB)
        text(d,1345,125,won(close),61,INK,True,anchor='ra');previous=float(bars[-2]['close']);change=close-previous;pct=100*change/previous
        text(d,1345,204,f'{change:+,.0f}원 ({pct:+.2f}%)',31,RED if change>0 else BLUE if change<0 else SUB,True,anchor='ra')
        gate=assess(r,bars)
        banner=(('과거 연구 예시 · '+asof+' · 실전 승인 아님') if report.get('example_only') else (asof+' 종가 · 연구 후보 · 진입 대기/CASH' if not gate['eligible'] else asof+' 종가 기준 · 연구 관찰용'))
        d.rectangle((48,252,1352,294),fill='#F0EBDD');text(d,700,258,banner,27,GOLD,True,anchor='ma')
        d.rounded_rectangle((48,316,1352,1192),radius=12,fill='white',outline='#DEDAD1',width=2);text(d,74,333,'일봉 · 가격과 거래량',31,INK,True)
        for i,n in enumerate((5,20,60)):
            xx=800+i*164;d.line((xx,353,xx+33,353),fill=MA_COLORS[n],width=4);text(d,xx+43,338,f'{n}일선',25,SUB)
        av,geometry=plot(d,bars,r,p);text(d,54,1218,'매매 관찰 구간',33,INK,True)
        cells=[('1차 매수 범위',won(p['low'])+' ~\n'+won(p['high']) if p else '미성립',GREEN),('2차 매수 범위','미확정',BLUE),('손절가',won(p.get('stop')) if p else '미확정',RED),('1차 저항',won(p.get('resistance')) if p else '미확정',GOLD),('2차 저항',won(p.get('resistance2')) if p else '미확정',PURPLE)]
        for i,(label,value,c) in enumerate(cells):
            x=48+i*261;d.rectangle((x,1270,x+252,1398),fill='white');d.line((x,1270,x+252,1270),fill=c,width=4);text(d,x+126,1286,label,28,c,True,anchor='ma')
            for k,line in enumerate(value.split('\n')):text(d,x+126,1330+k*33,line,31,c,True,anchor='ma')
        text(d,54,1428,'선정에 사용한 정량 근거',33,INK,True)
        rs=r.get('own_rs20',r.get('rs20'));accel=r.get('rs_accel5');money=r.get('turnover20')
        quant=[]
        if isinstance(rs,(int,float)):quant.append(f'RS20 {rs:+.2f}%p')
        if isinstance(accel,(int,float)):quant.append(f'5일 RS 개선 {accel:+.2f}%p')
        if isinstance(money,(int,float)):quant.append(f'20일 거래대금 {money/1e8:,.0f}억원')
        for k,line in enumerate(wrap(d,' · '.join(quant) or '원본의 가격·거래량 조건에 따른 연구 후보',1260,30,2)):text(d,56,1480+k*37,line,30,INK)
        text(d,54,1570,'선정 후 기업 자료 및 위험 검토',33,INK,True);rendered=[];layout=[]
        for i,(label,value) in enumerate(notes(r,p)):
            yy=1624+i*166;d.rectangle((48,yy,1352,yy+156),fill='white');d.line((48,yy,48,yy+156),fill=GOLD,width=5)
            text(d,72,yy+24,f'{i+1:02}',22,GOLD,True)
            label_parts=label.split('·')
            for k,line in enumerate(label_parts):text(d,118,yy+26+k*38,line+('·' if k<len(label_parts)-1 else ''),30,INK,True)
            lines=wrap(d,value,1002,31,3)
            for k,line in enumerate(lines):text(d,321,yy+23+k*38,line,31,INK)
            rendered.append(value);layout.append({'label':label,'lines':len(lines),'text_right_max':max(d.textlength(line,font=font(31)) for line in lines),'box_right':1352,'box_bottom':yy+156,'font_size':31})
        text(d,700,2310,'기업자료: DART·기업 IR · 선정 후 조사이며 점수·매수가에 미반영',25,SUB,anchor='ma')
        text(d,700,2352,'KRX 가격 · 정규장 범위 별도 검증 필요 · 실제 매수 승인이 아닙니다.',25,SUB,anchor='ma')
        path=root/(r['ticker']+'_integrated.png');im.save(path,optimize=True);files.append(path)
        diagnostics.append(dict(ticker=r['ticker'],entry_geometry_review=gate,asof=asof,source_rows=len(bars),visible_rows=min(30,len(bars)),source_basis=r['chart_price_basis'],previous_close=previous,close=close,change=change,change_pct=pct,
            ma_last={str(n):seq[-1] for n,seq in av.items()},ma_valid_points={str(n):sum(v is not None for v in seq) for n,seq in av.items()},last5=[dict(b,**{'ma'+str(n):av[n][i] for n in av}) for i,b in list(enumerate(bars))[-5:]],geometry=geometry,
            second_entry='NO_VALIDATED_SECOND_ENTRY_PLAN',company_context_status=(r.get('company_context') or {}).get('dart_status','NOT_ATTACHED'),company_context_missing=(r.get('company_context') or {}).get('missing',[]),notes=rendered,layout=layout,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (root/'render_diagnostics.json').write_text(json.dumps(dict(example_only=bool(report.get('example_only')),cards=diagnostics),ensure_ascii=False,indent=2)+'\n')
    return files
