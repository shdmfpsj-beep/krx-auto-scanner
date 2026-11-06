"""Mobile research status, dated price charts and separate selection/trade results."""
import argparse,html,json,re,shutil,statistics
from pathlib import Path


def deployment_status(data):
    """Report verified invocation evidence separately from an installed schedule."""
    context=data.get('invocation') or {}
    deployed=bool(data.get('scheduler_deployed') and context.get('mode')=='approved_daily')
    automatic=bool(deployed and context.get('automatic_event_observed') and context.get('event') in ('schedule','workflow_run'))
    state='MAIN_AUTOMATIC_EVENT_OBSERVED' if automatic else 'MAIN_MANUAL_RUN_ONLY' if deployed else 'RESEARCH_VALIDATION_ONLY' if context.get('mode') in ('research_direct','research_smoke') else 'DEPLOYMENT_UNVERIFIED'
    return dict(state=state,main_caller_observed=deployed,automatic_event_observed=automatic,
        schedule_event_observed=bool(automatic and context.get('event')=='schedule'),
        chatgpt_notification_delivery_verified=False)


def registration_note(data):
    if data.get('research_top2_registered_for_source_session') is True:
        return '아래 후보는 원본 거래일에 실제 등록된 연구 신호입니다. 실전 매수 승인은 아니며 정규장 가격 범위 검증은 별도입니다.'
    return '아래 후보는 미등록 연구 미리보기입니다. 과거 후보를 당일 신규 신호로 표시하거나 소급 체결하지 않습니다.'


def stored_chart(data,row,folder='reports/c3_forward_v8/mobile'):
    """Reuse a dated chart only when price, plan and registration label agree."""
    if not re.fullmatch('[A-Z0-9]{6}',row['ticker']):return None
    root=Path(folder);path=root/(row['ticker']+'_structure.png')
    try:previous=json.loads((root/'summary.json').read_text())
    except (OSError,ValueError):return None
    close=lambda r:r.get('reference_close',r.get('close'))
    same=previous.get('preview_price_asof')==data['preview_price_asof'] and previous.get('research_top2_is_registered_today')==data['research_top2_is_registered_today']
    if same and path.exists() and any(r['ticker']==row['ticker'] and close(r)==close(row) and r.get('entry_plans')==row.get('entry_plans') for r in previous.get('research_top2',[])):return path
    return None


def render(latest,outdir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import FuncFormatter
    data=json.loads(Path(latest).read_text());root=Path(outdir);root.mkdir(parents=True,exist_ok=True);cards=[]
    compact={k:v for k,v in data.items() if k not in ('observations','research_top2')}
    compact['research_top2']=[{k:v for k,v in r.items() if k!='chart_bars'} for r in data['research_top2']]
    operating=deployment_status(data);compact['operating_status']=operating
    (root/'summary.json').write_text(json.dumps(compact,ensure_ascii=False,indent=2)+'\n')
    price=lambda v:'미확인' if v is None else f'{v:,.0f}원'
    md=['# C3 연구용 TOP2·가상매매 일일 통합 보고','',f"- 보고일(KST): {data['report_day_kst']} / 실행: {data['source_run_id']}",
        f"- 확보된 가격 기준일: {data['source_price_asof'] or '미확보'} / 수집: {data['source_received_at'] or '미확보'}",
        f"- 분석 완료 시각: {data.get('analysis_completed_at','기존 보고')} / 보고 생성: {data['generated_at']}",
        f"- 보고 실행: {data.get('invocation',{}).get('run_id',data['source_run_id'])} / 가격 원본 실행: {data['source_run_id']}",
        f"- 데이터 상태: {data.get('data_quality_state','기존 보고')} / 원천: {data.get('source_provider','미확인')} / 정규장 전용 독립 인증: {data.get('source_regular_only_certified',False)}",
        '- 품질검사 통과는 거래일·OHLC 수치·시장 범위의 검사 결과이며 정규장 전용 거래량·거래대금 인증과 다릅니다.',
        '- 출처: 한국거래소 통계정보. FinanceData KRX 캐시 이용 시 동일 KRX 원천의 별도 전달 경로이며 독립 가격 공급사가 아닙니다.',
        f"- 마지막 확인 가격: {data['preview_price_asof']} / 오늘 등록된 결정: {data['new_decision_registered']}",
        f"- 신규 신호: {data['new_registered_signals']} / 신규 고유 종목: {data['new_registered_unique_tickers']}",'- 실전 행동: CASH / 실제 브로커 주문·체결 0','',
        registration_note(data),'']
    for r in data['research_top2']:
        p=r['entry_plans']['A_SUPPORT_LIMIT']['plan'];bars=r.get('chart_bars',[]);rows=[('종목',r['name']+' '+r['ticker']),('기준 거래일',data['preview_price_asof']),
            ('기준 종가',price(r.get('reference_close',r['close']))),('선정 근거',f"시장 대비 RS20 {r['own_rs20']:+.2f}%p · 5일 RS 개선 {r['rs_accel5']:+.2f}%p"),
            ('매수 관찰가',price(p['high']) if p else '신호 없음'),('연구 매수 범위',f"{price(p['low'])}~{price(p['high'])}" if p else '미성립'),
            ('구조손절가',price(p['stop']) if p else '미확인'),('손절 거리(범위 상단)',f"{p['risk_pct']:.2f}%" if p else '미확인'),
            ('1차 저항',price(p['resistance']) if p else '미확인'),('2차 저항',price(p['resistance2']) if p else '미확인'),('실전 행동','CASH')]
        md+=['## '+r['name']+' '+r['ticker'],'','|항목|값|','|---|---|']+['|'+k+'|'+v+'|' for k,v in rows]+['']
        table='<table>'+''.join('<tr><th>'+html.escape(k)+'</th><td>'+html.escape(v)+'</td></tr>' for k,v in rows)+'</table>'
        if bars:
            fig,(ax,vol)=plt.subplots(2,1,figsize=(6.3,9),sharex=True,gridspec_kw={'height_ratios':[4,1]})
            for i,b in enumerate(bars):
                c='#c64d5b' if b['close']>=b['open'] else '#417cac';ax.vlines(i,b['low'],b['high'],color=c,lw=.8)
                ax.add_patch(Rectangle((i-.28,min(b['open'],b['close'])),.56,max(abs(b['open']-b['close']),b['close']*.0002),color=c));vol.bar(i,b['volume']/1_000_000,color=c,width=.65)
            for n,c in ((5,'#c99a2e'),(10,'#6a9c6b'),(20,'#8974a5')):
                ax.plot(range(n-1,len(bars)),[statistics.mean(b['close'] for b in bars[j-n+1:j+1]) for j in range(n-1,len(bars))],color=c,lw=1,label=f'MA{n}')
            if p:
                ax.axhspan(p['low'],p['high'],color='#398f84',alpha=.18,label=f"Research band {p['low']:,}-{p['high']:,}")
                for v,label,c in ((p['support'],'Support','#708397'),(p['stop'],'Stop','#b63c52'),(p['resistance'],'R1','#a07c2e'),(p['resistance2'],'R2','#bf9e43')):
                    if v is not None:ax.axhline(v,color=c,ls='--',label=f'{label} {v:,.0f}')
            ax.axhline(r.get('reference_close',r['close']),color='#34465a',ls=':',label='Dated reference close')
            ax.set_title(f"RESEARCH ONLY | {r['ticker']} | {data['preview_price_asof']}\nCASH / registration today: {data['research_top2_is_registered_today']}",fontsize=10)
            fig.text(.5,.004,'Source: KRX statistics / dated research snapshot / CASH',ha='center',fontsize=7)
            ax.legend(fontsize=8,loc='upper left');ax.grid(alpha=.15);ax.yaxis.set_major_formatter(FuncFormatter(lambda v,pos:f'{v:,.0f}'))
            ticks=list(range(0,len(bars),max(1,len(bars)//5)));vol.set_xticks(ticks,[bars[i]['date'][5:] for i in ticks],rotation=25);vol.set_ylabel('Volume / million',fontsize=8)
            fig.tight_layout();name=r['ticker']+'_structure.png';fig.savefig(root/name,dpi=160);plt.close(fig);table+=f'<img src="{name}" alt="Dated research structure">';md+=['!['+r['name']+']('+name+')','']
        else:
            cached=stored_chart(data,r)
            if cached:
                name=cached.name
                if cached.resolve()!=(root/name).resolve():shutil.copyfile(cached,root/name)
                table+=f'<img src="{name}" alt="Verified same-date research chart">';md+=['!['+r['name']+']('+name+')','']
        cards.append('<section>'+table+'</section>')
    performance=data['performance'];counts=performance.get('registered_signals',0)
    md+=['## 신규 연구 성과','',f"- 보존된 선정 기록: {counts}개. A/B는 별도 비교하며 같은 종목을 합쳐 독립 거래 수로 제시하지 않습니다.",
        '- 선정 성과: 결정 종가→5/10/20일 종가와 자기 시장 지수 초과수익. 같은 종목의 20세션 중복 관찰 제외.',
        '- 타점 성과: 기존 진입 조건·1세션 유효·보수적 접촉/체결 구분·비용과 슬리피지·종가 손절 뒤 다음 거래 가능 시가.',
        '- 조기 청산 손익과 관찰기간 완료 여부를 분리하고, 청산 뒤에도 해당 종목의 관측을 계속합니다.']
    for model in ('A','B'):
        for h in (5,10,20):
            x=performance.get('selection',{}).get(model,{}).get(str(h),{});n=x.get('completed_nonoverlap',0);v=x.get('mean_excess_pct')
            md.append(f"- {model} 선정 {h}일 완료 {n}개 / 지수 대비 평균 "+('미확정' if v is None else f'{v:+.2f}%p'))
    paper=[]
    for variant,label in (('A_SUPPORT_LIMIT','지지 지정가'),('B_CONFIRMED_PULLBACK','눌림 확인 다음 시가'),('C_LIMITED_BREAKOUT','돌파 제한 매수')):
        for h in (5,10,20):
            p=performance.get('paper',{}).get('B',{}).get(variant,{}).get(str(h),{});v=p.get('mean_net_pct');statuses=p.get('status_counts',{})
            text=f"{label} · {h}일: 완료 {p.get('completed',0)}개 / 순손익 "+('미확정' if v is None else f'{v:+.2f}%')+f" / 손절 종료 {p.get('stop_exit_count',0)}개 / 상태 {json.dumps(statuses,ensure_ascii=False)}"
            paper.append(text)
    md+=['','## B 후보의 가상매매 성과','']+['- '+s for s in paper]+['','상태가 비어 있으면 등록 신호 자체가 0개입니다. NO_SIGNAL은 진입 조건 미성립, DAY_EXPIRED_NO_TOUCH는 지정가 미접촉 만료, TOUCH_WITHOUT_TRADE_THROUGH는 보수적 체결 미확인, DATA_UNUSABLE은 데이터 누락입니다. 가상 진입은 브로커 체결이 아닙니다.']
    md+=['','## 수집·실행 상태','']+['- '+s for s in data['errors']]+['',
        '- 운영 호출 검증 상태: '+operating['state'],
        '- 기본 브랜치 호출 관측: '+str(operating['main_caller_observed'])+' / 실제 자동 이벤트 관측: '+str(operating['automatic_event_observed'])+' / schedule 실행 관측: '+str(operating['schedule_event_observed']),
        '연구 브랜치 검증·기본 브랜치 호출·schedule 실행·ChatGPT 알림 전달은 각각 별도 증거로 확인합니다. 현재 ChatGPT 알림의 일정·활성 상태는 변경하지 않았으며 실제 전달은 미확인입니다.','실전 승인 TOP2 없음. GPT 실행·유료 API·실계좌 주문 없음.']
    if data.get('invocation'):
        v=data['invocation'];md+=['',f"- 호출: {v['mode']} / 원본 이벤트: {v['event']} / 실제 자동 이벤트 관측: {v['automatic_event_observed']}",
            f"- 완료 일봉 확인 대상: {v.get('expected_completed_session','미확인')} / 같은 원본 중복 갱신 생략: {v.get('duplicate_current_session_skipped',False)}"]
    for source in data.get('source_diagnostics',[]):md.append(f"- 가격 응답 {source['market']} {source['asof']}: HTTP {source.get('http_status')} / {source['status']} / OutBlock 행 {source.get('outblock_rows')}")
    if data.get('source_quality_gate'):md.append('- 선택된 원본 품질 검사: '+data['source_quality_gate']['status'])
    if data.get('primary_collection_status'):md.append('- 직접 공식 API 상태: '+data['primary_collection_status'])
    if data.get('current_scope'):md.append('- 현재 분석 가능 비바이오 보통주: '+str(data['current_scope']['analysis_eligible'])+' / 전체 가격 '+str(data['current_scope']['price_rows'])+'종목. 기존 시점 고정 종목 기본정보·업종 자료를 사용했으며 신규 분류를 추정하지 않았습니다.')
    if data.get('ledger_lane'):md.append('- 가격 원장: '+data['ledger_lane']+' (원본 암호화 보관, 기존 원장 보존). 캐시와 공식 API는 최종 KRX 원천을 공유하며 독립 공급사 둘로 계산하지 않습니다.')
    if data.get('alternative_cache_readiness'):md.append('- 캐시 경로 공표 점검: '+data['alternative_cache_readiness']['status']+' (공식 장애 복구 성공이나 새 가격 검증을 뜻하지 않음).')
    if data.get('private_storage_audit'):md.append('- 기존 원본 복호화 검사: '+str(data['private_storage_audit']['original_archives_verified'])+'개 / bootstrap '+str(data['private_storage_audit']['bootstrap_archives_verified'])+'개. 키 값 출력 없음.')
    if data.get('upstream_validation'):md.append('- 기존 스캐너 실제 수집 단계·아티팩트 확인: '+str(data['upstream_validation']['run_id']))
    if data.get('provisional_source'):
        v=data['provisional_source'];md+=['','## 격리한 임시 연구 자료','',f"- PROVISIONAL: {v['source_price_asof']} / {v['rows']}종목 / 최종 수집 {v['last_received_at']}",'- pykrx→NAVER 수정주가 요청의 종가 영수증만 보관했습니다. 완전한 OHLC·실제 거래대금·정규장 범위는 미검증입니다.','- 공식 OHLC·신호 원장·가상 체결·인증 성과에 섞지 않습니다. 신규 TOP2가 아닙니다.']
    (root/'mobile_report.md').write_text('\n'.join(md)+'\n')
    top='<section><h1>C3 연구용 TOP2·가상매매</h1><strong style="color:#a83e51">실전 행동: CASH</strong><p>보고일 '+data['report_day_kst']+' · 가격 '+data['preview_price_asof']+' · 신규 신호 '+str(data['new_registered_signals'])+'개</p><p>출처: 한국거래소 통계정보 · '+html.escape(data.get('source_provider') or '기존 자료')+' · '+html.escape(data.get('data_quality_state','미확인'))+'</p><p>신규 가격 미확보 또는 신규 기간 전에는 지난 후보를 신규 결정으로 등록하지 않습니다. 종목 선정과 진입 성과를 분리하며 미완성 수익률은 미확정으로 둡니다.</p></section>'
    top+='<section><h2>운영 실행 검증</h2><p>'+html.escape(operating['state'])+'</p><p>기본 브랜치 호출: '+str(operating['main_caller_observed'])+' · 자동 이벤트: '+str(operating['automatic_event_observed'])+' · schedule: '+str(operating['schedule_event_observed'])+'</p><p>ChatGPT 알림 실제 전달은 미확인입니다. 기존 알림 설정은 변경하지 않았습니다.</p></section>'
    doc='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>C3 전방 연구</title><style>body{font:16px/1.65 system-ui;background:#f1f4f8;color:#203047;max-width:780px;margin:auto;padding:16px}section{background:white;margin:14px 0;padding:16px;border-radius:12px}h1{font-size:25px}th,td{padding:7px;border-bottom:1px solid #ddd;text-align:left}table,img{width:100%}img{height:auto}</style>'+top+''.join(cards)+'<section><h2>B 후보 가상매매 성과</h2><ul>'+''.join('<li>'+html.escape(s)+'</li>' for s in paper)+'</ul></section><section><h2>오류와 검증 한계</h2><p>'+html.escape(' / '.join(data['errors']) or '이번 실행에서 수집 오류 없음')+'</p><p>신규 완료 표본이 없으면 성과 미확정입니다. 기존 과거 수익률은 재사용하지 않았습니다. 정규장 원천 인증·기업행위 전수 대조·기간 외 수익성은 별도 검증이 필요합니다.</p></section></html>'
    (root/'mobile_report.html').write_text(doc)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--latest',required=True);p.add_argument('--outdir',required=True);a=p.parse_args();render(a.latest,a.outdir)

