
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import FinanceDataReader as fdr
from pykrx import stock

OUT = Path(__file__).resolve().parents[1] / "reports"
OUT.mkdir(parents=True, exist_ok=True)

result = {
    "run_kst": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
    "tests": {},
}

for source in ("KRX-DESC", "KRX"):
    try:
        df = fdr.StockListing(source)
        result["tests"][f"FDR_{source}"] = {
            "success": df is not None and not df.empty,
            "rows": 0 if df is None else len(df),
            "columns": [] if df is None else list(df.columns),
            "note": "Current listing only; historical membership not verified",
        }
    except Exception as exc:
        result["tests"][f"FDR_{source}"] = {
            "success": False,
            "error": f"{type(exc).__name__}: {exc}"[:300],
        }

for market in ("KOSPI", "KOSDAQ"):
    try:
        codes = stock.get_market_ticker_list(
            "20260930", market=market
        )
        result["tests"][f"pykrx_{market}_historical"] = {
            "success": len(codes) > 0,
            "count": len(codes),
        }
    except Exception as exc:
        result["tests"][f"pykrx_{market}_historical"] = {
            "success": False,
            "error": f"{type(exc).__name__}: {exc}"[:300],
        }

path = OUT / "universe_diagnostic.json"
path.write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(json.dumps(result, ensure_ascii=False, indent=2))
