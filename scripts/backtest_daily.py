
import argparse
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from pykrx import stock

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports"
OUT.mkdir(parents=True, exist_ok=True)

INITIAL_CAPITAL = 440000
ROUND_TRIP_COST_PCT = 0.35
STOP_PCT = 3.0
TARGET_PCT = 3.3
MAX_HOLD_DAYS = 5
MAX_ENTRY_GAP_PCT = 3.0

TRADE_COLUMNS = [
    "ticker", "setup", "signal_date", "entry_date",
    "exit_date", "entry_price", "exit_price",
    "shares", "entry_amount", "exit_reason",
    "gross_return_pct", "net_return_pct",
    "net_profit_krw", "capital_after"
]


def load_codes(limit):
    path = OUT / "candidates.csv"
    if not path.exists():
        raise FileNotFoundError(
            "Run full_scan first: candidates.csv missing"
        )

    df = pd.read_csv(path, dtype={"ticker": str})

    if "ticker" not in df.columns:
        raise ValueError("ticker column missing")

    codes = (
        df["ticker"]
        .dropna()
        .astype(str)
        .str.zfill(6)
        .drop_duplicates()
        .tolist()
    )

    return codes[:limit]


def load_prices(code, start, end):
    df = stock.get_market_ohlcv_by_date(
        start, end, code, adjusted=True
    )

    if df is None or df.empty:
        raise ValueError("empty price history")

    df = df.sort_index()
    df = df.loc[
        ~df.index.duplicated(keep="last")
    ].copy()

    for col in ("시가", "고가", "저가", "종가", "거래량"):
        if col not in df.columns:
            raise ValueError(f"missing {col}")

        df[col] = pd.to_numeric(
            df[col], errors="coerce"
        )

    df = df.dropna(
        subset=["시가", "고가", "저가", "종가", "거래량"]
    )

    return df[
        (df["시가"] > 0)
        & (df["고가"] > 0)
        & (df["저가"] > 0)
        & (df["종가"] > 0)
    ].copy()


def build_signals(df):
    close = df["종가"].astype(float)
    high = df["고가"].astype(float)
    volume = df["거래량"].astype(float)

    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    ma120 = close.rolling(120).mean()

    prev_vol = volume.shift(1).rolling(20).mean()
    rvol = volume / prev_vol.replace(0, np.nan)

    prior_high = high.shift(1).rolling(20).max()

    breakout = (
        (close > prior_high)
        & (rvol >= 1.5)
        & (close > ma60)
    )

    pullback = (
        (ma20 > ma60)
        & (ma60 > ma120)
        & (close > ma20)
        & ((close / ma20 - 1).abs() <= 0.035)
    )

    reversal = (
        (close.shift(1) < ma60.shift(1))
        & (close > ma60)
        & (ma20 > ma20.shift(5))
    )

    weekly = close.resample("W-FRI").last().dropna()
    monthly = close.resample("ME").last().dropna()

    weekly_ok = (
        weekly > weekly.rolling(10).mean()
    )

    monthly_ok = (
        monthly > monthly.rolling(6).mean()
    )

    weekly_daily = (
        weekly_ok.shift(1)
        .reindex(close.index, method="ffill")
        .fillna(False)
    )

    monthly_daily = (
        monthly_ok.shift(1)
        .reindex(close.index, method="ffill")
        .fillna(False)
    )

    trend = weekly_daily & monthly_daily

    flags = {
        "REVERSAL_PROXY": reversal & trend,
        "PULLBACK_PROXY": pullback & trend,
        "BREAKOUT": breakout & trend,
    }

    score_base = {
        "REVERSAL_PROXY": 80,
        "PULLBACK_PROXY": 70,
        "BREAKOUT": 60,
    }

    results = []

    for setup, flag in flags.items():
        for date in df.index[flag.fillna(False)]:
            loc = df.index.get_loc(date)

            if loc + 1 >= len(df):
                continue

            close_price = float(close.loc[date])
            relative_volume = float(
                rvol.loc[date]
            ) if pd.notna(rvol.loc[date]) else 0.0

            score = (
                score_base[setup]
                + min(relative_volume, 5.0) * 2
            )

            results.append({
                "ticker": None,
                "setup": setup,
                "signal_date": pd.Timestamp(date),
                "signal_close": close_price,
                "score": round(score, 3),
            })

    return results


def collect_data(codes, fetch_start, fetch_end, delay):
    price_data = {}
    signals = []
    errors = []

    for idx, code in enumerate(codes, 1):
        try:
            df = load_prices(
                code,
                fetch_start.strftime("%Y%m%d"),
                fetch_end.strftime("%Y%m%d")
            )

            if len(df) < 150:
                raise ValueError(
                    f"insufficient history: {len(df)}"
                )

            price_data[code] = df

            for item in build_signals(df):
                item["ticker"] = code
                signals.append(item)

        except Exception as exc:
            errors.append(
                f"{code}: {type(exc).__name__}: {exc}"
            )

        print(
            f"Processed {idx}/{len(codes)}: {code}",
            flush=True
        )
        time.sleep(delay)

    return price_data, signals, errors


def simulate(price_data, signals, start_date, end_date):
    capital = float(INITIAL_CAPITAL)
    trades = []
    equity = []

    if not price_data:
        return trades, equity

    all_dates = sorted(set().union(
        *[set(df.index) for df in price_data.values()]
    ))

    candidates_by_date = {}

    for item in signals:
        day = item["signal_date"]

        if start_date <= day.date() <= end_date:
            candidates_by_date.setdefault(day, []).append(item)

    position = None
    pending = None

    for day in all_dates:
        if day.date() < start_date:
            continue

        if day.date() > end_date:
            break

        # Execute an order prepared after the previous close.
        if position is None and pending is not None:
            code = pending["ticker"]
            df = price_data[code]

            if day in df.index:
                row = df.loc[day]
                entry = float(row["시가"])
                signal_close = pending["signal_close"]

                gap_pct = (
                    entry / signal_close - 1
                ) * 100

                if (
                    entry > 0
                    and gap_pct <= MAX_ENTRY_GAP_PCT
                    and entry <= capital
                ):
                    shares = int(
                        capital / (
                            entry * (
                                1 + ROUND_TRIP_COST_PCT / 200
                            )
                        )
                    )

                    if shares >= 1:
                        position = {
                            "ticker": code,
                            "setup": pending["setup"],
                            "signal_date": str(
                                pending["signal_date"].date()
                            ),
                            "entry_date": str(day.date()),
                            "entry_day": day,
                            "entry_price": entry,
                            "shares": shares,
                            "entry_amount": entry * shares,
                            "days_held": 0,
                        }

            pending = None

        # Evaluate stop, target and time exit.
        if position is not None:
            code = position["ticker"]
            df = price_data[code]

            if day in df.index:
                row = df.loc[day]

                entry = position["entry_price"]
                open_price = float(row["시가"])
                high = float(row["고가"])
                low = float(row["저가"])
                close = float(row["종가"])

                stop_price = entry * (
                    1 - STOP_PCT / 100
                )
                target_price = entry * (
                    1 + TARGET_PCT / 100
                )

                position["days_held"] += 1

                exit_price = None
                reason = None

                # Gap through stop: fill at opening price.
                if open_price <= stop_price:
                    exit_price = open_price
                    reason = "GAP_STOP"

                elif open_price >= target_price:
                    exit_price = open_price
                    reason = "GAP_TARGET"

                elif low <= stop_price:
                    exit_price = stop_price
                    reason = "STOP"

                elif high >= target_price:
                    exit_price = target_price
                    reason = "TARGET"

                elif position["days_held"] >= MAX_HOLD_DAYS:
                    exit_price = close
                    reason = "TIME_EXIT"

                if exit_price is not None:
                    shares = position["shares"]

                    gross_pct = (
                        exit_price / entry - 1
                    ) * 100

                    net_pct = (
                        gross_pct - ROUND_TRIP_COST_PCT
                    )

                    profit = (
                        (exit_price - entry) * shares
                        - (
                            entry + exit_price
                        ) * shares * (
                            ROUND_TRIP_COST_PCT / 20000
                        )
                    )

                    capital += profit

                    trades.append({
                        "ticker": code,
                        "setup": position["setup"],
                        "signal_date": position["signal_date"],
                        "entry_date": position["entry_date"],
                        "exit_date": str(day.date()),
                        "entry_price": round(entry, 2),
                        "exit_price": round(exit_price, 2),
                        "shares": shares,
                        "entry_amount": round(
                            position["entry_amount"], 2
                        ),
                        "exit_reason": reason,
                        "gross_return_pct": round(
                            gross_pct, 4
                        ),
                        "net_return_pct": round(
                            net_pct, 4
                        ),
                        "net_profit_krw": round(
                            profit, 2
                        ),
                        "capital_after": round(
                            capital, 2
                        ),
                    })

                    position = None

        # End-of-day signal selection.
        if position is None and pending is None:
            available = candidates_by_date.get(day, [])

            if available:
                available.sort(
                    key=lambda x: (
                        -x["score"],
                        x["ticker"]
                    )
                )

                pending = available[0]

        # Mark-to-market account value.
        estimated_equity = capital

        if position is not None:
            code = position["ticker"]
            df = price_data[code]

            if day in df.index:
                current_close = float(
                    df.loc[day, "종가"]
                )
                estimated_equity += (
                    current_close
                    - position["entry_price"]
                ) * position["shares"]

        equity.append({
            "date": str(day.date()),
            "equity_krw": round(
                estimated_equity, 2
            ),
            "holding_ticker": (
                position["ticker"]
                if position is not None else ""
            ),
        })

    return trades, equity


def summarize(trades, equity, sample_count, errors):
    df = pd.DataFrame(trades)
    curve = pd.DataFrame(equity)

    final_equity = (
        float(curve.iloc[-1]["equity_krw"])
        if not curve.empty
        else float(INITIAL_CAPITAL)
    )

    total_return = (
        final_equity / INITIAL_CAPITAL - 1
    ) * 100

    if not curve.empty:
        running_peak = curve["equity_krw"].cummax()
        drawdown = (
            curve["equity_krw"] / running_peak - 1
        ) * 100
        max_drawdown = float(drawdown.min())
    else:
        max_drawdown = 0.0

    if not df.empty:
        r = df["net_profit_krw"].astype(float)
        wins = r[r > 0].sum()
        losses = -r[r < 0].sum()

        win_rate = float((r > 0).mean() * 100)
        pf = float(wins / losses) if losses > 0 else None
        avg_return = float(
            df["net_return_pct"].mean()
        )
    else:
        win_rate = 0.0
        pf = None
        avg_return = 0.0

    return {
        "version": "C3 portfolio backtest 0.2",
        "initial_capital_krw": INITIAL_CAPITAL,
        "final_equity_krw": round(final_equity, 2),
        "total_return_pct": round(total_return, 3),
        "max_drawdown_pct": round(max_drawdown, 3),
        "completed_trades": len(trades),
        "win_rate_pct": round(win_rate, 2),
        "average_net_return_pct": round(
            avg_return, 3
        ),
        "profit_factor": (
            round(pf, 3)
            if pf is not None else None
        ),
        "sample_count": sample_count,
        "errors": errors,
        "trade_approval": "NO",
        "limitations": [
            "Current candidates only: selection and survivorship bias",
            "Signal scores are heuristic, not probabilities",
            "Daily OHLCV cannot determine intraday stop/target order",
            "If stop and target both occur, stop is assumed first",
            "Historical fills are hypothetical",
            "Fixed stop and target are not optimized or validated",
            "Not an out-of-sample performance estimate"
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit", type=int, default=20
    )
    parser.add_argument(
        "--days", type=int, default=365
    )
    parser.add_argument(
        "--delay", type=float, default=0.2
    )

    args = parser.parse_args()

    if args.limit < 1 or args.days < 30:
        parser.error(
            "limit >= 1 and days >= 30 required"
        )

    now = datetime.now(
        ZoneInfo("Asia/Seoul")
    )

    end = now.date()
    start_date = end - timedelta(
        days=args.days
    )

    fetch_start = start_date - timedelta(
        days=550
    )
    fetch_end = end + timedelta(
        days=10
    )

    codes = load_codes(args.limit)

    price_data, signals, errors = collect_data(
        codes, fetch_start, fetch_end, args.delay
    )

    trades, equity = simulate(
        price_data, signals, start_date, end
    )

    trades_df = pd.DataFrame(
        trades, columns=TRADE_COLUMNS
    )

    equity_df = pd.DataFrame(equity)

    trades_df.to_csv(
        OUT / "backtest_portfolio_trades.csv",
        index=False,
        encoding="utf-8-sig"
    )

    equity_df.to_csv(
        OUT / "backtest_equity.csv",
        index=False,
        encoding="utf-8-sig"
    )

    status = summarize(
        trades, equity, len(codes), errors
    )

    status["run_kst"] = now.isoformat()
    status["evaluation_days"] = args.days
    status["stop_pct"] = STOP_PCT
    status["target_pct"] = TARGET_PCT
    status["max_hold_days"] = MAX_HOLD_DAYS
    status["max_entry_gap_pct"] = (
        MAX_ENTRY_GAP_PCT
    )
    status["round_trip_cost_pct"] = (
        ROUND_TRIP_COST_PCT
    )

    (
        OUT / "backtest_portfolio_status.json"
    ).write_text(
        json.dumps(
            status,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        json.dumps(
            status,
            ensure_ascii=False,
            indent=2
        )
    )


if __name__ == "__main__":
    main()
