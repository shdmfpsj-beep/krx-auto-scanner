"""Separate unverified reference images and receipts; never authorizes a buy."""
import argparse
import json
from pathlib import Path
from c3_watch5_delivery import run


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path('output/c3_top5'))
    result=run(parser.parse_args().root,review=True)
    print('C3_REVIEW_DELIVERY',json.dumps({k:result.get(k) for k in
        ('status','stage','asof','selected_count','telegram_photos_sent','reason','exception_type')}))
    raise SystemExit(1 if result['status'] in ('ERROR','PARTIAL_ERROR') else 0)
