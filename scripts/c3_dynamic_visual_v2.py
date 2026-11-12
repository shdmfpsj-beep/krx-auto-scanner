"""Source-linked research images; reuse the established true-price candle plot."""
import hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw,PngImagePlugin
from c3_classic_theme import plot,font,text,won,INK,SUB,GOLD,PAPER,MA_COLORS,validate_bars

LABELS={'HMA_FIRST_PULLBACK':'HMA60 전환 후 첫 눌림','BREAKOUT_RETEST':'돌파 후 재지지 확인','COMPRESSION_REBREAK':'가격 압축 후 재돌파','STRUCTURAL_WATCH':'확정 피벗 관찰 · 진입 확인 대기'}


def sha(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def card(row,bars,report,out,kind):
    plan=row.get('chosen_plan') or row.get('best_plan')
    if plan is None:
        options=[p for p in row.get('plans',[]) if p.get('low') and p.get('high') and p.get('stop')]
        plan=min(options,key=lambda p:(p.get('entry_distance_atr',999),p['method'])) if options else row.get('structural_watch')
    if plan is None:return dict(ticker=row['ticker'],status='NO_CONFIRMED_STRUCTURE_FOR_CHART')
    if len(bars)<119:return dict(ticker=row['ticker'],status='FULL_60_VISIBLE_MA60_WARMUP_UNAVAILABLE',available=len(bars),required=119)
    bars=bars[-119:];close=bars[-1]['close'];validate_bars(bars,report['asof'],close)
    im=Image.new('RGB',(1400,2150),PAPER);d=ImageDraw.Draw(im)
    d.rectangle((0,0,1400,100),fill=INK);text(d,48,28,'강현AI PRO | Dynamic Entry V2',43,'#F3E6CD',True)
    text(d,52,130,row['name'],64,INK,True);text(d,1340,135,won(close),52,INK,True,anchor='ra')
    text(d,54,216,row['ticker']+' · '+report['asof']+' 과거 자료 연구',30,SUB)
    d.rectangle((48,265,1352,320),fill='#EEE8DC');text(d,700,277,'연구용 · 실전 매수 승인 아님 · 재무 PIT/정규장 미인증',29,GOLD,True,anchor='ma')
    text(d,54,340,'일봉 60개 · MA60 전체 계산용 실제119봉',28,INK,True)
    for i,n in enumerate((5,20,60)):
        xx=825+i*170;d.line((xx,356,xx+26,356),fill=MA_COLORS[n],width=4);text(d,xx+34,340,'MA'+str(n),25,SUB)
    av,g=plot(d,bars,dict(close=close,reference_close=close),plan)
    second=plan.get('entry2')
    if second:
        y=lambda v:g['bottom']-(v-g['axis_min'])/(g['axis_max']-g['axis_min'])*(g['bottom']-g['top'])
        for level in (second['low'],second['high']):
            for x in range(int(g['left']),int(g['right']),20):d.line((x,y(level),min(x+9,g['right']),y(level)),fill='#3977B6',width=2)
    text(d,52,1225,LABELS.get(plan['method'],plan['method']),39,INK,True)
    rr=lambda x:'미확정' if x is None else f'{x:.2f}배'
    pct=lambda x:'미확정' if x is None else f'{x:.2f}'
    rows=[('1차 관찰 범위',won(plan['low'])+' ~ '+won(plan['high'])),
          ('독립 2차 지지',won(second['low'])+' ~ '+won(second['high']) if second else '없음 · 분할매수로 자동 해석하지 않음'),
          ('새 연구 구조손절',won(plan['stop'])+' · 원본 등록 손절 변경 없음'),
          ('가까운 R1 / R2',won(plan.get('resistance'))+' / '+won(plan.get('resistance2'))),
          ('비용 반영 RR1 / RR2',rr(plan.get('net_r1_rr'))+' / '+rr(plan.get('net_r2_rr'))),
          ('매수 거리 / 손절 위험',pct(plan.get('entry_distance_pct'))+'% · '+pct(plan.get('entry_distance_atr'))+' ATR / '+pct(plan.get('risk_pct'))+'%'),
          ('지지 확인 / 유효기간',str(plan.get('support_known_on'))+' / 다음 1·2·3거래일 비교')]
    y=1315
    for label,value in rows:
        d.line((52,y+60,1348,y+60),fill='#DDD8CE',width=2);text(d,56,y,label,27,SUB);text(d,1340,y,value,28,INK,True,anchor='ra');y+=85
    status=('기본 타점만 통과 · 선택된 BandWidth 조건은 미통과' if row.get('not_final_selected_model') else '기술·타점 조건 통과 · 기업 품질은 미확정') if plan.get('geometry_pass') and row.get('momentum_pass',True) and row.get('liquidity_pass',True) else '관찰/제외 · 조건 미충족'
    text(d,700,1940,status,30,'#B84B48',True,anchor='ma')
    text(d,700,2002,'미도달 PASS · 지지 붕괴/갭/저항 선도달 시 취소 · 텔레그램 발송 없음',25,SUB,anchor='ma')
    text(d,700,2074,'원본 '+str(report['provenance']['original_source_run_id'])+' · 결정 '+report['provenance']['original_decision_payload_sha256'][:16],23,SUB,anchor='ma')
    info=PngImagePlugin.PngInfo();trace=dict(asof=report['asof'],ticker=row['ticker'],kind=kind,plan_sha256=sha(plan),source_run_id=report['provenance']['original_source_run_id'],original_decision_sha256=report['provenance']['original_decision_payload_sha256'],protocol_sha256=report['protocol_sha256'])
    for k,v in trace.items():info.add_text(k,str(v))
    path=out/(kind+'_'+row['ticker']+'.png');im.save(path,pnginfo=info,optimize=True)
    with Image.open(path) as check:
        check.verify()
    return dict(trace,status='RESEARCH_CHART_CREATED',file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source_rows=119,visible_candles=60,ma60_visible_points=len(g['paths']['60']),
        source_first=bars[0]['date'],visible_first=bars[-60]['date'],last=bars[-1]['date'],displayed_plan=plan,
        source119_sha256=sha(bars),visible60_sha256=sha(bars[-60:]),average_audit=g['average_audit'],charted_prices_equal_plan=True,buy_approved=False)


def create_images(report,cases,current,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);rows=[]
    for r in report['technical_research_top2']:rows.append(card(r,current[r['ticker']],report,out,'technical_preview'))
    for r in report.get('ablation_base_watch_candidates',[]):rows.append(card(r,current[r['ticker']],report,out,'ablation_watch_not_top2'))
    for c in cases[:4]:
        r=c.get('dynamic')
        if r and r['ticker'] in current:rows.append(card(r,current[r['ticker']],report,out,'case'))
    im=Image.new('RGB',(1200,1460),PAPER);d=ImageDraw.Draw(im)
    d.rectangle((0,0,1200,110),fill=INK);text(d,55,35,'강현AI PRO | 연구 결과',42,'#F3E6CD',True)
    text(d,65,185,report['asof']+' · Dynamic Entry V2',40,INK,True)
    text(d,65,340,'CASH',115,GOLD,True);text(d,65,530,'통합 연구 TOP2 미확정',48,INK,True)
    lines=['새 타점은 실제 지지·저항에서 별도 계산',
           '기술·타점 잠정 후보: '+str(report['counts']['technical_research_top2'])+'개',
           '재무 공시 원본/PIT 검증은 미완료',
           '정규장 전용 가격·거래량·대금 미인증',
           '실전 매수 승인 없음 · 원본 신호 변경 없음',
           '과거 연구 결과 · 현재 신규 추천 아님']
    for i,line in enumerate(lines):text(d,65,720+i*90,line,32,SUB)
    p=out/'CASH_research_status.png';im.save(p,optimize=True)
    rows.append(dict(file=p.name,status='SELECTION_HELD_NOT_VALID_ZERO',sha256=hashlib.sha256(p.read_bytes()).hexdigest(),asof=report['asof'],buy_approved=False))
    return rows
