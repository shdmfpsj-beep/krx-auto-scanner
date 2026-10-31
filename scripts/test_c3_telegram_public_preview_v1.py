"""Synthetic public Telegram preview tests. No Telegram API or account access."""
from __future__ import annotations
import csv,json,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from c3_telegram_public_preview_v1 import parse_preview,run,CHANNELS

NOW=datetime(2026,10,31,9,0,tzinfo=timezone.utc)

def preview(channel,posts):
    out=["<html><body><div class='tgme_channel_history'>"]
    for pid,when,body in posts:
        out.extend([
            f'<div class="tgme_widget_message js-widget_message" data-post="{channel}/{pid}">',
            f'<div class="tgme_widget_message_text js-message_text">{body}</div>',
            f'<a class="tgme_widget_message_date" href="https://t.me/{channel}/{pid}">',
            f'<time datetime="{when}">{when}</time></a></div>'])
    out.append("</div></body></html>")
    return "".join(out)

class PublicTelegramTests(unittest.TestCase):
    def test_recent_sourced_message_with_link_and_sector(self):
        text=preview("good_trader_x100",[("123","2026-10-31T04:00:00+00:00",
          '전력반도체 <a href="https://example.com/a">외부기사</a> 관련 이슈')])
        p,st=parse_preview(text,"good_trader_x100",NOW)
        self.assertEqual(len(p),1)
        self.assertEqual(p[0]["post_url"],"https://t.me/good_trader_x100/123")
        self.assertIn("POWER",p[0]["sector_ids"])
        self.assertIn("https://example.com/a",p[0]["external_urls"])
        self.assertFalse(st["future_posts_ignored"])

    def test_old_future_and_undated_never_mislabelled_fresh(self):
        text=preview("Jegalstock",[
          ("1","2026-10-20T01:00:00+00:00","너무 옛날 주식"),
          ("2","2026-11-02T01:00:00+00:00","미래 반도체"),
          ("3","bad-date","날짜 미상"),
          ("4","2026-10-30T03:00:00+00:00","조선 수주")])
        p,st=parse_preview(text,"Jegalstock",NOW)
        self.assertEqual([x["post_id"] for x in p],["4"])
        self.assertEqual(st["old_posts_ignored"],1)
        self.assertEqual(st["future_posts_ignored"],1)
        self.assertEqual(st["posts_without_valid_time"],1)

    def test_public_preview_missing_is_not_treated_as_no_news(self):
        with tempfile.TemporaryDirectory() as d:
            st=run(d,NOW,fetcher=lambda ch:"<html>로그인해야 읽을 수 있습니다</html>")
            self.assertEqual(st["dated_72h_posts"],0)
            self.assertTrue(all(v["status"]=="PUBLIC_POST_PREVIEW_NOT_AVAILABLE"
                            for v in st["channels"].values()))
            self.assertTrue(st["no_missing_news_penalty"])
            self.assertFalse(st["buy_approved"])

    def test_one_channel_fails_other_succeeds(self):
        def fetcher(ch):
            if ch=="Jegalstock":raise TimeoutError("public preview unavailable")
            return preview(ch,[("50","2026-10-31T01:00:00+00:00","반도체 5일 실적")])
        with tempfile.TemporaryDirectory() as d:
            st=run(d,NOW,fetcher=fetcher)
            self.assertEqual(st["dated_72h_posts"],1)
            self.assertEqual(st["channels"]["Jegalstock"]["status"],
                             "NOT_ACCESSIBLE_OR_REQUEST_FAILED")
            self.assertEqual(st["channels"]["good_trader_x100"]["posts_dated_recent"],1)
            with (Path(d)/"c3_telegram_public_posts_72h.csv").open(
                encoding="utf-8-sig",newline="") as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["channel"],"good_trader_x100")
            self.assertTrue(st["no_private_groups_read"])
            self.assertFalse(st["orders_enabled"])

    def test_duplicate_ids_deduped(self):
        text=preview("good_trader_x100",[
          ("5","2026-10-31T03:00:00+00:00","삼성전자"),
          ("5","2026-10-31T03:00:00+00:00","삼성전자")])
        p,st=parse_preview(text,"good_trader_x100",NOW)
        self.assertEqual(len(p),1)

if __name__=="__main__":unittest.main()
