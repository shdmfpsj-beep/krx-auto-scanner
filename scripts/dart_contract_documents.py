#!/usr/bin/env python3
"""OpenDART direct issuer contract evidence: current-day only, no lookahead.

Direct firm filings are NOT confirmed positive catalysts. Search official
filing lists, verify receipt and ticker->corp_code, download a bounded official
document ZIP, and surface contract field *candidates* for human/cross-source
validation. NO auto BUY, score upgrade, contract value or earnings projection.
"""
import argparse,io,json,os,re,signal,threading,zipfile,urllib.parse,urllib.request
from datetime import date,datetime,timedelta
from pathlib import Path
from xml.etree import ElementTree
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from dart_financial_screen import corp_codes,api_json,iso_day
from dart_contract_terms import extract as parse_contract_terms

VERSION="dart_contract_source_v1"
API="https://opendart.fss.or.kr/api/document.xml"
KEYWORDS=("단일판매","공급계약","수주","계약체결")
RECEIPT=re.compile(r"[0-9]{14}\Z")
TICKER=re.compile(r"[0-9]{6}\Z")
AMOUNT=re.compile(r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\s*(?:원|백만원|천원|억원)\Z")
TARGET_LABELS=("계약금액","계약기간","계약상대","최근매출액","매출액대비","매출액 대비")
MAX_ZIP_BYTES=3_000_000
MAX_UNCOMPRESSED=6_000_000
MAX_SGML_FRAGMENT=250_000
MAX_PARSE_SECONDS=8

def contract_looking(name):
    title=str(name or "").replace(" ","")
    return any(term in title for term in KEYWORDS)

def discovery_stocks(report,max_stocks=5):
    sectors={str(x.get("sector_id")) for x in report.get("sector_top3",[])}
    found=[]
    for row in report.get("stock_research_top5",[])[:max_stocks]:
        t=str(row.get("ticker") or "")
        if (TICKER.fullmatch(t) and row.get("sector_id") in sectors and
            not any(bad in (str(row.get("name",""))+" "+str(
                row.get("sector_id",""))).upper()
                        for bad in ("PHARMA","BIOTECH","바이오","제약"))):
            found.append((t,str(row.get("name") or t)))
    return found

def dated_filings(response,corp,ticker,asof,max_per_ticker=2):
    if response.get("status") not in ("000","013"):
        return [],"DART_LIST_API_STATUS_"+str(response.get("status"))
    if response.get("status")=="013":
        return [],"NO_DART_FILINGS_IN_WINDOW"
    out=[]
    for r in response.get("list",[]):
        t=str(r.get("stock_code") or "")
        cc=str(r.get("corp_code") or "")
        receipt=str(r.get("rcept_no") or "")
        when=iso_day(r.get("rcept_dt"))
        title=str(r.get("report_nm") or "")
        if (t!=ticker or cc!=corp or not RECEIPT.fullmatch(receipt) or
            not when or when>=asof or (asof-when).days>7 or
            not contract_looking(title)):
            continue
        # Corrections must be reviewed with original & final contract; do not
        # silently use an old amended amount as if current.
        risk=("CORRECTION_OR_WITHDRAWAL" if any(k in title
              for k in ("정정","철회","해지","취소")) else "NO_CORRECTION_TITLE_FLAG")
        out.append(dict(ticker=t,receipt_no=receipt,date=str(when),
            title=title[:120],correction_risk=risk,
            url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo="+receipt))
    uniq={r["receipt_no"]:r for r in out}
    results=sorted(uniq.values(),key=lambda x:(x["date"],x["receipt_no"]),reverse=True)
    return results[:max_per_ticker],("RECEIPT_CANDIDATES" if results else
                                     "NO_DIRECT_CONTRACT_TITLE_IN_WINDOW")

def latest_preliminary_earnings(response,corp,ticker,asof):
    """As-of source receipt for quicker preliminary profits, never Q3 numbers.

    Only a matching official issuer and prior-day disclosure can be used
    without intraday timestamp precision. Earnings announcement content
    must be parsed separately before its financial metrics enter scoring.
    """
    if response.get("status")!="000":return []
    found=[]
    for r in response.get("list",[]):
        title="".join(str(r.get("report_nm") or "").split())
        day=iso_day(r.get("rcept_dt"))
        receipt=str(r.get("rcept_no") or "")
        if (r.get("stock_code")!=ticker or r.get("corp_code")!=corp or
            not RECEIPT.fullmatch(receipt) or not day or day>=asof or
            (asof-day).days>7):
            continue
        # Financial fair disclosure, NOT meeting invitation, forecast, or
        # investor-relations calendar.
        if not ("영업" in title and "잠정" in title and "실적" in title):
            continue
        found.append(dict(date=str(day),title=title[:110],
            receipt_no=receipt,ticker=ticker,
            url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo="+receipt,
            financial_figures_verified=False,
            source="OFFICIAL_PRELIMINARY_EARNINGS_DISCLOSURE_TITLE_ONLY",
            correction_flag=any(k in title for k in ("정정","취소"))))
    found.sort(key=lambda x:(x["date"],x["receipt_no"]),reverse=True)
    return found[:2]

def table_candidate_cells(rows,interpretation):
    fields=[]
    for cells in rows:
        texts=[" ".join(str(x or "").split())[:160] for x in cells]
        for idx,val in enumerate(texts[:-1]):
            label=val.replace(" ","")
            if not any(k.replace(" ","") in label for k in TARGET_LABELS):
                continue
            neighbor=texts[idx+1]
            if not neighbor or len(neighbor)>150:continue
            fields.append(dict(label=val[:65],neighboring_text=neighbor[:125],
                interpretation=interpretation))
    return fields

class LegacyTables(HTMLParser):
    """DART original ZIP often contains SGML/HTML tables, not strict XML."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows=[]
        self.row=None
        self.cell=None
    def finish_cell(self):
        if self.cell is not None and self.row is not None:
            self.row.append("".join(self.cell))
            self.cell=None
    def finish_row(self):
        self.finish_cell()
        if self.row is not None and len(self.row)>=2:
            self.rows.append(self.row[:30])
        self.row=None
    def handle_starttag(self,tag,attrs):
        if tag=="tr":
            self.finish_row()
            self.row=[]
        elif tag in ("td","th") and self.row is not None:
            self.finish_cell()
            self.cell=[]
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ("td","th"):self.finish_cell()
        elif tag in ("tr","table"):self.finish_row()

def text_decode(raw):
    head=raw[:500].decode("ascii","ignore")
    found=re.search(r'(?:encoding|charset)\s*=\s*["\x27]?([A-Za-z0-9_-]+)',head,re.I)
    options=([found.group(1)] if found else [])+["utf-8-sig","cp949","euc-kr"]
    for enc in dict.fromkeys(options):
        try:return raw.decode(enc)
        except (UnicodeError,LookupError,ValueError):continue
    return raw.decode("utf-8","replace")

def zip_document(raw):
    """Bounded strict XML or SGML table inspection from official ZIP only."""
    if len(raw)>MAX_ZIP_BYTES or not zipfile.is_zipfile(io.BytesIO(raw)):
        return {"status":"INVALID_OR_OVERSIZE_DART_DOCUMENT"}
    chunks=[]
    fallback=False
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        items=[x for x in z.infolist() if x.filename.lower().endswith((".xml",".xhtml"))]
        if len(items)>15 or not items:
            return {"status":"DART_DOCUMENT_XML_MISSING_OR_EXCESSIVE"}
        if sum(x.file_size for x in items)>MAX_UNCOMPRESSED or any(
            x.flag_bits & 0x1 or x.file_size>MAX_UNCOMPRESSED for x in items):
            return {"status":"DART_DOCUMENT_TOO_LARGE"}
        for item in items:
            data=z.read(item)
            try:
                root=ElementTree.fromstring(data)
                rows=[]
                for tr in root.iter():
                    if not isinstance(tr.tag,str) or tr.tag.split("}")[-1].upper()!="TR":
                        continue
                    cells=[node for node in tr if isinstance(node.tag,str) and
                        node.tag.split("}")[-1].upper() in ("TD","TH")]
                    if len(cells)>=2:
                        rows.append(["".join(c.itertext()) for c in cells[:30]])
                chunks.extend(table_candidate_cells(
                    rows,"XML_ADJACENT_CELL_UNVERIFIED"))
            except (ElementTree.ParseError,UnicodeError,ValueError):
                html=text_decode(data)
                if not re.search(r"<\s*table\b",html,re.I) or not re.search(
                        r"<\s*tr\b",html,re.I):
                    return {"status":"DART_DOCUMENT_XML_NOT_PARSEABLE"}
                partial=False
                # Historic SGML often has huge malformed tables. Parse only
                # relevant bounded TABLE windows, not 6MB of arbitrary HTML.
                if len(html)>MAX_SGML_FRAGMENT:
                    snippets=[]
                    lower=html.lower()
                    indices=[lower.find(term.lower()) for term in TARGET_LABELS]
                    for index in indices:
                        if index<0:continue
                        start=lower.rfind("<table",max(0,index-90000),index)
                        if start<0:continue
                        end=lower.find("</table",index,index+120000)
                        end=(end+8 if end>=0 else min(len(html),index+25000))
                        if 0<end-start<=MAX_SGML_FRAGMENT:
                            snippets.append(html[start:end])
                    if not snippets:
                        return {"status":"DART_DOCUMENT_SGML_LARGE_NO_SAFE_TARGET_TABLE"}
                    html="\n".join(snippets)[:MAX_SGML_FRAGMENT]
                    partial=True
                parser=LegacyTables()
                try:parser.feed(html)
                except (ValueError,AssertionError):
                    return {"status":"DART_DOCUMENT_SGML_TABLES_NOT_PARSEABLE"}
                if not parser.rows:
                    return {"status":"DART_DOCUMENT_SGML_TABLES_NOT_PARSEABLE"}
                fallback=True
                chunks.extend(table_candidate_cells(
                    parser.rows,"SGML_ADJACENT_CELL_UNVERIFIED"))
    unique={}
    for x in chunks:unique[(x["label"],x["neighboring_text"])]=x
    return dict(status=("DART_DOCUMENT_SGML_TABLES_PARSED" if fallback
                        else "DART_DOCUMENT_XML_TABLES_PARSED"),
        extracted_candidate_cells=list(unique.values())[:15],
        amount_verified=False,contract_effect_verified=False)

def download_original(receipt,key,fetch=None,parser=None):
    if not RECEIPT.fullmatch(str(receipt)):return {"status":"INVALID_RECEIPT"}
    if parser is None:parser=zip_document
    url=API+"?"+urllib.parse.urlencode({"crtfc_key":key,"rcept_no":receipt})
    if fetch is None:
        def fetch(u):
            req=urllib.request.Request(u,headers={"User-Agent":"KRX-research-readonly/1.0"})
            with urllib.request.urlopen(req,timeout=15) as response:
                return response.read(MAX_ZIP_BYTES+1)
    # On Linux GitHub runner, enforce finite CPU parsing time for untrusted
    # filings. Historical SGML may have pathological nesting or giant tables.
    def deadline(signum,frame):
        raise TimeoutError("DART_ORIGINAL_PARSE_TIME_LIMIT")
    armed=(hasattr(signal,"SIGALRM") and
           threading.current_thread() is threading.main_thread())
    previous=None
    try:
        raw=fetch(url)
        if armed:
            previous=signal.getsignal(signal.SIGALRM)
            signal.signal(signal.SIGALRM,deadline)
            signal.setitimer(signal.ITIMER_REAL,MAX_PARSE_SECONDS)
        return parser(raw)
    except TimeoutError:
        return {"status":"DART_ORIGINAL_PARSE_TIMEOUT_REVIEW_REQUIRED"}
    except Exception as ex:
        # Error class only; exceptions may include URLs with secret parameters!
        return {"status":"DOCUMENT_FETCH_FAILED_"+type(ex).__name__}
    finally:
        if armed and previous is not None:
            signal.setitimer(signal.ITIMER_REAL,0)
            signal.signal(signal.SIGALRM,previous)

def collect(report,key,today=None,list_api=api_json,corps=corp_codes,
            document_reader=download_original,max_downloads=4,
            preliminary_reader=None):
    now=today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    asof=iso_day(report.get("asof"))
    out=dict(schema=VERSION,asof=str(asof) if asof else None,
        status="UNVERIFIED",issuer_samples=[],document_attempts=0,
        confirmed_positive_company_contracts=0,
        contract_amounts_confirmed=0,
        final_85_score_verified=False,trade_approved=False,
        orders_enabled=False,decision="CASH")
    # Absolutely no historical replay against today's mutable endpoint.
    if not asof or now!=asof or not report.get("daily_money_rank_applied"):
        out["status"]="HISTORICAL_OR_INCOMPLETE_KRX_NO_RETROACTIVE_DART"
        return out
    stocks=discovery_stocks(report)
    if not stocks:
        out["status"]="NO_TOP3_STOCK_CANDIDATES"
        return out
    if not key or not re.fullmatch(r"[A-Za-z0-9]{40}",key):
        out["status"]="DART_SECRET_NOT_AVAILABLE"
        return out
    try:lookup=corps(key)
    except Exception as err:
        out["status"]="CORPCODE_LOOKUP_FAILED_"+type(err).__name__
        return out
    # Imported here because the strict original parser shares the bounded
    # legacy DART table code from this module.
    from dart_preliminary_financials import decode_document,assess
    if preliminary_reader is None:
        if document_reader is download_original:
            preliminary_reader=lambda receipt,key:download_original(
                receipt,key,parser=decode_document)
        else:
            preliminary_reader=document_reader
    for ticker,name in stocks:
        item=dict(ticker=ticker,name=name,filings=[],latest_preliminary_earnings=[],
                  source="OPEN_DART_OFFICIAL_LIST_AND_DOCUMENT",
                  trade_approval="NO")
        cc=lookup.get(ticker)
        if not cc:
            item["status"]="MISSING_CORP_CODE"
            out["issuer_samples"].append(item)
            continue
        try:
            result=list_api("list.json",dict(corp_code=cc,
                bgn_de=(asof-timedelta(days=7)).strftime("%Y%m%d"),
                end_de=(asof-timedelta(days=1)).strftime("%Y%m%d"),
                page_count=100),key)
            recent,state=dated_filings(result,cc,ticker,asof)
            item["latest_preliminary_earnings"]=latest_preliminary_earnings(
                result,cc,ticker,asof)
            item["newer_preliminary_results_require_review"]=bool(
                item["latest_preliminary_earnings"])
            # Latest quarterly evidence is more time-sensitive than the
            # contract title. Allocate the first free original download to
            # provisional earnings when such a notice exists.
            for notice in item["latest_preliminary_earnings"][:1]:
                notice["original_financial_status"]="NOT_DOWNLOADED_LIMIT_OR_BUDGET"
                notice["financial_figures_verified"]=False
                if out["document_attempts"]<max_downloads:
                    out["document_attempts"]+=1
                    raw=preliminary_reader(notice["receipt_no"],key)
                    study=assess(raw,notice,asof)
                    notice["original_financial_status"]=study["status"]
                    notice["original_financial_analysis"]=study
                    notice["financial_figures_verified"]=bool(
                        study["preliminary_figures_source_verified"])
            item["status"]=state
            for filing in recent:
                filing["contract_amount_verified"]=False
                filing["positive_catalyst_verified"]=False
                filing["filing_contents_status"]="NOT_DOWNLOADED_LIMIT_OR_BUDGET"
                if out["document_attempts"]<max_downloads:
                    out["document_attempts"]+=1
                    content=document_reader(filing["receipt_no"],key)
                    filing["filing_contents_status"]=content.get("status")
                    filing["original_text_fields"]=content.get(
                        "extracted_candidate_cells",[])
                    filing["structured_contract_terms"]=parse_contract_terms(
                        filing["original_text_fields"],
                        correction_risk=filing["correction_risk"])
                    filing["document_labeled_amount_research_only"]=bool(
                        filing["structured_contract_terms"].get("amount_krw"))
                item["filings"].append(filing)
        except Exception as ex:
            item["status"]="ISSUER_SEARCH_FAILED_"+type(ex).__name__
        out["issuer_samples"].append(item)
    out["status"]="DIRECT_DART_EVIDENCE_COLLECTED_UNVERIFIED_IMPACT"
    out["preliminary_financial_source_verified_count"]=sum(
        bool(x.get("financial_figures_verified"))
        for issuer in out["issuer_samples"]
        for x in issuer.get("latest_preliminary_earnings",[]))
    out["preliminary_earnings_weakening_count"]=sum(
        x.get("original_financial_analysis",{}).get("earnings_quality")==
              "RECENT_PRELIMINARY_WEAKENING"
        for issuer in out["issuer_samples"]
        for x in issuer.get("latest_preliminary_earnings",[]))
    return out

def render(r):
    lines=["","## 회사 직접 계약공시 원문 조회 (호재 여부 별도)","",
        "**신규매수 CASH · 계약 제목·원문 표 수치만으로 긍정적 수혜나 수익을 단정하지 않습니다.**","",
        "| 종목 | 최근 직접계약 공시 | 원문 추출 계약액(억) | 검증 상태 |",
        "|---|---|---:|---|"]
    for issuer in r.get("issuer_samples",[]):
        filings=issuer["filings"]
        if not filings:
            lines.append("| "+issuer["name"]+" | 없음/미확인 | — | "+issuer["status"]+" |")
        for f in filings:
            terms=f.get("structured_contract_terms") or {}
            amount=terms.get("amount_krw")
            # A typed amount is a document quote, not a verified active
            # contract. In particular amendments cannot count as new sales.
            display=("%.2f"%(amount/100_000_000) if isinstance(amount,int)
                     else "—")
            status=terms.get("status") or f["filing_contents_status"]
            if f.get("correction_risk")!="NO_CORRECTION_TITLE_FLAG":
                status="정정/해지 검토 필수: "+status
            lines.append("| "+issuer["name"]+" | ["+f["date"]+" "+
                f["title"].replace("|","/").replace("[","(").replace("]",")")[:40]+"]("+
                f["url"]+") | "+display+" | "+status+" |")
    if not r.get("issuer_samples"):
        lines.append("| 회사 직접공시 미수집 | — | "+r["status"]+" | 아니요 |")
    lines+=["","### 최신 잠정실적 실제 숫자 검증 (비감사 자료)",""]
    earnings_count=0
    for issuer in r.get("issuer_samples",[]):
        for x in issuer.get("latest_preliminary_earnings",[]):
            earnings_count+=1
            study=x.get("original_financial_analysis",{})
            if x.get("financial_figures_verified"):
                rev=study.get("revenue_yoy_pct")
                op=study.get("operating_profit_yoy_pct")
                info=("매출 YoY "+str(rev)+"%, 영업이익 YoY "+
                       (str(op)+"%" if op is not None else "흑자전환/비교 불가")+
                       " / "+str(study.get("earnings_quality")))
            else:
                info="수치 미검증: "+str(x.get("original_financial_status",
                                            "SOURCE_NOT_EXTRACTED"))
            lines.append("- "+issuer["name"]+": ["+x["date"]+" "+
                x["title"]+"]("+x["url"]+") — "+info)
    if not earnings_count:
        lines.append("- 최근 7일 적격 잠정실적 공시 없음/미수집")
    lines+=["","*접수일만 확인한 공시는 기준일 당일 자료를 제외합니다. 정정·해지 공시는"
        " 원본 및 추가 변경사항을 확인하기 전까지 긍정적 수주로 분류하지 않습니다.",
        "*계약금액(억)은 공식 원문 표에서 읽힌 단위 있는 후보값일 뿐, 현재 유효한 계약인지"
        " 또는 실제 납품·이익이 생기는지는 검증되지 않았습니다.",
        "*계약액/최근매출액/공시 비율의 산술 일치 여부는 단일 공시 내부 검산이며"
        " 다른 정보원으로 독립 확인한 사실이 아닙니다.",
        "*원문 단위가 불분명하거나 공시 간 정정·해지 내용이 있으면"
        " 실질 호재 점수에 포함하지 않습니다.",
        "*잠정실적은 비감사 분기 성적표입니다. 검증된 같은 분기 실적과"
        " 연간·반기 누적 실적을 서로 섞지 않으며 최종 BUY 승인으로 보지 않습니다.",
        "*출처: 금융감독원 OpenDART 공식 list.json 및 document.xml API.",""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("output"))
    a=p.parse_args();a.root.mkdir(parents=True,exist_ok=True)
    source=a.root/"sector_first_with_financials.json"
    if not source.is_file():raise SystemExit("MISSING_DATED_FINANCIAL_STOCK_REPORT")
    report=json.loads(source.read_text(encoding="utf-8"))
    key=(os.environ.get("OPENDART_API_KEY") or
         os.environ.get("OPEN_DART_API_KEY") or os.environ.get("DART_API_KEY"))
    result=collect(report,key)
    (a.root/"direct_dart_contracts.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    (a.root/"direct_dart_contracts_mobile.md").write_text(
        render(result),encoding="utf-8")
    compact=a.root/"sector_first_compact_mobile.md"
    if compact.is_file():
        with compact.open("a",encoding="utf-8") as fd:fd.write("\n"+render(result))
    print(json.dumps({"status":result["status"],"issuers":len(result["issuer_samples"]),
        "documents_checked":result["document_attempts"],
        "confirmed_positive":0,"decision":"CASH"},ensure_ascii=False))

if __name__=="__main__":main()
