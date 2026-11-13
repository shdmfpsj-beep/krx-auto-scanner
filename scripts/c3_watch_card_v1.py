"""Expose existing WATCH ranks and true-price cards without approving entry."""
import hashlib,json
from pathlib import Path

def watch_rows(pool,entry_fit):
    """Projection only: never reorder the existing stock-quality pool."""
    fitted={r['ticker'] for r in entry_fit}
    return [dict(ticker=r['ticker'],name=r['name'],close=r['close'],rank=i,status='WATCH',
        entry_fit_selected=r['ticker'] in fitted,score=None,score_basis='EXISTING_LEXICOGRAPHIC_RANK_NO_WEIGHTED_SCORE',
        own_rs20=r.get('own_rs20'),rs_accel5=r.get('rs_accel5'),turnover20=r.get('turnover20'),
        sector=r.get('sector'),financial_observed_positive=r.get('financial',{}).get('observed_positive'),
        financial_original_pit_verified=False,buy_approved=False) for i,r in enumerate(pool[:2],1)]

def render_watch(row,bars,report,path,rank):
    from PIL import Image,ImageDraw,PngImagePlugin
    from c3_classic_theme import W,H,INK,SUB,GOLD,PAPER,GREEN,RED,BLUE,PURPLE,MA_COLORS,text,won,plot,validate_bars,wrap
    from c3_range_card_v1 import stamp,LABELS
    validate_bars(bars,report['source_date'],row['close'])
    if len(bars)<119:raise ValueError('WATCH_FULL_60_VISIBLE_MA60_REQUIRES_119_REAL_BARS')
    best=row.get('range_review',{}).get('best')
    p=best if best and best.get('range_valid') and best.get('stop_reliability',{}).get('research_eligible') else None
    r=p['range'] if p else None
    plan=dict(low=r['low'],high=r['high'],stop=p['stop'],resistance=p['r1'],resistance2=p['r2']) if p else None
    fitted=row['ticker'] in {x['ticker'] for x in report['final_research_top2']}
    im=Image.new('RGB',(W,H),PAPER);d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,98),fill=INK);d.rectangle((0,94,W,99),fill=GOLD)
    text(d,52,26,'강현AI PRO | C3 TOP2',46,'#F3E6CD',True)
    text(d,1345,37,report['source_date'].replace('-','.'),31,'#EEEAE2',anchor='ra')
    text(d,54,123,row['name'],65,INK,True);text(d,54,205,row['ticker']+' · '+row['sector']+' · WATCH TOP'+str(rank),30,SUB)
    text(d,1345,125,won(row['close']),61,INK,True,anchor='ra')
    change=row['close']-bars[-2]['close'];pct=100*change/bars[-2]['close']
    text(d,1345,204,f'{change:+,.0f}원 ({pct:+.2f}%)',31,RED if change>0 else BLUE,True,anchor='ra')
    d.rectangle((48,252,1352,294),fill='#F0EBDD')
    text(d,700,258,'사후 연구 WATCH · 종목 관찰과 진입 적합성은 별도 · BUY 승인 없음',26,GOLD,True,anchor='ma')
    d.rounded_rectangle((48,316,1352,1192),radius=12,fill='white',outline='#DEDAD1',width=2)
    text(d,74,333,'실제 일봉 60거래일 · 거래량',31,INK,True)
    for i,n in enumerate((5,20,60)):
        x=770+i*175;d.line((x,353,x+28,353),fill=MA_COLORS[n],width=4);text(d,x+34,338,f'{n}일선',22,SUB)
    _,geometry=plot(d,bars,row,plan)
    if len(geometry['paths']['60'])!=60:raise ValueError('WATCH_MA60_VISIBLE_POINTS_INCOMPLETE')
    text(d,54,1218,'연구용 관찰 가격 · 주문 승인이 아님',33,INK,True)
    cells=[('매수 관찰 범위',won(r['low'])+' ~\n'+won(r['high']) if r else '미확정',GREEN),
        ('구조손절',won(p['stop']) if p else '미확정',RED),('1차 저항 R1',won(p['r1']) if p else '미확정',GOLD),
        ('2차 저항 R2',won(p['r2']) if p else '미확정',PURPLE),('최종 상태','ENTRY 연구' if fitted else 'WATCH\n진입 보류',BLUE)]
    for i,(label,value,color) in enumerate(cells):
        x=48+i*261;d.rectangle((x,1270,x+252,1406),fill='white');d.line((x,1270,x+252,1270),fill=color,width=4)
        text(d,x+126,1285,label,26,color,True,anchor='ma')
        for k,line in enumerate(value.split('\n')):text(d,x+126,1330+k*34,line,29,color,True,anchor='ma')
    text(d,54,1432,'기존 정렬 순위 '+str(rank)+' · 임의 가중 점수 없음',32,INK,True)
    summary=f"상단 위험 {r['endpoints']['upper']['stop_risk_pct']:.2f}% · 최소 순RR {r['min_net_r1_rr']:.2f}배" if p else '진입 적합 범위·손절 미확정. 좋은 종목과 지금 살 가격을 구분.'
    text(d,56,1480,summary,28,INK)
    text(d,56,1522,'2차 매수: 별도 검증 계획 없음 · 주문 횟수·수량은 사용자 결정',27,SUB)
    q=row.get('financial',{}).get('statement') or {}
    observation=row.get('observation_audit') or {};pm=observation.get('price') or {}
    money=lambda k:f"{q[k]/1e8:,.0f}억" if isinstance(q.get(k),(int,float)) else '미확인'
    financial=f"{q.get('fiscal_year','')}년 {q.get('fs_div','미확인')} · 매출 {money('revenue_krw')} · 영업익 {money('operating_profit_krw')} · 영업CF {money('operating_cashflow_ytd_krw')}. 순이익·이자보상 미확인, 재무 우량성·원문 PIT 미인증."
    states=sorted({v.get('stop_reliability',{}).get('status','STOP_UNVERIFIED') for v in row.get('range_review',{}).get('plans',[])})
    risk=(f"저점 {p.get('evidence',{}).get('low_date','미확인')} · 손절 {p['stop']:,.0f}원 · ATR {p['atr14']:,.0f}원. " if p else '진입 적합 손절 미확정. ')+(' / '.join(LABELS.get(x,x) for x in states[:2]) or '가격 구조 미확인')+'. 갭 손실 확대 가능.'
    if pm:
        risk=f"MA20 이격 {pm['ma20_extension_pct']:+.2f}% / {pm['ma20_extension_atr']:.2f}ATR · 5일 수익 {pm['returns_pct']['5']:+.2f}%. 갭 확대 주의. "+('진입 적합 범위 없음.' if not p else '연구 구간만 관찰.')
    previous=observation.get('previous_watch_rank');previous_day=observation.get('previous_watch_day')
    rank_note=(f"{previous_day[5:]} {previous}위 → 현재 {rank}위. " if previous is not None and previous_day else '직전 WATCH 순위 미확인. ')
    rank_note+=('동일 성장·업종 그룹의 거래대금 우선 순위 유지.' if observation.get('repeated_watch') else '당일 전체 후보 새 계산. 가중 총점 없음.')
    notes=[('정량·섹터',f"RS20 {row['own_rs20']:+.2f}%p · 5일 개선 {row['rs_accel5']:+.2f}%p · 20일 거래대금 {row['turnover20']/1e8:,.0f}억원. "+rank_note),
        ('재무·실적',financial),('주요 이슈·수급','확인된 뉴스·외국인·기관 수급 원본 미확인. 재무 접수 '+str(q.get('receipt_no','미확인'))+'. 사후 조회 자료이며 당시 확인 근거로 소급하지 않음.'),('리스크·구조손절',risk)]
    layout=[]
    for i,(label,value) in enumerate(notes):
        y=1624+i*156;d.rectangle((48,y,1352,y+146),fill='white');d.line((48,y,48,y+146),fill=GOLD,width=5)
        text(d,72,y+23,f'{i+1:02}',22,GOLD,True)
        for k,line in enumerate(label.split('·')):text(d,118,y+25+k*37,line+('·' if k==0 else ''),29,INK,True)
        lines=wrap(d,value,1002,29,3)
        for k,line in enumerate(lines):text(d,321,y+23+k*38,line,29,INK)
        from c3_classic_theme import font
        right=321+max(d.textlength(line,font=font(29)) for line in lines)
        if right>1352 or y+23+(len(lines)-1)*38+36>y+146:raise ValueError('WATCH_NOTE_TEXT_OUTSIDE_CARD_BOX')
        layout.append(dict(label=label,lines=len(lines),text_right_max=right,box_right=1352,box_bottom=y+146))
    text(d,700,2267,'FDR 일별 · 공식 KRX 비교 미완료 · 정규장·재무 PIT 미인증',25,SUB,anchor='ma')
    text(d,700,2310,'가격 '+report['source_date']+' · 수집 '+stamp(report['source_received_at'])+' · 생성 '+stamp(report['generated_at']),23,SUB,anchor='ma')
    text(d,700,2360,'과거 날짜 사후 연구 · 현재 매수 추천·실시간 성과가 아님',25,RED,True,anchor='ma')
    manifest=dict(role='WATCH',rank=rank,ticker=row['ticker'],name=row['name'],close=row['close'],status='WATCH',entry_fit_selected=fitted,
        price_asof=report['source_date'],source_run_id=report['source_run_id'],source_hash=report['source_hash'],report_hash=report['report_payload_sha256'],
        visible_bars=60,source_bars=len(bars),ma60_visible_points=60,ma_audit=geometry['average_audit'],
        range=[r['low'],r['high']] if r else None,stop=p['stop'] if p else None,r1=p['r1'] if p else None,r2=p['r2'] if p else None,
        chart_source_sha256=row['chart_source_sha256'],buy_approved=False,official_krx_match_verified=False,
        quality_audit_sha256=report.get('watch_quality_audit_sha256'),price_extension=pm,previous_watch_day=previous_day,
        previous_watch_rank=previous,repeat_reason=observation.get('repeat_reason'),layout=layout,
        score=None,score_basis='DETERMINISTIC_LEXICOGRAPHIC_NO_WEIGHTED_TOTAL')
    info=PngImagePlugin.PngInfo();info.add_text('C3_manifest',json.dumps(manifest,ensure_ascii=False,sort_keys=True))
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);im.save(path,pnginfo=info,optimize=True)
    with Image.open(path) as saved:
        if json.loads(saved.info['C3_manifest'])!=manifest:raise ValueError('WATCH_PNG_PAYLOAD_MISMATCH')
    return dict(manifest,png=path.name,png_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
