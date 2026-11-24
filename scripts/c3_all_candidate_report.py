#!/usr/bin/env python3
"""Complete C3 candidate ranking and one PNG per detected candidate; non-trading report."""
import argparse,hashlib,json,math,os
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from PIL.PngImagePlugin import PngInfo
from c3_top5_financial_selection import classify, financial_points, valid_entry

def image_identity(row, asof):
    identity = {"asof": asof, **{key: row.get(key) for key in (
        "code", "name", "asof_close", "entry_low", "entry_high", "stop_ref",
        "r1_ref", "r2_ref", "risk_pct", "status", "entry_valid_until", "top5",
        "ma5", "ma20", "ma60", "volume", "support", "financial_verdict", "rejection_reasons")}}
    if row.get('financial_model'):
        identity.update({key: row.get(key) for key in ('financial_model', 'quality_100', 'risk_flags',
            'financial_evidence_state', 'stop_execution_rule')})
    return identity

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--pool',required=True);p.add_argument('--selection',required=True);p.add_argument('--financial',required=True);p.add_argument('--out',required=True)
    a=p.parse_args()
    src=json.loads(Path(a.pool).read_text())
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    try: fin=json.loads(Path(a.selection).read_text())
    except (OSError,ValueError): fin={}
    evidence=json.loads(Path(a.financial).read_text())
    covered={str(x['ticker']):x for x in evidence.get('researched',[])+evidence.get('excluded',[]) if isinstance(x,dict) and x.get('ticker')}
    if evidence.get('asof')!=src.get('asof'):covered={}
    candidates=src.get('candidates',[])
    valid_until=src.get('entry_valid_until')
    selected_codes=[x['code'] for x in fin.get('selected',[]) if isinstance(x,dict) and x.get('code')]
    if fin.get('asof')!=src.get('asof') or len(selected_codes)>5 or len(set(selected_codes))!=len(selected_codes):
        selected_codes=[]
    selected_set=set(selected_codes)
    selected_names={x['code']:x.get('name') for x in fin.get('selected',[]) if isinstance(x,dict) and x.get('code')}
    if not selected_set.issubset({x['code'] for x in candidates}):
        raise ValueError('SELECTION_NOT_IN_CHART_POOL')
    for x in candidates:
        e=covered.get(x['code'])
        flag=classify(e, src.get('asof')) if e else 'REVIEW_INSUFFICIENT_EVIDENCE'
        points=None
        if e and e.get('annual_status')=='DATED_ANNUAL_RESEARCH_ONLY' and e.get('interim_status')=='DATED_INTERIM_YTD_RESEARCH_ONLY' and e.get('filing_date') and e.get('interim_filing_date'):
            # Evidence quality score is separate from the hard financial eligibility gate.
            # Weak interim results remain visible for review but NEVER authorize TOP5.
            points=financial_points(e)
        x['financial_flag']=flag;x['financial_points']=points
        x['composite_score']=round(float(x.get('opportunity_score',x.get('score',0)) or 0),2)
        x['top5_eligible']=bool(x['code'] in selected_set and valid_entry(x)
                              and flag=='QUALIFIED_BASIC_FINANCIAL_RISK')
    candidates.sort(key=lambda x:(selected_codes.index(x['code']) if x['code'] in selected_set else 100,
                                  -float(x.get('opportunity_score',0)),x['code']))
    approved_top5=selected_set
    if any(x['code'] in selected_set and x.get('name')!=selected_names.get(x['code']) for x in candidates):
        raise ValueError('SELECTION_NAME_MISMATCH')
    if sum(x['top5_eligible'] for x in candidates)!=len(selected_codes):
        raise ValueError('SELECTION_GEOMETRY_MISMATCH')
    fontdir=Path(os.environ.get('C3_FONT_DIR','/usr/share/fonts/truetype/nanum'))
    regular=str(fontdir/'NanumGothic.ttf')
    bold=str(fontdir/'NanumGothicBold.ttf')
    def font(n,b=False):return ImageFont.truetype(bold if b else regular,n)
    rows=[]
    for rank,x in enumerate(candidates,1):
        valid=bool(x.get('geometry_validated'))
        verdict=fin.get('financial_verdicts', {}).get(x['code'])
        state=('ERROR' if verdict=='ERROR' else 'REJECTED' if verdict=='REJECTED_FINANCIAL_RISK' or not valid
               else 'REVIEW_REQUIRED' if verdict=='REVIEW_REQUIRED' else x.get('entry_status','WATCH'))
        is_fin=x['financial_points'] is not None
        score=round(float(x.get('opportunity_score',x.get('score',0))),2)
        composite=x['composite_score'];top5=x['code'] in approved_top5
        bars=x['bars'];prices=[float(b['close']) for b in bars]
        # Restore the proven C3 classic visual hierarchy: headline, chart,
        # four trading-level cards, then risk/strength metrics.
        if len(bars)!=60 or any(not all(k in bar for k in ('open','high','low','close','volume','date')) for bar in bars):
            raise ValueError('CLASSIC_REQUIRES_60_REAL_OHLCV_'+x['code'])
        if ([b['date'] for b in bars]!=sorted(set(b['date'] for b in bars)) or
            bars[-1]['date']!=src['asof'] or prices[-1]!=x.get('close')):
            raise ValueError('CLASSIC_SOURCE_DATE_OR_CLOSE_MISMATCH_'+x['code'])
        im=Image.new('RGB',(1400,1710),(250,249,245));d=ImageDraw.Draw(im)
        ink=(42,44,46);muted=(105,111,114);gold=(170,136,74)
        green=(43,122,86);red=(179,74,72);blue=(54,117,170)
        d.rectangle((0,0,1400,102),fill=ink)
        d.text((48,24),'강현AI PRO | C3 TOP5',font=font(40,True),fill='white')
        if evidence.get('model')=='BALANCED_QUALITY_TIMING_V1':
            d.text((650,39),'Balanced Quality & Timing',font=font(23),fill=(225,215,193))
        d.text((1340,32),src['asof'],font=font(27),fill='white',anchor='ra')
        d.line((0,103,1400,103),fill=gold,width=5)
        d.text((50,136),x['name'],font=font(59,True),fill=ink)
        d.text((50,216),f"{x['code']} · {state} · "+('TOP5' if top5 else '관찰 후보'),font=font(29),fill=muted)
        d.text((1350,139),f"{prices[-1]:,.0f}원",font=font(56,True),fill=ink,anchor='ra')
        d.rectangle((46,271,1354,318),fill=(239,235,224))
        d.text((700,281),'매수 범위 도달 시에만 관찰 · 미도달 PASS · 직접 매매',font=font(25),fill=(122,97,57),anchor='ma')
        d.rounded_rectangle((42,342,1358,1158),radius=15,fill='white',outline=(216,216,212),width=2)
        synthetic=src.get('fixture_kind')=='SYNTHETIC_NOT_MARKET_SELECTION'
        d.text((70,359),'합성 검증 60봉 · 실제 선정 아님' if synthetic else '실제 일봉 60거래일 · 거래량',font=font(30,True),fill=ink)
        d.text((1320,364),'MA5 · MA20 · MA60(마지막 값만)',font=font(22),fill=muted,anchor='ra')
        left,right,top,bottom=150,1100,440,957
        highs=[float(z['high']) for z in bars];lows=[float(z['low']) for z in bars]
        opens=[float(z['open']) for z in bars]
        levels=[float(x[k]) for k in ('entry_low','entry_high','stop_ref','r1_ref','r2_ref') if valid and isinstance(x.get(k),(int,float))]
        lo=min(lows+levels)*.965;hi=max(highs+levels)*1.035
        if hi<=lo:raise ValueError('INVALID_PRICE_RANGE')
        px=lambda i:round(left+i*(right-left)/59)
        py=lambda v:round(bottom-(v-lo)/(hi-lo)*(bottom-top))
        for j in range(5):
            price=lo+(hi-lo)*j/4;yy=py(price)
            d.line((left,yy,right,yy),fill=(232,231,227),width=2)
            d.text((left-14,yy),f"{price:,.0f}",font=font(23),fill=muted,anchor='rm')
        if valid and isinstance(x.get('entry_low'),(int,float)) and isinstance(x.get('entry_high'),(int,float)):
            ya,yb=py(x['entry_high']),py(x['entry_low'])
            d.rectangle((left,ya,right,yb),fill=(235,244,237))
            for yy in (ya,yb):
                for xx in range(left,right,21):d.line((xx,yy,min(xx+12,right),yy),fill=green,width=3)
            for xx in (left,right):
                for yy in range(ya,yb,18):d.line((xx,yy,xx,min(yy+10,yb)),fill=green,width=3)
            if isinstance(x.get('pivot_support'),(int,float)):
                support=x['pivot_support'];yy=py(support)
                d.text((left+8,yy+8),f"지지 {support:,.0f}",font=font(19),fill=green)
        if valid:
            for k,color in (('stop_ref',red),('r1_ref',gold),('r2_ref',(128,101,159))):
                v=x.get(k)
                if isinstance(v,(int,float)):
                    yy=py(v)
                    for xx in range(left,right,21):d.line((xx,yy,min(xx+11,right),yy),fill=color,width=2)
        for i,z in enumerate(bars):
            xx=px(i);color=red if float(z['close'])>=float(z['open']) else blue
            d.line((xx,py(float(z['high'])),xx,py(float(z['low']))),fill=color,width=2)
            y1,y2=sorted((py(float(z['open'])),py(float(z['close']))))
            d.rectangle((xx-5,y1,xx+5,max(y1+2,y2)),fill=color)
        for n,color in ((5,(63,93,132)),(20,(174,139,64)),(60,(107,141,130))):
            pts=[(px(i),py(sum(prices[i-n+1:i+1])/n)) for i in range(n-1,60)]
            if len(pts)>1:d.line(pts,fill=color,width=4)
            elif pts:
                xx,yy=pts[0];d.ellipse((xx-4,yy-4,xx+4,yy+4),fill=color)
        close_y=py(prices[-1])
        d.rounded_rectangle((1120,close_y-25,1340,close_y+25),radius=5,fill=ink)
        d.text((1327,close_y),f"종가 {prices[-1]:,.0f}",font=font(23,True),fill='white',anchor='rm')
        for i in (0,12,24,36,48,59):
            day=str(bars[i]['date']).replace('-','')
            d.text((px(i),985),day[4:6]+'/'+day[6:8],font=font(21),fill=muted,anchor='ma')
        vmax=max(float(z['volume']) for z in bars) or 1
        for i,z in enumerate(bars):
            xx=px(i);v=float(z['volume']);color=red if prices[i]>=opens[i] else blue
            d.rectangle((xx-5,1110-v/vmax*100,xx+5,1110),fill=color)
        d.text((151,1117),'거래량',font=font(22),fill=muted)
        d.text((1095,1117),f"최대 {vmax/10000:,.1f}만주",font=font(22),fill=muted,anchor='ra')
        d.text((50,1190),'매매 관찰 기준',font=font(33,True),fill=ink)
        cards=[('매수 관찰 범위',f"{x['entry_low']:,.0f} ~ {x['entry_high']:,.0f}" if valid and x.get('entry_low') is not None and x.get('entry_high') is not None else '미확정',green),
               ('구조손절',f"{x['stop_ref']:,.0f}" if valid and x.get('stop_ref') is not None else '미확정',red),
               ('1차 저항 R1',f"{x['r1_ref']:,.0f}" if valid and x.get('r1_ref') is not None else '미확정',gold),
               ('2차 저항 R2',f"{x['r2_ref']:,.0f}" if valid and x.get('r2_ref') is not None else '미확정',(128,101,159))]
        for i,(label,value,color) in enumerate(cards):
            l=46+i*332
            d.rounded_rectangle((l,1248,l+318,1377),radius=9,fill='white',outline=(216,216,212),width=2)
            d.line((l+12,1256,l+306,1256),fill=color,width=5)
            d.text((l+159,1280),label,font=font(24),fill=muted,anchor='ma')
            d.text((l+159,1325),value,font=font(28,True),fill=color,anchor='ma')
        risk=x.get('risk_pct') if valid else None
        financial_item=covered.get(x['code']) or {}
        quality=financial_item.get('quality_100')
        quality_label=(f"{quality['score']:.1f}/100"+(' 부분' if not quality.get('complete') else '')) if quality and quality.get('score') is not None else (f"{x['financial_points']}/30" if is_fin else '미검증')
        d.text((50,1415),f"진입 {state} · 위험 "+(f"{risk:.2f}%" if isinstance(risk,(int,float)) else '미확정')+
               f" · 기술 {score:.2f} · 재무 "+quality_label,font=font(29,True),fill=ink)
        d.text((50,1475),f"MA5 {sum(prices[-5:])/5:,.0f} · MA20 {sum(prices[-20:])/20:,.0f} · MA60 {sum(prices)/60:,.0f} | 거래량 {bars[-1]['volume']:,.0f}",font=font(24),fill=muted)
        if quality:
            risks=financial_item.get('risk_assessment',{})
            notice='재무 '+financial_item.get('financial_evidence_state','REVIEW_REQUIRED')+' · '+str(quality.get('available_points',0))+'/100점 항목 관측'
            d.text((50,1515),notice,font=font(22),fill=muted)
            codes=risks.get('hard_failures',[])+risks.get('mandatory_missing',[])+risks.get('risk_flags',[])
            labels={'NEGATIVE_OCF_NOT_AUTOMATIC_EXCLUSION':'영업현금흐름 음수',
                    'RECENT_NEGATIVE_OCF_NOT_AUTOMATIC_EXCLUSION':'최근 누적현금흐름 음수',
                    'NEGATIVE_FCF_CAPEX_OR_WORKING_CAPITAL_REVIEW':'FCF 음수·투자/운전자본 확인',
                    'RECENT_EARNINGS_SLOWDOWN':'최근 실적 둔화',
                    'RECENT_OCF_WEAKENING':'최근 영업현금흐름 감소',
                    'RECENT_EARNINGS_CASH_FLOW_DIVERGENCE':'이익 증가·현금흐름 감소',
                    'EXISTING_LEVERAGE_CEILING_300PCT':'부채비율 300% 초과',
                    'RECENT_EXISTING_LEVERAGE_CEILING_300PCT':'최근 부채비율 300% 초과',
                    'TWO_ANNUAL_LOSSES_AND_CURRENT_YTD_LOSS':'2년 연속·최근 누적 영업손실',
                    'ANNUAL_LOSS_CURRENT_YTD_POSITIVE':'연간 적자 후 최근 누적 흑자',
                    'EBITDA_AND_NET_DEBT_EXCLUDE_LEASE_ADJUSTMENTS':'EBITDA·순차입금 리스 조정 미반영'}
            hints=list(dict.fromkeys(labels.get(code,'필수 재무자료 추가 확인') for code in codes))
            d.text((50,1548),'위험: '+(' / '.join(hints[:2]) if hints else '구조화 항목 심사 통과'),font=font(21),fill=muted)
        d.text((50,1580),'종가 < 구조손절 → 다음 거래일 직접 정리 · 미도달 PASS',font=font(24),fill=muted)
        expiry=valid_until[:10]+' 장종료까지' if valid_until else '미확정'
        d.text((50,1620),f"기준 {src['asof']} | 유효 {expiry} | 매수 전 재확인 · 직접 매매",font=font(24),fill=muted)
        d.text((50,1661),'합성 검증 자료 · 실제 시장 선정 또는 매매용 신호 아님' if synthetic else
               'KRX 일봉 · 정규장 종가/수정주가 미인증 · 추세·지지 눌림 후보',font=font(21),fill=muted)
        name=f"{rank:02d}_{x['code']}_all_candidate.png"
        row={'rank':rank,'code':x['code'],'name':x['name'],'technical_score':score,
          'score_type':'CHARTIST_TECHNICAL_OPPORTUNITY_ONLY','status':state,'financial_selected':top5,'financial_evidence_scored':is_fin,
          'financial_flag':x['financial_flag'],'financial_points':x['financial_points'],
          'financial_eligibility':'PASS' if x['top5_eligible'] else 'WATCH_ONLY',
          'financial_exclusion_reasons':(covered.get(x['code']) or {}).get('exclusion_reasons',[]),
          'composite_score':composite,'top5':top5,'geometry_validated':valid,'image':name,
          'entry_low':x.get('entry_low') if valid else None,'entry_high':x.get('entry_high') if valid else None,
          'stop_ref':x.get('stop_ref') if valid else None,
          'risk_pct':x.get('risk_pct') if valid else None,
          'r1_ref':x.get('r1_ref') if valid else None,
          'r2_ref':x.get('r2_ref') if valid else None,
          'entry_valid_until':valid_until,
          'ma5':sum(prices[-5:])/5,'ma20':sum(prices[-20:])/20,'ma60':sum(prices)/60,
          'volume':bars[-1]['volume'],'support':x.get('pivot_support'),
          'financial_verdict':verdict,'rejection_reasons':x.get('rejection_reasons',[]),
          'asof_close':prices[-1]}
        if financial_item.get('financial_model'):
            row.update(financial_model=financial_item['financial_model'],quality_100=quality,
                       risk_flags=financial_item.get('risk_assessment',{}).get('risk_flags',[]),
                       financial_evidence_state=financial_item.get('financial_evidence_state'),
                       stop_execution_rule='CLOSE_BELOW_STRUCTURAL_STOP_EXIT_NEXT_SESSION_MANUALLY')
        info=PngInfo()
        info.add_text('c3_candidate',json.dumps(image_identity(row,src['asof']),
                                             ensure_ascii=False,sort_keys=True))
        im.save(out/name,optimize=True,pnginfo=info)
        row['image_sha256']=hashlib.sha256((out/name).read_bytes()).hexdigest()
        rows.append(row)
    result={'schema':'C3_ALL_CANDIDATES_V2','asof':src['asof'],'entry_valid_until':valid_until,'candidate_count':len(rows),
      'score_disclaimer':'Separate financial /30, technical strength and entry opportunity; TOP5 follows financial selection; no trade approval',
      'candidates':rows,'selected_codes':selected_codes,'trade_approved':False,
      'financial_diagnostics':{'evidence_count':sum(x['financial_points'] is not None for x in rows),
       'eligible_top5_count':sum(x['top5'] for x in rows),
       'failed_gate_count':sum(x['financial_flag']=='REVIEW_FAILED_FINANCIAL_GATE' for x in rows),
       'unverified_count':sum(x['financial_points'] is None for x in rows)}}
    (out/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C3_ALL_CANDIDATES',json.dumps({'asof':src['asof'],'count':len(rows),
      'images':len(rows),'top5':[x['code'] for x in rows if x['top5']]},ensure_ascii=False))
if __name__=='__main__':main()
