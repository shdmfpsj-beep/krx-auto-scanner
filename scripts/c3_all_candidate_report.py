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
        d.text((45,25),'강현AI PRO | 전체 후보 순위',font=font(42,True),fill='white')
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
        left,top,right,bottom=90,715,1320,1275
        d.rectangle((left,top,right,bottom),outline=(203,204,204),width=2)
        lo=min(prices)*.98;hi=max(prices)*1.02
        if hi<=lo:hi=lo+1
        xy=[(left+i*(right-left)/max(1,len(prices)-1),bottom-(v-lo)/(hi-lo)*(bottom-top)) for i,v in enumerate(prices)]
        d.line(xy,fill=(50,109,166),width=5,joint='curve')
        for window,color in ((5,(187,91,66)),(20,(42,137,91)),(60,(137,96,172))):
            ma=[sum(prices[max(0,i-window+1):i+1])/min(window,i+1) for i in range(len(prices))]
            pts=[(left+i*(right-left)/max(1,len(prices)-1),bottom-(v-lo)/(hi-lo)*(bottom-top)) for i,v in enumerate(ma)]
            d.line(pts,fill=color,width=3)
        d.text((65,1325),"종가(파랑) / MA5(빨강) / MA20(초록) / MA60(보라)",font=font(25),fill=muted)
        d.text((65,1390),"거래량",font=font(29,True),fill=ink)
        volumes=[float(b['volume']) for b in bars];vmax=max(volumes) or 1
        for i,v in enumerate(volumes):
            px=left+i*(right-left)/len(volumes)
            d.rectangle((px,1580-v/vmax*140,px+max(2,(right-left)/len(volumes)-2),1580),fill=(140,151,161))
        d.text((65,1630),"WATCH·NEAR는 매수 신호 아님 | 조건 충족 전 PASS | 주문은 사용자 직접",font=font(23),fill=muted)
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
