"""Command-line entry point for downloading one Tushare trading day."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import tushare as ts
from dotenv import load_dotenv

from tushare_pipeline import download_trade_date, parse_trade_date


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = PROJECT_ROOT / "data"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and validate one complete Tushare Pro trading day."
    )
    parser.add_argument(
        "--date",
        required=True,
        type=parse_trade_date,
        help="Trading date in YYYYMMDD or YYYY-MM-DD format.",
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
        raise RuntimeError(
            "TUSHARE_TOKEN is missing. Add it to the project .env file after "
            "registering at https://tushare.pro/"
        )

    print(f"[Tushare] SDK {ts.__version__}; downloading {args.date}", flush=True)
    api = ts.pro_api(token, timeout=args.timeout)
    target = download_trade_date(
        api=api,
        trade_date=args.date,
        data_root=args.data_root,
        sdk_version=ts.__version__,
    )
    print(f"[Tushare] validated data written to {target}", flush=True)


if __name__ == "__main__":
    main()
