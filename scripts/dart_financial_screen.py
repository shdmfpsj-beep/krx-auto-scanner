#!/usr/bin/env python3
"""As-of-gated free OpenDART annual fundamentals for sector research stocks.

The DART API key stays in GitHub Secrets. No same-day retroactive financials:
only run on the current Asia/Seoul calendar date and require a dated, filed
annual report before consulting the annual financial statement endpoint.
Annual thstrm/frmtrm figures from ONE filing avoid mixing restated fiscal years.
No estimated upside probabilities, financial 15/15 scores or BUY authorization.
"""
import argparse,csv,io,json,math,os,re,urllib.parse,urllib.request,zipfile
from datetime import date,datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from xml.etree import ElementTree

API="https://opendart.fss.or.kr/api/"
VERSION="opendart_annual_research_v1"
REVENUE={"ifrs_Revenue","ifrs-full_Revenue",
         "ifrs-full_RevenueFromContractsWithCustomers"}
OPERATING={"dart_OperatingIncomeLoss"}
ASSETS={"ifrs_Assets","ifrs-full_Assets"}
LIABILITIES={"ifrs_Liabilities","ifrs-full_Liabilities"}
EQUITY={"ifrs_Equity","ifrs-full_Equity"}
EXCLUDE=("바이오","제약","PHARMA","BIOTECH","HEALTH")

def iso_day(value):
    try:return date.fromisoformat(str(value)[:10])
    except (TypeError,ValueError):return None

def integer(value):
    if value is None or value in ("","-","－"):return None
    try:
        v=float(str(value).replace(",",""))
        return int(v) if math.isfinite(v) else None
    except (ValueError,TypeError):return None

def api_json(endpoint,params,key,fetch=None):
    """Restrict all remote reads to literal OpenDART official endpoints."""
    if endpoint not in ("list.json","fnlttSinglAcntAll.json"):
        raise ValueError("UNSUPPORTED_DART_ENDPOINT")
    args=urllib.parse.urlencode({"crtfc_key":key,**params})
    request=urllib.request.Request(API+endpoint+"?"+args,
            headers={"User-Agent":"KRX-research-readonly/1.0"})
    if fetch is None:
        def fetch(req):
            with urllib.request.urlopen(req,timeout=12) as r:
                return r.read()
    response=json.loads(fetch(request).decode("utf-8"))
    if not isinstance(response,dict):
        raise ValueError("INVALID_DART_RESPONSE")
    return response

def parse_corps(binary):
    with zipfile.ZipFile(io.BytesIO(binary)) as archive:
        files=[x for x in archive.namelist() if x.lower().endswith(".xml")]
        if len(files)!=1:
            raise ValueError("INVALID_CORPCODE_ZIP")
        root=ElementTree.fromstring(archive.read(files[0]))
    result={}
    for node in root.findall(".//list"):
        stock=(node.findtext("stock_code") or "").strip()
        code=(node.findtext("corp_code") or "").strip()
        if re.fullmatch(r"\d{6}",stock) and re.fullmatch(r"\d{8}",code):
            if stock in result and result[stock]!=code:
                raise ValueError("DUPLICATE_CORP_CODE")
            result[stock]=code
    return result

def corp_codes(key,download=None):
    if download is None:
        def download(url):
            with urllib.request.urlopen(url,timeout=20) as r:
                return r.read()
    url=API+"corpCode.xml?"+urllib.parse.urlencode({"crtfc_key":key})
    return parse_corps(download(url))

def annual_receipt(payload,year,asof):
    if payload.get("status")!="000":return None
    candidates=[]
    pattern=re.compile(r"\("+str(year)+r"\.12\)")
    for filing in payload.get("list",[]):
        title=str(filing.get("report_nm","")).replace(" ","")
        filing_day=iso_day(filing.get("rcept_dt"))
        receipt=str(filing.get("rcept_no",""))
        if ("사업보고서" not in title or not pattern.search(title) or
            not filing_day or filing_day>asof or
            not re.fullmatch(r"\d{14}",receipt)):
            continue
        candidates.append((filing_day,receipt))
    return max(candidates) if candidates else None

def extract_metric(rows,ids,statement,period):
    possibilities=[]
    for r in rows:
        if r.get("sj_div")!=statement or r.get("account_id") not in ids:
            continue
        if r.get("account_detail") not in ("","-"):
            continue
        amount=integer(r.get(period))
        if amount is not None:possibilities.append(amount)
    return possibilities[0] if len(set(possibilities))==1 and possibilities else None

def evaluate_accounts(payload,division):
    if payload.get("status")!="000" or not isinstance(payload.get("list"),list):
        return {"status":"FINANCIAL_API_UNAVAILABLE","division":division}
    rows=[r for r in payload["list"] if r.get("fs_div")==division]
    revenue=extract_metric(rows,REVENUE,"IS","thstrm_amount")
    previous=extract_metric(rows,REVENUE,"IS","frmtrm_amount")
    profit=extract_metric(rows,OPERATING,"IS","thstrm_amount")
    previous_profit=extract_metric(rows,OPERATING,"IS","frmtrm_amount")
    assets=extract_metric(rows,ASSETS,"BS","thstrm_amount")
    liabilities=extract_metric(rows,LIABILITIES,"BS","thstrm_amount")
    equity=extract_metric(rows,EQUITY,"BS","thstrm_amount")
    result=dict(division=division,revenue_krw=revenue,
        previous_revenue_krw=previous,
        operating_profit_krw=profit,
        previous_operating_profit_krw=previous_profit,
        assets_krw=assets,liabilities_krw=liabilities,equity_krw=equity,
        sales_yoy_pct=None,operating_margin_pct=None,
        accounting_identity_gap_pct=None,financial_quality="UNVERIFIED")
    if (revenue is None or previous is None or profit is None or
        previous_profit is None or revenue<=0 or previous<=0 or
        assets is None or liabilities is None or equity is None or
        assets<=0 or equity<=0):
        result["status"]="ANNUAL_METRICS_INCOMPLETE"
        return result
    # Check BS identities to avoid a wrong account extraction or unit mix.
    gap=abs(assets-liabilities-equity)/assets*100
    result["accounting_identity_gap_pct"]=round(gap,2)
    if gap>1.0:
        result["status"]="BALANCE_SHEET_INCONSISTENT"
        return result
    result["sales_yoy_pct"]=round((revenue/previous-1)*100,2)
    result["operating_margin_pct"]=round(profit/revenue*100,2)
    # Sector-adjusted ratios and cash flow still need separate research.
    if profit<=0 or revenue<previous or profit<previous_profit:
        quality="ANNUAL_RISK_OR_SLOWDOWN"
    elif profit>previous_profit and revenue>previous and profit/revenue>=.05:
        quality="ANNUAL_GROWTH_AND_MARGIN_OBSERVED"
    else:
        quality="ANNUAL_POSITIVE_MIXED"
    result["financial_quality"]=quality
    result["status"]="DATED_ANNUAL_RESEARCH_ONLY"
    return result

def read_stocks(path,asof,limit=20):
    if not path.is_file():return []
    with path.open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    found={}
    for r in rows:
        ticker=str(r.get("ticker","")).strip()
        name=str(r.get("name",""))
        sid=str(r.get("sector_id",""))
        if (r.get("asof")!=asof or not re.fullmatch(r"\d{6}",ticker) or
            any(term in (name+" "+sid).upper() for term in EXCLUDE)):
            continue
        found.setdefault(ticker,dict(ticker=ticker,name=name,sector_id=sid,
           research_proxy_index=r.get("research_proxy_index","")))
    return list(found.values())[:limit]

def collect(asof,stocks,key=None,request_json=api_json,get_corps=corp_codes,today=None):
    today=today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    summary=dict(schema=VERSION,asof=str(asof),requested_stocks=len(stocks),
         researched=[],data_source="OPENDART_OFFICIAL_PERIODIC_REPORT",
         historical_replay_forbidden=True,trade_approved=False,decision="CASH",
         final_85_score_verified=False)
    if asof!=today:
        summary["status"]="HISTORICAL_REPLAY_NO_RETROACTIVE_FINANCIALS"
        return summary
    if not stocks:
        summary["status"]="NO_VALID_ASOF_RESEARCH_STOCKS"
        return summary
    if not key:
        summary["status"]="MISSING_DART_KEY"
        return summary
    if not re.fullmatch(r"[A-Za-z0-9]{40}",key):
        summary["status"]="INVALID_DART_KEY_FORMAT"
        return summary
    try:
        lookup=get_corps(key)
    except Exception as e:
        summary["status"]="CORPCODE_DOWNLOAD_FAILED_"+type(e).__name__
        return summary
    # In January-March, the prior fiscal year's annual report may not yet
    # be published. Use the most recent ACTUALLY filed annual report,
    # rather than treating all issuers as having missing fundamentals.
    possible_years=(asof.year-1,asof.year-2)
    for s in stocks:
        item=dict(**s,annual_fiscal_year=None,
                  point_in_time_basis="FILING_RECEIVED_BY_ASOF_22KST")
        company=lookup.get(s["ticker"])
        if not company:
            item["status"]="NO_LISTED_CORP_CODE"
            summary["researched"].append(item)
            continue
        try:
            filings=request_json("list.json",{"corp_code":company,
                "bgn_de":f"{asof.year-2}0101",
                "end_de":asof.strftime("%Y%m%d"),
                "page_count":100,"pblntf_ty":"A"},key)
            matched=[(year,annual_receipt(filings,year,asof))
                     for year in possible_years]
            matched=[(year,receipt) for year,receipt in matched if receipt]
            if not matched:
                item["status"]="NO_ELIGIBLE_DATED_ANNUAL_FILING"
                summary["researched"].append(item)
                continue
            year,receipt=max(matched,key=lambda x:x[0])
            day_received,number=receipt
            item["annual_fiscal_year"]=year
            item["receipt_date"]=str(day_received)
            item["receipt_no"]=number
            item["receipt_url"]="https://dart.fss.or.kr/dsaf001/main.do?rcpNo="+number
            for div in ("CFS","OFS"):
                response=request_json("fnlttSinglAcntAll.json",
                    {"corp_code":company,"bsns_year":str(year),
                     "reprt_code":"11011","fs_div":div},key)
                financial=evaluate_accounts(response,div)
                if financial["status"]=="DATED_ANNUAL_RESEARCH_ONLY":
                    break
            item.update(financial)
            item["financial_screen_pass"]=financial.get(
                "financial_quality")=="ANNUAL_GROWTH_AND_MARGIN_OBSERVED"
            # Banks, insurers and brokerages have industry-specific
            # balance sheet definitions and must not pass a generic 5% margin
            # or liabilities test designed for non-financial companies.
            if s["sector_id"] in ("BANK","INSURANCE","SECURITIES"):
                item["financial_screen_pass"]=False
                item["financial_quality"]="FINANCIAL_SECTOR_SPECIAL_MODEL_REQUIRED"
            item["trade_approval"]="NO"
        except Exception as e:
            item["status"]="DART_REQUEST_FAILED_"+type(e).__name__
            item["trade_approval"]="NO"
        summary["researched"].append(item)
    summary["status"]="PARTIAL_FINANCIAL_RESEARCH" if len(
        summary["researched"])!=len(stocks) or any(
        r.get("status")!="DATED_ANNUAL_RESEARCH_ONLY" for r in summary["researched"]) else "ANNUAL_RESEARCH_READ"
    summary["screen_pass_count"]=sum(
        bool(x.get("financial_screen_pass")) for x in summary["researched"])
    return summary

def render(result):
    lines=["# 국내 섹터 TOP3 종목의 OpenDART 재무 분석","",
      "**재무 연구와 매수 승인은 별개이며 최종 신규매수: CASH**","",
      "OpenDART 분석 상태: "+result.get("status","UNKNOWN"),"",
      "| 종목 | 연결/별도 | 매출 성장률 | 영업이익률 | 재무 연구 판정 |",
      "|---|---|---:|---:|---|"]
    for x in result.get("researched",[]):
        lines.append("| "+x.get("name",x["ticker"])+" | "+
          str(x.get("division") or "—")+" | "+
          str(x.get("sales_yoy_pct") if x.get("sales_yoy_pct") is not None else "—")+
          " | "+str(x.get("operating_margin_pct") if x.get("operating_margin_pct") is not None else "—")+
          " | "+str(x.get("financial_quality") or x.get("status","UNKNOWN"))+" |")
    if not result.get("researched"):lines.append("| 미확인 | — | — | — | 실적점수 부여 금지 |")
    lines+=["","*당해연도 분기 실적, 업종별 재무비율, 향후 컨센서스 및 뉴스의 실제 계약효과는 여기서 검증하지 않습니다.",
      "*연결재무제표를 우선하되 없는 경우 별도재무제표를 명시하며 두 기준을 무분별하게 섞지 않습니다.",
      "*공시 제출일 이후 자료만 취급하며 과거 리플레이에 현재 재무API 내용을 소급 투입하지 않습니다.",
      "*매출 증가만으로 최종 85점이나 5거래일 상승확률을 만들어내지 않습니다.",""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,default=Path("output/sector_stock_research_ranking.csv"))
    p.add_argument("--out",type=Path,default=Path("output"))
    p.add_argument("--asof",type=str,default=datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat())
    args=p.parse_args()
    today=datetime.now(ZoneInfo("Asia/Seoul")).date()
    asof=iso_day(args.asof)
    if not asof:raise SystemExit("INVALID_ASOF")
    key=(os.environ.get("DART_API_KEY") or os.environ.get("OPENDART_API_KEY")
         or os.environ.get("OPEN_DART_API_KEY"))
    result=collect(asof,read_stocks(args.input,args.asof),key,today=today)
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/"financial_research.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    (args.out/"financial_research_mobile.md").write_text(
        render(result),encoding="utf-8")
    print(json.dumps({"status":result["status"],"count":len(result["researched"]),
       "financial_screen_pass_count":result.get("screen_pass_count",0),
       "trade_approved":False},ensure_ascii=False))

if __name__=="__main__":main()
