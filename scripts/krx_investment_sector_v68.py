#!/usr/bin/env python3
"""v6.8 investment-sector membership expansion; research-only, no BUY signals.

Uses v6.7 seed mapping plus a conservatively curated, explicitly UNVERIFIED
extension. Never infers theme membership from KIND industry or price changes.
All accepted rows require exact ticker AND company-name match to the dated
market snapshot. An absent company is rejected, not silently substituted.
"""
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from krx_investment_sector_v67 import SEEDS, norm_name

# Proposed memberships; these are research hypotheses, NOT independently
# verified exposure/earnings attribution. A company can have multiple themes.
EXTENSIONS = '''반도체|소재·부품|074600|원익QnC
반도체|소재·부품|064760|티씨케이
반도체|소재·부품|166090|하나머티리얼즈
반도체|전공정 장비|084370|유진테크
반도체|전공정 장비|095610|테스
반도체|장비·소재|281820|케이씨텍
반도체|장비|039440|에스티아이
반도체|검사·테스트|003160|디아이
반도체|검사·테스트|058470|리노공업
반도체|테스트 소켓|095340|ISC
반도체|후공정|036540|SFA반도체
반도체|패키징 기판|222800|심텍
반도체|패키징 기판|353200|대덕전자
반도체|패키징 기판|007810|코리아써키트
반도체|장비|079370|제우스
반도체|검사·테스트|348210|넥스틴
반도체|검사·테스트|232140|와이씨
반도체|검사·테스트|089030|테크윙
반도체|소재|014680|한솔케미칼
2차전지|소재|450080|에코프로머티
2차전지|소재|278280|천보
2차전지|음극재 소재|078600|대주전자재료
2차전지|소재|121600|나노신소재
2차전지|전해액|348370|엔켐
2차전지|소재·지주|036830|솔브레인홀딩스
2차전지|소재|093370|후성
2차전지|재활용|365340|성일하이텍
2차전지|장비|382840|원준
2차전지|장비|262260|에이프로
2차전지|장비|372170|윤성에프앤씨
전력·전력인프라|전력 설비|147830|제룡산업
전력·전력인프라|변압기|062040|산일전기
전력·전력인프라|전선|000500|가온전선
전력·전력인프라|전선|006340|대원전선
전력·전력인프라|전력 부품|017510|세명전기
원전|원전 기자재|042370|비츠로테크
원전|원전 서비스|130660|한전산업
원전|원전 제어|032820|우리기술
원전|원전 계측|105840|우진
원전|원전 보조기기|083650|비에이치아이
원전|원전 정비|051600|한전KPS
원전|원전·에너지 장비|100840|SNT에너지
방산|탄약·소재|103140|풍산
방산|구동계|003570|SNT다이내믹스
방산|엔진|077970|STX엔진
조선|선박 엔진|082740|한화엔진
조선|선박 엔진|071970|HD현대마린엔진
조선|선박 엔진|077970|STX엔진
조선|보냉재|033500|동성화인텍
조선|보냉재|017960|한국카본
로봇|산업·물류 로봇|117730|티로보틱스
로봇|협동 로봇|348340|뉴로메카
로봇|감속기·모터|058610|에스피지
로봇|감속기|389500|에스비비테크
로봇|산업 로봇|090360|로보스타
로봇|모터|160190|하이젠알앤엠
로봇|서비스 로봇|466100|클로봇
로봇|로봇|090710|휴림로봇
로봇|서비스 로봇|270660|에브리봇
로봇|자동화|388720|유일로보틱스
바이오|신약 개발|310210|보로노이
바이오|신약 개발|298380|에이비엘바이오
바이오|신약 개발|087010|펩트론
바이오|신약 개발|028300|HLB
바이오|제약|000100|유한양행
바이오|신약 개발|326030|SK바이오팜
바이오|바이오 의약품 생산|053030|바이넥스
바이오|CDMO·원료의약품|237690|에스티팜
바이오|신약 개발|039200|오스코텍
자동차·모빌리티|물류|086280|현대글로비스
자동차·모빌리티|부품|011210|현대위아
자동차·모빌리티|부품|015750|성우하이텍
자동차·모빌리티|부품|005850|에스엘
자동차·모빌리티|부품|010690|화신
AI·데이터센터|반도체 부품|095340|ISC
AI·데이터센터|반도체 검사|089030|테크윙
AI·데이터센터|전력 장비|062040|산일전기
AI·데이터센터|서버 기판|353200|대덕전자
인터넷·플랫폼|커머스 솔루션|042000|카페24
인터넷·플랫폼|인터넷 서비스|181710|NHN'''


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', default='reports/v65_sector_stock_map.csv')
    p.add_argument('--outdir', default='reports')
    args = p.parse_args()
    source = Path(args.input)
    if not source.is_file():
        p.error(f'Input missing: {source}')
    with source.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not {'ticker', 'name', 'snapshot_date'}.issubset(reader.fieldnames or []):
            p.error('Missing required columns: ticker,name,snapshot_date')
        data = list(reader)
    if not data:
        p.error('Empty market snapshot')
    dates = {r['snapshot_date'].strip() for r in data}
    if len(dates) != 1 or not next(iter(dates)):
        p.error('Mixed/empty snapshot dates')
    by_code = {}
    for r in data:
        t = r['ticker'].strip().zfill(6)
        if not re.fullmatch(r'\d{6}', t) or t in by_code:
            p.error(f'Invalid/duplicate ticker: {t}')
        by_code[t] = r

    proposals = []
    for origin, block in [('V67_SEED', SEEDS), ('V68_EXTENSION', EXTENSIONS)]:
        for line in block.splitlines():
            sector, subtheme, ticker, name = line.split('|')
            proposals.append((origin, sector, subtheme, ticker, name))
    accepted, rejected, seen = [], [], set()
    for origin, sector, subtheme, ticker, name in proposals:
        key = (ticker, sector)
        market = by_code.get(ticker)
        reason = None
        if key in seen:
            reason = 'DUPLICATE_SECTOR_TICKER'
        elif market is None:
            reason = 'NOT_IN_MARKET_SNAPSHOT'
        elif norm_name(market['name']) != norm_name(name):
            reason = 'NAME_MISMATCH'
        if reason:
            rejected.append({'ticker':ticker,'expected_name':name,
                             'actual_name':market['name'] if market else '',
                             'investment_sector':sector,'reason':reason,'mapping_origin':origin})
            continue
        seen.add(key)
        accepted.append({'ticker':ticker,'name':market['name'],'market':market.get('market',''),
                         'snapshot_date':market['snapshot_date'], 'investment_sector':sector,
                         'subtheme':subtheme,'mapping_origin':origin,
                         'mapping_basis':'CURATED_RESEARCH_HYPOTHESIS',
                         'theme_exposure_verified':'false'})
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    def write(name, fields, rows):
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
            w.writeheader(); w.writerows(rows)
    write('v68_investment_sector_members.csv',
          ['ticker','name','market','snapshot_date','investment_sector','subtheme','mapping_origin','mapping_basis','theme_exposure_verified'], accepted)
    write('v68_investment_sector_rejections.csv',
          ['ticker','expected_name','actual_name','investment_sector','reason','mapping_origin'], rejected)
    by_sector=defaultdict(set)
    for r in accepted: by_sector[r['investment_sector']].add(r['ticker'])
    coverage=[{'investment_sector':s,'mapped_unique_tickers':len(tickers),
               'mapping_status':'EXPANDED_RESEARCH_NOT_COMPLETE'} for s,tickers in sorted(by_sector.items())]
    write('v68_investment_sector_coverage.csv',
          ['investment_sector','mapped_unique_tickers','mapping_status'], coverage)
    unique={r['ticker'] for r in accepted}
    audit={'status':'RESEARCH_EXPANSION_NOT_TRADE_READY',
           'snapshot_date':next(iter(dates)), 'market_rows':len(data),
           'proposed_mapping_rows':len(proposals),'accepted_mapping_rows':len(accepted),
           'unique_mapped_tickers':len(unique), 'unmapped_market_tickers':len(by_code)-len(unique),
           'investment_sectors':len(by_sector), 'rejected_mapping_rows':len(rejected),
           'mapping_origin_counts':dict(Counter(r['mapping_origin'] for r in accepted)),
           'sector_counts':dict(sorted((s,len(v)) for s,v in by_sector.items())),
           'overlapping_tickers':dict(sorted((t,n) for t,n in Counter(r['ticker'] for r in accepted).items() if n>1)),
           'limitations':['Theme membership is a manually curated, UNVERIFIED research hypothesis.',
                          'No earnings-exposure validation, theme-source evidence, or historical point-in-time mapping.',
                          'Coverage is partial; unmatched stocks must remain eligible for independent market-wide screening.',
                          'Sector overlap allowed: do not sum cross-sector turnover as market money flow.',
                          'No 5/20-day sector relative strength, institutional flows, TOP3 or trading signals.']}
    (out/'v68_investment_sector_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:audit[k] for k in ['status','market_rows','accepted_mapping_rows','unique_mapped_tickers','investment_sectors','rejected_mapping_rows']},ensure_ascii=False))

if __name__=='__main__': main()
