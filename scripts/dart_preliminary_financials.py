#!/usr/bin/env python3
"""Fail-closed OpenDART preliminary earnings original (SGML/XML) reader.

Unlike periodic fnlttSinglAcntAll records, preliminary fair disclosures have
no universal structured profit API. Require explicit same-table metric names,
current/comparable column labels, unit, and quarter dates before calculating
a quarterly YoY. Never mistake provisional, revised or unparseable filings
for audited earnings or final BUY evidence.
"""
import io,re,zipfile
from datetime import date,datetime
from decimal import Decimal,InvalidOperation
from xml.etree import ElementTree
from dart_contract_documents import (text_decode,LegacyTables,MAX_ZIP_BYTES,
                                      MAX_UNCOMPRESSED,MAX_SGML_FRAGMENT)

SCHEMA="dart_preliminary_earnings_original_v1"
UNITS={"원":1,"천원":1000,"백만원":1_000_000,"억원":100_000_000}
REQUIRED=("revenue","operating_profit")
UNIT_RE=re.compile(r"(?:단위|금액단위)\s*[:：]\s*(억원|백만원|천원|원)")
DATE_RE=re.compile(r"(20\d{2})[./-](0[1-9]|1[0-2])[./-]([0-2]\d|3[01])")
AMOUNT_RE=re.compile(r"^(-?)([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{1,4})?$")
CURRENT=("당해실적","당기실적","이번분기","당해분기")
PREVIOUS=("전년동기실적","전년동기","전년대비기준")
EXCLUDED=("전기실적","전분기실적","직전분기","증감률","증감액","매출액대비")
def clean(value):
    return re.sub(r"\s+","",str(value or "")).replace("ㆍ","").replace("·","")

def metric(label):
    s=clean(label)
    if any(p in s for p in ("전년","전분기","증감","전기","영업외")):return None
    if s in ("매출액","매출액합계","총매출액"):return "revenue"
    if s in ("영업이익","영업이익(손실)","영업손익","영업이익(손실)액"):
        return "operating_profit"
    return None

def column_kind(label):
    s=clean(label)
    if any(k in s for k in EXCLUDED):return None
    if any(k in s for k in PREVIOUS):return "previous_same_period"
    if any(k in s for k in CURRENT):return "current"
    return None

def parse_amount(value,unit):
    if unit not in UNITS:return None
    s=clean(value).replace("△","-").replace("▲","-")
    if s.startswith("(") and s.endswith(")"):s="-"+s[1:-1]
    m=AMOUNT_RE.fullmatch(s)
    if not m:return None
    try:amount=Decimal(s.replace(",",""))*UNITS[unit]
    except (InvalidOperation,OverflowError):return None
    if not amount.is_finite() or abs(amount)>Decimal("1e18"):return None
    if amount!=amount.to_integral_value():return None
    return int(amount)

def parse_date_pairs(rows):
    """Only explicit current and prior quarter periods in labeled table rows."""
    periods={}
    for row in rows:
        texts=[clean(x) for x in row[:12]]
        for i,key in enumerate(texts[:-1]):
            kind=column_kind(key)
            if kind not in ("current","previous_same_period"):continue
            # Do not read an unrelated metric amount as a period.
            matches=DATE_RE.findall(texts[i+1])
            if len(matches)!=2:continue
            days=[]
            try:
                for y,m,d in matches:days.append(date(int(y),int(m),int(d)))
            except ValueError:continue
            if days[0]>days[1]:continue
            periods.setdefault(kind,set()).add(tuple(days))
    if any(len(periods.get(k,set()))!=1 for k in
           ("current","previous_same_period")):return None
    a,b=(next(iter(periods[k])) for k in ("current","previous_same_period"))
    if ((a[1]-a[0]).days not in range(75,105) or
        (b[1]-b[0]).days not in range(75,105) or
        a[0].month!=b[0].month or a[1].month!=b[1].month or
        a[0].year!=b[0].year+1 or a[1].year!=b[1].year+1):
        return None
    return dict(current_start=a[0].isoformat(),current_end=a[1].isoformat(),
                previous_start=b[0].isoformat(),previous_end=b[1].isoformat(),
                frequency="SINGLE_QUARTER_NON_CUMULATIVE")

def metrics_from_rows(rows,unit):
    """Require exact current+prior column headers and consistent metric values."""
    values={}
    for i,head in enumerate(rows):
        labels=[column_kind(h) for h in head]
        if labels.count("current")!=1 or labels.count("previous_same_period")!=1:
            continue
        c=labels.index("current")
        p=labels.index("previous_same_period")
        if c==p or max(c,p)>=14:continue
        for row in rows[i+1:i+14]:
            if len(row)<=max(c,p):continue
            k=metric(row[0] if row else "")
            if k not in REQUIRED:continue
            curr=parse_amount(row[c],unit)
            prev=parse_amount(row[p],unit)
            if curr is not None and prev is not None:
                values.setdefault(k,set()).add((curr,prev))
    conflicts=[k for k in REQUIRED if len(values.get(k,set()))>1]
    found={k:next(iter(values[k])) if len(values.get(k,set()))==1 else None
           for k in REQUIRED}
    return found,conflicts

def source_table_groups(rows):
    """Preserve table boundaries: a period from table A must not authorize B."""
    groups=[];current=[]
    for row in rows:
        if row==["__TABLE_BOUNDARY__"]:
            if current:groups.append(current)
            current=[]
        else:current.append(row)
    if current:groups.append(current)
    return groups

class LegacyPreliminaryTables(LegacyTables):
    def handle_starttag(self,tag,attrs):
        if tag=="table":
            self.finish_row()
            self.rows.append(["__TABLE_BOUNDARY__"])
        super().handle_starttag(tag,attrs)
    def handle_endtag(self,tag):
        super().handle_endtag(tag)
        if tag=="table":self.rows.append(["__TABLE_BOUNDARY__"])

def decode_document(data):
    """Extract bounded tables, typed units and per-period evidence only."""
    if len(data)>MAX_ZIP_BYTES or not zipfile.is_zipfile(io.BytesIO(data)):
        return dict(status="INVALID_OR_OVERSIZE_PRELIMINARY_ZIP")
    rows=[]
    unit_candidates=set()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        files=[x for x in z.infolist()
               if x.filename.lower().endswith((".xml",".xhtml",".html"))]
        if len(files)>15 or not files or sum(f.file_size for f in files)>MAX_UNCOMPRESSED:
            return dict(status="PRELIMINARY_DOCUMENT_TOO_LARGE")
        if any(x.flag_bits&1 for x in files):
            return dict(status="ENCRYPTED_PRELIMINARY_DOCUMENT")
        for f in files:
            raw=z.read(f)
            doc=text_decode(raw)
            units=set(UNIT_RE.findall(doc[:400000]))
            unit_candidates.update(units)
            try:
                root=ElementTree.fromstring(raw)
                parsed=[]
                for table in root.iter():
                    if not isinstance(table.tag,str) or (
                        table.tag.split("}")[-1].upper()!="TABLE"):continue
                    parsed.append(["__TABLE_BOUNDARY__"])
                    for tr in table.iter():
                        if not isinstance(tr.tag,str) or tr.tag.split("}")[-1].upper()!="TR":
                            continue
                        cells=[c for c in tr if isinstance(c.tag,str) and
                            c.tag.split("}")[-1].upper() in ("TD","TH")]
                        if 2<=len(cells)<=14:
                            parsed.append([" ".join("".join(c.itertext()).split())[:160]
                                for c in cells])
                    parsed.append(["__TABLE_BOUNDARY__"])
                rows.extend(parsed[:2500])
            except (ElementTree.ParseError,ValueError,UnicodeError):
                # Legacy DART SGML has no universal well-formed XML guarantee.
                # Large documents: parse bounded relevant TABLE windows only.
                if len(doc)>MAX_SGML_FRAGMENT:
                    low=doc.lower()
                    fragments=[]
                    for target in ("매출액","영업이익","당해실적","전년동기실적"):
                        idx=low.find(target.lower())
                        if idx<0:continue
                        begin=low.rfind("<table",max(0,idx-70000),idx)
                        end=low.find("</table",idx,idx+70000)
                        if begin<0 or end<0:continue
                        piece=doc[begin:end+8]
                        if len(piece)<=100000:fragments.append(piece)
                    if not fragments:continue
                    doc="\n".join(fragments)[:MAX_SGML_FRAGMENT]
                parser=LegacyPreliminaryTables()
                try:parser.feed(doc)
                except (ValueError,AssertionError):continue
                rows.extend([[" ".join(str(c).split())[:160] for c in r[:14]]
                             for r in parser.rows[:2500]])
    return dict(status="PRELIMINARY_TABLE_ROWS_READ",rows=rows[:3000],
                unit_candidates=sorted(unit_candidates))

def assess(data,filing,asof):
    """Only prior-day valid original + exact unit + period + both metrics."""
    result=dict(schema=SCHEMA,status="NOT_VERIFIED",
       source="OFFICIAL_DART_ORIGINAL_PRELIMINARY_FILING",
       receipt_no=filing.get("receipt_no"),receipt_date=filing.get("date"),
       ticker=filing.get("ticker"),statement_scope=(
         "CFS" if "연결" in str(filing.get("title","")) else
         "OFS" if "별도" in str(filing.get("title","")) else "UNKNOWN"),
       quarter_period=None,currency="KRW",
       unit=None,revenue_current_krw=None,revenue_previous_krw=None,
       operating_profit_current_krw=None,operating_profit_previous_krw=None,
       revenue_yoy_pct=None,operating_profit_yoy_pct=None,
       preliminary_figures_source_verified=False,
       earnings_quality="UNVERIFIED",full_investment_score_verified=False,
       impact_verified=False,trade_approved=False)
    day=None
    try:day=date.fromisoformat(str(filing.get("date","")))
    except ValueError:pass
    if not day or day>=asof or (asof-day).days>7:
        result["status"]="PRELIMINARY_FILING_DATE_NOT_PIT_SAFE";return result
    if filing.get("correction_flag"):
        result["status"]="PRELIMINARY_AMENDED_REQUIRES_RECONCILIATION";return result
    if data.get("status")!="PRELIMINARY_TABLE_ROWS_READ":
        result["status"]=data.get("status","SOURCE_UNREADABLE");return result
    units=data.get("unit_candidates",[])
    if len(units)!=1:
        result["status"]="PRELIMINARY_UNIT_MISSING_OR_AMBIGUOUS";return result
    unit=units[0]
    result["unit"]=unit
    groups=source_table_groups(data.get("rows",[]))
    dated=[]
    complete=[]
    conflicts_found=False
    for rows in groups:
        period=parse_date_pairs(rows)
        if period is None:continue
        dated.append(period)
        vals,conflicts=metrics_from_rows(rows,unit)
        if conflicts:conflicts_found=True
        if all(vals.get(k) is not None for k in REQUIRED) and not conflicts:
            complete.append((period,vals))
    if conflicts_found:
        result["status"]="PRELIMINARY_DUPLICATE_METRIC_CONFLICT";return result
    if not dated:
        result["status"]="PRELIMINARY_QUARTER_COMPARISON_PERIOD_NOT_VERIFIED"
        return result
    if not complete:
        result["status"]="PRELIMINARY_SAME_ROW_YOY_VALUES_MISSING";return result
    if len(complete)!=1:
        result["status"]="PRELIMINARY_MULTIPLE_QUARTER_TABLES_AMBIGUOUS";return result
    period,vals=complete[0]
    if date.fromisoformat(period["current_end"])>day:
        result["status"]="PRELIMINARY_RESULTS_AFTER_RECEIPT_DATE";return result
    result["quarter_period"]=period
    rev,prior_rev=vals["revenue"]
    op,prior_op=vals["operating_profit"]
    result.update(revenue_current_krw=rev,revenue_previous_krw=prior_rev,
         operating_profit_current_krw=op,operating_profit_previous_krw=prior_op)
    if prior_rev<=0 or rev<=0:
        result["status"]="PRELIMINARY_INVALID_REVENUE_BASE";return result
    result["revenue_yoy_pct"]=round((rev/prior_rev-1)*100,2)
    if prior_op>0:result["operating_profit_yoy_pct"]=round((op/prior_op-1)*100,2)
    result["preliminary_figures_source_verified"]=True
    result["status"]="PRELIMINARY_SINGLE_QUARTER_SOURCE_RESEARCH_ONLY"
    if rev<prior_rev or op<prior_op or op<=0:
        result["earnings_quality"]="RECENT_PRELIMINARY_WEAKENING"
    elif prior_op<=0:
        result["earnings_quality"]="PRELIMINARY_OPERATING_TURNAROUND_NO_YOY_PERCENT"
    elif rev>prior_rev and op>prior_op:
        result["earnings_quality"]="PRELIMINARY_SALES_AND_OP_GROWTH_OBSERVED"
    else:
        result["earnings_quality"]="PRELIMINARY_MIXED"
    return result
