#!/usr/bin/env python3
"""OpenDART current-year interim statement safety: same-period cumulative YoY.

Full statement API's thstrm_amount may mean ONLY the latest 3 months
in interim IS/CIS. Never compare it against another 3-month/cumulative
period as if it were YTD. Require thstrm_add_amount / frmtrm_add_amount
explicitly and a dated, named 03/06/09 filing before any interim trend claim.
This is research evidence, NOT a final 15-point grade or trade approval.
"""
import math,re
from datetime import date

REPORT_CODES={"03":"11013","06":"11012","09":"11014"}
REVENUE={"ifrs_Revenue","ifrs-full_Revenue",
         "ifrs-full_RevenueFromContractsWithCustomers"}
OPERATING={"dart_OperatingIncomeLoss"}
DETAILS=("","-")

def amount(value):
    if value is None or str(value).strip() in ("","-","－"):return None
    try:
        v=float(str(value).replace(",","").strip())
        return int(v) if math.isfinite(v) else None
    except (ValueError,TypeError):
        return None

def identify_interim_filing(latest,asof):
    """Return pinned period and receipt, or None; no inference by run month."""
    if not latest:return None
    day,receipt,name=latest
    if not isinstance(day,date) or day>asof:return None
    if not re.fullmatch(r"\d{14}",str(receipt)):return None
    m=re.search(r"\(\s*(20\d\d)\s*\.\s*(03|06|09)\s*\)",str(name))
    if not m:return None
    year,month=int(m[1]),m[2]
    if year>asof.year:return None
    typ=str(name).split("(")[0].strip()
    if month=="06" and "반기보고서" not in typ:return None
    if month!="06" and "분기보고서" not in typ:return None
    # No bare same-day market pre-close use: actual scanner runs after 22:00.
    return dict(fiscal_year=year,month=month,report_code=REPORT_CODES[month],
                period_end=f"{year}-{month}-"+("31" if month in ("03","09") else "30"),
                receipt_date=day.isoformat(),receipt_no=str(receipt),
                receipt_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo="+str(receipt),
                basis="CUMULATIVE_YEAR_TO_DATE")

def select(rows,ids,period):
    """Use unique standard account and exact cumulative period; never 3-mo."""
    for statement in ("IS","CIS"):
        amounts=[]
        for row in rows:
            if row.get("sj_div")!=statement or row.get("account_id") not in ids:
                continue
            if str(row.get("account_detail") or "").strip() not in DETAILS:
                continue
            a=amount(row.get(period))
            if a is None:continue
            amounts.append(a)
        if amounts:
            return amounts[0] if len(set(amounts))==1 else None
    return None

def evaluate_interim(payload,division,filing):
    status=str(payload.get("status") or "UNKNOWN")
    result=dict(status="INTERIM_NOT_VERIFIED",division=division,
        source_api_status=status,filing=dict(filing),
        data_basis="YTD_NOT_SINGLE_QUARTER",
        yoy_revenue_pct=None,yoy_operating_profit_pct=None,
        ytd_operating_margin_pct=None,quality="UNVERIFIED",
        latest_periodic_financials_verified=False,
        trade_approval="NO")
    if status!="000" or not isinstance(payload.get("list"),list):
        result["status"]="INTERIM_API_UNAVAILABLE"
        return result
    raw=payload["list"]
    rows=[r for r in raw if r.get("fs_div") in (None,"",division)]
    result["row_count"]=len(rows)
    # Reject API responses for another fiscal year/report code when stated.
    for r in rows:
        if r.get("reprt_code") not in (None,"",filing["report_code"]) or str(
          r.get("bsns_year") or filing["fiscal_year"])!=str(filing["fiscal_year"]):
            result["status"]="INTERIM_SOURCE_PERIOD_MISMATCH"
            return result
        if r.get("currency") not in (None,"","KRW"):
            result["status"]="INTERIM_NON_KRW"
            return result
    current_sales=select(rows,REVENUE,"thstrm_add_amount")
    previous_sales=select(rows,REVENUE,"frmtrm_add_amount")
    current_profit=select(rows,OPERATING,"thstrm_add_amount")
    previous_profit=select(rows,OPERATING,"frmtrm_add_amount")
    result.update(current_ytd_revenue_krw=current_sales,
        previous_ytd_revenue_krw=previous_sales,
        current_ytd_operating_profit_krw=current_profit,
        previous_ytd_operating_profit_krw=previous_profit)
    missing=[k for k,v in (
        ("current_ytd_revenue_krw",current_sales),
        ("previous_ytd_revenue_krw",previous_sales),
        ("current_ytd_operating_profit_krw",current_profit),
        ("previous_ytd_operating_profit_krw",previous_profit)) if v is None]
    result["missing_cumulative_keys"]=missing
    if missing or not current_sales or current_sales<=0 or not previous_sales or previous_sales<=0:
        result["status"]="INTERIM_CUMULATIVE_METRICS_INCOMPLETE"
        return result
    result["yoy_revenue_pct"]=round(100*(current_sales/previous_sales-1),2)
    result["ytd_operating_margin_pct"]=round(100*current_profit/current_sales,2)
    # Operating YoY from negative/zero prior base is nonsensical as percentage.
    if previous_profit>0:
        result["yoy_operating_profit_pct"]=round(100*(current_profit/previous_profit-1),2)
    result["latest_periodic_financials_verified"]=True
    result["status"]="DATED_INTERIM_YTD_RESEARCH_ONLY"
    if current_profit<=0 or current_sales<previous_sales or current_profit<previous_profit:
        result["quality"]="INTERIM_PROFIT_OR_SALES_WEAKENING"
    elif previous_profit>0 and current_profit>previous_profit and current_sales>previous_sales:
        result["quality"]="INTERIM_SALES_AND_PROFIT_GROWTH_OBSERVED"
    else:
        result["quality"]="INTERIM_MIXED"
    return result
