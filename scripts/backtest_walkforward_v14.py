
"""C3 v1.4 exploratory walk-forward backtest.

Uses today's KRX listings, so survivorship bias remains.
Signals use data available by the signal close.
Orders are simulated at the next trading day's open.
Research only. No live trading.
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import FinanceDataReader as fdr
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports"
OUT.mkdir(parents=True, exist_ok=True)


def get_universe(limit):
    df = fdr.StockListing("KRX")
    df = df[
        df["Market"].astype(str).str.upper().isin(
            ["KOSPI", "KOSDAQ"]
        )
    ].copy()

    df["Code"] = df["Code"].astype(str).str.zfill(6)
    df = df.drop_duplicates("Code")
    df = df.sort_values("Code")

    if limit > 0:
        df = df.head(limit)

    return df[["Code", "Name", "Market"]]


def fetch_history(code, start, end):
    df = fdr.DataReader(code, start, end)

    if df is None or df.empty:
        return None

    required = ["Open", "High", "Low", "Close", "Volume"]

    if not all(c in df.columns for c in required):
        return None

    df = df[required].copy()
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]

    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=required)
    df = df[
        (df["Open"] > 0)
        & (df["High"] > 0)
        & (df["Low"] > 0)
        & (df["Close"] > 0)
        & (df["Volume"] >= 0)
    ]

    return df if len(df) >= 130 else None


def calculate_signals(df):
    x = df.copy()

    x["ma20"] = x["Close"].rolling(20).mean()
    x["ma60"] = x["Close"].rolling(60).mean()
    x["ma120"] = x["Close"].rolling(120).mean()

    x["vol20"] = x["Volume"].shift(1).rolling(20).mean()
    x["rvol20"] = x["Volume"] / x["vol20"].replace(0, np.nan)

    x["prev_high20"] = (
        x["High"].shift(1).rolling(20).max()
    )

    x["ret20"] = x["Close"].pct_change(20)

    x["trend"] = (
        (x["Close"] > x["ma20"])
        & (x["ma20"] > x["ma60"])
        & (x["ma60"] > x["ma120"])
    )

    x["breakout"] = (
        x["trend"]
        & (x["Close"] > x["prev_high20"])
        & (x["rvol20"] >= 1.5)
    )

    x["pullback"] = (
        x["trend"]
        & (x["Low"] <= x["ma20"] * 1.02)
        & (x["Close"] >= x["ma20"])
        & (x["Close"] > x["Open"])
        & (x["rvol20"] >= 0.8)
    )

    x["signal"] = x["breakout"] | x["pullback"]

    x["score"] = (
        x["breakout"].astype(int) * 4
        + x["pullback"].astype(int) * 3
        + x["trend"].astype(int) * 2
        + x["rvol20"].clip(0, 5).fillna(0)
        + x["ret20"].clip(-0.2, 0.3).fillna(0) * 10
    )

    return x


def build_candidates(universe, start, end):
    records = []
    failures = []

    total = len(universe)

    for i, row in enumerate(universe.itertuples(index=False), 1):
        code, name, market = row

        try:
            raw = fetch_history(code, start, end)

            if raw is None:
                failures.append({
                    "ticker": code,
                    "reason": "insufficient_or_invalid_history",
                })
                continue

            x = calculate_signals(raw)
            x = x[x["signal"].fillna(False)]

            for day, r in x.iterrows():
                records.append({
                    "date": day,
                    "ticker": code,
                    "name": name,
                    "market": market,
                    "score": float(r["score"]),
                    "rvol20": float(r["rvol20"]),
                    "setup": (
                        "breakout"
                        if r["breakout"]
                        else "pullback"
                    ),
                })

        except Exception as exc:
            failures.append({
                "ticker": code,
                "reason": str(exc)[:160],
            })

        if i % 10 == 0:
            print(f"Fetched {i}/{total}", flush=True)

        time.sleep(0.12)

    candidates = pd.DataFrame(records)

    if not candidates.empty:
        candidates = candidates.sort_values(
            ["date", "score", "rvol20", "ticker"],
            ascending=[True, False, False, True],
        )

    return candidates, failures


def simulate(candidates, start_date, end_date,
             holding_days, cost_bps):
    """One position at a time, next-open entry and exit.

    This first version uses a second OHLCV request per trade.
    Entry and exit must exist in the actual ticker's data.
    """

    trades = []
    next_allowed = pd.Timestamp(start_date)
    cache = {}

    for day, group in candidates.groupby("date", sort=True):
        day = pd.Timestamp(day)

        if day < pd.Timestamp(start_date):
            continue

        if day > pd.Timestamp(end_date):
            continue

        if day < next_allowed:
            continue

        best = group.iloc[0]
        code = best["ticker"]

        try:
            if code not in cache:
                cache[code] = fetch_history(
                    code,
                    (
                        pd.Timestamp(start_date)
                        - pd.Timedelta(days=250)
                    ).strftime("%Y-%m-%d"),
                    (
                        pd.Timestamp(end_date)
                        + pd.Timedelta(days=30)
                    ).strftime("%Y-%m-%d"),
                )

            prices = cache[code]

            if prices is None:
                continue

            future = prices[prices.index > day]

            if len(future) <= holding_days:
                continue

            entry = future.iloc[0]
            exit_row = future.iloc[holding_days]

            entry_price = float(entry["Open"])
            exit_price = float(exit_row["Open"])

            if entry_price <= 0 or exit_price <= 0:
                continue

            gross_return = exit_price / entry_price - 1
            net_return = gross_return - 2 * cost_bps / 10000

            exit_date = future.index[holding_days]
            next_allowed = exit_date + pd.Timedelta(days=1)

            trades.append({
                "signal_date": str(day.date()),
                "entry_date": str(future.index[0].date()),
                "exit_date": str(exit_date.date()),
                "ticker": code,
                "name": best["name"],
                "setup": best["setup"],
                "score": round(float(best["score"]), 3),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_return": gross_return,
                "net_return": net_return,
            })

        except Exception as exc:
            print(f"Trade skipped {code}: {exc}")

    return pd.DataFrame(trades)


def summarize(trades, failures, universe_count, args):
    summary = {
        "version": "C3 v1.4",
        "run_kst": datetime.now(
            ZoneInfo("Asia/Seoul")
        ).isoformat(),
        "universe_source": "FDR current KRX listing",
        "survivorship_bias": True,
        "point_in_time_universe": False,
        "live_trade_approval": False,
        "strategy": "breakout_or_pullback_proxy",
        "universe_count": universe_count,
        "fetch_failures": len(failures),
        "holding_days": args.hold,
        "round_trip_cost_bps": args.cost_bps * 2,
        "trades": len(trades),
    }

    if trades.empty:
        summary["status"] = "NO_VALID_TRADES"
        return summary

    r = trades["net_return"].astype(float)

    equity = (1 + r).cumprod()
    drawdown = equity / equity.cummax() - 1

    summary.update({
        "status": "EXPLORATORY_ONLY",
        "win_rate": round(float((r > 0).mean()), 4),
        "avg_trade_return": round(float(r.mean()), 6),
        "compounded_return": round(
            float(equity.iloc[-1] - 1), 6
        ),
        "max_drawdown_trade_sequence": round(
            float(drawdown.min()), 6
        ),
        "warning": (
            "Current listings only. Delisted stocks missing. "
            "No market-wide PIT validation."
        ),
    })

    return summary


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--hold", type=int, default=3)
    parser.add_argument("--cost-bps", type=float, default=15)

    args = parser.parse_args()

    if args.hold < 1:
        raise ValueError("--hold must be >= 1")

    warmup = (
        pd.Timestamp(args.start)
        - pd.Timedelta(days=260)
    ).strftime("%Y-%m-%d")

    print("C3 v1.4 exploratory backtest")
    print("Survivorship bias: TRUE")
    print("Live trading: DISABLED")

    universe = get_universe(args.limit)

    if universe.empty:
        raise RuntimeError("No valid KRX universe")

    candidates, failures = build_candidates(
        universe, warmup, args.end
    )

    if not candidates.empty:
        candidates = candidates[
            (candidates["date"] >= pd.Timestamp(args.start))
            & (candidates["date"] <= pd.Timestamp(args.end))
        ]

    if candidates.empty:
        trades = pd.DataFrame()
    else:
        trades = simulate(
            candidates,
            args.start,
            args.end,
            args.hold,
            args.cost_bps,
        )

    summary = summarize(
        trades, failures, len(universe), args
    )

    (OUT / "walkforward_v14_summary.json").write_text(
        json.dumps(
            summary, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )

    pd.DataFrame(candidates).to_csv(
        OUT / "walkforward_v14_candidates.csv",
        index=False,
        encoding="utf-8-sig",
    )

    trades.to_csv(
        OUT / "walkforward_v14_trades.csv",
        index=False,
        encoding="utf-8-sig",
    )

    pd.DataFrame(failures).to_csv(
        OUT / "walkforward_v14_failures.csv",
        index=False,
        encoding="utf-8-sig",
    )

    print(json.dumps(
        summary, ensure_ascii=False, indent=2
    ))


if __name__ == "__main__":
    main()
