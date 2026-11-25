"""Source-scoped note recovery; synthetic inputs never represent market picks."""
import copy
import unittest
from xml.etree import ElementTree as ET
from c3_dart_document_evidence import reported_finance_facts
from c3_dart_normalization import current_column, audit_note
from c3_dart_note_reconciliation import column_financing_debt, standard_interest_breakdown, primary_debt_covered


def finance_xml(entity='00111111',year=2025,member='ConsolidatedMember',unit='KRW',extra=''):
    return ET.fromstring(f'''<x:xbrl xmlns:x="http://www.xbrl.org/2003/instance" xmlns:d="http://xbrl.org/2006/xbrldi"
      xmlns:f="http://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full" xmlns:t="http://dart.fss.or.kr/taxonomy/2025-03-31/dart">
      <x:unit id="won"><x:measure>iso4217:{unit}</x:measure></x:unit>
      <x:context id="annual"><x:entity><x:identifier>{entity}</x:identifier><x:segment>
      <d:explicitMember dimension="ifrs-full:ConsolidatedAndSeparateFinancialStatementsAxis">ifrs-full:{member}</d:explicitMember>
      <d:explicitMember dimension="ifrs-full:CarryingAmountAccumulatedDepreciationAmortisationAndImpairmentAndGrossCarryingAmountAxis">dart:ReportedAmountMember</d:explicitMember>{extra}
      </x:segment></x:entity><x:period><x:startDate>{year}-01-01</x:startDate><x:endDate>{year}-12-31</x:endDate></x:period></x:context>
      <f:FinanceCosts contextRef="annual" unitRef="won" decimals="-3">10000</f:FinanceCosts>
      <t:InterestExpenseFinanceExpense contextRef="annual" unitRef="won" decimals="-3">4000</t:InterestExpenseFinanceExpense>
      <t:AdjustmentsForInterestExpense contextRef="annual" unitRef="won" decimals="-3">9999</t:AdjustmentsForInterestExpense>
      </x:xbrl>''')


def interest_table():
    return dict(scale=1000,metadata='금융수익 및 금융비용 당기 (단위:천원)',context='금융비용',rows=[
        ['','','','공시금액'],['금융비용','금융비용','금융비용','(10)'],
        ['금융비용','이자비용(금융원가)','이자비용(금융원가)','(4)'],
        ['금융비용','이자비용(금융원가)','차입금이자비용','(1)'],
        ['금융비용','이자비용(금융원가)','리스부채이자비용','(3)'],
        ['금융비용','기타금융비용','기타금융비용','(6)']])


def debt_table():
    return dict(scale=1000,metadata='당기 (단위:천원)',context='재무활동에서 생기는 부채의 조정',rows=[
        ['','','리스 부채','차입금','전환사채'],
        ['기초부채','기초부채','4','10','20'],
        ['변동','변동','','',''],
        ['변동','차입금 증가','0','5','0'],
        ['변동','차입금 상환','(1)','(2)','0'],
        ['기말부채','기말부채','3','13','20']])


class NoteReconciliationTests(unittest.TestCase):
    def facts(self,**kwargs):return reported_finance_facts(finance_xml(**kwargs),'CFS',2025,'00111111')

    def test_whole_entity_reported_amount_is_explicit_standard_is_not_cashflow_proxy(self):
        facts=self.facts()
        self.assertEqual({f['account'] for f in facts},{'FinanceCosts','InterestExpenseFinanceExpense'})
        self.assertTrue(all(f['precision_krw']==1000 and f['entity']=='00111111' for f in facts))

    def test_wrong_entity_year_scope_currency_or_business_segment_are_rejected(self):
        variants=[dict(entity='00999999'),dict(year=2024),dict(member='SeparateMember'),dict(unit='USD'),
                  dict(extra='<d:explicitMember dimension="entity:BusinessAxis">entity:Subsidiary</d:explicitMember>')]
        for kwargs in variants:self.assertEqual(self.facts(**kwargs),[])

    def test_unknown_fact_precision_and_custom_interest_do_not_fill(self):
        root=finance_xml()
        for n in root:
            if n.tag.endswith('InterestExpenseFinanceExpense'):n.set('decimals','unknown')
        self.assertEqual([f['account'] for f in reported_finance_facts(root,'CFS',2025,'00111111')],['FinanceCosts'])
        self.assertIsNone(standard_interest_breakdown(interest_table(),10000,[]))

    def test_hierarchical_note_parent_and_children_not_double_counted(self):
        fact=standard_interest_breakdown(interest_table(),10000,self.facts())
        self.assertEqual(fact['value'],4000)
        self.assertFalse(fact['reconciliation']['parent_child_double_counted'])
        self.assertTrue(fact['reconciliation']['other_costs_not_used_as_interest'])

    def test_note_child_conflict_standard_mismatch_or_cross_context_blocks(self):
        table=interest_table();table['rows'][4][-1]='(6)'
        self.assertIsNone(standard_interest_breakdown(table,10000,self.facts()))
        self.assertIsNone(standard_interest_breakdown(interest_table(),99000,self.facts()))
        facts=self.facts();facts[-1]['context']='different'
        self.assertIsNone(standard_interest_breakdown(interest_table(),10000,facts))

    def test_explicit_current_amount_header_supports_four_columns_not_prior_period(self):
        table=interest_table();self.assertEqual(current_column(table),3)
        table['metadata']='전기 (단위:천원)';self.assertIsNone(current_column(table))

    def test_complete_financing_columns_reconcile_without_inventing_total_or_zeros(self):
        f=column_financing_debt(debt_table())
        self.assertEqual(f['value'],33000);self.assertEqual(f['precision_krw'],2000)
        self.assertEqual(f['reconciliation']['maximum_rounding_error_krw'],1000)

    def test_financing_missing_cell_unknown_column_bad_movement_or_prior_blocks(self):
        variants=[]
        for row,col,value in [(2,2,'5'),(3,3,''),(0,4,'기타금융부채'),(4,3,'(9)')]:
            t=debt_table();t['rows'][row][col]=value;variants.append(t)
        t=debt_table();t['metadata']='전기 (단위:천원)';variants.append(t)
        for t in variants:self.assertIsNone(column_financing_debt(t),str(t))

    def test_financing_parent_child_double_count_blocks(self):
        t=debt_table();t['rows'].insert(3,['변동','변동','(1)','3','0'])
        self.assertIsNone(column_financing_debt(t))

    def test_zero_debt_without_explicit_total_keeps_existing_review_policy(self):
        t=debt_table()
        for row in t['rows'][1:]:
            if any(row[2:]):row[3:]=['0','0']
        self.assertIsNone(column_financing_debt(t))

    def metrics(self):
        return dict(unresolved_debt_accounts=[dict(account_id='ifrs-full_CurrentLoansReceivedAndCurrentPortionOfNoncurrentLoansReceived',value=5000)],
            direct_account_evidence=dict(long_term_borrowings=dict(state='VALID',value=8000,sources=[dict(account_id='long',value=8000)]),
                current_portion_bonds=dict(state='VALID',value=20000,sources=[dict(account_id='bond',value=20000)])))

    def fact(self):
        f=column_financing_debt(debt_table())
        return dict(value=f['value'],provenance=dict(method=f['method'],reconciliation=f['reconciliation'],source_table_scale=1000))

    def test_known_current_loan_rollup_and_bond_match_complete_note_groups(self):
        self.assertTrue(primary_debt_covered(self.metrics(),self.fact()))

    def test_unclassified_account_overlap_or_wrong_group_blocks(self):
        variants=[]
        m=self.metrics();m['unresolved_debt_accounts'][0]['account_id']='entity:CustomBorrowing';variants.append(m)
        m=self.metrics();m['direct_account_evidence']['short_term_borrowings']=dict(value=5000,state='VALID',sources=[]);variants.append(m)
        m=self.metrics();m['unresolved_debt_accounts'][0]['value']=9000;variants.append(m)
        for m in variants:self.assertFalse(primary_debt_covered(m,self.fact()))

    def test_group_rounding_tolerance_is_bounded_by_number_of_summed_columns(self):
        t=debt_table();t['rows'][0][3:]=['단기차입금','장기차입금']
        f=column_financing_debt(t);fact=dict(provenance=dict(method=f['method'],reconciliation=f['reconciliation'],source_table_scale=1000))
        m=self.metrics();m['unresolved_debt_accounts'][0]['value']=25000
        m['direct_account_evidence'].pop('current_portion_bonds')
        m['direct_account_evidence']['long_term_borrowings']['sources'][0]['value']=8625
        self.assertTrue(primary_debt_covered(m,fact))
        m['direct_account_evidence']['long_term_borrowings']['sources'][0]['value']=10001
        self.assertFalse(primary_debt_covered(m,fact))

    def audit(self,term='11',year=2025,opinion='적정',concern='없음'):
        return ET.fromstring(f'''<DOCUMENT><COVER>사업보고서 (제 {term} 기)<TU AUNIT="PERIODFROM" AUNITVALUE="{year}0101"/><TU AUNIT="PERIODTO" AUNITVALUE="{year}1231"/></COVER>
        <TABLE><TR><TH>사업연도</TH><TH>구분</TH><TH>감사의견</TH><TH>계속기업 불확실성</TH><TH>강조사항</TH></TR>
        <TR><TD>제11기</TD><TD>연결감사보고서</TD><TD>{opinion}</TD><TD>{concern}</TD><TD>없음</TD></TR>
        <TR><TD>제10기</TD><TD>연결감사보고서</TD><TD>적정</TD><TD>없음</TD><TD>없음</TD></TR></TABLE></DOCUMENT>''')

    def test_audit_fiscal_term_is_bound_to_cover_and_exact_year(self):
        self.assertEqual(audit_note(self.audit(),'CFS',2025)['state'],'PASS')
        self.assertEqual(audit_note(self.audit(year=2024),'CFS',2025)['state'],'REVIEW_REQUIRED')
        self.assertEqual(audit_note(self.audit(term='12'),'CFS',2025)['state'],'REVIEW_REQUIRED')

    def test_audit_adverse_and_going_concern_are_preserved(self):
        self.assertEqual(audit_note(self.audit(opinion='의견거절'),'CFS',2025)['state'],'FAIL')
        self.assertEqual(audit_note(self.audit(concern='유의적 불확실성'),'CFS',2025)['state'],'REVIEW_REQUIRED')


if __name__=='__main__':unittest.main()
