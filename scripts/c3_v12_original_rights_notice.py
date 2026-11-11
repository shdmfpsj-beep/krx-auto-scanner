#!/usr/bin/env python3
"""Retrieve five exact 2026 KRX rights notices from OpenDART original ZIP,
validate raw ZIP against prior captured SHA and parse structured announcement.
No split-adjusted total shareholder return, no trading approvals.
"""
import argparse,csv,datetime as dt,hashlib,html,io,json,os,re,urllib.parse,urllib.request,urllib.error,zipfile
from html.parser import HTMLParser
from pathlib import Path
from c3_v12_opendart_original_receipts import URL,MAX_RAW,analyze_document

TARGETS=(
 ("475460","20260915900714","2026-09-16"),
 ("303360","20261012900612","2026-10-13"),
 ("117670","20261020900760","2026-10-21"),
 ("290650","20261023900853","2026-10-26"),
 ("052400","20261028900690","2026-10-29"),
)

def sha(b):return hashlib.sha256(b).hexdigest()
def clean(v):return re.sub(r"\s+","",html.unescape(str(v or "")))
class TableRows(HTMLParser):
 def __init__(self):
    super().__init__(convert_charrefs=True)
    self.rows=[];self.row=None;self.cell=None
 def handle_starttag(self,tag,attrs):
    if tag.lower()=="tr":self.row=[]
    if tag.lower() in ("td","th") and self.row is not None:self.cell=[]
 def handle_data(self,text):
    if self.cell is not None:self.cell.append(text)
 def handle_endtag(self,tag):
    if tag.lower() in ("td","th") and self.cell is not None:
      self.row.append("".join(self.cell))
      self.cell=None
    if tag.lower()=="tr" and self.row is not None:
      self.rows.append(self.row)
      self.row=None
def decode_document(raw):
    for codec in ("utf-8-sig","euc-kr","cp949"):
        try:return raw.decode(codec)
        except UnicodeDecodeError:continue
    return raw.decode("utf-8",errors="replace")

def parse_rights(text,ticker,receipt_date):
    parsed=TableRows()
    parsed.feed(text)
    flat=clean(text)
    values={}
    # Require same table row cell label, then one and only one adjacent value.
    expected={
      "reference_price":("기준가","권리락기준가"),
      "ex_date":("권리락실시일","권리락일","권리락실시일자"),
      "short_code":("단축코드",),
      "cause":("사유",)
    }
    rows=[]
    for row in parsed.rows:
        cells=[clean(c) for c in row if clean(c)]
        if cells:rows.append(cells)
    for field,labels in expected.items():
        matches=[]
        for row_index,cells in enumerate(rows):
            for i,v in enumerate(cells):
                key=re.sub(r"^[0-9]+[.)]","",v)
                key=re.sub(r"\(원\)$","",key)
                if key not in labels:continue
                # Korean KRX tables usually have six headers in one TR,
                # followed by a second TR with six positionally aligned values.
                # Some older notices use alternating label/value TD cells instead.
                adjacent=cells[i+1] if i+1<len(cells) else None
                if adjacent and not re.match(r"^[0-9]+[.)]",adjacent):
                    matches.append(adjacent)
                elif row_index+1<len(rows) and i<len(rows[row_index+1]):
                    matches.append(rows[row_index+1][i])
        if len(set(matches))==1:values[field]=matches[0]
    # Ex-date and reference must appear in exact table fields, not nearby prose.
    mprice=re.fullmatch(r"(\d{1,3}(?:,\d{3})*|\d+)(?:원)?",values.get("reference_price",""))
    mdate=re.fullmatch(r"(20\d{2})[-./년](\d{1,2})[-./월](\d{1,2})일?",values.get("ex_date",""))
    if not mdate and re.fullmatch(r"20\d{6}",values.get("ex_date","")):
        x=values["ex_date"];mdate=re.fullmatch(r"(20\d{2})(\d{2})(\d{2})",x)
    actual_date=None
    if mdate:
        try:actual_date=dt.date(*map(int,mdate.groups())).isoformat()
        except ValueError:pass
    price=int(mprice.group(1).replace(",","")) if mprice else None
    is_ticker_matching=clean(values.get("short_code","")).replace("A","")==ticker
    cause_bonus="무상증자" in values.get("cause","")
    return {
        "rights_table_rows_parsed":len(rows),
        "ex_date_raw_row_value":values.get("ex_date"),
        "reference_price_raw_row_value":values.get("reference_price"),
        "short_code_raw_row_value":values.get("short_code"),
        "cause_raw_row_value":values.get("cause"),
        "parsed_ex_date":actual_date,
        "parsed_reference_price_krw":price,
        "ticker_table_matches":is_ticker_matching,
        "cause_table_bonus_issue":cause_bonus,
        "original_structured_notice_approved":bool(
           price and actual_date and is_ticker_matching and cause_bonus and
           actual_date>receipt_date.isoformat())
    }

def run(evidence,source_prices,key):
    expected={r["receipt_no"]:r for r in evidence["receipts"]}
    prices=source_prices
    out=[]
    for ticker,no,claimed in TARGETS:
        prev=expected.get(no)
        if not prev or not prev.get("original_archive_sha256"):
            raise ValueError("MISSING_PRIOR_ORIGINAL_DOCUMENT_DIGEST")
        record={"ticker":ticker,"receipt_no":no,"DART_receipt_date":no[:4]+"-"+no[4:6]+"-"+no[6:8],
            "asof_dart_title_indicated_ex_date":claimed,
            "file_sha256_expected":prev["original_archive_sha256"],
            "status":"BLOCKED_NO_KEY"}
        if not key:out.append(record);continue
        try:
            url=URL+"?"+urllib.parse.urlencode({"crtfc_key":key,"rcept_no":no})
            with urllib.request.urlopen(
              urllib.request.Request(url,headers={"User-Agent":"C3-Research-Rights/1.2"}),timeout=16
            ) as response:
              raw=response.read(MAX_RAW+1)
            if len(raw)>MAX_RAW:record["status"]="BLOCKED_MAX_DOCUMENT_SIZE";out.append(record);continue
            record["current_archive_sha256"]=sha(raw)
            if record["current_archive_sha256"]!=record["file_sha256_expected"]:
                record["status"]="BLOCKED_RAW_ARCHIVE_HASH_CHANGED";out.append(record);continue
            doc=analyze_document(raw)
            if not doc.get("zip_authenticated") or doc.get("file_count")!=1:
                record["status"]="BLOCKED_ORIGINAL_ARCHIVE_NOT_SINGLE";out.append(record);continue
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                member=z.namelist()[0]
                data=z.read(member)
            p=parse_rights(decode_document(data),ticker,
                           dt.date.fromisoformat(record["DART_receipt_date"]))
            record.update(p)
            record["status"]="PRIMARY_RIGHTS_NOTICE_VERIFIED" if (
                p["original_structured_notice_approved"] and
                p["parsed_ex_date"]==claimed) else "UNVERIFIED_STRUCTURED_RIGHTS_FIELDS"
            date=record.get("parsed_ex_date")
            observed=prices.get((ticker,date)) if date else None
            if observed is not None and record.get("parsed_reference_price_krw"):
                record["actual_ex_date_closing_price"]=observed["close"]
                record["close_vs_official_reference_pct"]=round(
                  (observed["close"]/record["parsed_reference_price_krw"]-1)*100,4)
                prev_data=prices.get((ticker,observed["previous_market_date"]))
                if prev_data:
                    record["raw_previous_market_close"]=prev_data["close"]
                    record["raw_close_ratio"]=round(observed["close"]/prev_data["close"],6)
            out.append(record)
        except (urllib.error.URLError,TimeoutError,OSError,ValueError,zipfile.BadZipFile):
            record["status"]="BLOCKED_NETWORK_OR_DOC_PARSING"
            out.append(record)
    return {"schema":"C3_V12_PRIMARY_EX_RIGHTS_NOTICE_PROVENANCE",
        "requested_primary_rights_notices":len(out),
        "primary_structured_notice_verified":sum(x["status"]=="PRIMARY_RIGHTS_NOTICE_VERIFIED" for x in out),
        "primary_digest_unchanged":sum(x.get("current_archive_sha256")==x["file_sha256_expected"] for x in out),
        "historical_original_record_vintage_signing_verified":False,
        "price_adjusted_shareholder_total_return_verified":False,
        "non_rights_65_anomaly_cause_verified":False,
        "actual_ex_date_market_open_reference_certified_to_follow_KRX":False,
        "profitability_signal_changed":False,
        "trade_approved":False,"operating_main_modified":False,"decision":"CASH","cases":out}

def read_price_sample(root):
    days=[];d={}
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or not (folder/"krx_v65_collect_status.json").is_file():continue
        m=json.loads((folder/"krx_v65_collect_status.json").read_text())
        if m.get("official_dataset_usable"):days.append(folder.name)
    for code,_,day in TARGETS:
        n=days.index(day)
        relevant=days[n-1:n+1]
        for date in relevant:
            folder=root/date
            for market in ("KOSPI","KOSDAQ"):
                fp=folder/f"{market}_official.csv"
                if not fp.exists():continue
                with fp.open(encoding="utf-8-sig",newline="") as f:
                    for row in csv.DictReader(f):
                        if row["ticker"]==code and row["valid_daily_bar"]=="True":
                            d[(code,date)]={"close":float(row["close"]),"previous_market_date":days[days.index(date)-1]}
    return d

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--original-evidence",type=Path,required=True)
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    prior=json.loads(a.original_evidence.read_text())
    d=run(prior,read_price_sample(a.root),os.environ.get("OPENDART_API_KEY",""))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n")
    print("C3_RIGHTS_PRIMARY",json.dumps({k:v for k,v in d.items() if k!="cases"},ensure_ascii=False))
    print("C3_RIGHTS_CASE_SUMMARY",json.dumps([{k:r.get(k) for k in
      ("ticker","status","parsed_ex_date","parsed_reference_price_krw","actual_ex_date_closing_price",
       "close_vs_official_reference_pct","raw_close_ratio","ticker_table_matches")}
       for r in d["cases"]],ensure_ascii=False))
if __name__=="__main__":main()
