"""High-contrast mobile cards from real OHLCV and the exact report payload."""
import hashlib,json,math
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image,ImageDraw,PngImagePlugin
from c3_classic_theme import font,moving_average,audit_averages,validate_bars

W,H=1200,2200
BG,PANEL,WHITE,MUTED='#090F1C','#111D30','#F2F5FA','#A6B6CE'
TEAL,RED,GOLD,BLUE='#45E2BD','#FF6D85','#FFD16D','#6CAEFF'
def text(d,x,y,value,size=34,color=WHITE,bold=False,anchor=None):
    d.text((x,y),str(value),font=font(size,bold),fill=color,anchor=anchor)
def won(v):return f'{v:,.0f}' if v is not None else '미확인'
def wrapped(d,x,y,s,width=1080,size=32,color=MUTED):
    line=''
    for ch in str(s):
        if d.textlength(line+ch,font=font(size))>width:
            text(d,x,y,line,size,color);y+=size+13;line=ch
        else:line+=ch
    if line:text(d,x,y,line,size,color)
    return y+size+13
def stamp(s):
    if not s:return '미확인'
    return datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(ZoneInfo('Asia/Seoul')).strftime('%m/%d %H:%M:%S KST')

def render(row,bars,report,path):
    validate_bars(bars,report['source_date'],row['close'])
    if len(bars)<119:raise ValueError('FULL_60_VISIBLE_MA60_REQUIRES_119_REAL_BARS')
    av={n:moving_average(bars,n) for n in (5,20,60)};audit=audit_averages(bars,av)
    bs=bars[-60:];p=row.get('display_plan');valid=bool(p and p['range_valid']);r=p['range'] if valid else None
    prices=[b[k] for b in bs for k in ('low','high')]
    if p:prices += [v for v in (p['stop'],p['r1'],p['r2']) if v is not None]
    if r:prices += [r['low'],r['high']]
    for values in av.values():prices.extend(v for v in values[-60:] if v is not None)
    lo,hi=min(prices),max(prices);span=hi-lo;lo-=span*.06;hi+=span*.06
    im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
    text(d,55,35,'강현AI PRO  /  C3 TOP2',34,TEAL,True)
    text(d,55,95,row['name'],66,WHITE,True);text(d,55,182,row['ticker']+'  ·  '+row['market']+'  ·  '+row['sector'],32,MUTED)
    d.rounded_rectangle((55,245,1145,402),radius=23,fill=PANEL)
    text(d,80,265,'기준 종가',30,MUTED);text(d,80,310,won(row['close'])+'원',52,WHITE,True)
    text(d,650,265,'시장 관찰 / 인증',30,MUTED)
    text(d,650,317,report['regime']['observed_regime']+' / UNVERIFIED',34,GOLD,True)
    state='ENTRY RANGE · 연구 관찰' if valid else 'WATCH · 진입 구간 미확인'
    text(d,55,433,state,39,TEAL if valid else GOLD,True)
    text(d,55,494,'실제 일봉 60개  ·  MA 5 / 20 / 60',29,MUTED)
    for n,color,x in ((5,BLUE,630),(20,GOLD,780),(60,'#C1A4FF',945)):
        d.line((x,513,x+30,513),fill=color,width=4);text(d,x+40,494,str(n),28,color)
    left,right,top,bottom=80,950,560,1220
    py=lambda v:bottom-(v-lo)/(hi-lo)*(bottom-top)
    step=(right-left)/60
    if r:
        d.rectangle((left,py(r['high']),right,py(r['low'])),fill='#16453D')
        d.line((left,py(r['high']),right,py(r['high'])),fill=TEAL,width=2)
        d.line((left,py(r['low']),right,py(r['low'])),fill=TEAL,width=2)
    for j in range(6):
        v=lo+(hi-lo)*j/5;y=py(v);d.line((left,y,right,y),fill='#263247',width=1)
        text(d,970,y-17,won(v),24,MUTED)
    for i,b in enumerate(bs):
        x=left+(i+.5)*step;color=RED if b['close']>=b['open'] else BLUE
        d.line((x,py(b['high']),x,py(b['low'])),fill=color,width=2)
        y1,y2=sorted((py(b['open']),py(b['close'])))
        d.rectangle((x-step*.27,y1,x+step*.27,max(y1+2,y2)),fill=color)
    for n,color in ((5,BLUE),(20,GOLD),(60,'#C1A4FF')):
        pts=[(left+(i+.5)*step,py(v)) for i,v in enumerate(av[n][-60:])]
        d.line(pts,fill=color,width=3)
    levels=[('종가',row['close'],WHITE)]
    if p:levels += [('손절',p['stop'],RED),('R1',p['r1'],GOLD),('R2',p['r2'],'#C1A4FF')]
    # All exact level prices are repeated below; adjacent plot tags are offset
    # to avoid overlapping while their lines stay at the true coordinates.
    occupied=[]
    for label,value,color in sorted((v for v in levels if v[1] is not None),key=lambda v:-v[1]):
        y=py(value)
        for x in range(left,right,18):d.line((x,y,min(x+9,right),y),fill=color,width=2)
        tag=y
        if occupied:tag=max(tag,occupied[-1]+34)
        occupied.append(tag);text(d,952,tag-14,label+' '+won(value),22,color)
    vmax=max(b['volume'] for b in bs) or 1;vtop,vbottom=1280,1435
    text(d,55,1245,'거래량',25,MUTED)
    for i,b in enumerate(bs):
        x=left+(i+.5)*step;y=vbottom-b['volume']/vmax*(vbottom-vtop)
        d.rectangle((x-step*.27,y,x+step*.27,vbottom),fill=RED if b['close']>=b['open'] else BLUE)
    for i in (0,20,40,59):text(d,left+(i+.5)*step,1452,bs[i]['date'][5:],23,MUTED,anchor='mt')
    d.rounded_rectangle((55,1515,1145,1805),radius=22,fill=PANEL)
    if valid:
        text(d,80,1532,'매수 관찰 범위  ·  범위 안에서 한 번만 진입',29,TEAL,True)
        text(d,80,1577,won(r['low'])+' ~ '+won(r['high'])+'원',49,WHITE,True)
        text(d,80,1645,'하단 위험 '+f"{r['endpoints']['lower']['stop_risk_pct']:.2f}%"+'  /  상단 위험 '+f"{r['endpoints']['upper']['stop_risk_pct']:.2f}%",29,MUTED)
        text(d,80,1692,'최소 순손익비 R1 '+f"{r['min_net_r1_rr']:.2f}배"+'  ·  미도달 PASS',31,GOLD)
        text(d,80,1745,'추격·추가매수 금지  ·  가격일 후 1거래일 연구',28,MUTED)
    else:
        text(d,80,1540,'우량성 확인 전 기술·재무 관찰 후보',33,GOLD,True)
        wrapped(d,80,1600,'현재 구조에서 위험 조건을 충족한 연속 매수 범위가 없습니다. 신규 진입은 CASH입니다.',1020,34,WHITE)
        text(d,80,1745,'구조손절·R1·R2 미확정  ·  범위를 임의 상향하지 않음',28,MUTED)
    y=1834
    if p:
        text(d,55,y,'구조손절 '+won(p['stop'])+'   R1 '+won(p['r1'])+'   R2 '+won(p['r2']),30,WHITE);y+=48
    y=wrapped(d,55,y,row['reason_text'],1085,29,MUTED)
    text(d,55,1986,'가격 기준 '+report['source_date']+'  |  원본 수집 '+stamp(report['source_received_at']),24,MUTED)
    mode='과거 원본 재검토' if report.get('mode')=='ARCHIVED_PRICE_CURRENT_CONTEXT_REVIEW' else '신규 거래일 연구 관찰'
    text(d,55,2026,'검토·이미지 생성 '+stamp(report['generated_at'])+'  |  '+mode,24,MUTED)
    text(d,55,2066,'정규장·재무 PIT 미인증  /  BUY 승인 없음  /  신규 매수 CASH',26,RED,True)
    text(d,55,2120,'매수 범위는 분할매수가 아닙니다. 실계좌 주문은 실행하지 않습니다.',23,MUTED)
    payload=dict(ticker=row['ticker'],name=row['name'],close=row['close'],price_asof=report['source_date'],
        source_run_id=report['source_run_id'],source_hash=report['source_hash'],report_hash=report['report_payload_sha256'],
        range=[r['low'],r['high']] if r else None,stop=p['stop'] if p else None,r1=p['r1'] if p else None,r2=p['r2'] if p else None,
        visible_bars=60,ma60_visible_points=60,source_bars=len(bars),ma_audit=audit,
        source_received_at=report['source_received_at'],generated_at=report['generated_at'],max_purchases=1,buy_approved=False)
    info=PngImagePlugin.PngInfo();info.add_text('C3_manifest',json.dumps(payload,ensure_ascii=False,sort_keys=True))
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);im.save(path,pnginfo=info)
    with Image.open(path) as saved:
        if json.loads(saved.info['C3_manifest'])!=payload:raise ValueError('PNG_SOURCE_PAYLOAD_MISMATCH')
    return dict(payload,png=path.name,png_sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def hold_card(report,path):
    im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
    text(d,65,70,'강현AI PRO · C3 TOP2',46,TEAL,True)
    text(d,65,280,'CASH / UNVERIFIED',65,GOLD,True)
    wrapped(d,65,460,'매수 승인 보류. 인증 미완료를 후보 없음으로 기록하지 않습니다.',1070,44,WHITE)
    wrapped(d,65,720,'정규장 가격 인증 또는 재무 원문 PIT 검증이 완료되지 않았습니다. 과거 결과를 오늘의 신규 추천으로 전송하지 않습니다.',1070,38,MUTED)
    text(d,65,1590,'가격 기준일 '+report['source_date'],36,WHITE)
    text(d,65,1680,'검토 '+stamp(report['generated_at']),32,MUTED)
    text(d,65,1840,'신규 매수 CASH · 주문 및 실제 Telegram 전송 없음',29,RED)
    payload=dict(source_run_id=report['source_run_id'],source_hash=report['source_hash'],
        report_hash=report['report_payload_sha256'],price_asof=report['source_date'],status='UNVERIFIED',not_no_candidate_confirmation=True)
    info=PngImagePlugin.PngInfo();info.add_text('C3_manifest',json.dumps(payload,ensure_ascii=False,sort_keys=True))
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);im.save(path,pnginfo=info)
    return dict(payload,png=path.name,png_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
