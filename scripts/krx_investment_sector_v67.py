#!/usr/bin/env python3
"""v6.7: auditable investment-theme seed mapping, not KIND industry sectors.

Research-only, conservative seed universe. NO price signals, TOP3 or real money flow.
No web requests. A ticker is accepted only if both code and expected name match.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Each row: investment sector, subtheme, ticker, expected listed name.
# Deliberately a SMALL manually reviewed seed set, NOT a complete thematic universe.
SEEDS = '''반도체|메모리|005930|삼성전자
반도체|메모리|000660|SK하이닉스
반도체|후공정·패키징|042700|한미반도체
반도체|전공정 장비|240810|원익IPS
반도체|전공정 장비|403870|HPSP
반도체|장비|039030|이오테크닉스
반도체|소재|005290|동진쎄미켐
반도체|소재|357780|솔브레인
반도체|전공정 장비|036930|주성엔지니어링
반도체|전공정 장비|319660|피에스케이
반도체|장비·냉각|083450|GST
2차전지|셀|373220|LG에너지솔루션
2차전지|셀|006400|삼성SDI
2차전지|양극재|247540|에코프로비엠
2차전지|소재 지주·관련|086520|에코프로
2차전지|양극·음극재|003670|포스코퓨처엠
2차전지|양극재|066970|엘앤에프
2차전지|장비|137400|피엔티
전력·전력인프라|전력기기|010120|LS ELECTRIC
전력·전력인프라|변압기|267260|HD현대일렉트릭
전력·전력인프라|변압기·중전기|298040|효성중공업
전력·전력인프라|전선|103590|일진전기
전력·전력인프라|전선|001440|대한전선
전력·전력인프라|변압기|033100|제룡전기
전력·전력인프라|전선·지주|006260|LS
원전|원전 설비|034020|두산에너빌리티
원전|원전 설계|052690|한전기술
방산|지상무기|064350|현대로템
방산|항공·엔진|012450|한화에어로스페이스
방산|항공|047810|한국항공우주
방산|전자·방산|272210|한화시스템
조선|조선 지주|009540|HD한국조선해양
조선|조선·선박|329180|HD현대중공업
조선|조선·선박|010140|삼성중공업
조선|조선·선박|042660|한화오션
로봇|휴머노이드·로봇|277810|레인보우로보틱스
로봇|협동로봇|454910|두산로보틱스
로봇|로봇 구동·서비스|108490|로보티즈
로봇|서비스로봇|056080|유진로봇
바이오|바이오시밀러|068270|셀트리온
바이오|CDMO|207940|삼성바이오로직스
바이오|플랫폼 기술|196170|알테오젠
바이오|ADC|141080|리가켐바이오
자동차·모빌리티|완성차|005380|현대차
자동차·모빌리티|완성차|000270|기아
자동차·모빌리티|부품|012330|현대모비스
자동차·모빌리티|부품|204320|HL만도
AI·데이터센터|서버 반도체·메모리|000660|SK하이닉스
AI·데이터센터|서버 반도체·메모리|005930|삼성전자
AI·데이터센터|전력 인프라|010120|LS ELECTRIC
AI·데이터센터|전력 인프라|267260|HD현대일렉트릭
AI·데이터센터|냉각|083450|GST
인터넷·플랫폼|검색·플랫폼|035420|NAVER
인터넷·플랫폼|메신저·플랫폼|035720|카카오'''


def norm_name(s):
    return ''.join(str(s).split()).casefold()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default='reports/v65_sector_stock_map.csv')
    ap.add_argument('--outdir', default='reports')
    args = ap.parse_args()
    src = Path(args.input)
    if not src.is_file():
        ap.error(f'Input missing: {src}')
    with src.open(encoding='utf-8-sig', newline='') as f:
        data = list(csv.DictReader(f))
    if not data or not {'ticker','name','snapshot_date'}.issubset(data[0]):
        ap.error('Input must have ticker,name,snapshot_date columns')
    dates = {r['snapshot_date'].strip() for r in data}
    if len(dates) != 1 or not next(iter(dates)):
        ap.error('Mixed or empty snapshot dates')
    by_code = {}
    for r in data:
        code = str(r['ticker']).strip().zfill(6)
        if code in by_code:
            ap.error(f'Duplicate market ticker: {code}')
        by_code[code] = r
    accepted, rejected = [], []
    for line in SEEDS.splitlines():
        sector, subtheme, ticker, name = line.split('|')
        market = by_code.get(ticker)
        if market is None:
            rejected.append({'ticker':ticker,'expected_name':name,'sector':sector,'reason':'NOT_IN_MARKET_SNAPSHOT'})
        elif norm_name(market['name']) != norm_name(name):
            rejected.append({'ticker':ticker,'expected_name':name,'actual_name':market['name'],'sector':sector,'reason':'NAME_MISMATCH'})
        else:
            accepted.append({'ticker':ticker,'name':market['name'],'market':market.get('market',''),
                             'snapshot_date':market['snapshot_date'],'investment_sector':sector,
                             'subtheme':subtheme,'mapping_basis':'MANUAL_SEED_RESEARCH_ONLY',
                             'mapping_verified':'false'})
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    def save_csv(name, rows, fields):
        with (out / name).open('w', encoding='utf-8-sig', newline='') as f:
            w=csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            w.writeheader();w.writerows(rows)
    save_csv('v67_investment_sector_members.csv', accepted,
             ['ticker','name','market','snapshot_date','investment_sector','subtheme','mapping_basis','mapping_verified'])
    sector_count = Counter(r['investment_sector'] for r in accepted)
    unique_by_sector = defaultdict(set)
    for r in accepted:
        unique_by_sector[r['investment_sector']].add(r['ticker'])
    summary = [{'investment_sector':s,'mapped_unique_tickers':len(v),'coverage_status':'SEED_ONLY_NOT_COMPLETE'}
               for s,v in sorted(unique_by_sector.items())]
    save_csv('v67_investment_sector_coverage.csv', summary,
             ['investment_sector','mapped_unique_tickers','coverage_status'])
    save_csv('v67_investment_sector_rejections.csv', rejected,
             ['ticker','expected_name','actual_name','sector','reason'])
    unique_codes = {r['ticker'] for r in accepted}
    audit = {
        'status':'RESEARCH_SEED_ONLY_NOT_TRADE_READY',
        'snapshot_date':next(iter(dates)),
        'market_rows':len(data),
        'mapping_rows':len(accepted),
        'unique_mapped_tickers':len(unique_codes),
        'unmapped_market_tickers':len(by_code)-len(unique_codes),
        'investment_sectors':len(sector_count),
        'overlapping_tickers':dict(sorted((t,n) for t,n in Counter(r['ticker'] for r in accepted).items() if n>1)),
        'rejected_mapping_rows':len(rejected),
        'sector_counts':dict(sorted(sector_count.items())),
        'limitations':['Curated seed list, not a complete market-wide sector membership map.',
                       'Company membership is a research hypothesis; not independently verified or point-in-time historical.',
                       'Multi-sector memberships intentionally allowed; never sum cross-sector turnover as total market flow.',
                       'No 5/20-day sector relative strength, institutional flow, TOP3, or entry/stop signal.',
                       'KIND industry labels remain separate from investment sectors.'],
    }
    (out/'v67_investment_sector_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:audit[k] for k in ['status','snapshot_date','market_rows','mapping_rows','unique_mapped_tickers','investment_sectors','rejected_mapping_rows']},ensure_ascii=False))

if __name__ == '__main__':
    main()
