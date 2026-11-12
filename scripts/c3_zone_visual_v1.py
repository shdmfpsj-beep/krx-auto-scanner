"""Source-linked mobile zone cards, using real prices and existing MA audit."""
import hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw,PngImagePlugin
from c3_classic_theme import plot,text,won,INK,SUB,GOLD,PAPER,MA_COLORS,validate_bars
from c3_zone_entry_v1 import allocation


def sha(obj):return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def chart(row,plan,bars,summary,out,kind):
    if plan is None:return dict(ticker=row['ticker'],status='NO_AUTHENTICATED_ORIGINAL_RANGE')
    if len(bars)<119:return dict(ticker=row['ticker'],status='BLOCKED_FULL_MA60_WARMUP',available=len(bars),required=119)
    bars=bars[-119:];day=bars[-1]['date'];close=bars[-1]['close'];validate_bars(bars,day,close);a=allocation(plan)
    im=Image.new('RGB',(1400,2340),PAPER);d=ImageDraw.Draw(im)
    d.rectangle((0,0,1400,100),fill=INK);text(d,45,28,'강현AI PRO | Zone Entry V1',45,'#F3E6CD',True)
    text(d,52,132,row['name'],63,INK,True);text(d,1340,139,won(close),52,INK,True,anchor='ra')
    text(d,54,215,row['ticker']+' · '+day+' · '+('과거 원본 범위 비교' if kind=='original_case' else '신규 가격 연구 후보'),30,SUB)
    d.rectangle((48,266,1352,320),fill='#EEE8DC');text(d,700,277,'연구용 · 실제 주문 아님 · 정규장/재무 PIT 미인증',31,GOLD,True,anchor='ma')
    text(d,54,340,'실제 일봉60개 · MA60 전체 계산용119봉',29,INK,True)
    for i,n in enumerate((5,20,60)):
        x=825+i*170;d.line((x,356,x+26,356),fill=MA_COLORS[n],width=4);text(d,x+33,340,'MA'+str(n),25,SUB)
    av,g=plot(d,bars,dict(close=close),plan)
    rr=lambda x:'미확정' if x is None else f'{x:.2f}배'
    f=lambda x:f'{x:,.0f}'
    text(d,54,1220,'하나의 관찰 범위 · 상단 1차 / 하단 2차',37,INK,True)
    rows=[('1차 상단 / 계획금액',won(plan['high'])+' / 250만원 (50%)'),('2차 하단 / 계획금액',won(plan['low'])+' / 250만원 (50%)'),
        ('사전 고정 모델 수량',str(a['legs'][0]['quantity'])+'주 / '+str(a['legs'][1]['quantity'])+'주 · 실제 체결 수량 아님'),
        ('전량 지정가 체결 평균',won(a['weighted_average_price'])),('원본/연구 구조손절',won(plan['stop'])),
        ('1차 / 2차 저항',won(plan.get('resistance'))+' / '+won(plan.get('resistance2'))),
        ('전량 체결 통합 RR1 / RR2',rr(a['full_fill_net_r1_rr'])+' / '+rr(a['full_fill_net_r2_rr'])),
        ('총계획 500만원 기준 위험',f(a['full_stop_loss_krw'])+'원 / '+f"{a['full_plan_risk_pct']:.2f}%"),
        ('상단만 체결될 때 위험',f(a['first_only_stop_loss_krw'])+'원 / '+f"{a['first_only_plan_risk_pct']:.2f}%"),
        ('진입 주문 유효기간','다음 1·2·3거래일 비교 · 미도달 PASS')]
    y=1302
    for label,value in rows:
        text(d,56,y,label,27,SUB);text(d,1340,y,value,29,INK,True,anchor='ra');d.line((52,y+57,1348,y+57),fill='#DDD8CE',width=2);y+=79
    if kind=='original_case':
        note='삼성E&A: 사용자 두 주문 체결 보고 · 수량/시각 증빙 미확인' if row['ticker']=='028050' else '원익홀딩스: 사용자 상단 체결 보고 · 하단 2차는 연구 가정'
    else:note='가격 조건 통과 연구 후보 · 기업 품질 인증 및 실전 승격 없음'
    text(d,700,2120,note,29,'#B84B48',True,anchor='ma')
    text(d,700,2185,'일봉 순서 불확실성·시가 갭 별도 평가 · 원본 원장 변경 없음',27,SUB,anchor='ma')
    text(d,700,2250,'표시 위험은 예정 손절가 기준 · 갭 급락 손실은 더 커질 수 있음',26,SUB,anchor='ma')
    text(d,700,2300,'Telegram 발송 없음 · 계획 '+sha(plan)[:16],23,SUB,anchor='ma')
    info=PngImagePlugin.PngInfo();trace=dict(asof=day,ticker=row['ticker'],kind=kind,plan_sha256=sha(plan),protocol_sha256=summary['protocol_sha256'],source_run_id=row.get('source_run_id') or summary['provenance']['original_source_run_id'])
    for k,v in trace.items():info.add_text(k,str(v))
    path=out/(kind+'_'+day+'_'+row['ticker']+'.png');im.save(path,pnginfo=info,optimize=True)
    return dict(trace,file=path.name,status='CHART_CREATED',sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source_rows=119,visible_candles=60,ma60_visible_points=len(g['paths']['60']),average_audit=g['average_audit'],displayed_plan=plan,allocation=a,buy_approved=False)


def create_images(summary,cases,current,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);result=[]
    for c in cases:
        if c['asof']=='2026-11-05':result.append(chart(c,c['original_plan'],c['chart_bars'],summary,out,'original_case'))
    for r in summary['technical_research_top2']:result.append(chart(r,r['zone'],current[r['ticker']],summary,out,'zone_price_candidate'))
    im=Image.new('RGB',(1200,1500),PAPER);d=ImageDraw.Draw(im);d.rectangle((0,0,1200,110),fill=INK);text(d,50,30,'강현AI PRO | Zone Entry V1',44,'#F3E6CD',True)
    text(d,65,180,'2026-11-11 과거 자료 연구',45,INK,True);text(d,65,330,'CASH',118,GOLD,True)
    lines=['실전 매수 승인 보류 · 통합 선정 미완료','새 범위 생성: '+str(summary['counts']['zone_generated'])+'개',
        '가격·강도·유동성 통과: '+str(summary['counts']['momentum_liquidity_and_zone_pass'])+'개',
        '상단·하단 각50% · 정수 수량·현금 반영','재무 공시 원문/PIT · 정규장 인증 미완료','과거 원본 신호·손절·영수증 변경 없음','새 지표 추가 없음 · 텔레그램 발송 없음']
    for i,line in enumerate(lines):text(d,65,550+i*105,line,32,SUB)
    path=out/'CASH_ZoneEntryV1_20261111.png';im.save(path,optimize=True);result.append(dict(file=path.name,status='SELECTION_HELD_NOT_CERTIFIED_ZERO',sha256=hashlib.sha256(path.read_bytes()).hexdigest(),buy_approved=False))
    return result
