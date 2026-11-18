"""C3 quality context: point-in-time OpenDART, no speculative news sentiment.
Enrich only technically qualified candidates. Missing data is neutral/UNVERIFIED.
Financial and disclosure observations cannot rescue invalid entry geometry.
"""
import datetime,io,json,os,re,urllib.parse,urllib.request,zipfile
from xml.etree import ElementTree
try:
    from scripts.dart_interim_periods import identify_interim_filing,evaluate_interim
except ModuleNotFoundError:
    from dart_interim_periods import identify_interim_filing,evaluate_interim

API="https://opendart.fss.or.kr/api/"
FIN_IDS={"equity":{"ifrs-full_Equity","ifrs_Equity"},
         "assets":{"ifrs-full_Assets","ifrs_Assets"},
         "liabilities":{"ifrs-full_Liabilities","ifrs_Liabilities"},
         "sales":{"ifrs-full_Revenue","ifrs_Revenue","ifrs-full_RevenueFromContractsWithCustomers"},
         "profit":{"dart_OperatingIncomeLoss"}}
RISK_TERMS=("감사의견거절","의견거절","상장폐지","횡령","배임","회생절차","거래정지")
EXCLUDE_TERMS=("제약","바이오","PHARMA","BIOTECH")

def get_json(path,params,key):
    query=urllib.parse.urlencode({"crtfc_key":key,**params})
    with urllib.request.urlopen(API+path+"?"+query,timeout=12) as r:
        obj=json.load(r)
    if not isinstance(obj,dict):raise ValueError("INVALID_DART_JSON")
    return obj

def corps(key):
    with urllib.request.urlopen(API+"corpCode.xml?"+urllib.parse.urlencode({"crtfc_key":key}),timeout=20) as r:
        raw=r.read(12_000_001)
    if len(raw)>12_000_000:raise ValueError("CORP_ZIP_TOO_LARGE")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=[n for n in z.namelist() if n.lower().endswith(".xml")]
        if len(names)!=1:raise ValueError("INVALID_CORP_ZIP")
        root=ElementTree.fromstring(z.read(names[0]))
    return {str(n.findtext("stock_code") or "").strip():str(n.findtext("corp_code") or "").strip()
            for n in root.findall(".//list") if re.fullmatch(r"\d{6}",str(n.findtext("stock_code") or "").strip())
            and re.fullmatch(r"\d{8}",str(n.findtext("corp_code") or "").strip())}

def amount(row,field):
    s=str(row.get(field) or "").replace(",","").strip()
    return int(s) if re.fullmatch(r"-?\d+",s) else None

def metric(rows,kind,field,section):
    values=[amount(r,field) for r in rows if r.get("account_id") in FIN_IDS[kind]
            and r.get("sj_div") in section and str(r.get("account_detail") or "").strip() in ("","-")]
    values=[v for v in values if v is not None]
    return values[0] if values and len(set(values))==1 else None

def annual_asof(corp,key,asof):
    # Only annual reports actually filed by as-of; never future/retroactive financials.
    # Bounded complete pagination: no financial or disclosure claim from a partial list.
    params={"corp_code":corp,"bgn_de":str(asof.year-2)+"0101",
        "end_de":asof.strftime("%Y%m%d"),"page_count":100}
    filings=[]
    total_pages=None
    for page in range(1,21):
        response=get_json("list.json",{**params,"page_no":page},key)
        if response.get("status")!="000":
            return None,[],"FILINGS_UNAVAILABLE"
        try:
            count=int(response.get("total_page",1))
        except (ValueError,TypeError):
            return None,[],"FILINGS_PAGE_METADATA_INVALID"
        if count<1 or count>20 or (total_pages is not None and count!=total_pages):
            return None,[],"FILINGS_PAGINATION_INCOMPLETE"
        total_pages=count
        rows=response.get("list")
        if not isinstance(rows,list):
            return None,[],"FILINGS_PAGE_INVALID"
        filings.extend(rows)
        if page>=total_pages:break
    available=[r for r in filings if str(r.get("rcept_dt",""))<=asof.strftime("%Y%m%d")]
    years=[]
    for r in available:
        name=str(r.get("report_nm","")).replace(" ","")
        match=re.search(r"사업보고서\((20\d{2})\.12\)",name)
        if match:years.append((int(match.group(1)),r))
    if not years:return None,available,"NO_FILED_ANNUAL"
    year,filing=max(years,key=lambda x:(x[0],x[1].get("rcept_dt",""),x[1].get("rcept_no","")))
    for div in ("CFS","OFS"):
        payload=get_json("fnlttSinglAcntAll.json",{"corp_code":corp,"bsns_year":str(year),
            "reprt_code":"11011","fs_div":div},key)
        if payload.get("status")!="000":continue
        rows=[r for r in payload.get("list",[]) if r.get("fs_div") in (None,"",div)]
        values={k:metric(rows,k,"thstrm_amount",("BS",) if k in ("equity","assets","liabilities") else ("IS","CIS"))
                for k in FIN_IDS}
        values.update({k+"_prev":metric(rows,k,"frmtrm_amount",("IS","CIS"))
                       for k in ("sales","profit")})
        if all(values.get(k) is not None for k in ("equity","assets","liabilities","sales","profit","sales_prev","profit_prev")):
            values.update({"fiscal_year":year,"division":div,"filing_date":filing.get("rcept_dt"),
                "filing_receipt":filing.get("rcept_no")})
            return values,available,"VERIFIED_ANNUAL"
    return None,available,"ANNUAL_INCOMPLETE"

def interim_asof(corp,key,asof,filings,annual_year):
    """Newest filed fiscal interim, verified cumulative YTD only."""
    candidates=[]
    for row in filings:
        day_text=str(row.get("rcept_dt",""))
        receipt=str(row.get("rcept_no",""))
        try:day=datetime.datetime.strptime(day_text,"%Y%m%d").date()
        except ValueError:continue
        if day>asof:continue
        filing=identify_interim_filing((day,receipt,row.get("report_nm","")),asof)
        if not filing:continue
        end=datetime.date.fromisoformat(filing["period_end"])
        if day<=end or filing["fiscal_year"]<=annual_year:continue
        candidates.append((end,day,receipt,filing))
    if not candidates:return None,"NO_NEWER_INTERIM_FILING"
    filing=max(candidates,key=lambda x:(x[0],x[1],x[2]))[3]
    for division in ("CFS","OFS"):
        payload=get_json("fnlttSinglAcntAll.json",{
            "corp_code":corp,"bsns_year":str(filing["fiscal_year"]),
            "reprt_code":filing["report_code"],"fs_div":division},key)
        result=evaluate_interim(payload,division,filing)
        if result["status"]=="DATED_INTERIM_YTD_RESEARCH_ONLY":
            return result,"VERIFIED_INTERIM_YTD"
    return None,"INTERIM_CUMULATIVE_UNVERIFIED"

# Sector evidence must be independently sourced; never infer industry from company name.
SECTOR_EXCLUDED=("제약","의약품","바이오","생명공학","PHARMACEUTICAL","BIOTECH")
SECTOR_DEFENSIVE=("전기·가스","전기가스","유틸리티")
SECTOR_CYCLICAL=("건설","반도체","자동차","철강","화학","조선")

def sector_evidence(candidate,asof):
    """Only explicit dated KRX classification, never a guessed sector."""
    sector=candidate.get("krx_sector_name")
    source=candidate.get("krx_sector_source")
    dated=candidate.get("krx_sector_asof")
    if not isinstance(sector,str) or not sector.strip():
        return {"status":"UNVERIFIED","score":None,"exclude":False}
    if source!="KRX_OFFICIAL" or not isinstance(dated,str) or not re.fullmatch(r"\\d{8}",dated) or dated>asof:
        return {"status":"UNVERIFIED","score":None,"exclude":False}
    normalized=sector.upper().replace(" ","")
    if any(t.upper().replace(" ","") in normalized for t in SECTOR_EXCLUDED):
        return {"status":"EXCLUDED_VERIFIED_SECTOR","score":None,"exclude":True,"name":sector}
    # No sector outperformance data is provided; score stays neutral.
    kind=("CYCLICAL" if any(t in normalized for t in SECTOR_CYCLICAL)
          else "DEFENSIVE" if any(t in normalized for t in SECTOR_DEFENSIVE)
          else "OTHER")
    return {"status":"VERIFIED_CLASSIFICATION_"+kind,"score":5.0,
            "exclude":False,"name":sector}

def enrich(pool,asof,key,max_requests=12):
    """Return a NEW ranked list and audit. Keep original technical score intact."""
    output=[dict(x) for x in pool]
    audit={"schema":"C3_QUALITY_CONTEXT_V1","asof":asof,"mode":"TECHNICAL_FIRST",
           "weights":{"technical":65,"financial_and_earnings":20,"industry":10,"disclosures":5},
           "industry_policy":"DATED_KRX_CLASSIFICATION_ONLY_NEUTRAL_WITHOUT_SECTOR_PERFORMANCE",
           "news_policy":"OFFICIAL_DART_DISCLOSURES_ONLY",
           "checked":[]}
    if not key or not re.fullmatch(r"[A-Za-z0-9]{40}",key):
        audit["status"]="DART_KEY_MISSING_OR_INVALID"
        return output,audit
    today=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date()
    try:target=datetime.datetime.strptime(asof,"%Y%m%d").date()
    except ValueError:
        audit["status"]="INVALID_ASOF"
        return output,audit
    # A prior completed KRX session is normal for morning/manual previews.
    # Never use filings later than the price as-of, or backfill distant history.
    if target>today or (today-target).days>5:
        audit["status"]="ASOF_OUTSIDE_RECENT_WINDOW"
        return output,audit
    try:lookup=corps(key)
    except Exception as ex:
        audit["status"]="CORP_LOOKUP_FAILED_"+type(ex).__name__
        return output,audit
    checked=0
    for x in output:
        x["context_status"]="UNVERIFIED"
        x["quality_score"]=None
        x["quality_risk_flag"]=False
        sector=sector_evidence(x,asof)
        x["sector_quality_status"]=sector["status"]
        x["sector_score"]=sector["score"]
        if sector["exclude"]:
            x["quality_risk_flag"]=True
            x["context_status"]="EXCLUDED_VERIFIED_SECTOR"
            audit["checked"].append({"code":x["code"],"context_status":x["context_status"],
                "sector_quality_status":sector["status"],"risk_flag":True})
            continue
        x["disclosure_status"]="UNVERIFIED"
        if not x.get("geometry_validated"):continue
        if checked>=max_requests:continue
        checked+=1
        ticker=x["code"]
        if any(t in x["name"].upper() for t in EXCLUDE_TERMS):
            x["quality_risk_flag"]=True
            x["context_status"]="EXCLUDED_NAME_CATEGORY"
            continue
        corp=lookup.get(ticker)
        if not corp:continue
        try:
            values,filings,status=annual_asof(corp,key,datetime.datetime.strptime(asof,"%Y%m%d").date())
            x["context_status"]=status
            if values:
                equity=values["equity"];assets=values["assets"];liab=values["liabilities"]
                sales=values["sales"];prior=values["sales_prev"]
                profit=values["profit"];prior_profit=values["profit_prev"]
                identity_ok=assets>0 and abs(assets-liab-equity)/assets<=.01
                if identity_ok:
                    if equity<=0:
                        x["quality_risk_flag"]=True
                        x["context_status"]="NONPOSITIVE_EQUITY"
                    else:
                        revenue_growth=prior>0 and sales>prior
                        profit_growth=profit>prior_profit
                        # Lightweight quality; loss or leverage alone is caution, not exclusion.
                        x["quality_score"]=round(8+4*(profit>0)+4*revenue_growth+4*profit_growth,2)
                        x["financial_quality_status"]=("IMPROVING" if revenue_growth and profit_growth and profit>0
                                                       else "CAUTION" if profit<=0 else "MIXED")
                        x["financial_filing_date"]=values["filing_date"]
                        x["financial_fiscal_year"]=values["fiscal_year"]
                else:x["context_status"]="BALANCE_SHEET_IDENTITY_UNVERIFIED"
            # Verify latest interim YTD; no fabricated single-quarter growth.
            interim,interim_status=interim_asof(corp,key,target,filings,
                values["fiscal_year"] if values else target.year-2)
            x["interim_status"]=interim_status
            if interim:
                x["interim_quality"]=interim["quality"]
                x["interim_filing_date"]=interim["filing"]["receipt_date"]
                x["interim_yoy_revenue_pct"]=interim["yoy_revenue_pct"]
                x["interim_yoy_operating_profit_pct"]=interim["yoy_operating_profit_pct"]
                # Separate revenue contraction from profit deterioration.
                revenue=interim["yoy_revenue_pct"]
                profit_now=interim.get("current_ytd_operating_profit_krw")
                profit_prev=interim.get("previous_ytd_operating_profit_krw")
                if revenue is not None and revenue<0 and profit_now is not None and profit_prev is not None and profit_now>profit_prev and profit_now>0:
                    x["financial_quality_status"]="REVENUE_DOWN_PROFIT_UP"
                    x["quality_score"]=max(0,(x.get("quality_score") or 10)-2)
                elif interim["quality"]=="INTERIM_PROFIT_OR_SALES_WEAKENING":
                    x["quality_score"]=min(x.get("quality_score") or 10,10)
                    x["financial_quality_status"]="RECENT_INTERIM_WEAKENING"
                elif interim["quality"]=="INTERIM_SALES_AND_PROFIT_GROWTH_OBSERVED":
                    x["quality_score"]=min(20,(x.get("quality_score") or 10)+2)
            # Check latest public filing titles; cannot treat absence as no risk.
            recent=[r for r in filings if str(r.get("rcept_dt",""))>=
                    (datetime.datetime.strptime(asof,"%Y%m%d").date()-datetime.timedelta(days=90)).strftime("%Y%m%d")]
            flagged=[r for r in recent if any(term in str(r.get("report_nm","")).replace(" ","") for term in RISK_TERMS)]
            x["disclosure_status"]="RISK_TITLE_REVIEW_REQUIRED" if flagged else "NO_MATCH_IN_RETRIEVED_PERIODIC_LIST"
            x["disclosure_title_flags"]=[str(r.get("report_nm",""))[:90] for r in flagged[:3]]
            if flagged:x["context_status"]="DISCLOSURE_REVIEW_REQUIRED"
        except Exception as ex:
            x["context_status"]="DART_REQUEST_FAILED_"+type(ex).__name__
        audit["checked"].append({"code":ticker,"context_status":x["context_status"],
            "financial_quality_status":x.get("financial_quality_status"),
            "disclosure_status":x["disclosure_status"],"interim_status":x.get("interim_status"),
            "interim_quality":x.get("interim_quality"),"risk_flag":x["quality_risk_flag"]})
    # Never replace the technical entry-first ordering; quality only tie-breaks within status.
    for x in output:
        x.setdefault("context_status","UNVERIFIED")
        x.setdefault("quality_score",None)
        x.setdefault("quality_risk_flag",False)
        x.setdefault("sector_quality_status","UNVERIFIED")
        x.setdefault("disclosure_status","UNVERIFIED")
        x["context_composite_score"]=round(
            min(65,max(0,x["opportunity_score"])*.65)+
            (x["quality_score"] if x["quality_score"] is not None else 10)+
            (x.get("sector_score") if x.get("sector_score") is not None else 5)+2.5,2)
    audit["status"]="CONTEXT_RESEARCH_COMPLETED"
    audit["reviewed_count"]=checked
    return output,audit
