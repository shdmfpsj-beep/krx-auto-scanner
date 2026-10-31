"""Read-only C3 daily 20:00 scan/news safety checks; not profit backtests."""
import csv,datetime,json,tempfile,unittest
from pathlib import Path
from zoneinfo import ZoneInfo
from c3_daily_20k_review_v1 import inspect_scan,read_rss,run

KST=ZoneInfo('Asia/Seoul')

class TestDaily20K(unittest.TestCase):
    def test_weekend_rescreens_all_archived_tickers_without_adding_price(self):
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/'source';src.mkdir()
            (src/'status.json').write_text(json.dumps({
                'market_data_date':'2026-10-30','universe':2000,
                'scan_complete':True,'run_kst':'2026-10-30T20:57:00+09:00'}))
            with (src/'c3_premove_observations_v1.csv').open(
                'w',newline='',encoding='utf-8') as f:
                w=csv.DictWriter(f,fieldnames=['ticker','asof','observation_status',
                               'price_stage_pass','ret5','ret20','rsi14'])
                w.writeheader()
                for i in range(2000):
                    w.writerow(dict(ticker=f'{i:06}',asof='2026-10-30',
                       observation_status='PRICE_ONLY_OBSERVED',
                       price_stage_pass='True' if i<150 else 'False',
                       ret5='1',ret20='3',rsi14='52'))
            output=Path(temp)/'out'
            fake=lambda _:b'<rss><channel></channel></rss>'
            x=run(src,output,datetime.datetime(2026,10,31,20,tzinfo=KST),fetch=fake)
            self.assertEqual(x['mode'],'WEEKEND_NEWS_OVER_LAST_COMPLETED_DAY')
            self.assertEqual(x['source_market']['early_candidate_count'],150)
            self.assertEqual(x['all_market_rescreen_rows_written'],2000)
            self.assertFalse(x['full_market_scanned_fresh_now'])
            self.assertFalse(x['trade_approved'])
            self.assertTrue((output/'c3_20k_all_market_rescreen.csv').exists())

    def test_missing_archive_is_news_only_and_not_faked(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp)
            x=run(d/'none',d/'output',
                datetime.datetime(2026,10,31,20,tzinfo=KST),
                fetch=lambda _:b'<rss><channel></channel></rss>')
            self.assertEqual(x['mode'],'NO_FULL_MARKET_SOURCE_NEWS_ONLY')
            self.assertEqual(x['all_market_rescreen_rows_written'],0)
            self.assertFalse(x['completed_market_universe_rescreened'])

    def test_rss_does_not_use_future_publication(self):
        now=datetime.datetime(2026,10,31,20,tzinfo=KST)
        xml=b'<rss><channel><item><title>future release</title><link>https://news.example.org/a</link><pubDate>Sun, 01 Nov 2026 20:00:00 +0900</pubDate></item></channel></rss>'
        self.assertEqual(read_rss('example',now,lambda _:xml),[])

if __name__=='__main__':unittest.main()
