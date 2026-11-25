#!/usr/bin/env python3
"""Opt-in Balanced Quality & Timing evidence. No orders, writes to main or sends.

The generic 300% leverage ceiling is deliberately unchanged. Missing mandatory
evidence is REVIEW_REQUIRED, never evidence of financial health or normal CASH.
Snapshots are keyed by actual filing receipt and statement division, not ticker.
"""
import hashlib
import json
import re
import time
import urllib.error
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from dart_financial_screen import (api_json, corp_codes, annual_receipt,
    latest_interim_filing, evaluate_accounts, extract_metric, integer)
from dart_interim_periods import evaluate_interim
from c3_top5_financial_selection import finite

MODEL = "BALANCED_QUALITY_TIMING_V1"
WEIGHTS = {"safety": 30, "cash_quality": 25, "growth": 20,
           "capital_efficiency": 15, "improvement": 10}


def annual_statement_version(payload, year, asof, corp_code=None, ticker=None):
    """Separate body corrections from attachment-only correction receipts.

    OpenDART explicitly defines [첨부정정]/[첨부추가] as attachment changes.
    They remain visible and require review; they are not primary XBRL IDs.
    Body corrections are never skipped in favour of an older financial report.
    """
    eligible=[]
    for row in payload.get('list',[]):
        title=str(row.get('report_nm','')).replace(' ','')
        if '사업보고서' not in title or f'({year}.12)' not in title:continue
        receipt=str(row.get('rcept_no',''));received=str(row.get('rcept_dt',''))
        if not re.fullmatch(r'\d{14}',receipt) or received!=receipt[:8]:
            raise ValueError('FILING_RECEIPT_DATE_MISMATCH')
        if received>asof.strftime('%Y%m%d'):continue
        if (corp_code and row.get('corp_code') not in (None,'',corp_code) or
            ticker and row.get('stock_code') not in (None,'',ticker)):
            raise ValueError('FILING_COMPANY_MISMATCH')
        eligible.append(row)
    bodies=[r for r in eligible if not re.match(r'^\[(첨부정정|첨부추가)\]',str(r.get('report_nm','')).replace(' ',''))]
    if not bodies:return None
    selected=max(bodies,key=lambda r:(r['rcept_dt'],r['rcept_no']))
    if '철' in str(selected.get('rm','')):raise ValueError('WITHDRAWN_ANNUAL_FILING_REVIEW')
    amendments=[r for r in eligible if r not in bodies and r['rcept_no']>selected['rcept_no']]
    return dict(financial_receipt=selected['rcept_no'],financial_filing_date=selected['rcept_dt'],
        selected_body=selected,latest_disclosure=max(eligible,key=lambda r:r['rcept_no']),
        attachment_amendments=sorted(amendments,key=lambda r:r['rcept_no']),
        attachment_review_required=bool(amendments),
        policy='PRIMARY_BODY_XBRL_WITH_SEPARATE_ATTACHMENT_REVIEW')
METRICS = {
    "cash": ("BS", {"ifrs-full_CashAndCashEquivalents", "ifrs_CashAndCashEquivalents"}),
    "current_assets": ("BS", {"ifrs-full_CurrentAssets", "ifrs_CurrentAssets"}),
    "current_liabilities": ("BS", {"ifrs-full_CurrentLiabilities", "ifrs_CurrentLiabilities"}),
    "inventory": ("BS", {"ifrs-full_Inventories", "ifrs_Inventories"}),
    "receivables": ("BS", {"ifrs-full_TradeAndOtherCurrentReceivables", "ifrs-full_TradeReceivables"}),
    "ocf": ("CF", {"ifrs-full_CashFlowsFromUsedInOperatingActivities", "ifrs_CashFlowsFromUsedInOperatingActivities"}),
    "icf": ("CF", {"ifrs-full_CashFlowsFromUsedInInvestingActivities", "ifrs_CashFlowsFromUsedInInvestingActivities"}),
    "capex": ("CF", {"ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "ifrs-full_PurchaseOfPropertyPlantAndEquipment"}),
    "interest_expense": ("IS", {"ifrs-full_InterestExpense", "ifrs_InterestExpense"}),
    "net_income": ("IS", {"ifrs-full_ProfitLoss", "ifrs_ProfitLoss"}),
    "tax_expense": ("IS", {"ifrs-full_IncomeTaxExpenseContinuingOperations", "ifrs_IncomeTaxExpenseContinuingOperations"}),
    "pretax_profit": ("IS", {"ifrs-full_ProfitLossBeforeTax", "ifrs_ProfitLossBeforeTax"}),
    "depreciation": ("CF", {"ifrs-full_AdjustmentsForDepreciationExpense", "dart_AdjustmentsForDepreciationExpense"}),
    "amortisation": ("CF", {"ifrs-full_AdjustmentsForAmortisationExpense", "dart_AdjustmentsForAmortisationExpense"}),
    "interest_expense_cf_adjustment": ("CF", {"dart_AdjustmentsForInterestExpenses"}),
    "equity": ("BS", {"ifrs-full_Equity", "ifrs_Equity"}),
    "revenue": ("IS", {"ifrs-full_Revenue", "ifrs_Revenue", "ifrs-full_RevenueFromContractsWithCustomers"}),
    "operating_profit": ("IS", {"dart_OperatingIncomeLoss"}),
}
# Sum disjoint borrowing categories only. Do not sum a total and its components.
DEBT_IDS = (
    {"ifrs-full_ShorttermBorrowings", "ifrs_ShorttermBorrowings"},
    {"dart_CurrentPortionOfLongTermBorrowings", "ifrs-full_CurrentPortionOfLongtermBorrowings"},
    {"dart_LongTermBorrowingsGross", "ifrs-full_LongtermBorrowings"},
    {"dart_BondsIssued", "ifrs-full_BondsIssued"},
)
DEBT_LABELS = ({'단기차입금'}, {'유동성장기차입금'},
               {'장기차입금'}, {'사채'})
NONCURRENT_LOAN_IDS = {'ifrs-full_NoncurrentPortionOfOtherNoncurrentBorrowings',
                      'ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived'}
NONCURRENT_BOND_IDS = {'ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued'}
CURRENT_BOND_IDS = {'dart_CurrentPortionOfBonds', 'dart_CurrentPortionOfConvertibleBonds', 'ifrs-full_CurrentPortionOfNoncurrentBondsIssued'}


def retry_network(operation, pause=time.sleep):
    """Retry transient transport failures only; never retry invalid evidence.

    Do not log authenticated request URLs or use an older successful statement
    to conceal a failed current request.
    """
    for attempt in range(3):
        try:
            return operation()
        except urllib.error.HTTPError as exc:
            if exc.code not in (408, 429, 500, 502, 503, 504) or attempt==2:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt==2:
                raise
        pause(attempt+1)


def direct_account(rows, ids, section, field, labels):
    """Exact direct-account fallback for issuer extension tags, never proxies.

    Do not reinterpret total financial liabilities, finance costs, interest paid
    or CF add-backs as borrowings/IS interest. A conflicting direct value is an
    integrity error, not an opportunity to select a favourable alias.
    """
    options=[section] if section!='IS' else ['IS','CIS']
    for statement in options:
        selected=[]
        for row in rows:
            if row.get('sj_div')!=statement or str(row.get('account_detail') or '').strip() not in ('','-'):
                continue
            tag=str(row.get('account_id') or '')
            label=re.sub(r'\s+','',str(row.get('account_nm') or ''))
            custom=not tag.startswith(('ifrs_','ifrs-full_','dart_'))
            if tag in ids or (custom and label in labels):
                value=integer(row.get(field))
                if value is not None:
                    selected.append({'account_id':tag,'account_name':row.get('account_nm'),
                                     'statement':statement,'field':field,'value':value})
        if selected:
            values={row['value'] for row in selected}
            state='VALID' if len(values)==1 and min(values)>=0 else 'CONFLICT_OR_INVALID_SIGN'
            return {'value':selected[0]['value'] if state=='VALID' else None,
                    'state':state,'sources':selected}
    return {'value':None,'state':'UNAVAILABLE','sources':[]}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()


class SnapshotCache:
    """Create-only sanitized JSON snapshots; live filing lists are never cached.

    A fresh list selects the receipt on every run. New receipts invalidate only
    the corresponding statements. No successful payload is reused for a failed
    request. Snapshot observation timestamps are never backdated to filing dates.
    """
    def __init__(self, root, clock=None):
        self.root = Path(root)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.events = []
        self.session_id = os.environ.get('GITHUB_RUN_ID') or uuid.uuid4().hex

    def observe(self, identity, payload, source_observed_at=None):
        """Preserve public API responses, scoped to one run; no cross-run list reuse."""
        record=dict(identity=identity,payload=payload,sha256=digest(payload),
            observed_at=self.clock().isoformat(),source_observed_at=source_observed_at,
            run_id=self.session_id)
        folder=self.root/'observations'/self.session_id
        folder.mkdir(parents=True,exist_ok=True)
        path=folder/(digest(identity)+'_'+digest(record)+'.json')
        path.write_text(json.dumps(record,ensure_ascii=False,sort_keys=True))

    def observed_or_request(self, endpoint, params, key, request, receipt=None):
        """Reuse a response only within this run's already-fresh observation."""
        identity=dict(endpoint=endpoint,params=params,receipt=receipt)
        folder=self.root/'observations'/self.session_id
        records=[]
        for path in folder.glob(digest(identity)+'_*.json'):
            record=json.loads(path.read_text())
            if (record.get('identity')!=identity or record.get('run_id')!=self.session_id or
                digest(record.get('payload'))!=record.get('sha256')):
                raise ValueError('OBSERVATION_INTEGRITY_ERROR')
            records.append(record)
        if records:
            return max(records,key=lambda r:r['observed_at'])['payload']
        return self.request(endpoint,params,key,request,receipt)

    def listed_corps(self, key, fetch):
        """24-hour routing-only cache, independently checked by company.json.

        Corporate-code routing is not dated financial evidence. Never backdate
        its observation time. Expired maps are refreshed, with no stale fallback.
        """
        path = self.root/'listed_corp_codes.json'
        now = self.clock()
        if path.is_file():
            record = json.loads(path.read_text())
            if record.get('endpoint')!='corpCode.xml' or digest(record.get('mapping'))!=record.get('sha256'):
                raise ValueError('CORPCODE_CACHE_INTEGRITY_ERROR')
            age = (now-datetime.fromisoformat(record['observed_at'])).total_seconds()
            if 0<=age<86400:
                self.events.append({'endpoint':'corpCode.xml','state':'HIT','observed_at':record['observed_at'],
                                    'sha256':record['sha256']})
                return record['mapping']
        mapping = retry_network(lambda:fetch(key))
        if not mapping or not isinstance(mapping,dict) or any(
            not re.fullmatch(r'[0-9A-Z]{6}',str(k)) or not re.fullmatch(r'\d{8}',str(v)) for k,v in mapping.items()):
            raise ValueError('INVALID_CORPCODE_MAP')
        self.root.mkdir(parents=True, exist_ok=True)
        record = dict(endpoint='corpCode.xml',observed_at=now.isoformat(),sha256=digest(mapping),mapping=mapping)
        path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True))
        self.events.append({k:v for k,v in {**record,'state':'FETCH'}.items() if k!='mapping'})
        return mapping

    def request(self, endpoint, params, key, request, receipt=None):
        identity = {"endpoint": endpoint, "params": params, "receipt": receipt}
        path = self.root / (digest(identity) + ".json")
        if receipt and path.is_file():
            record = json.loads(path.read_text())
            if record.get("identity") != identity or digest(record["payload"]) != record.get("sha256"):
                raise ValueError("CACHE_INTEGRITY_ERROR")
            self.events.append({"endpoint": endpoint, "state": "HIT", "sha256": record["sha256"],
                                "observed_at": record["observed_at"]})
            self.observe(identity,record['payload'],record['observed_at'])
            return record["payload"]
        try:
            payload = retry_network(lambda:request(endpoint, params, key))
        except Exception as exc:
            self.events.append({'endpoint':endpoint,'state':'ERROR','expected_receipt':receipt,
                'observed_at':self.clock().isoformat(),'error_class':type(exc).__name__,
                'transport_reason_class':type(getattr(exc,'reason',None)).__name__})
            self.events[-1]['http_status']=getattr(exc,'code',None)
            raise
        if not isinstance(payload, dict):
            raise ValueError("INVALID_DART_RESPONSE")
        self.observe(identity,payload)
        stamp = self.clock().isoformat()
        self.events.append({"endpoint": endpoint, "state": "FETCH", "observed_at": stamp,
                            "sha256": digest(payload), "api_status": payload.get("status")})
        if endpoint == 'fnlttSinglAcntAll.json':
            rows=payload.get('list', [])
            self.events[-1].update(expected_receipt=receipt,
                returned_receipts=sorted({str(r.get('rcept_no', '')) for r in rows}),
                payload_row_count=len(rows))
        cacheable = (endpoint != "fnlttSinglAcntAll.json" or
                     (isinstance(payload.get("list"), list) and payload["list"] and
                      all(r.get("rcept_no") == receipt for r in payload["list"])))
        if receipt and payload.get("status") == "000" and cacheable:
            self.root.mkdir(parents=True, exist_ok=True)
            record = {"identity": identity, "observed_at": stamp,
                      "sha256": digest(payload), "payload": payload}
            with path.open("x", encoding="utf-8") as stream:
                json.dump(record, stream, ensure_ascii=False, sort_keys=True)
        elif receipt and payload.get('status') == '000' and not cacheable:
            # Preserve mismatching public statements as quarantined evidence,
            # never as a reusable snapshot for the requested historical filing.
            quarantine=self.root/'quarantine'
            quarantine.mkdir(parents=True,exist_ok=True)
            record={'identity':identity,'observed_at':stamp,'sha256':digest(payload),
                    'payload':payload,'state':'RECEIPT_MISMATCH_NOT_REUSABLE'}
            invalid=quarantine/(digest(record)+'.json')
            with invalid.open('x',encoding='utf-8') as stream:
                json.dump(record,stream,ensure_ascii=False,sort_keys=True)
        return payload


def sector_profile(industry, name=""):
    code = str(industry or "")
    if not re.fullmatch(r"\d{2,6}", code):
        return "UNKNOWN"
    if code.startswith("21") or any(x in name.upper() for x in
        ("제약", "바이오", "파마", "약품", "신약", "PHARMA", "BIOTECH")):
        return "EXCLUDED_PHARMA_BIO"
    if code[:2] in ("64", "65", "66"):
        return "FINANCIAL_SPECIAL_MODEL_REQUIRED"
    if code.startswith("61"):
        return "TELECOM"
    if code[:2] in ("41", "42"):
        return "CONSTRUCTION"
    if code.startswith("35"):
        return "UTILITY"
    if code[:2] in ("45", "46", "47"):
        return "RETAIL_CONSUMER"
    if code[:2] in ("30", "31"):
        return "AUTO_PARTS"
    if code.startswith("26"):
        return "SEMICON_EQUIPMENT"
    if 10 <= int(code[:2]) <= 34:
        return "MANUFACTURING"
    return "OTHER_NONFINANCIAL"


def validate_payload(payload, division, year, report, receipt, asof, corp_code=None):
    """Reject restatements/other periods before assigning a filing date to values."""
    if payload.get("status") != "000" or not isinstance(payload.get("list"), list):
        raise ValueError("DART_NO_DATA" if payload.get("status") in ("013", "014") else "DART_API_ERROR")
    if not payload["list"]:
        raise ValueError("EMPTY_STATEMENT")
    for row in payload["list"]:
        if corp_code and row.get('corp_code')!=corp_code:
            raise ValueError('STATEMENT_COMPANY_MISMATCH')
        actual = str(row.get("rcept_no", ""))
        if actual != receipt or not re.fullmatch(r"\d{14}", actual):
            raise ValueError("STATEMENT_RECEIPT_MISMATCH_OR_RESTATEMENT")
        if date(int(actual[:4]), int(actual[4:6]), int(actual[6:8])) > asof:
            raise ValueError("FUTURE_STATEMENT_RECEIPT")
        if str(row.get("bsns_year")) != str(year) or row.get("reprt_code") != report:
            raise ValueError("STATEMENT_PERIOD_MISMATCH")
        if row.get("fs_div") not in (None, "", division) or row.get("currency") not in (None, "", "KRW"):
            raise ValueError("STATEMENT_DIVISION_OR_CURRENCY_MISMATCH")


def statement_metrics(payload, interim=False, ticker=None, division=None):
    rows = payload["list"]
    result = {}
    sources={};payload_sha=digest(payload)
    for name, (section, ids) in METRICS.items():
        for prefix, field in (("", "thstrm_amount"), ("previous_", "frmtrm_amount"),
                              ("before_previous_", "bfefrmtrm_amount")):
            if interim and section == "IS":
                field = {"thstrm_amount": "thstrm_add_amount", "frmtrm_amount": "frmtrm_add_amount",
                         "bfefrmtrm_amount": "bfefrmtrm_add_amount"}[field]
            result[prefix + name] = extract_metric(rows, ids, section, field)
            matched=[r for r in rows if r.get('account_id') in ids and
                     r.get('sj_div') in ([section] if section!='IS' else ['IS','CIS']) and integer(r.get(field)) is not None]
            sources[prefix+name]=dict(source_type='OPENDART_STATEMENT_API',payload_sha256=payload_sha,
                verification_state='API_VALUE_AVAILABLE' if result[prefix+name] is not None else 'UNAVAILABLE_OR_AMBIGUOUS',
                accounts=[dict(ticker=ticker,corp_code=r.get('corp_code'),receipt_no=r.get('rcept_no'),
                    filing_date=str(r.get('rcept_no',''))[:8],fiscal_year=r.get('bsns_year'),report_code=r.get('reprt_code'),
                    division=r.get('fs_div') or division,statement=r.get('sj_div'),account_id=r.get('account_id'),
                    account_name=r.get('account_nm'),field=field,raw_value=r.get(field),value_krw=integer(r.get(field)),
                    unit=r.get('currency','KRW')) for r in matched])
    result['metric_sources']=sources
    result['finance_costs']=extract_metric(rows,{'ifrs-full_FinanceCosts','ifrs_FinanceCosts'},'IS',
                                         'thstrm_add_amount' if interim else 'thstrm_amount')
    result["period_basis"] = "INTERIM_YTD_CF_AND_IS_CURRENT_BS" if interim else "ANNUAL_FULL_YEAR"
    # A missing borrowing category may mean an omitted zero or an unrecognised
    # custom XBRL tag. Never silently treat it as zero.
    aliases=[DEBT_IDS[0],DEBT_IDS[1],DEBT_IDS[2]|NONCURRENT_LOAN_IDS,DEBT_IDS[3]|NONCURRENT_BOND_IDS]
    debt_evidence=[direct_account(rows,ids,'BS','thstrm_amount',labels)
                   for ids,labels in zip(aliases,DEBT_LABELS)]
    debt=[source['value'] for source in debt_evidence]
    current_bonds=direct_account(rows,CURRENT_BOND_IDS,'BS','thstrm_amount',{'유동성사채'})
    interest_field='thstrm_add_amount' if interim else 'thstrm_amount'
    interest=direct_account(rows,METRICS['interest_expense'][1],'IS',interest_field,{'이자비용'})
    result['interest_expense']=interest['value']
    result['direct_account_evidence']={'short_term_borrowings':debt_evidence[0],
        'current_portion_long_term_borrowings':debt_evidence[1],
        'long_term_borrowings':debt_evidence[2],'bonds_issued':debt_evidence[3],
        'interest_expense':interest,'current_portion_bonds':current_bonds}
    result['account_validation_errors']=[name for name,source in result['direct_account_evidence'].items()
        if source['state']=='CONFLICT_OR_INVALID_SIGN']
    first=rows[0] if rows else {}
    source_identity=dict(ticker=ticker,corp_code=first.get('corp_code'),receipt_no=first.get('rcept_no'),
        filing_date=str(first.get('rcept_no',''))[:8],fiscal_year=first.get('bsns_year'),
        report_code=first.get('reprt_code'),division=first.get('fs_div') or division,unit='KRW',
        period_basis=result['period_basis'],payload_sha256=payload_sha)
    sources['interest_expense']=dict(**source_identity,source_type='OPENDART_DIRECT_IS_ACCOUNT',**interest)
    bond_tags={r['account_id'] for r in debt_evidence[3]['sources']}
    noncurrent_bonds=bool(bond_tags & NONCURRENT_BOND_IDS)
    bond_scope_ok=(current_bonds['value'] is not None if noncurrent_bonds else current_bonds['value'] in (None,0))
    known_tags=set.union(*aliases,CURRENT_BOND_IDS)
    accounted={(r['account_id'],re.sub(r'\s+','',str(r['account_name'] or '')))
               for e in debt_evidence+[current_bonds] for r in e['sources']}
    unresolved=[{'account_id':r.get('account_id'),'account_name':r.get('account_nm'),
                 'value':integer(r.get('thstrm_amount'))} for r in rows if r.get('sj_div')=='BS'
        and str(r.get('account_detail') or '').strip() in ('','-')
        and any(term in str(r.get('account_nm') or '') for term in ('차입','사채'))
        and r.get('account_id') not in known_tags
        and (r.get('account_id'),re.sub(r'\s+','',str(r.get('account_nm') or ''))) not in accounted]
    result['unresolved_debt_accounts']=unresolved
    result['current_portion_bonds']=current_bonds['value']
    result['debt_scope_state']=('UNCLASSIFIED_BORROWING_ACCOUNTS' if unresolved else
        'BOND_CLASSIFICATION_RECONCILIATION_REQUIRED' if not bond_scope_ok else 'DIRECT_COMPONENT_SCOPE')
    result["interest_bearing_debt_excluding_leases"] = (
        sum(debt)+(current_bonds['value'] if noncurrent_bonds else 0)
        if all(finite(x) and x>=0 for x in debt) and bond_scope_ok and not unresolved else None)
    result["debt_components"] = debt
    sources['interest_bearing_debt_excluding_leases']=dict(**source_identity,
        source_type='DISJOINT_DIRECT_BS_COMPONENTS',value=result['interest_bearing_debt_excluding_leases'],
        verification_state='VALID' if result['interest_bearing_debt_excluding_leases'] is not None else 'REVIEW_REQUIRED',
        components=result['direct_account_evidence'],scope=result['debt_scope_state'])
    return derived_metrics(result)


def derived_metrics(result):
    """Recompute the unchanged ratios after an independently verified note fill."""
    capex = result["capex"]
    # The standard Purchase... tag denotes an outflow. Negative net cash flow
    # lines or custom net-capex tags are not assumed to be a gross acquisition.
    result["fcf"] = result["ocf"] - capex if finite(result["ocf"]) and finite(capex) and capex >= 0 else None
    result["fcf_definition"] = "OCF minus gross cash purchase of property, plant and equipment; excludes intangible acquisitions"
    debt_total, cash = result["interest_bearing_debt_excluding_leases"], result["cash"]
    result["net_debt_excluding_leases"] = debt_total - cash if finite(debt_total) and finite(cash) else None
    op, interest = result["operating_profit"], result["interest_expense"]
    result["interest_coverage"] = op / interest if finite(op) and finite(interest) and interest > 0 else None
    result["interest_free_verified"] = interest == 0
    cf_interest=result.get('interest_expense_cf_adjustment')
    result['interest_coverage_cf_proxy']=op/cf_interest if finite(op) and finite(cf_interest) and cf_interest > 0 else None
    result['interest_coverage_cf_proxy_definition']='Operating profit / CF reconciliation interest-expense adjustment; not verified IS interest expense and never substitutes for mandatory coverage evidence'
    ca, cl = result["current_assets"], result["current_liabilities"]
    result["current_ratio"] = ca / cl if finite(ca) and finite(cl) and cl > 0 else None
    eq, peq, income = result["equity"], result["previous_equity"], result["net_income"]
    result["roe_pct"] = income / ((eq + peq) / 2) * 100 if all(finite(x) for x in (eq, peq, income)) and min(eq, peq) > 0 else None
    result['roe_definition']='Net income for reported period / average current and previous BS equity; interim ratio is not annualized'
    tax, pretax = result["tax_expense"], result["pretax_profit"]
    tax_rate = tax / pretax if finite(tax) and finite(pretax) and pretax > 0 else None
    capital = eq + debt_total - cash if all(finite(x) for x in (eq, debt_total, cash)) else None
    result["roic_pct"] = op * (1 - tax_rate) / capital * 100 if finite(op) and capital and capital > 0 and tax_rate is not None and 0 <= tax_rate <= 1 else None
    result["roic_definition"] = "Operating profit * (1-effective tax rate) / year-end (equity + borrowings excluding leases - cash); not average invested capital"
    dep, amort = result["depreciation"], result["amortisation"]
    result["ebitda_proxy"] = op + dep + amort if all(finite(x) for x in (op, dep, amort)) and min(dep, amort) >= 0 else None
    ebitda = result["ebitda_proxy"]
    nd = result["net_debt_excluding_leases"]
    result["net_debt_to_ebitda_proxy"] = nd / ebitda if finite(nd) and finite(ebitda) and ebitda > 0 else None
    return result


def quality_score(m, annual, interim, recent=None):
    """Explicit /100 weights; missing features reduce coverage, not earned score.

    A partial normalized score can rank only against the same feature signature.
    It is labelled partial and is never an eligibility threshold.
    """
    parts = {k: {"earned": 0.0, "available": 0, "maximum": v} for k, v in WEIGHTS.items()}
    features, missing, feature_scores = [], [], {}
    def add(group, name, weight, fraction):
        if fraction is None:
            missing.append(name)
            return
        features.append(name)
        parts[group]["available"] += weight
        parts[group]["earned"] += weight * max(0, min(1, fraction))
        feature_scores[name] = {"group": group, "weight": weight,
                               "earned": weight * max(0, min(1, fraction))}
    def positive_ratio(a, b):
        return a / b if finite(a) and finite(b) and b > 0 else None
    eq_ratio = positive_ratio(annual.get("equity_krw"), annual.get("assets_krw"))
    add("safety", "equity_ratio", 10, eq_ratio / .5 if eq_ratio is not None else None)
    cash_metrics=recent if recent is not None else m
    cr = cash_metrics.get("current_ratio")
    add("safety", "current_ratio", 10, cr / 2 if cr is not None else (1 if cash_metrics.get("current_liabilities") == 0 else None))
    ic = m.get("interest_coverage")
    add("safety", "interest_coverage", 10, ic / 5 if ic is not None else (1 if m.get("interest_free_verified") else None))
    ocf, op = cash_metrics.get("ocf"), cash_metrics.get("operating_profit")
    add("cash_quality", "positive_ocf", 12, float(ocf > 0) if finite(ocf) else None)
    conversion = positive_ratio(ocf, op)
    add("cash_quality", "ocf_to_operating_profit", 8, conversion)
    fcf = cash_metrics.get("fcf")
    add("cash_quality", "positive_fcf", 5, float(fcf >= 0) if finite(fcf) else None)
    for name, field in (("sales_growth", "yoy_revenue_pct"), ("operating_growth", "yoy_operating_profit_pct")):
        value = interim.get(field)
        # Turnaround is scored from actual signs, never an invented growth %.
        if name == "operating_growth" and value is None and finite(interim.get("current_ytd_operating_profit_krw")) and finite(interim.get("previous_ytd_operating_profit_krw")):
            fraction = float(interim["current_ytd_operating_profit_krw"] > interim["previous_ytd_operating_profit_krw"])
        else:
            fraction = .5 + value / 40 if finite(value) else None
        add("growth", name, 10, fraction)
    for name, weight, target in (("roe_pct", 8, 15), ("roic_pct", 7, 12)):
        v = m.get(name)
        add("capital_efficiency", name, weight, v / target if finite(v) else None)
    prev = cash_metrics.get("previous_ocf")
    add("improvement", "ocf_improvement", 5, float(ocf >= prev) if finite(ocf) and finite(prev) else None)
    now_margin, prev_op, prev_rev = interim.get("ytd_operating_margin_pct"), interim.get("previous_ytd_operating_profit_krw"), interim.get("previous_ytd_revenue_krw")
    prev_margin = positive_ratio(prev_op, prev_rev)
    add("improvement", "recent_margin_improvement", 5, float(now_margin >= prev_margin * 100) if finite(now_margin) and prev_margin is not None else None)
    earned = sum(x["earned"] for x in parts.values())
    available = sum(x["available"] for x in parts.values())
    return {"weights": WEIGHTS, "components": parts, "earned_points": round(earned, 3),
            "available_points": available, "maximum_points": 100,
            "score": round(earned / available * 100, 3) if available else None,
            "complete": available == 100, "missing_features": missing,
            "comparison_signature": sorted(features), "feature_scores": feature_scores,
            "cash_quality_basis": cash_metrics.get('period_basis','ANNUAL_FULL_YEAR'),
            "capital_efficiency_basis": 'ANNUAL_NOT_ANNUALIZED_INTERIM',
            "score_is_eligibility_gate": False}


def assess(annual, interim, m, audit, sector, recent=None):
    missing, failed, flags = [], [], []
    def require(name, value):
        if not finite(value):
            missing.append(name)
            return False
        return True
    for name in ("equity_krw", "liabilities_krw", "operating_profit_krw", "assets_krw"):
        require(name, annual.get(name))
    eq, liabilities, op = (annual.get(k) for k in ("equity_krw", "liabilities_krw", "operating_profit_krw"))
    if finite(liabilities) and liabilities < 0:
        missing.append("INVALID_NEGATIVE_LIABILITIES")
    if finite(eq) and eq <= 0:
        failed.append("NONPOSITIVE_EQUITY")
    generic_leverage = sector not in ('UNKNOWN', 'FINANCIAL_SPECIAL_MODEL_REQUIRED')
    if generic_leverage and finite(eq) and eq > 0 and finite(liabilities) and liabilities / eq > 3:
        failed.append("EXISTING_LEVERAGE_CEILING_300PCT")
    if finite(op) and op <= 0:
        previous_op = annual.get('previous_operating_profit_krw',m.get('previous_operating_profit'))
        current_op = interim.get('current_ytd_operating_profit_krw')
        if not finite(previous_op) or not finite(current_op):
            missing.append('LOSS_PERSISTENCE_OR_TURNAROUND_EVIDENCE')
        elif current_op > 0:
            flags.append('ANNUAL_LOSS_CURRENT_YTD_POSITIVE')
        elif previous_op <= 0:
            failed.append('TWO_ANNUAL_LOSSES_AND_CURRENT_YTD_LOSS')
        else:
            # One annual loss and one interim observation do not by themselves
            # establish persistent insolvency; more recovery context is needed.
            missing.append('LOSS_RECOVERY_CONTEXT_REVIEW')
    if recent is not None:
        for name in ("equity", "cash", "current_assets", "current_liabilities", "ocf"):
            require("recent_" + name, recent.get(name))
        if finite(recent.get("equity")) and recent["equity"] <= 0:
            failed.append("RECENT_NONPOSITIVE_EQUITY")
        if (generic_leverage and finite(recent.get('equity')) and recent['equity'] > 0 and
            finite(recent.get('liabilities')) and recent['liabilities']/recent['equity'] > 3):
            failed.append('RECENT_EXISTING_LEVERAGE_CEILING_300PCT')
        if recent.get("current_ratio") is not None and recent["current_ratio"] < 1:
            missing.append("RECENT_LIQUIDITY_MITIGANTS_REVIEW")
        if finite(recent.get("ocf")) and recent["ocf"] < 0:
            flags.append("RECENT_NEGATIVE_OCF_NOT_AUTOMATIC_EXCLUSION")
        if finite(recent.get('ocf')) and finite(recent.get('previous_ocf')) and recent['ocf'] < recent['previous_ocf']:
            flags.append('RECENT_OCF_WEAKENING')
            current_op=interim.get('current_ytd_operating_profit_krw')
            previous_op=interim.get('previous_ytd_operating_profit_krw')
            if finite(current_op) and finite(previous_op) and current_op > previous_op:
                flags.append('RECENT_EARNINGS_CASH_FLOW_DIVERGENCE')
    for name in ("ocf", "current_assets", "current_liabilities", "cash", "interest_expense"):
        require(name, m.get(name))
    require("interest_bearing_debt_excluding_leases", m.get("interest_bearing_debt_excluding_leases"))
    if any(finite(m.get(k)) and m[k] < 0 for k in ("current_assets", "current_liabilities", "cash", "interest_expense")):
        missing.append("INVALID_NEGATIVE_BALANCE_OR_INTEREST")
    if m.get("current_ratio") is not None and m["current_ratio"] < 1:
        flags.append("CURRENT_RATIO_BELOW_ONE_REVIEW")
        if recent is None:
            missing.append("LIQUIDITY_MITIGANTS_OR_DEBT_MATURITY_REVIEW")
    if m.get("interest_coverage") is not None and m["interest_coverage"] < 1:
        flags.append("INTEREST_COVERAGE_BELOW_ONE_REVIEW")
        missing.append("DEBT_SERVICE_MITIGANTS_REVIEW")
    if finite(m.get("ocf")) and m["ocf"] < 0:
        flags.append("NEGATIVE_OCF_NOT_AUTOMATIC_EXCLUSION")
    if finite(m.get("fcf")) and m["fcf"] < 0:
        flags.append("NEGATIVE_FCF_CAPEX_OR_WORKING_CAPITAL_REVIEW")
    if interim.get("quality") == "INTERIM_PROFIT_OR_SALES_WEAKENING":
        flags.append("RECENT_EARNINGS_SLOWDOWN")
    if audit.get("state") == "FAIL":
        failed.extend(audit.get("reasons", ["AUDIT_RISK"]))
    elif audit.get("state") != "PASS":
        missing.append("AUDIT_OPINION_AND_GOING_CONCERN_REVIEW")
    if sector in ("UNKNOWN", "FINANCIAL_SPECIAL_MODEL_REQUIRED"):
        missing.append("SECTOR_MODEL_REQUIRED")
    if sector == "EXCLUDED_PHARMA_BIO":
        failed.append("PHARMA_BIO_EXCLUDED")
    if sector == "CONSTRUCTION":
        # These cannot be inferred safely from the primary BS/IS/CF accounts.
        missing.extend(["PF_AND_CONTINGENT_GUARANTEES", "CONTRACT_RECEIVABLES_AND_UNBILLED_WORK",
                        "LOSS_PROVISIONS_AND_ORDER_BACKLOG_QUALITY"])
    if sector in ("MANUFACTURING", "AUTO_PARTS", "SEMICON_EQUIPMENT", "RETAIL_CONSUMER"):
        for name in ("inventory", "previous_inventory", "receivables", "previous_receivables"):
            if not finite(m.get(name)):
                flags.append('SUPPLEMENTARY_' + name.upper() + '_UNAVAILABLE')
        sales_growth = annual.get("sales_yoy_pct")
        for name in ("inventory", "receivables"):
            now, prev = m.get(name), m.get("previous_" + name)
            if finite(now) and finite(prev) and prev > 0 and finite(sales_growth) and (now / prev - 1) * 100 > sales_growth + 20:
                flags.append(name.upper() + "_GROWTH_EXCEEDS_SALES")
    if sector in ("TELECOM", "UTILITY"):
        require('net_debt_excluding_leases',m.get('net_debt_excluding_leases'))
        for name in ('capex','fcf'):
            if not finite(m.get(name)):
                flags.append('SUPPLEMENTARY_' + name.upper() + '_UNAVAILABLE')
        if sector == "TELECOM":
            for name in ("ebitda_proxy", "net_debt_to_ebitda_proxy"):
                if not finite(m.get(name)):
                    flags.append('SUPPLEMENTARY_' + name.upper() + '_UNAVAILABLE')
            flags.append("EBITDA_AND_NET_DEBT_EXCLUDE_LEASE_ADJUSTMENTS")
    # This function receives validated source accounts. A decisive exclusion is
    # not cancelled by unavailable indicators that cannot reverse that finding.
    return {"state": "FAIL" if failed else "REVIEW_REQUIRED" if missing else "PASS",
            "mandatory_missing": sorted(set(missing)), "hard_failures": failed,
            "additional_checks_not_required_for_rejection": sorted(set(missing)) if failed else [],
            "risk_flags": flags, "sector_profile": sector,
            "leverage_ceiling_pct": 300, "leverage_policy_changed": False}


def audit_evidence(payload, year, receipt):
    if payload.get("status") != "000":
        return {"state": "REVIEW_REQUIRED", "api_status": payload.get("status")}
    rows=[]
    for row in payload.get('list',[]):
        label=re.sub(r'\s+','',str(row.get('bsns_year','')))
        # Actual DART responses label fiscal periods as 제43기(당기), etc.
        # stlm_dt may be repeated for prior-year rows and cannot identify them.
        current=label==str(year) or ('(당기)' in label and
            str(row.get('stlm_dt','')).replace('.','-').startswith(str(year)))
        if row.get('rcept_no')==receipt and current:
            rows.append(row)
    if not rows:
        return {"state":"REVIEW_REQUIRED","reason":"AUDIT_CURRENT_YEAR_UNAVAILABLE"}
    opinions=[re.sub(r'\s+','',str(row.get('adt_opinion',''))) for row in rows]
    metadata={'opinions':opinions,'current_row_count':len(rows)}
    if any(opinion in ('부적정의견','의견거절','한정의견','부적정','한정') for opinion in opinions):
        return {**metadata,'state':'FAIL','reasons':['MODIFIED_AUDIT_OPINION']}
    if any(opinion not in ('적정','적정의견') for opinion in opinions):
        return {**metadata,'state':'REVIEW_REQUIRED','reason':'UNKNOWN_CURRENT_AUDIT_OPINION'}
    for row in rows:
        notes=' '.join(str(row.get(k) or '') for k in ('emphs_matter','adt_reprt_spcmnt_matter'))
        if any(term in notes for term in ('계속기업','계속 기업','존속능력')):
            return {**metadata,'state':'REVIEW_REQUIRED','reason':'GOING_CONCERN_TEXT_REVIEW'}
        if not notes.replace('-','').strip():
            return {**metadata,'state':'REVIEW_REQUIRED','reason':'AUDIT_NOTES_UNAVAILABLE'}
    return {**metadata,'state':'PASS',
        'going_concern_basis':'ALL_CURRENT_STRUCTURED_EMPHASIS_ROWS_SCREENED_FULL_REPORT_NOT_REVIEWED'}


def related_audit_receipt(payload, version):
    """Use only a catalogue-verified body or its attachment amendment.

    This does not verify the amended attachment's contents or clear its review
    requirement. An arbitrary API receipt remains a source mismatch.
    """
    primary=version['financial_receipt']
    if payload.get('status')!='000':return primary
    allowed={primary}|{r['rcept_no'] for r in version['attachment_amendments']}
    returned={str(r.get('rcept_no','')) for r in payload.get('list',[])}
    if not returned & allowed:raise ValueError('AUDIT_RECEIPT_MISMATCH')
    return max(returned & allowed)


def collect_balanced(asof, stocks, key, today, cache, request=api_json, get_corps=corp_codes, document_fetch=None):
    """Read only filings <= signal date; API rows must match selected receipts."""
    result = {"model": MODEL, "asof": asof.strftime("%Y%m%d"), "researched": [], "excluded": [],
              "status": "FAILED_FINANCIAL_EVIDENCE", "financial_data_complete": False,
              "financial_observed_on": today.isoformat(), "point_in_time_snapshot_verified": False,
              "data_source": "OPENDART_OFFICIAL_PUBLIC_FILING_API",
              "api_base": "https://opendart.fss.or.kr/api/",
              "collection_time_utc": datetime.now(timezone.utc).isoformat(),
              "unverified_checks": ["IMMUTABLE_HISTORICAL_PIT_AT_SELECTION", "FULL_AUDIT_REPORT_TEXT",
                                    "CONSTRUCTION_PF_AND_CONTINGENCIES", "LEASE_ADJUSTED_NET_DEBT"],
              "historical_restatement_policy": "EXACT_RECEIPT_MATCH_REQUIRED_OBSERVATION_NOT_BACKDATED",
              "trade_approved": False}
    if asof > today:
        result["error"] = "INVALID_DATE_OR_DART_KEY"
        return result
    if not stocks:
        result.update(status="NO_CANDIDATES", financial_data_complete=True)
        return result
    if not key or not re.fullmatch(r"[A-Za-z0-9]{40}", key):
        result["error"] = "INVALID_DATE_OR_DART_KEY"
        return result
    try:
        corps = cache.listed_corps(key, get_corps)
    except Exception as exc:
        result["error"] = "CORPCODE_" + type(exc).__name__
        result['transport_reason_class'] = type(getattr(exc,'reason',None)).__name__
        return result
    for stock in stocks:
        ticker, name = stock["ticker"], stock.get("name", "")
        item = {"ticker": ticker, "name": name, "financial_model": MODEL,
                "financial_evidence_complete": False, "financial_evidence_state": "INSUFFICIENT_DATA",
                "financial_risk_gate_pass": False, "exclusion_reasons": []}
        start = len(cache.events)
        try:
            company = corps.get(ticker)
            if not company:
                raise ValueError("NO_LISTED_CORP_CODE")
            item['corp_code']=company
            info = cache.request("company.json", {"corp_code": company}, key, request)
            if info.get("status") != "000" or info.get("stock_code") != ticker:
                raise ValueError("COMPANY_INDUSTRY_UNVERIFIED")
            profile = sector_profile(info.get("induty_code"), name)
            item.update(industry_code=info.get('induty_code'),sector_profile=profile)
            filings = {"status": "000", "list": []}
            page = 1
            while True:
                part = cache.request("list.json", {"corp_code": company,
                    "bgn_de": f"{asof.year-3}0101", "end_de": asof.strftime("%Y%m%d"),
                    "pblntf_ty": "A", "last_reprt_at": "N", "page_count": 100, "page_no": page}, key, request)
                if part.get("status") != "000":
                    raise ValueError("FILINGS_API_ERROR")
                filings["list"].extend(part.get("list", []))
                total = int(part.get("total_page", 1))
                if total > 10:
                    raise ValueError("FILING_PAGINATION_BUDGET_EXCEEDED")
                if page >= total:
                    break
                page += 1
            annuals = [(y, annual_statement_version(filings, y, asof, company, ticker)) for y in (asof.year-1, asof.year-2)]
            annuals = [(y, r) for y, r in annuals if r]
            if not annuals:
                raise ValueError("NO_DATED_ANNUAL")
            year, version = max(annuals,key=lambda r:r[0])
            received=datetime.strptime(version['financial_filing_date'],'%Y%m%d').date()
            receipt=version['financial_receipt']
            item['disclosure_version']=version
            interim_filing = latest_interim_filing(filings, asof)
            if not interim_filing or interim_filing["fiscal_year"] <= year:
                raise ValueError("CURRENT_INTERIM_UNAVAILABLE_REVIEW")
            item.update(requested_annual_receipt_no=receipt,requested_annual_filing_date=received.isoformat(),
                        requested_interim_receipt_no=interim_filing['receipt_no'],annual_fiscal_year=year)
            if profile=='FINANCIAL_SPECIAL_MODEL_REQUIRED':
                item['risk_assessment']={'state':'REVIEW_REQUIRED','mandatory_missing':['SECTOR_MODEL_REQUIRED'],
                    'hard_failures':[],'risk_flags':[],'sector_profile':profile}
                if request is api_json or document_fetch is not None:
                    from c3_balanced_source_probe import DocumentCache
                    from c3_dart_document_evidence import download_document
                    from c3_dart_normalization import insurance_capital_disclosure
                    documents=DocumentCache(cache.root/'documents')
                    try:
                        binary=documents.get('document.xml',interim_filing['receipt_no'],interim_filing['report_code'],
                            key,document_fetch or download_document)
                        capital=insurance_capital_disclosure(binary,dict(ticker=ticker,corp_code=company,
                            receipt_no=interim_filing['receipt_no'],fiscal_year=interim_filing['fiscal_year'],
                            report_code=interim_filing['report_code'],filing_date=interim_filing['receipt_date']))
                        item['insurance_capital_evidence']=capital
                        item['risk_assessment']['mandatory_missing'].append(capital['reason'])
                    finally:
                        cache.events.extend(documents.events)
                raise ValueError('FINANCIAL_SECTOR_MODEL_REQUIRED')
            annual = None
            for division in ("CFS", "OFS"):
                item['statement_division_attempted']=division
                params = {"corp_code": company, "bsns_year": str(year), "reprt_code": "11011", "fs_div": division}
                payload = cache.request("fnlttSinglAcntAll.json", params, key, request, receipt)
                if payload.get("status") in ("013", "014") and division == "CFS":
                    continue
                validate_payload(payload, division, year, "11011", receipt, asof, company)
                annual = evaluate_accounts(payload, division)
                # Invalid CFS evidence is never replaced with a convenient OFS pass.
                if annual.get("status") != "DATED_ANNUAL_RESEARCH_ONLY":
                    raise ValueError("ANNUAL_" + annual["status"])
                break
            if annual is None:
                raise ValueError("ANNUAL_UNAVAILABLE")
            m = statement_metrics(payload,ticker=ticker,division=division)
            if m['account_validation_errors']:
                raise ValueError('DIRECT_FINANCIAL_ACCOUNT_CONFLICT_OR_SIGN')
            interim_payload = cache.request("fnlttSinglAcntAll.json", {"corp_code": company,
                "bsns_year": str(interim_filing["fiscal_year"]), "reprt_code": interim_filing["report_code"],
                "fs_div": division}, key, request, interim_filing["receipt_no"])
            validate_payload(interim_payload, division, interim_filing["fiscal_year"],
                             interim_filing["report_code"], interim_filing["receipt_no"], asof, company)
            interim = evaluate_interim(interim_payload, division, interim_filing)
            if interim["status"] != "DATED_INTERIM_YTD_RESEARCH_ONLY":
                raise ValueError("INTERIM_" + interim["status"])
            recent_metrics = statement_metrics(interim_payload, interim=True,ticker=ticker,division=division)
            if recent_metrics['account_validation_errors']:
                raise ValueError('RECENT_DIRECT_FINANCIAL_ACCOUNT_CONFLICT_OR_SIGN')
            current_bs = {k: extract_metric(interim_payload["list"], ids, "BS", "thstrm_amount")
                          for k, ids in (("assets", {"ifrs-full_Assets", "ifrs_Assets"}),
                                         ("liabilities", {"ifrs-full_Liabilities", "ifrs_Liabilities"}))}
            recent_metrics.update(current_bs)
            eq_now = recent_metrics.get("equity")
            if not all(finite(v) for v in (*current_bs.values(), eq_now)) or current_bs["assets"] <= 0 or current_bs["liabilities"] < 0 or abs(current_bs["assets"]-current_bs["liabilities"]-eq_now)/current_bs["assets"] > .01:
                raise ValueError("RECENT_BALANCE_SHEET_INCOMPLETE_OR_INCONSISTENT")
            audit_payload = cache.request("accnutAdtorNmNdAdtOpinion.json", {"corp_code": company,
                "bsns_year": str(year), "reprt_code": "11011"}, key, request, receipt)
            if audit_payload.get('status') not in ('000','013','014'):
                raise ValueError('AUDIT_API_ERROR')
            audit_receipt=related_audit_receipt(audit_payload,version)
            audit = audit_evidence(audit_payload, year, audit_receipt)
            audit['source_receipt_no']=audit_receipt
            # Source enrichment never replaces already-valid direct metrics or
            # an adverse audit opinion. A transport failure remains an error.
            needs_notes=any(m.get(k) is None for k in ('interest_expense','interest_bearing_debt_excluding_leases')) or audit.get('state')=='REVIEW_REQUIRED'
            decisive=assess(annual,interim,m,audit,profile,recent_metrics)['state']=='FAIL'
            if needs_notes and not decisive and (request is api_json or document_fetch is not None):
                from c3_dart_normalization import enrich_financial_notes
                enriched=enrich_financial_notes(cache,key,dict(ticker=ticker,corp_code=company,
                    receipt_no=receipt,fiscal_year=year,report_code='11011',division=division,
                    filing_date=received.isoformat()),dict(Assets=annual['assets_krw'],
                    Liabilities=annual['liabilities_krw'],Equity=annual['equity_krw']),m,audit,document_fetch)
                item['note_normalization']=enriched
                derived_metrics(m)
            risk = assess(annual, interim, m, audit, profile, recent_metrics)
            interest_source=m.get('metric_sources',{}).get('interest_expense',{})
            uncertainty=interest_source.get('reconciliation',{}).get('maximum_rounding_error_krw',0)
            if uncertainty and finite(m.get('interest_expense')) and m['interest_expense']>0:
                lower=m['operating_profit']/(m['interest_expense']+uncertainty)
                m['interest_coverage_min_verified']=lower
                if lower<1 and risk['state']!='FAIL':
                    risk['mandatory_missing']=sorted(set(risk['mandatory_missing']+['INTEREST_COVERAGE_ROUNDING_REVIEW']))
                    risk['state']='REVIEW_REQUIRED'
            if version['attachment_review_required']:
                risk['mandatory_missing']=sorted(set(risk['mandatory_missing']+['ATTACHMENT_AMENDMENT_CONTENT_REVIEW']))
                if risk['state']!='FAIL':risk['state']='REVIEW_REQUIRED'
            quality = quality_score(m, annual, interim, recent_metrics)
            item.update(annual_status=annual["status"], interim_status=interim["status"],
                filing_date=received.isoformat(), annual_receipt_no=receipt,
                interim_filing_date=interim_filing["receipt_date"], interim_receipt_no=interim_filing["receipt_no"],
                statement_division=division, annual_fiscal_year=year, industry_code=info.get("induty_code"),
                financial_quality=annual.get("financial_quality"), interim_quality=interim.get("quality"),
                equity_krw=annual.get("equity_krw"), liabilities_krw=annual.get("liabilities_krw"),
                operating_profit_krw=annual.get("operating_profit_krw"),
                liabilities_to_equity_pct=round(annual["liabilities_krw"] / annual["equity_krw"] * 100, 3) if annual["equity_krw"] > 0 else None,
                latest_liabilities_to_equity_pct=round(current_bs['liabilities']/eq_now*100,3) if eq_now > 0 else None,
                financial_evidence_complete=risk["state"] != "REVIEW_REQUIRED",
                financial_evidence_state=('REJECTED_FINANCIAL_RISK' if risk['state']=='FAIL' else
                                          'COMPLETE' if risk['state']=='PASS' else 'REVIEW_REQUIRED'),
                financial_verdict=('REJECTED_FINANCIAL_RISK' if risk['state']=='FAIL' else
                                   'QUALIFIED' if risk['state']=='PASS' else 'REVIEW_REQUIRED'),
                decision_basis={'source_validated':True,'statement_division':division,
                    'annual_sha256':digest(payload),'interim_sha256':digest(interim_payload),
                    'annual_assets_krw':annual['assets_krw'],
                    'recent_assets_krw':current_bs['assets'],
                    'recent_liabilities_krw':current_bs['liabilities'],
                    'sector_profile':profile,'industry_code':info.get('induty_code')},
                supplementary_data_complete=not bool(risk['mandatory_missing']),
                financial_risk_gate_pass=risk["state"] == "PASS", risk_assessment=risk,
                exclusion_reasons=risk["hard_failures"], quality_100=quality, metrics=m,
                audit=audit, recent_metrics=recent_metrics, annual_trend={k: m.get(k) for k in ("revenue", "previous_revenue", "before_previous_revenue",
                    "operating_profit", "previous_operating_profit", "before_previous_operating_profit")},
                recent_slowdown_flag=interim.get("quality") == "INTERIM_PROFIT_OR_SALES_WEAKENING")
        except Exception as exc:
            # Never print exceptions containing authenticated request URLs.
            item["error"] = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r"[A-Z0-9_]+", str(exc)) else type(exc).__name__
            item["financial_evidence_state"] = "API_ERROR" if not isinstance(exc, ValueError) or "API_ERROR" in item["error"] else "REVIEW_REQUIRED"
            if any(word in item['error'] for word in ('MISMATCH','INCONSISTENT','FUTURE_STATEMENT','CACHE_INTEGRITY')):
                item['financial_evidence_state']='VALIDATION_ERROR'
            unavailable=('NO_LISTED_CORP_CODE','NO_DATED_ANNUAL','CURRENT_INTERIM_UNAVAILABLE_REVIEW',
                         'DART_NO_DATA','EMPTY_STATEMENT','ANNUAL_UNAVAILABLE','FINANCIAL_SECTOR_MODEL_REQUIRED',
                         'WITHDRAWN_ANNUAL_FILING_REVIEW')
            item['financial_verdict']='REVIEW_REQUIRED' if item['error'] in unavailable or 'INCOMPLETE' in item['error'] else 'ERROR'
            if item['financial_evidence_state'] in ('API_ERROR','VALIDATION_ERROR'):
                item['financial_verdict']='ERROR'
        # Add the public PASS spelling without changing legacy QUALIFIED fields.
        item['financial_decision']='PASS' if item.get('financial_verdict')=='QUALIFIED' else item.get('financial_verdict')
        item["source_observations"] = cache.events[start:]
        (result["researched"] if item["financial_risk_gate_pass"] else result["excluded"]).append(item)
    items = result["researched"] + result["excluded"]
    result['decision_counts']={state:sum(x.get('financial_verdict')==state for x in items)
        for state in ('QUALIFIED','REJECTED_FINANCIAL_RISK','REVIEW_REQUIRED','ERROR')}
    result["financial_data_complete"] = all(x.get('financial_verdict') in ('QUALIFIED','REJECTED_FINANCIAL_RISK') for x in items)
    result['decision_evidence_complete']=result['financial_data_complete']
    if result["financial_data_complete"]:
        result["status"] = "PARTIAL_OR_FAILED_FINANCIAL_GATE" if result["excluded"] else "FINANCIAL_RESEARCH_GATE_PASSED"
    elif result['decision_counts']['ERROR']:
        result['status']='ERROR'
    else:
        result['status']='REVIEW_REQUIRED'
    return result


def rejection_proven(item, asof):
    """Check the decisive evidence, independent of supplementary score coverage."""
    basis=item.get('decision_basis',{})
    if (item.get('annual_status')!='DATED_ANNUAL_RESEARCH_ONLY' or
        item.get('interim_status')!='DATED_INTERIM_YTD_RESEARCH_ONLY' or
        item.get('financial_risk_gate_pass') is not False or
        item.get('risk_assessment',{}).get('state')!='FAIL' or
        item.get('exclusion_reasons') != item.get('risk_assessment',{}).get('hard_failures')):
        return False
    if (basis.get('source_validated') is not True or basis.get('statement_division') not in ('CFS','OFS') or
        basis.get('statement_division') != item.get('statement_division') or
        any(not re.fullmatch(r'[a-f0-9]{64}',str(basis.get(k,''))) for k in ('annual_sha256','interim_sha256'))):
        return False
    try:
        day=datetime.strptime(asof,'%Y%m%d').date()
        for receipt_key,date_key in (('annual_receipt_no','filing_date'),('interim_receipt_no','interim_filing_date')):
            receipt=item[receipt_key];received=date.fromisoformat(item[date_key])
            if not re.fullmatch(r'\d{14}',receipt) or received>day or receipt[:8] != received.strftime('%Y%m%d'):
                return False
    except (KeyError,TypeError,ValueError):
        return False
    def balance_valid(a,l,e):
        return all(finite(v) for v in (a,l,e)) and a>0 and l>=0 and abs(a-l-e)/a<=.01
    a,l,e=basis.get('annual_assets_krw'),item.get('liabilities_krw'),item.get('equity_krw')
    ra,rl,re_=basis.get('recent_assets_krw'),basis.get('recent_liabilities_krw'),item.get('recent_metrics',{}).get('equity')
    if not balance_valid(a,l,e) or not balance_valid(ra,rl,re_):
        return False
    profile=basis.get('sector_profile')
    if profile != sector_profile(basis.get('industry_code'),item.get('name','')):
        return False
    generic=profile not in ('UNKNOWN','FINANCIAL_SPECIAL_MODEL_REQUIRED')
    metrics=item.get('metrics',{});recent=item.get('recent_metrics',{})
    checks={'NONPOSITIVE_EQUITY':e<=0,'RECENT_NONPOSITIVE_EQUITY':re_<=0,
        'EXISTING_LEVERAGE_CEILING_300PCT':generic and e>0 and l/e>3,
        'RECENT_EXISTING_LEVERAGE_CEILING_300PCT':generic and re_>0 and rl/re_>3,
        'TWO_ANNUAL_LOSSES_AND_CURRENT_YTD_LOSS':all(finite(v) and v<=0 for v in
            (item.get('operating_profit_krw'),metrics.get('previous_operating_profit'),recent.get('operating_profit'))),
        'MODIFIED_AUDIT_OPINION':item.get('audit',{}).get('state')=='FAIL' and any(
            opinion in ('부적정의견','의견거절','한정의견','부적정','한정') for opinion in item.get('audit',{}).get('opinions',[])),
        'PHARMA_BIO_EXCLUDED':profile=='EXCLUDED_PHARMA_BIO'}
    reasons=item.get('risk_assessment',{}).get('hard_failures',[])
    return bool(reasons) and all(checks.get(reason) is True for reason in reasons)
