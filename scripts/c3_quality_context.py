"""C3 quality context: point-in-time OpenDART, no speculative news sentiment.
Enrich only technically qualified candidates. Missing data is neutral/UNVERIFIED.
Financial and disclosure observations cannot rescue invalid entry geometry.
"""
import datetime,io,json,os,re,urllib.parse,urllib.request,zipfile
from xml.etree import ElementTree

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
    filings=get_json("list.json",{"corp_code":corp,"bgn_de":str(asof.year-2)+"0101",
        "end_de":asof.strftime("%Y%m%d"),"page_count":100,"pblntf_ty":"A"},key)
    if filings.get("status")!="000":return None,[], "FILINGS_UNAVAILABLE"
    available=[r for r in filings.get("list",[]) if str(r.get("rcept_dt",""))<=asof.strftime("%Y%m%d")]
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

def enrich(pool,asof,key,max_requests=12):
    """Return a NEW ranked list and audit. Keep original technical score intact."""
    output=[dict(x) for x in pool]
    audit={"schema":"C3_QUALITY_CONTEXT_V1","asof":asof,"mode":"TECHNICAL_FIRST",
           "weights":{"technical":65,"financial_and_earnings":20,"industry":10,"disclosures":5},
           "industry_policy":"NO_VERIFIED_SECTOR_CLASSIFICATION_NEUTRAL",
           "news_policy":"OFFICIAL_DART_DISCLOSURES_ONLY",
           "checked":[]}
    if not key or not re.fullmatch(r"[A-Za-z0-9]{40}",key):
        audit["status"]="DART_KEY_MISSING_OR_INVALID"
        return output,audit
    if datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y%m%d")!=asof:
        audit["status"]="HISTORICAL_ASOF_CONTEXT_NOT_RETROFITTED"
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
        x["sector_quality_status"]="UNVERIFIED"
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
            # Check latest public filing titles; cannot treat absence as no risk.
            recent=[r for r in filings if str(r.get("rcept_dt",""))>=
                    (datetime.datetime.strptime(asof,"%Y%m%d").date()-datetime.timedelta(days=90)).strftime("%Y%m%d")]
            flagged=[r for r in recent if any(term in str(r.get("report_nm","")).replace(" ","") for term in RISK_TERMS)]
            x["disclosure_status"]="RISK_TITLE_REVIEW_REQUIRED" if flagged else "NO_MATCH_IN_RETRIEVED_PERIODIC_LIST"
            x["disclosure_title_flags"]=[str(r.get("report_nm",""))[:90] for r in flagged[:3]]
            if flagged:x["quality_risk_flag"]=True
        except Exception as ex:
            x["context_status"]="DART_REQUEST_FAILED_"+type(ex).__name__
        audit["checked"].append({"code":ticker,"context_status":x["context_status"],
            "financial_quality_status":x.get("financial_quality_status"),
            "disclosure_status":x["disclosure_status"],"risk_flag":x["quality_risk_flag"]})
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
            5+2.5,2)
    audit["status"]="CONTEXT_RESEARCH_COMPLETED"
    audit["reviewed_count"]=checked
    return output,audit
