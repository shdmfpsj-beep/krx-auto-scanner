#!/usr/bin/env python3
"""Finite exactly-14 original OpenDART financial document audit.

The original document archive is downloaded in runner memory only. The output
contains hashes, matched literal indicators and per-receipt BLOCKED reasons;
it NEVER certifies a number merely because a string is present in a report.
No time-unverified PIT, trading, operating code or provisional data mutation.
"""
import argparse,csv,hashlib,html,io,json,os,re,urllib.parse,urllib.request,urllib.error,zipfile
from collections import Counter
from pathlib import Path

URL="https://opendart.fss.or.kr/api/document.xml"
MAX_ARCHIVE=25*1024*1024
MAX_EXPAND=50*1024*1024
FIELDS=("revenue_amount_krw","op_profit_amount_krw","liabilities_amount_krw","equity_amount_krw")
CANONICAL_CLASSES=("MATCHES_FIRST_FROZEN_KRX_SESSION",
                   "ORIGINAL_AVAILABLE_DATE_IS_NOT_MARKET_SESSION",
                   "OUTSIDE_ARCHIVED_KRX_CALENDAR_CANNOT_CERTIFY")

def digest(b):return hashlib.sha256(b).hexdigest()
def match_literal_amount(doc,num):
    """Non-certifying string-match diagnostic, never an accounting equivalence."""
    try:amount=int(str(num))
    except (TypeError,ValueError):return False
    choices=set()
    for divisor in (1,1000,1000000):
        if abs(amount)%divisor:continue
        v=abs(amount)//divisor
        choices.add(f"{v:,}")
        if v>=100000:choices.add(str(v))
    text=doc
    return any(re.search(r"(?<!\d)"+re.escape(c)+r"(?!\d)",text) for c in choices)

def safe_doc_text(raw):
    if len(raw)>MAX_ARCHIVE or not zipfile.is_zipfile(io.BytesIO(raw)):
        raise ValueError("ORIGINAL_NOT_VALID_ZIP")
    fragments=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist()
        if not infos or len(infos)>30 or sum(i.file_size for i in infos)>MAX_EXPAND:
            raise ValueError("ORIGINAL_UNSAFE_EXPANSION")
        for info in infos:
            if info.is_dir() or ".." in Path(info.filename).parts:
                raise ValueError("UNSAFE_ARCHIVE_PATH")
            raw_part=z.read(info)
            for codec in ("utf-8","cp949","euc-kr"):
                try:part=raw_part.decode(codec);break
                except UnicodeDecodeError:continue
            else:part=raw_part.decode("utf-8","replace")
            fragments.append(part)
    rawtext=html.unescape(" ".join(fragments))
    # Restrict this to report text, not a claim of parsed statement rows.
    rawtext=re.sub(r"(?is)<script.*?</script>|<style.*?</style>"," ",rawtext)
    rawtext=re.sub(r"(?s)<[^>]+>"," ",rawtext)
    rawtext=re.sub(r"\s+"," ",rawtext)
    return rawtext,len(infos)

def fetch_original(receipt,key):
    if not re.fullmatch(r"\d{14}",receipt):raise ValueError("INVALID_RECEIPT")
    if not key:return None,"BLOCKED_NO_OPENDART_KEY"
    q=urllib.parse.urlencode({"crtfc_key":key,"rcept_no":receipt})
    try:
        req=urllib.request.Request(URL+"?"+q,headers={"User-Agent":"C3-ReadOnly-FinitePIT-v13"})
        with urllib.request.urlopen(req,timeout=18) as response:raw=response.read(MAX_ARCHIVE+1)
        if len(raw)>MAX_ARCHIVE:return None,"BLOCKED_DOC_TOO_LARGE"
        if not zipfile.is_zipfile(io.BytesIO(raw)):
            return None,"BLOCKED_DART_NOT_ZIP_OR_STATUS"
        return raw,"ARCHIVE_FETCHED"
    except urllib.error.HTTPError as ex:return None,"BLOCKED_HTTP_"+str(ex.code)
    except (urllib.error.URLError,TimeoutError,OSError):return None,"BLOCKED_NETWORK"

def evaluate(root,pit,prior,key):
    records={r["receipt_no"]:r for r in csv.DictReader((root/"reports/v91_financial_pit_provisional.csv").open(encoding="utf-8-sig",newline=""))}
    actual=pit["events"]
    wanted={str(r["receipt_no"]) for r in actual}
    if len(actual)!=14 or len(wanted)!=14:raise ValueError("FROZEN_14_NOT_PRESERVED")
    old={r["receipt_no"]:r for r in prior["receipts"] if r.get("kind")=="FINANCIAL_PROVISIONAL_DATE_LINK"}
    if len(old)!=14 or set(old)!=wanted:raise ValueError("ORIGINAL_RECEIPT_INVENTORY_NOT_FROZEN")
    if set(wanted)-set(records):raise ValueError("MISSING_V91_SNAPSHOT_RECEIPTS")
    results=[]
    for ev in actual:
        receipt=ev["receipt_no"];row=records[receipt];origin=old[receipt]
        if row["ticker"]!=ev["ticker"] or row["filing_date"]!=ev["filing_date"]:
            raise ValueError("PROVISIONAL_LINK_INCONSISTENT")
        if receipt[:8]!=row["filing_date"].replace("-",""):
            raise ValueError("RECEIPT_DATE_INVALID")
        if ev["classification"] not in CANONICAL_CLASSES:
            raise ValueError("INVALID_PREVIOUS_PIT_CALENDAR_CLASS")
        report={"ticker":row["ticker"],"selection_date":ev["selection_date"],
            "receipt_no":receipt,"filing_date":ev["filing_date"],
            "original_old_available_date":ev["old_available_date"],
            "frozen_calendar_classification":ev["classification"],
            "first_KRX_market_session_after_filing":ev.get("first_observed_KRX_market_session_after_filing"),
            "financial_statement_division_in_provisional_snapshot":row["fs_div"],
            "fiscal_year_in_provisional_snapshot":row["report_year"],
            "report_code_in_provisional_snapshot":row["report_code"],
            "source_archive_prior_sha256":origin["original_archive_sha256"],
            "source_archive_current_sha256":None,
            "source_original_archive_sha_matches_prior":False,
            "literal_amount_presence_diagnostic":{},
            "verification_status":"BLOCKED",
            "reason":"BLOCKED_ORIGINAL_DOCUMENT_UNAVAILABLE",
            "numeric_PIT_approved":False}
        raw,fetch_status=fetch_original(receipt,key)
        if raw is None:report["reason"]=fetch_status
        else:
            report["source_archive_current_sha256"]=digest(raw)
            report["source_original_archive_sha_matches_prior"]=(digest(raw)==origin["original_archive_sha256"])
            if not report["source_original_archive_sha_matches_prior"]:
                report["reason"]="BLOCKED_ORIGINAL_ARCHIVE_SHA_CHANGED"
            else:
                try:
                    rawtext,numfiles=safe_doc_text(raw)
                    report["original_document_file_count"]=numfiles
                    report["document_contains_financial_statement_terms"]=(
                        any(x in rawtext for x in ("재무상태표","포괄손익계산서","손익계산서")) and
                        "영업이익" in rawtext)
                    report["literal_amount_presence_diagnostic"]={
                        name:match_literal_amount(rawtext,row.get(name)) for name in FIELDS}
                    # Original report may include tables for multiple periods, note
                    # disclosures, and consolidated/separate statements. Literal
                    # occurrences cannot certify the same account or the FY/Q basis.
                    # NEVER promote into VERIFIED without row, unit, FS/period and
                    # amendment chain cross-validation.
                    if ev["classification"]=="OUTSIDE_ARCHIVED_KRX_CALENDAR_CANNOT_CERTIFY":
                        report["reason"]="BLOCKED_ORIGINAL_NUMERIC_SCOPE_AND_TRADE_CALENDAR"
                    elif not report["document_contains_financial_statement_terms"]:
                        report["reason"]="BLOCKED_STATEMENT_SECTIONS_NOT_IDENTIFIED"
                    else:
                        report["reason"]="BLOCKED_UNPARSED_ORIGINAL_ACCOUNT_ROWS_FS_PERIOD_AND_AMENDMENTS"
                except ValueError as e:report["reason"]="BLOCKED_"+str(e)
        results.append(report)
    summary=Counter(r["reason"] for r in results)
    return {"schema":"C3_V13_FINITE_14_ORIGINAL_PIT_AUDIT","source":"EXACT_V91_CSV_PLUS_PRIOR_HASH_LOCKED_DART_ZIPS",
        "expected_receipts":14,"total_classified":len(results),
        "statuses":{"VERIFIED":0,"INVALID":0,"BLOCKED":len(results)},
        "reconfirmed_identical_original_zip_sha_count":sum(r["source_original_archive_sha_matches_prior"] for r in results),
        "reason_counts":dict(summary),
        "literal_number_presence_does_not_prove_specific_statement_row":True,
        "no_original_zip_redistributed":True,
        "asof_original_numeric_accepted_for_research_ranking":0,
        "no_pit_financial_rank_promotion":True,
        "production_changed":False,"trade_approved":False,"decision":"CASH",
        "records":results}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--pit",type=Path,required=True)
    p.add_argument("--prior",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    root=Path(".")
    result=evaluate(root,json.loads(a.pit.read_text()),json.loads(a.prior.read_text()),os.environ.get("OPENDART_API_KEY",""))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("C3_V13_14_CASE_FINITE_AUDIT",json.dumps({k:v for k,v in result.items() if k!="records"},ensure_ascii=False))
if __name__=="__main__":main()
