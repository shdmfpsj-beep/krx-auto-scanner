import copy,csv,gzip,hashlib,json,tempfile,unittest
from pathlib import Path
from c3_selection_scope_v5 import classify,unique_index,selection_features,rank_stocks,freeze_forward,load_sources,current_histories
from c3_classification_collect_v5 import kind_rows,sector_rows


def fixture():
    p=dict(ticker="0220W0",market="KOSPI",asof="2026-11-04")
    b=dict(security_group="주권",share_kind="보통주",market="KOSPI")
    k=dict(market="KOSPI",listed_date="2026-08-25",industry="반도체 제조업",products="반도체 장비")
    n=[dict(sector="반도체와반도체장비",market="KOSPI",krx_tradable_status="tradable")]
    return p,b,k,n


class SelectionScopeTests(unittest.TestCase):
    def test_preferred_is_not_promoted_by_complete_industries(self):
        p,b,k,n=fixture();b["share_kind"]="우선주"
        self.assertEqual(classify(p,b,k,n),"COMMON_SHARE_UNCONFIRMED_OR_SPECIAL")

    def test_biotech_hidden_in_generic_kind_industry_is_blocked(self):
        p,b,k,n=fixture();k.update(industry="특수 목적용 기계 제조업",products="GasScrubber");n[0]["sector"]="생물공학"
        self.assertEqual(classify(p,b,k,n),"PHARMA_BIOTECH_EXCLUDED")

    def test_explicit_drug_business_overrides_nonbio_secondary(self):
        p,b,k,n=fixture();k["products"]="반도체 장비 및 항암 치료제"
        self.assertEqual(classify(p,b,k,n),"PHARMA_BIOTECH_EXCLUDED")

    def test_biofuel_is_not_guessed_as_pharmaceutical_from_its_name(self):
        p,b,k,n=fixture();k["products"]="바이오디젤 및 연료";n[0]["sector"]="석유와가스"
        self.assertEqual(classify(p,b,k,n),"VERIFIED_NONBIO_COMMON_AS_REPORTED")

    def test_micro_semiconductor_is_not_a_cro_clinical_service(self):
        p,b,k,n=fixture();k["products"]="Micro/Mini-LED Display Driver IC"
        self.assertEqual(classify(p,b,k,n),"VERIFIED_NONBIO_COMMON_AS_REPORTED")
        k["products"]="임상 CRO서비스";self.assertEqual(classify(p,b,k,n),"PHARMA_BIOTECH_EXCLUDED")

    def test_missing_or_conflicting_industry_remains_unverified(self):
        p,b,k,n=fixture();self.assertEqual(classify(p,b,k,[]),"SECONDARY_INDUSTRY_MISSING_OR_CONFLICT")
        n.append(dict(n[0],sector="기계"));self.assertEqual(classify(p,b,k,n),"SECONDARY_INDUSTRY_MISSING_OR_CONFLICT")

    def test_spac_is_not_an_operating_business(self):
        p,b,k,n=fixture();k.update(industry="금융 지원 서비스업",products="기업인수합병")
        self.assertEqual(classify(p,b,k,n),"SPAC_WITHOUT_OPERATING_BUSINESS")

    def test_market_conflict_and_suspended_security_are_excluded(self):
        p,b,k,n=fixture();n[0]["market"]="KOSDAQ"
        self.assertEqual(classify(p,b,k,n),"SECONDARY_MARKET_CONFLICT")
        n[0].update(market="KOSPI",krx_tradable_status="suspended")
        self.assertEqual(classify(p,b,k,n),"CURRENT_KRX_TRADABILITY_UNCONFIRMED")

    def test_alpha_short_code_is_preserved_and_duplicate_rejected(self):
        self.assertIn("0220W0",unique_index([dict(ticker="0220W0")]))
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):unique_index([dict(ticker="0220W0")]*2)

    def test_kind_parser_preserves_product_and_alphanumeric_code(self):
        body='<table><tr><th>종목코드</th><th>업종</th><th>주요제품</th><th>상장일</th><th>회사명</th></tr><tr><td>0220W0</td><td>반도체 제조업</td><td>반도체</td><td>2026-08-25</td><td>예시</td></tr></table>'.encode('euc-kr')
        row=kind_rows(body,"KOSPI")[0];self.assertEqual(row["ticker"],"0220W0");self.assertEqual(row["products"],"반도체")

    def test_secondary_collection_does_not_keep_nxt_or_price_fields(self):
        payload=dict(hasNext=False,items=[dict(itemCode="0220W0",itemName="예시",marketType="KOSPI",krx=dict(tradableStatus="tradable",currentPrice=100),nxt=dict(currentPrice=120))])
        rows,_=sector_rows(dict(code="1",name="기계"),lambda url:(json.dumps(payload).encode(),{}))
        self.assertNotIn("nxt",rows[0]);self.assertNotIn("currentPrice",rows[0])

    def test_stock_selection_does_not_require_a_confirmed_pivot_or_entry(self):
        past=[dict(close=100+i,turnover_krw=1000) for i in range(65)]
        self.assertIsNotNone(selection_features(past,0))

    def test_future_return_cannot_reorder_selected_names(self):
        pool=[dict(ticker=t,turnover20=v,rs20=2,sector_excess20=1) for t,v in [('A',3),('B',2),('C',1)]]
        pool[-1]["future_return"]=100000
        self.assertEqual([r["ticker"] for r in rank_stocks(pool)],["A","B"])
        pool[0]["sector_excess20"]=None
        self.assertEqual([r["ticker"] for r in rank_stocks(pool,True)],["B","C"])

    def test_forward_record_cannot_be_backdated_or_overwritten(self):
        r=dict(decision_date="2026-11-06",price_asof="2026-11-05",known_at="2026-11-05T22:00:00Z",expected_last_completed_session="2026-11-05",execution_open_at="2026-11-06T00:00:00Z")
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"TODAY"):freeze_forward(d,r,"2026-11-07T00:00:00Z")
            with self.assertRaisesRegex(ValueError,"PRECEDE_NEXT_EXECUTION_OPEN"):freeze_forward(d,r,"2026-11-06T00:00:01Z")
            p=freeze_forward(d,r,"2026-11-05T23:00:01Z");before=p.read_bytes()
            with self.assertRaises(FileExistsError):freeze_forward(d,dict(r,fake=1),"2026-11-05T23:00:02Z")
            self.assertEqual(before,p.read_bytes())

    def test_completed_same_day_close_can_be_frozen_before_later_execution(self):
        r=dict(decision_date="2026-11-06",price_asof="2026-11-06",known_at="2026-11-06T07:00:00Z",expected_last_completed_session="2026-11-06",execution_open_at="2026-11-09T00:00:00Z")
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"NOT_YET_COMPLETE"):freeze_forward(d,r,"2026-11-06T05:00:00Z")
            self.assertTrue(freeze_forward(d,r,"2026-11-06T07:01:00Z").is_file())

    def test_stale_source_and_pre_forward_registration_are_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            r=dict(decision_date="2026-11-06",price_asof="2026-11-04",known_at="2026-11-06T00:00:00Z",expected_last_completed_session="2026-11-05")
            with self.assertRaisesRegex(ValueError,"STALE"):freeze_forward(d,r,"2026-11-06T00:00:01Z")
            r.update(decision_date="2026-11-05")
            with self.assertRaisesRegex(ValueError,"NOT_STARTED"):freeze_forward(d,r,"2026-11-05T00:00:01Z")

    def test_later_classification_receipt_cannot_be_hidden_by_an_earlier_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'krx_v65_collect_status.json').write_text(json.dumps(dict(retrieval_utc='2026-11-05T00:00:00Z')))
            (p/'krx_basic_v610_status.json').write_text(json.dumps(dict(received_utc='2026-11-05T00:00:00Z')))
            (p/'classification_sources.json').write_text(json.dumps(dict(frozen_at='2026-11-05T00:00:00Z',receipts=[dict(received_at='2026-11-06T00:00:00Z')])))
            with self.assertRaisesRegex(ValueError,'NOT_YET_KNOWN'):load_sources(p,p,p,'2026-11-05T01:00:00Z')

    def test_latest_unresolved_price_unit_jump_resets_history(self):
        from datetime import date,timedelta
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);days=[(date(2026,5,1)+timedelta(days=i)).isoformat() for i in range(66)]
            rows=[dict(ticker='000001',date=day,name='example',open='100',high='102',low='98',close='100',volume='10',turnover_krw='1000',tradable='True',ohlc_valid='True') for day in days[:-1]]
            with gzip.open(p/'panel.gz','wt') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            (p/'audit.json').write_text(json.dumps(dict(panel_sha256=hashlib.sha256((p/'panel.gz').read_bytes()).hexdigest(),requested_end=days[-1],missing_market_dates=[],reference_rebase_candidates=[])))
            latest=dict(rows[-1],asof=days[-1],valid_daily_bar='True',open='200',high='204',low='198',close='200')
            histories,reasons=current_histories(p/'panel.gz',p/'audit.json',{'000001':latest})
            self.assertNotIn('000001',histories);self.assertIn('000001',reasons)


if __name__=='__main__':unittest.main()
