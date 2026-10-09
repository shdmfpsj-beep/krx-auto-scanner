
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import FinanceDataReader as fdr

OUT = Path(__file__).resolve().parents[1] / "reports"
OUT.mkdir(parents=True, exist_ok=True)

result = {
    "version": "C3 v1.3 delisting availability diagnostic",
    "run_kst": datetime.now(
        ZoneInfo("Asia/Seoul")
    ).isoformat(),
    "tests": {},
    "trade_approval": "NO",
}

sources = [
    "KRX-DELISTING",
    "KRX",
]

for source in sources:
    try:
        df = fdr.StockListing(source)

        if df is None:
            raise ValueError("Returned None")

        info = {
            "success": not df.empty,
            "rows": len(df),
            "columns": list(df.columns),
        }

        date_columns = [
            col for col in df.columns
            if any(
                word in str(col).lower()
                for word in (
                    "date", "listing", "delist",
                    "상장", "폐지"
                )
            )
        ]

        info["date_columns"] = date_columns

        if not df.empty:
            info["sample"] = (
                df.head(3)
                .fillna("")
                .astype(str)
                .to_dict(orient="records")
            )

        result["tests"][source] = info

    except Exception as exc:
        result["tests"][source] = {
            "success": False,
            "error": (
                f"{type(exc).__name__}: {exc}"
            )[:300],
        }

path = OUT / "universe_diagnostic.json"
path.write_text(
    json.dumps(
        result,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8",
)

print(
    json.dumps(
        result,
        ensure_ascii=False,
        indent=2
    )
)
