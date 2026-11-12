"""Reference-standard ivory mobile cards, using the existing true-price plot.

The user photograph defines layout/colors only. Its old prices, orders and
financial/news narrative are never copied. All content comes from report JSON.
"""
import hashlib,json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image,ImageDraw,PngImagePlugin
from c3_classic_theme import (font,text,won,wrap,plot,validate_bars,W,H,
    INK,SUB,GOLD,PAPER,GREEN,BLUE,RED,PURPLE,MA_COLORS)

REFERENCE_SHA256='b28d58dae4cc5de165616aa5ece660ed69f4b758d62d688241f644e9202bfdc3'
LABELS={'STRUCTURAL_STOP_CONFIRMED':'일봉 구조 확인','STRUCTURAL_STOP_WEAK':'구조 근거 약함',
    'STOP_TOO_TIGHT_FOR_VOLATILITY':'정상 변동 대비 촘촘','STOP_RISK_EXCESSIVE':'손절 위험 과다','STOP_UNVERIFIED':'손절 미확인',
    'RANGE_VALID':'연구 범위 유효','RANGE_TOO_NARROW':'범위 폭 과소','RANGE_TOO_FAR':'범위 이격 과다'}

def stamp(s):
    if not s:return '미확인'
    return datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(ZoneInfo('Asia/Seoul')).strftime('%m/%d %H:%M KST')

def box_notes(row,p,report):
    q=(row.get('financial') or {}).get('statement') or {};sr=p.get('stop_reliability',{}) if p else {}
    quants=f"RS20 {row.get('own_rs20',0):+.2f}%p · 5일 개선 {row.get('rs_accel5',0):+.2f}%p · 거래대금20일 {row.get('turnover20',0)/1e8:,.0f}억원. {row.get('sector','업종 미확인')} / 시장 {report['regime']['observed_regime']}(미인증)."
    if q:
        finance=f"{q.get('fiscal_year','')}년 공시 API({q.get('fs_div','구분 미확인')}) · 매출 {q['revenue_krw']/1e8:,.0f}억 · 영업익 {q['operating_profit_krw']/1e8:,.0f}억 · 영업CF {q['operating_cashflow_ytd_krw']/1e8:,.0f}억. 사후 조회, 원문 PIT 미확인."
    else:finance='재무 원문 및 당시 이용 가능 자료 미확인. 재무 우량 기업 확정 아님.'
    issue='확인된 뉴스·외국인·기관 수급 원본 없음. 주요 이슈와 수급 강도를 추정하지 않음.'
    if q:issue+=f" 공시 접수 {q.get('published_on','미확인')} / 현재 API 근거."
    risk=(f"{LABELS.get(sr.get('status'),'손절 미확인')} · 독립 지지 접촉 {sr.get('independent_contacts','미확인')}회 · 완충 {sr.get('buffer_krw',0):,.0f}원. "
        '손절·범위를 임의 변경하지 않음. 갭 하락 시 손실 확대 가능.')
    return [('정량·섹터',quants),('재무·실적',finance),('주요 이슈·수급',issue),('리스크·구조손절',risk)]

def render(row,bars,report,path):
    validate_bars(bars,report['source_date'],row['close'])
    if len(bars)<119:raise ValueError('FULL_60_VISIBLE_MA60_REQUIRES_119_REAL_BARS')
    p=row.get('display_plan');r=p['range'] if p and p['range_valid'] else None
    diagnostic=row.get('is_diagnostic') is True
    if not r:raise ValueError('STOCK_CARD_REQUIRES_A_PROVENANCE_LINKED_RESEARCH_PLAN')
    rank=row.get('research_rank');status='PASS' if diagnostic else '매수 관찰\nWAIT'
    im=Image.new('RGB',(W,H),PAPER);d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,98),fill=INK);d.rectangle((0,94,W,99),fill=GOLD)
    text(d,52,26,'강현AI PRO | C3 TOP2',46,'#F3E6CD',True)
    text(d,1345,37,report['source_date'].replace('-','.'),31,'#EEEAE2',anchor='ra')
    text(d,54,123,row['name'],65,INK,True)
    label='사례 검토 · TOP 미선정' if diagnostic else 'TOP'+str(rank)
    text(d,54,205,row['ticker']+' · '+row['sector']+' · '+label,30,SUB)
    text(d,1345,125,won(row['close']),61,INK,True,anchor='ra')
    previous=bars[-2]['close'];change=row['close']-previous;pct=100*change/previous
    text(d,1345,204,f'{change:+,.0f}원 ({pct:+.2f}%)',31,RED if change>0 else BLUE,True,anchor='ra')
    d.rectangle((48,252,1352,294),fill='#F0EBDD')
    banner=report['source_date']+' 과거 자료 재검토 · '+('기존 연구 범위 진단 / PASS' if diagnostic else '연구 관찰 / 실제 BUY 승인 아님')
    text(d,700,258,banner,27,GOLD,True,anchor='ma')
    d.rounded_rectangle((48,316,1352,1192),radius=12,fill='white',outline='#DEDAD1',width=2)
    text(d,74,333,'일봉 · 최근 60거래일 가격과 거래량',31,INK,True)
    for i,n in enumerate((5,20,60)):
        x=770+i*175;d.line((x,353,x+28,353),fill=MA_COLORS[n],width=4);text(d,x+34,338,f'{n}일선',22,SUB)
    price_plan=dict(low=r['low'],high=r['high'],stop=p['stop'],resistance=p['r1'],resistance2=p['r2'])
    av,geometry=plot(d,bars,row,price_plan)
    text(d,54,1218,'기존 연구 구간 진단' if diagnostic else '매매 관찰 구간',33,INK,True)
    cells=[('기존 범위(부적합)' if diagnostic else '매수 가능 범위',won(r['low'])+' ~\n'+won(r['high']),GREEN),
        ('구조손절',won(p['stop']),RED),('1차 저항 R1',won(p['r1']),GOLD),('2차 저항 R2',won(p['r2']),PURPLE),('최종 상태',status,BLUE)]
    for i,(label,value,color) in enumerate(cells):
        x=48+i*261;d.rectangle((x,1270,x+252,1406),fill='white');d.line((x,1270,x+252,1270),fill=color,width=4)
        text(d,x+126,1285,label,26,color,True,anchor='ma')
        for k,line in enumerate(value.split('\n')):text(d,x+126,1330+k*34,line,30,color,True,anchor='ma')
    text(d,54,1432,'범위·구조손절 실용성 평가',33,INK,True)
    sr=p.get('stop_reliability',{});pr=p.get('practicality',{})
    summary=(f"폭 {r['high']-r['low']:,.0f}원 / {r['width_atr']:.3f}ATR · 상단 위험 {r['endpoints']['upper']['stop_risk_pct']:.2f}% · 최소 순RR {r['min_net_r1_rr']:.2f}배")
    text(d,56,1480,summary,29,INK)
    text(d,56,1522,LABELS.get(pr.get('status'),'범위 검토')+' / '+LABELS.get(sr.get('status'),'손절 미확인')+' · 범위 미도달 PASS',28,RED if diagnostic else SUB)
    text(d,54,1570,'선정 근거 및 가격 구조 검토',33,INK,True)
    layout=[];notes=box_notes(row,p,report)
    for i,(label,value) in enumerate(notes):
        yy=1624+i*156;d.rectangle((48,yy,1352,yy+146),fill='white');d.line((48,yy,48,yy+146),fill=GOLD,width=5)
        text(d,72,yy+23,f'{i+1:02}',22,GOLD,True)
        for k,line in enumerate(label.split('·')):text(d,118,yy+25+k*37,line+('·' if k==0 else ''),29,INK,True)
        lines=wrap(d,value,1002,30,3)
        for k,line in enumerate(lines):text(d,321,yy+23+k*38,line,30,INK)
        layout.append(dict(label=label,lines=len(lines),text_right_max=321+max(d.textlength(v,font=font(30)) for v in lines),box_right=1352,box_bottom=yy+146))
    text(d,700,2267,'KRX 일별·보존 캐시 / 정규장 전용 미인증 / 재무 원문 PIT 미확인',23,SUB,anchor='ma')
    text(d,700,2303,'가격 '+report['source_date']+' · 수집 '+stamp(report['source_received_at'])+' · 생성 '+stamp(report['generated_at']),21,SUB,anchor='ma')
    text(d,700,2330,'연구용 · 실제 매수 승인 없음 · 주문 횟수·수량·체결 방식은 사용자 결정',23,RED,True,anchor='ma')
    text(d,700,2368,'유효기간 비교 1·2·3거래일 / 이번 재현은 과거 계획, 현재 주문 지시 아님',21,SUB,anchor='ma')
    payload=dict(ticker=row['ticker'],name=row['name'],close=row['close'],price_asof=report['source_date'],
        source_run_id=report['source_run_id'],source_hash=report['source_hash'],report_hash=report['report_payload_sha256'],
        range=[r['low'],r['high']],stop=p['stop'],r1=p['r1'],r2=p['r2'],is_diagnostic=diagnostic,rank=rank,
        stop_reliability=sr.get('status'),range_status=pr.get('status'),visible_bars=60,source_bars=len(bars),ma60_visible_points=len(geometry['paths']['60']),
        ma_audit=geometry['average_audit'],source_received_at=report['source_received_at'],generated_at=report['generated_at'],
        theme='USER_REFERENCE_IVORY_GREY_V3',reference_image_sha256=REFERENCE_SHA256,layout=layout,analysis_sections=[n[0] for n in notes],
        entry_execution_policy='USER_DISCRETION_NO_PRESCRIBED_COUNT',buy_approved=False)
    info=PngImagePlugin.PngInfo();info.add_text('C3_manifest',json.dumps(payload,ensure_ascii=False,sort_keys=True))
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);im.save(path,pnginfo=info,optimize=True)
    with Image.open(path) as saved:
        if json.loads(saved.info['C3_manifest'])!=payload:raise ValueError('PNG_SOURCE_PAYLOAD_MISMATCH')
    return dict(payload,png=path.name,png_sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def hold_card(report,path):
    im=Image.new('RGB',(W,H),PAPER);d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,98),fill=INK);d.rectangle((0,94,W,99),fill=GOLD)
    text(d,52,26,'강현AI PRO | C3 TOP2',46,'#F3E6CD',True);text(d,1345,37,report['source_date'].replace('-','.'),31,'#EEEAE2',anchor='ra')
    text(d,700,220,'CASH',130,GOLD,True,anchor='ma');text(d,700,410,'최종 매수 관찰 후보 없음',52,INK,True,anchor='ma')
    text(d,700,520,'11월 11일 과거 자료 재검토 · 현재 매수 추천 아님',32,SUB,anchor='ma')
    funnel=report['funnel'];lines=[
        ('01 전체시장 재현',f"KRX {funnel['full_market']:,} → 분석 {funnel['analysis_eligible']:,} → 기술 {funnel['technical']}종목"),
        ('02 범위 실용성','좁거나 먼 구간은 별도 보류. 범위를 억지로 넓히지 않음.'),
        ('03 구조손절','현재 MA 접촉만으로 지지 강도를 확정하지 않음. 약한 구조 제외.'),
        ('04 인증·운영','정규장·재무 PIT 미인증. BUY 승인 없음. 실제 Telegram 전송 없음.')]
    for i,(title,body) in enumerate(lines):
        yy=700+i*265;d.rectangle((65,yy,1335,yy+225),fill='white');d.line((65,yy,65,yy+225),fill=GOLD,width=5)
        text(d,98,yy+30,title,36,INK,True)
        for k,line in enumerate(wrap(d,body,1170,33,3)):text(d,98,yy+102+k*41,line,33,SUB)
    text(d,700,1920,'데이터 인증 보류와 연구 조건 통과 0개는 서로 다른 상태입니다.',31,RED,True,anchor='ma')
    text(d,700,2160,'가격일 '+report['source_date']+' / 수집 '+stamp(report['source_received_at']),28,SUB,anchor='ma')
    text(d,700,2220,'생성 '+stamp(report['generated_at'])+' / KRX 일별·보존 원본',28,SUB,anchor='ma')
    text(d,700,2300,'실제 주문 횟수·수량·가격은 사용자가 결정합니다. 자동 주문 없음.',28,SUB,anchor='ma')
    payload=dict(source_run_id=report['source_run_id'],source_hash=report['source_hash'],report_hash=report['report_payload_sha256'],
        price_asof=report['source_date'],status='CASH_RESEARCH_NO_PRACTICAL_ENTRY',certification_status='UNVERIFIED',theme='USER_REFERENCE_IVORY_GREY_V3',
        reference_image_sha256=REFERENCE_SHA256,not_data_failure_relabelled_zero=True)
    info=PngImagePlugin.PngInfo();info.add_text('C3_manifest',json.dumps(payload,ensure_ascii=False,sort_keys=True))
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);im.save(path,pnginfo=info,optimize=True)
    return dict(payload,png=path.name,png_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
