"""Incrementally download all missing Tushare trading days."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import tushare as ts
from dotenv import load_dotenv

from .tushare_pipeline import (
    ENDPOINT_SPECS,
    TushareApi,
    download_trade_date,
    parse_trade_date,
    query_frame,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = PROJECT_ROOT / "data"
CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")
DATA_READY_TIME = time(18, 0)


def default_end_date(now: datetime | None = None) -> str:
    current = now or datetime.now(CHINA_TIMEZONE)
    if current.tzinfo is None:
        raise ValueError("now must include timezone information")

    china_now = current.astimezone(CHINA_TIMEZONE)
    candidate = china_now.date()
    if china_now.time() < DATA_READY_TIME:
        candidate -= timedelta(days=1)
    return candidate.strftime("%Y%m%d")


def existing_trade_dates(data_root: Path) -> list[str]:
    source_root = data_root.resolve() / "raw" / "tushare"
    dates: list[str] = []
    for path in source_root.glob("trade_date=*"):
        if path.is_dir():
            dates.append(parse_trade_date(path.name.removeprefix("trade_date=")))
    return sorted(dates)


def resolve_start_date(data_root: Path, requested_start: str | None) -> str:
    if requested_start is not None:
        return parse_trade_date(requested_start)

    existing = existing_trade_dates(data_root)
    if not existing:
        raise RuntimeError(
            "No Tushare data exists yet. Supply --start for the initial backfill."
        )

    next_day = datetime.strptime(existing[-1], "%Y%m%d").date() + timedelta(days=1)
    return next_day.strftime("%Y%m%d")


def query_open_dates(api: TushareApi, start_date: str, end_date: str) -> list[str]:
    spec = ENDPOINT_SPECS["trade_cal"]
    frame = query_frame(
        api,
        "trade_cal",
        spec,
        exchange="SSE",
        start_date=start_date,
        end_date=end_date,
    )
    if frame.empty:
        raise RuntimeError(
            f"Tushare trade_cal returned no rows for {start_date} through {end_date}"
        )
    if frame.duplicated(list(spec.keys)).any():
        raise RuntimeError("Tushare trade_cal returned duplicate exchange/date rows")

    actual_dates = frame["cal_date"].astype(str)
    outside = actual_dates[(actual_dates < start_date) | (actual_dates > end_date)]
    if not outside.empty:
        raise RuntimeError(
            "Tushare trade_cal returned dates outside the requested range: "
            + ", ".join(sorted(set(outside)))
        )

    open_dates = frame.loc[frame["is_open"].astype(str).eq("1"), "cal_date"]
    return sorted(open_dates.astype(str).tolist())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download every missing Tushare trading day in a date range."
    )
    parser.add_argument(
        "--start",
        type=parse_trade_date,
        help=(
            "Inclusive start date. Required for the first backfill; afterwards the "
            "day after the latest local partition is used automatically."
        ),
    )
    parser.add_argument(
        "--end",
        type=parse_trade_date,
        help=(
            "Inclusive end date. Defaults to today after 18:00 China time, otherwise "
            "yesterday; the exchange calendar removes weekends and holidays."
        ),
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
        help="Destination data root. Defaults to the project's data directory.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Tushare HTTP timeout in seconds. Defaults to 30.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is missing from the project .env file")

    data_root = args.data_root.resolve()
    start_date = resolve_start_date(data_root, args.start)
    end_date = args.end or default_end_date()
    if start_date > end_date:
        if args.start is not None:
            raise ValueError(f"Start date {start_date} is after end date {end_date}")
        print(f"[Tushare] already current through {end_date}", flush=True)
        return

    print(
        f"[Tushare] SDK {ts.__version__}; checking {start_date} through {end_date}",
        flush=True,
    )
    api = ts.pro_api(token, timeout=args.timeout)
    open_dates = query_open_dates(api, start_date, end_date)
    existing = set(existing_trade_dates(data_root))
    missing_dates = [
        trade_date for trade_date in open_dates if trade_date not in existing
    ]
    if not missing_dates:
        print("[Tushare] no missing trading days in the requested range", flush=True)
        return

    for position, trade_date in enumerate(missing_dates, start=1):
        print(
            f"[Tushare] {position}/{len(missing_dates)} downloading {trade_date}",
            flush=True,
        )
        target = download_trade_date(
            api=api,
            trade_date=trade_date,
            data_root=data_root,
            sdk_version=ts.__version__,
        )
        print(f"[Tushare] validated data written to {target}", flush=True)


if __name__ == "__main__":
    main()
