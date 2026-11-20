#!/usr/bin/env python3
"""Complete C3 candidate ranking and one PNG per detected candidate; non-trading report."""
import argparse,json,math
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from c3_top5_financial_selection import classify

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
    candidates=src.get('candidates',[])[:10]
    selected_codes=[x['code'] for x in fin.get('selected',[]) if isinstance(x,dict) and x.get('code')]
    if fin.get('asof')!=src.get('asof') or len(selected_codes)>5 or len(set(selected_codes))!=len(selected_codes):
        selected_codes=[]
    selected_set=set(selected_codes)
    selected_names={x['code']:x.get('name') for x in fin.get('selected',[]) if isinstance(x,dict) and x.get('code')}
    if not selected_set.issubset({x['code'] for x in candidates}):
        raise ValueError('SELECTION_NOT_IN_CHART_POOL')
    for x in candidates:
        e=covered.get(x['code'])
        flag=classify(e) if e else 'REVIEW_INSUFFICIENT_EVIDENCE'
        points=None
        if e and e.get('annual_status')=='DATED_ANNUAL_RESEARCH_ONLY' and e.get('interim_status')=='DATED_INTERIM_YTD_RESEARCH_ONLY' and e.get('filing_date') and e.get('interim_filing_date'):
            # Evidence quality score is separate from the hard financial eligibility gate.
            # Weak interim results remain visible for review but NEVER authorize TOP5.
            annual={'ANNUAL_GROWTH_AND_MARGIN_OBSERVED':16,'ANNUAL_POSITIVE_MIXED':11,
                    'ANNUAL_RISK_OR_SLOWDOWN':5}.get(e.get('financial_quality'),0)
            interim={'INTERIM_SALES_AND_PROFIT_GROWTH_OBSERVED':14,'INTERIM_MIXED':9,
                     'INTERIM_PROFIT_OR_SALES_WEAKENING':4}.get(e.get('interim_quality'),0)
            points=annual+interim
        x['financial_flag']=flag;x['financial_points']=points
        x['composite_score']=round(float(x.get('opportunity_score',x.get('score',0)) or 0),2)
        x['top5_eligible']=bool(x['code'] in selected_set and x.get('geometry_validated') and x.get('entry_status') in ('ENTRY_READY','NEAR_ENTRY'))
    candidates.sort(key=lambda x:(selected_codes.index(x['code']) if x['code'] in selected_set else 100,
                                  -float(x.get('opportunity_score',0)),x['code']))
    approved_top5=selected_set
    if any(x['code'] in selected_set and x.get('name')!=selected_names.get(x['code']) for x in candidates):
        raise ValueError('SELECTION_NAME_MISMATCH')
    if sum(x['top5_eligible'] for x in candidates)!=len(selected_codes):
        raise ValueError('SELECTION_GEOMETRY_MISMATCH')
    regular='/usr/share/fonts/truetype/nanum/NanumGothic.ttf'
    bold='/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf'
    def font(n,b=False):return ImageFont.truetype(bold if b else regular,n)
    rows=[]
    for rank,x in enumerate(candidates,1):
        valid=bool(x.get('geometry_validated'))
        state=x.get('entry_status','WATCH') if valid else 'WATCH'
        is_fin=x['financial_points'] is not None
        score=round(float(x.get('opportunity_score',x.get('score',0))),2)
        composite=x['composite_score'];top5=x['code'] in approved_top5
        bars=x['bars'];prices=[float(b['close']) for b in bars]
        im=Image.new('RGB',(1400,1710),(249,248,244));d=ImageDraw.Draw(im)
        ink=(39,43,49);muted=(97,104,110);gold=(162,121,54)
        d.rectangle((0,0,1400,110),fill=ink)
        d.text((45,25),'강현AI PRO | C3 TOP5 차트',font=font(42,True),fill='white')
        d.text((1325,36),src['asof'],font=font(28),fill='white',anchor='ra')
        d.text((55,145),x['name'],font=font(62,True),fill=ink)
        d.text((55,242),f"전체 {rank}위 / {len(candidates)} | 종합 "+(f"{composite:.2f}점" if composite is not None else "미산정")+(" | TOP5" if top5 else ""),font=font(37,True),fill=gold)
        d.text((55,315),f"{x['code']}  |  {state}  |  "+x['financial_flag'],font=font(31),fill=ink)
        d.text((55,395),f"종가 {prices[-1]:,.0f}원 | 기술 {score:.2f} | 재무 "+(str(x["financial_points"])+"/30" if is_fin else "미검증"),font=font(43,True),fill=ink)
        d.text((55,477),"매수범위 / 구조손절 / 목표가",font=font(31,True),fill=ink)
        if valid and all(x.get(k) is not None for k in ('entry_low','entry_high','stop_ref','r1_ref')):
            levels=f"{x['entry_low']:,.0f} ~ {x['entry_high']:,.0f}원  /  {x['stop_ref']:,.0f}원"
            target=f"R1 {x['r1_ref']:,.0f}원  /  R2 "+(f"{x['r2_ref']:,.0f}원" if x.get('r2_ref') else '미확정')
        else:
            levels="진입 구조 미확정 · 관찰 전용 (매수 금지)"
            target="R1 / R2 미확정"
        d.text((55,535),levels,font=font(30),fill=ink)
        d.text((55,595),target,font=font(29),fill=muted)
        # Confirmed phone-readable trading chart: actual OHLC candles, MA5/20/60,
        # dashed entry box, structural stop, R1/R2, and volume.
        if len(bars)!=60:
            raise ValueError('CHART_REQUIRES_60_BARS_'+x['code'])
        left,top,right,bottom=125,690,1080,1260
        highs=[float(b['high']) for b in bars]
        lows=[float(b['low']) for b in bars]
        opens=[float(b['open']) for b in bars]
        levels=[float(v) for v in (x.get('entry_low'),x.get('entry_high'),
                x.get('stop_ref'),x.get('r1_ref'),x.get('r2_ref')) if v is not None] if valid else []
        lo=min(lows+levels)*.97;hi=max(highs+levels)*1.03
        if hi<=lo:hi=lo+1
        py=lambda v:round(bottom-(v-lo)/(hi-lo)*(bottom-top))
        px=lambda i:round(left+i*(right-left)/59)
        d.rectangle((left-20,top-20,1320,1600),fill='white',outline=(213,214,212),width=2)
        for j in range(5):
            price=lo+(hi-lo)*j/4
            yy=py(price)
            d.line((left,yy,right,yy),fill=(231,232,231),width=1)
            d.text((left-12,yy),f"{price:,.0f}",font=font(19),fill=muted,anchor='rm')
        def dashed_line(y,color,width=3):
            for xx in range(left,right,22):
                d.line((xx,y,min(xx+12,right),y),fill=color,width=width)
        if valid and x.get('entry_low') is not None and x.get('entry_high') is not None:
            ya,yb=py(float(x['entry_high'])),py(float(x['entry_low']))
            for yy in (ya,yb):dashed_line(yy,(33,132,91),4)
            for xx in (left,right):
                for yy in range(ya,yb,22):
                    d.line((xx,yy,xx,min(yy+12,yb)),fill=(33,132,91),width=3)
            d.text((1095,ya),f"매수상단 {x['entry_high']:,.0f}",font=font(19,True),fill=(33,132,91))
            d.text((1095,yb),f"매수하단 {x['entry_low']:,.0f}",font=font(19,True),fill=(33,132,91))
        for key,label,color in (('stop_ref','손절',(185,58,58)),
                                ('r1_ref','R1',(160,113,38)),('r2_ref','R2',(115,81,163))):
            value=x.get(key) if valid else None
            if value is not None:
                yy=py(float(value));dashed_line(yy,color,2)
                d.text((1095,yy+3),f"{label} {value:,.0f}",font=font(20,True),fill=color)
        for i,b in enumerate(bars):
            xx=px(i);color=(194,70,65) if float(b['close'])>=float(b['open']) else (45,102,175)
            d.line((xx,py(float(b['high'])),xx,py(float(b['low']))),fill=color,width=2)
            a1,a2=sorted((py(float(b['open'])),py(float(b['close']))))
            d.rectangle((xx-5,a1,xx+5,max(a1+2,a2)),fill=color)
        for window,color in ((5,(188,89,61)),(20,(37,132,89)),(60,(118,85,162))):
            pts=[(px(i),py(sum(prices[i-window+1:i+1])/window)) for i in range(window-1,60)]
            if len(pts)>1:d.line(pts,fill=color,width=4)
        d.text((65,1330),"일봉 60거래일  |  MA5 빨강 · MA20 초록 · MA60 보라",font=font(27,True),fill=ink)
        d.text((65,1390),"거래량",font=font(29,True),fill=ink)
        volumes=[float(b['volume']) for b in bars];vmax=max(volumes) or 1
        for i,v in enumerate(volumes):
            xx=px(i);color=(194,70,65) if prices[i]>=opens[i] else (45,102,175)
            d.rectangle((xx-5,1575-v/vmax*125,xx+5,1575),fill=color)
        d.text((65,1630),"기준일 "+src['asof']+" | 다음 거래일 재확인 | 미도달 PASS | 직접 매매",font=font(23),fill=muted)
        name=f"{rank:02d}_{x['code']}_all_candidate.png"
        im.save(out/name,optimize=True)
        rows.append({'rank':rank,'code':x['code'],'name':x['name'],'technical_score':score,
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
          'asof_close':prices[-1]})
    result={'schema':'C3_ALL_CANDIDATES_V2','asof':src['asof'],'candidate_count':len(rows),
      'score_disclaimer':'Technical opportunity score only; financial evidence is basic risk exclusion, not ranking; no trade approval',
      'candidates':rows,'selected_codes':selected_codes,'trade_approved':False,
      'financial_diagnostics':{'evidence_count':sum(x['financial_points'] is not None for x in rows),
       'eligible_top5_count':sum(x['top5'] for x in rows),
       'failed_gate_count':sum(x['financial_flag']=='REVIEW_FAILED_FINANCIAL_GATE' for x in rows),
       'unverified_count':sum(x['financial_points'] is None for x in rows)}}
    (out/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C3_ALL_CANDIDATES',json.dumps({'asof':src['asof'],'count':len(rows),
      'images':len(rows),'top5':[x['code'] for x in rows if x['top5']]},ensure_ascii=False))
if __name__=='__main__':main()
