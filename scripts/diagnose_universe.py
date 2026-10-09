
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import FinanceDataReader as fdr
from pykrx import stock

OUT = Path(__file__).resolve().parents[1] / "reports"
OUT.mkdir(parents=True, exist_ok=True)

result = {
    "version": "C3 v1.2 data access diagnostic",
    "run_kst": datetime.now(
        ZoneInfo("Asia/Seoul")
    ).isoformat(),
    "tests": {},
    "trade_approval": "NO",
}

try:
    listing = fdr.StockListing("KRX")
    market = listing[
        listing["Market"].astype(str).str.upper().isin(
            ["KOSPI", "KOSDAQ"]
        )
    ]
    result["tests"]["FDR_current_universe"] = {
        "success": not market.empty,
        "rows": len(market),
        "note": "Current listing, not historical PIT universe",
    }
except Exception as exc:
    result["tests"]["FDR_current_universe"] = {
        "success": False,
        "error": str(exc)[:300],
    }

test_codes = {
    "Samsung_Electronics": "005930",
    "GST": "083450",
    "Hyundai_Motor": "005380",
}

for name, code in test_codes.items():
    try:
        df = fdr.DataReader(
            code, "2025-01-01", "2025-03-31"
        )
        result["tests"][f"FDR_OHLCV_{name}"] = {
            "success": df is not None and not df.empty,
            "rows": 0 if df is None else len(df),
            "columns": [] if df is None else list(df.columns),
            "first_date": (
                None if df is None or df.empty
                else str(df.index.min().date())
            ),
            "last_date": (
                None if df is None or df.empty
                else str(df.index.max().date())
            ),
        }
    except Exception as exc:
        result["tests"][f"FDR_OHLCV_{name}"] = {
            "success": False,
            "error": f"{type(exc).__name__}: {exc}"[:300],
        }

path = OUT / "universe_diagnostic.json"
path.write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(json.dumps(result, ensure_ascii=False, indent=2))
