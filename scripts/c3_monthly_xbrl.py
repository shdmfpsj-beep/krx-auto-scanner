"""One-off, receipt-pinned XBRL input adapter. No selection or scoring rules."""
import io
import re
import zipfile
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

XBRLI = 'http://www.xbrl.org/2003/instance'
XBRLDI = 'http://xbrl.org/2006/xbrldi'
XLINK = 'http://www.w3.org/1999/xlink'
CONCEPTS = {'Revenue', 'RevenueFromContractsWithCustomers', 'OperatingIncomeLoss',
            'Assets', 'Liabilities', 'Equity'}

def local(value):
    return str(value).rsplit('}', 1)[-1].rsplit(':', 1)[-1]

def division(member):
    value = str(member).lower().replace('_', '').replace('-', '')
    if 'nonconsolidated' in value or 'separate' in value:
        return 'OFS'
    if 'consolidatedmember' in value or 'consolidatedfinancialstatementsmember' in value:
        return 'CFS'
    return None

def consolidation_axis(value):
    return 'consolidatedandseparatefinancialstatementsaxis' in re.sub('[^a-z]', '', str(value).lower())

def parse_archive(raw):
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        raise ValueError('ORIGINAL_XBRL_NOT_ZIP')
    facts = defaultdict(set)
    diagnostics = {'instances': [], 'contexts': [], 'defaults': [], 'facts_kept': 0}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) > 1000 or sum(e.file_size for e in entries) > 300_000_000:
            raise ValueError('ORIGINAL_XBRL_ARCHIVE_LIMIT')
        defaults = set()
        # The consolidation default must come from the actual filed linkbase,
        # not a guess based on a context name or today's financial API.
        for entry in entries:
            if not entry.filename.lower().endswith('.xml') or entry.file_size > 20_000_000:
                continue
            data = archive.read(entry)
            if b'dimension-default' not in data:
                continue
            try:
                root = ET.fromstring(data)
            except ET.ParseError:
                continue
            for link in root:
                locations = {n.get('{'+XLINK+'}label'): n.get('{'+XLINK+'}href', '')
                             for n in link if local(n.tag) == 'loc'}
                for arc in link:
                    if not arc.get('{'+XLINK+'}arcrole', '').endswith('/dimension-default'):
                        continue
                    axis = locations.get(arc.get('{'+XLINK+'}from'), '')
                    member = locations.get(arc.get('{'+XLINK+'}to'), '')
                    if consolidation_axis(axis) and division(member):
                        defaults.add(division(member))
        diagnostics['defaults'] = sorted(defaults)
        for entry in entries:
            if not entry.filename.lower().endswith(('.xbrl', '.xml')):
                continue
            if entry.file_size > 64_000_000:
                continue
            data = archive.read(entry)
            if not re.search(rb'<(?:[A-Za-z0-9_-]+:)?xbrl[\s>]', data[:15000]):
                continue
            root = ET.fromstring(data)
            if local(root.tag) != 'xbrl':
                continue
            diagnostics['instances'].append(entry.filename)
            units = set()
            for unit in root.findall('{'+XBRLI+'}unit'):
                measures = unit.findall('{'+XBRLI+'}measure')
                if len(measures) == 1 and local(measures[0].text) == 'KRW':
                    units.add(unit.get('id'))
            hint = ('CFS' if re.search(r'(^|[/_.-])cfs([/_.-]|$)', entry.filename, re.I)
                    else 'OFS' if re.search(r'(^|[/_.-])ofs([/_.-]|$)', entry.filename, re.I) else None)
            contexts = {}
            for context in root.findall('{'+XBRLI+'}context'):
                members = context.findall('.//{'+XBRLDI+'}explicitMember')
                if context.findall('.//{'+XBRLDI+'}typedMember'):
                    continue
                if any(not consolidation_axis(m.get('dimension', '')) for m in members):
                    continue
                choices = {division(m.text) for m in members}
                scope = (next(iter(choices)) if len(choices) == 1 and None not in choices
                         else next(iter(defaults)) if not members and len(defaults) == 1
                         else hint if not members else None)
                period = context.find('{'+XBRLI+'}period')
                if period is None:
                    continue
                instant = period.findtext('{'+XBRLI+'}instant')
                start = period.findtext('{'+XBRLI+'}startDate')
                end = period.findtext('{'+XBRLI+'}endDate')
                if instant:
                    kind, begin, finish = 'instant', '', instant[:10]
                elif start and end:
                    kind, begin, finish = 'duration', start[:10], end[:10]
                else:
                    continue
                if len(diagnostics['contexts']) < 24:
                    diagnostics['contexts'].append({'id': context.get('id'), 'scope': scope,
                        'members': [dict(axis=m.get('dimension'), member=m.text) for m in members],
                        'kind': kind, 'start': begin, 'end': finish})
                if scope:
                    contexts[context.get('id')] = (scope, kind, begin, finish)
            for fact in root:
                concept = local(fact.tag)
                namespace = fact.tag.split('}')[0].lower()
                if (concept not in CONCEPTS or fact.get('unitRef') not in units or
                    fact.get('contextRef') not in contexts or
                    not ('ifrs' in namespace or 'dart.fss' in namespace)):
                    continue
                try:
                    number = Decimal((fact.text or '').strip().replace(',', ''))
                    if not number.is_finite() or number != number.to_integral_value():
                        continue
                except InvalidOperation:
                    continue
                facts[contexts[fact.get('contextRef')] + (concept,)].add(int(number))
                diagnostics['facts_kept'] += 1
    return dict(facts), diagnostics

def payload_for(facts, year, report_code, scope, receipt):
    month = {'11011': '12', '11013': '03', '11012': '06', '11014': '09'}[report_code]
    last = '31' if month in ('03', '12') else '30'
    end, previous_end = f'{year}-{month}-{last}', f'{year-1}-{month}-{last}'
    def value(concepts, instant=False, previous=False):
        finish = previous_end if previous else end
        begin = '' if instant else f'{year-1 if previous else year}-01-01'
        found = set()
        for concept in concepts:
            found.update(facts.get((scope, 'instant' if instant else 'duration', begin, finish, concept), set()))
        return str(next(iter(found))) if len(found) == 1 else ''
    rows = []
    specs = [('ifrs-full_Revenue', ['Revenue', 'RevenueFromContractsWithCustomers'], False),
             ('dart_OperatingIncomeLoss', ['OperatingIncomeLoss'], False),
             ('ifrs-full_Assets', ['Assets'], True),
             ('ifrs-full_Liabilities', ['Liabilities'], True), ('ifrs-full_Equity', ['Equity'], True)]
    for account, concepts, instant in specs:
        current, previous = value(concepts, instant), value(concepts, instant, True)
        row = dict(rcept_no=receipt, bsns_year=str(year), reprt_code=report_code,
                   fs_div=scope, currency='KRW', account_id=account,
                   sj_div='BS' if instant else 'IS', account_detail='-',
                   thstrm_amount=current, frmtrm_amount=previous)
        if report_code != '11011' and not instant:
            row.update(thstrm_add_amount=current, frmtrm_add_amount=previous)
        rows.append(row)
    return {'status': '000', 'list': rows}
