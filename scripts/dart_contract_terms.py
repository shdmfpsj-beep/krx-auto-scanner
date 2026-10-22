#!/usr/bin/env python3
"""Parse bounded labeled OpenDART contract cells without guessing units.

This is *one public filing's* read-only typed evidence, never independent
verification of contract validity, counterparty, amendment, or investment.
Ambiguous units, conflicting cells or mismatched disclosed ratios block
numeric promotion. No automated buy or positive-catalyst classification.
"""
import re
from decimal import Decimal,InvalidOperation
from datetime import datetime

UNITS={"원":1,"천원":1000,"백만원":1_000_000,"억원":100_000_000}
MAX_KRW=10**18
VALUE=re.compile(r"^([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.([0-9]{1,4}))?$")
BLOCK=("약","추정","미정","예정","이상","이하","외화","usd","달러","포함","별도","변경전","변경후")
LABEL_CONFLICT=("변경전","변경후","최초","증감","전년","금액변동","확정전")
FRACTION=re.compile(r"^([0-9]+(?:\.[0-9]{1,4})?)\s*(%)?$")
DATE=re.compile(r"(20\d{2})[.\-/ ](0[1-9]|1[0-2])[.\-/ ]([0-2]\d|3[01])")

def norm_label(v):
    return re.sub(r"[\s\-\[\]{}()（）_%·ㆍ,]", "",str(v or "")).lower()

def classify(label):
    s=norm_label(label)
    if any(x in s for x in LABEL_CONFLICT):return None
    if "계약금액" in s or "총계약금액" in s:return "contract_amount"
    if "최근매출액" in s or "최근사업연도매출액" in s:return "recent_sales"
    if "매출액대비" in s:return "disclosed_sales_ratio_pct"
    if "계약기간" in s:return "contract_period"
    if "계약상대" in s:return "counterparty_text"
    return None

def amount_krw(text,label):
    """No implicit KRW unless cell or its precise label states the unit."""
    original=str(text or "").strip()
    hint=str(label or "")
    if not original or len(original)>100:return None
    compact=re.sub(r"\s+","",original)
    if any(term in compact.lower() for term in BLOCK):return None
    m=re.fullmatch(r"([0-9][0-9,]*(?:\.[0-9]{1,4})?)\s*(억원|백만원|천원|원)?",compact)
    if not m:return None
    unit=m[2]
    specified=re.findall(r"\((억원|백만원|천원|원)\)|（(억원|백만원|천원|원)）",hint)
    label_units={x for group in specified for x in group if x}
    if len(label_units)>1:return None
    label_unit=next(iter(label_units),None)
    if unit and label_unit and label_unit!=unit:return None
    unit=unit or label_unit
    if not unit:return None
    raw=m[1].split(".")[0]
    if "," in raw and not re.fullmatch(r"[0-9]{1,3}(?:,[0-9]{3})+",raw):
        return None
    try:
        val=Decimal(m[1].replace(",",""))*UNITS[unit]
    except (InvalidOperation,OverflowError):return None
    if not val.is_finite() or val<=0 or val>MAX_KRW or val!=val.to_integral_value():
        return None
    return int(val)

def ratio_percent(text,label):
    raw=str(text or "").strip()
    if len(raw)>60 or any(x in raw.lower() for x in BLOCK):return None
    m=FRACTION.fullmatch(raw)
    if not m:return None
    has_percent=m[2] or "%" in str(label)
    if not has_percent:return None
    try:v=Decimal(m[1])
    except InvalidOperation:return None
    if not v.is_finite() or v<=0 or v>1000:return None
    return v

def dates_in(text):
    parts=DATE.findall(str(text or "")[:120])
    found=[]
    for year,month,day in parts:
        try:found.append(datetime(int(year),int(month),int(day)).date())
        except ValueError:return []
    return found

def extract(fields,correction_risk="NO_CORRECTION_TITLE_FLAG"):
    """Returns exact textual provenance plus conservative typed candidates."""
    result=dict(status="NO_UNAMBIGUOUS_LABELED_TERMS",
        amount_krw=None,recent_sales_krw=None,
        disclosed_sales_ratio_pct=None,
        calculated_sales_ratio_pct=None,
        contract_period=None,counterparty_text=None,
        consistency="NOT_TESTABLE",
        correction_risk=correction_risk,
        direct_company_positive_impact_verified=False,
        contract_amount_independently_verified=False,
        source="SINGLE_OFFICIAL_FILING_LABELED_TABLE_CELLS",
        entry_or_stop_signal=False)
    buckets={}
    for row in (fields if isinstance(fields,list) else [])[:30]:
        if not isinstance(row,dict):continue
        label=str(row.get("label") or "")
        value=str(row.get("neighboring_text") or "").strip()
        category=classify(label)
        if category and value:
            buckets.setdefault(category,[]).append((label,value))
    conflicts=[]
    for key,out in (("contract_amount","amount_krw"),
                    ("recent_sales","recent_sales_krw"),
                    ("disclosed_sales_ratio_pct","disclosed_sales_ratio_pct")):
        observations=buckets.get(key,[])
        parsed=[]
        for label,value in observations:
            parsed.append(ratio_percent(value,label) if key=="disclosed_sales_ratio_pct"
                          else amount_krw(value,label))
        parsed=set(parsed)
        if len(parsed)>1:
            conflicts.append(key)
        elif parsed and None not in parsed:
            result[out]=next(iter(parsed))
    periods=set()
    for _,v in buckets.get("contract_period",[]):
        days=dates_in(v)
        if len(days)==2 and days[0]<=days[1]:
            periods.add((days[0].isoformat(),days[1].isoformat()))
    if len(periods)>1:conflicts.append("contract_period")
    elif len(periods)==1:
        start,end=next(iter(periods))
        result["contract_period"]={"start":start,"end":end}
    if len(buckets.get("counterparty_text",[]))==1:
        label,v=buckets["counterparty_text"][0]
        if len(v)<=100 and v not in ("-","해당사항 없음"):
            result["counterparty_text"]=v
    result["conflicting_fields"]=conflicts
    if conflicts:
        result["status"]="CONFLICTING_LABELED_FILING_VALUES"
        result["consistency"]="CONFLICT"
        result["amount_krw"]=None
        result["disclosed_sales_ratio_pct"]=None
        return result
    amount=result["amount_krw"];sales=result["recent_sales_krw"]
    disclosed=result["disclosed_sales_ratio_pct"]
    if amount is not None and sales is not None:
        calc=(Decimal(amount)/Decimal(sales))*100
        result["calculated_sales_ratio_pct"]=float(round(calc,4))
        if disclosed is not None:
            # 0.15 percentage-point tolerance covers common filing rounding;
            # this only checks a *single* filing's arithmetic, not its truth.
            diff=abs(calc-disclosed)
            if diff>Decimal("0.15"):
                result["consistency"]="DOCUMENT_RATIO_MISMATCH_REVIEW"
                result["status"]="FILING_RATIO_MISMATCH"
                return result
            result["consistency"]="SINGLE_FILING_ARITHMETIC_MATCH"
    elif disclosed is not None:
        result["consistency"]="RATIO_ONLY_NO_SALES_BASE"
    if correction_risk!="NO_CORRECTION_TITLE_FLAG":
        result["status"]="CORRECTION_OR_WITHDRAWAL_REVIEW"
    elif amount is not None:
        result["status"]="LABELED_AMOUNT_READ_FROM_OFFICIAL_SOURCE"
    else:
        result["status"]="NO_UNAMBIGUOUS_LABELED_AMOUNT"
    return result
