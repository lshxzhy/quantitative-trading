from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Protocol

import pandas as pd


TARGET_INDEX_CODES = ("000001.SH", "000300.SH", "000852.SH", "000905.SH")
BSE_OPEN_DATE = date(2021, 11, 15)


class TushareApi(Protocol):
    def query(self, api_name: str, fields: str = "", **kwargs: str) -> pd.DataFrame: ...


@dataclass(frozen=True)
class EndpointSpec:
    fields: tuple[str, ...]
    keys: tuple[str, ...]
    date_column: str | None = None
    allow_empty: bool = False


ENDPOINT_SPECS: Mapping[str, EndpointSpec] = {
    "trade_cal": EndpointSpec(
        fields=("exchange", "cal_date", "is_open", "pretrade_date"),
        keys=("exchange", "cal_date"),
        date_column="cal_date",
    ),
    "stock_basic": EndpointSpec(
        fields=(
            "ts_code",
            "symbol",
            "name",
            "area",
            "industry",
            "fullname",
            "enname",
            "cnspell",
            "market",
            "exchange",
            "curr_type",
            "list_status",
            "list_date",
            "delist_date",
            "is_hs",
        ),
        keys=("ts_code",),
    ),
    "daily": EndpointSpec(
        fields=(
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "change",
            "pct_chg",
            "vol",
            "amount",
            "ah_vol",
            "ah_amount",
        ),
        keys=("ts_code", "trade_date"),
        date_column="trade_date",
    ),
    "daily_basic": EndpointSpec(
        fields=(
            "ts_code",
            "trade_date",
            "close",
            "turnover_rate",
            "turnover_rate_f",
            "volume_ratio",
            "pe",
            "pe_ttm",
            "pb",
            "ps",
            "ps_ttm",
            "dv_ratio",
            "dv_ttm",
            "total_share",
            "float_share",
            "free_share",
            "total_mv",
            "circ_mv",
            "limit_status",
        ),
        keys=("ts_code", "trade_date"),
        date_column="trade_date",
    ),
    "adj_factor": EndpointSpec(
        fields=("ts_code", "trade_date", "adj_factor"),
        keys=("ts_code", "trade_date"),
        date_column="trade_date",
    ),
    "stk_limit": EndpointSpec(
        fields=("trade_date", "ts_code", "pre_close", "up_limit", "down_limit"),
        keys=("ts_code", "trade_date"),
        date_column="trade_date",
    ),
    "suspend_d": EndpointSpec(
        fields=("ts_code", "trade_date", "suspend_timing", "suspend_type"),
        keys=("ts_code", "trade_date", "suspend_type"),
        date_column="trade_date",
        allow_empty=True,
    ),
    "index_daily": EndpointSpec(
        fields=(
            "ts_code",
            "trade_date",
            "close",
            "open",
            "high",
            "low",
            "pre_close",
            "change",
            "pct_chg",
            "vol",
            "amount",
        ),
        keys=("ts_code", "trade_date"),
        date_column="trade_date",
    ),
}


def parse_trade_date(value: str) -> str:
    normalized = value.replace("-", "")
    parsed = datetime.strptime(normalized, "%Y%m%d").date()
    if parsed.strftime("%Y%m%d") != normalized:
        raise ValueError(f"Invalid trade date: {value}")
    return normalized


def fields_text(spec: EndpointSpec) -> str:
    return ",".join(spec.fields)


def query_frame(
    api: TushareApi,
    api_name: str,
    spec: EndpointSpec,
    **params: str,
) -> pd.DataFrame:
    try:
        frame = api.query(api_name, fields=fields_text(spec), **params)
    except Exception as error:
        raise RuntimeError(
            f"Tushare endpoint {api_name} failed with parameters {params}"
        ) from error

    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"Tushare endpoint {api_name} did not return a DataFrame")

    missing = [field for field in spec.fields if field not in frame.columns]
    if missing:
        raise RuntimeError(f"Tushare endpoint {api_name} is missing fields: {missing}")

    return frame.loc[:, spec.fields].copy()


def validate_frame(
    name: str,
    frame: pd.DataFrame,
    spec: EndpointSpec,
    trade_date: str,
) -> pd.DataFrame:
    if frame.empty and not spec.allow_empty:
        raise RuntimeError(f"Tushare endpoint {name} returned no rows")

    for key in spec.keys:
        values = frame[key]
        blank = values.isna() | values.astype(str).str.strip().eq("")
        if blank.any():
            raise RuntimeError(f"Tushare endpoint {name} has blank key values in {key}")

    if frame.duplicated(list(spec.keys)).any():
        duplicates = frame.loc[frame.duplicated(list(spec.keys), keep=False), list(spec.keys)]
        raise RuntimeError(
            f"Tushare endpoint {name} has duplicate keys: "
            f"{duplicates.head(10).to_dict(orient='records')}"
        )

    if spec.date_column is not None and not frame.empty:
        actual_dates = set(frame[spec.date_column].astype(str))
        if actual_dates != {trade_date}:
            raise RuntimeError(
                f"Tushare endpoint {name} returned dates {sorted(actual_dates)}, "
                f"expected only {trade_date}"
            )

    return frame.sort_values(list(spec.keys), kind="stable").reset_index(drop=True)


def validate_market_coverage(frame: pd.DataFrame, trade_date: str, name: str) -> None:
    suffixes = set(frame["ts_code"].str.rsplit(".", n=1).str[-1])
    expected = {"SH", "SZ"}
    if datetime.strptime(trade_date, "%Y%m%d").date() >= BSE_OPEN_DATE:
        expected.add("BJ")
    missing = expected - suffixes
    if missing:
        raise RuntimeError(
            f"Tushare endpoint {name} is missing market suffixes: {sorted(missing)}"
        )


def fetch_trade_date(api: TushareApi, trade_date: str) -> dict[str, pd.DataFrame]:
    trade_date = parse_trade_date(trade_date)
    frames: dict[str, pd.DataFrame] = {}

    trade_cal_spec = ENDPOINT_SPECS["trade_cal"]
    frames["trade_cal"] = validate_frame(
        "trade_cal",
        query_frame(
            api,
            "trade_cal",
            trade_cal_spec,
            exchange="SSE",
            start_date=trade_date,
            end_date=trade_date,
        ),
        trade_cal_spec,
        trade_date,
    )
    if str(frames["trade_cal"].iloc[0]["is_open"]) != "1":
        raise RuntimeError(f"{trade_date} is not an open SSE trading day")

    stock_basic_spec = ENDPOINT_SPECS["stock_basic"]
    frames["stock_basic"] = validate_frame(
        "stock_basic",
        query_frame(
            api,
            "stock_basic",
            stock_basic_spec,
            exchange="",
            list_status="L",
        ),
        stock_basic_spec,
        trade_date,
    )
    validate_market_coverage(frames["stock_basic"], trade_date, "stock_basic")

    for name in ("daily", "daily_basic", "adj_factor", "stk_limit", "suspend_d"):
        spec = ENDPOINT_SPECS[name]
        frames[name] = validate_frame(
            name,
            query_frame(api, name, spec, trade_date=trade_date),
            spec,
            trade_date,
        )

    validate_market_coverage(frames["daily"], trade_date, "daily")
    daily_codes = set(frames["daily"]["ts_code"])
    daily_basic_codes = set(frames["daily_basic"]["ts_code"])
    if not daily_codes.issubset(daily_basic_codes):
        missing_codes = sorted(daily_codes - daily_basic_codes)
        raise RuntimeError(
            "daily_basic is missing codes returned by daily: "
            + ", ".join(missing_codes[:20])
        )

    index_spec = ENDPOINT_SPECS["index_daily"]
    index_parts = [
        query_frame(
            api,
            "index_daily",
            index_spec,
            ts_code=code,
            trade_date=trade_date,
        )
        for code in TARGET_INDEX_CODES
    ]
    frames["index_daily"] = validate_frame(
        "index_daily",
        pd.concat(index_parts, ignore_index=True),
        index_spec,
        trade_date,
    )
    actual_indexes = set(frames["index_daily"]["ts_code"])
    expected_indexes = set(TARGET_INDEX_CODES)
    if actual_indexes != expected_indexes:
        raise RuntimeError(
            f"index_daily codes are {sorted(actual_indexes)}, "
            f"expected {sorted(expected_indexes)}"
        )

    return frames


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig", lineterminator="\n")
    temporary.replace(path)


def download_trade_date(
    api: TushareApi,
    trade_date: str,
    data_root: Path,
    sdk_version: str,
) -> Path:
    trade_date = parse_trade_date(trade_date)
    data_root = data_root.resolve()
    staging = data_root / ".staging" / "tushare" / trade_date
    target = data_root / "raw" / "tushare" / f"trade_date={trade_date}"

    if staging.exists():
        raise FileExistsError(f"Staging directory already exists: {staging}")
    if target.exists():
        raise FileExistsError(f"Target directory already exists: {target}")

    staging.mkdir(parents=True)
    frames = fetch_trade_date(api, trade_date)

    file_entries: list[dict[str, object]] = []
    for name, frame in frames.items():
        path = staging / f"{name}.csv"
        write_csv(path, frame)
        file_entries.append(
            {
                "name": path.name,
                "rows": len(frame),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )

    manifest = {
        "schema_version": 1,
        "source": "tushare_pro",
        "trade_date": trade_date,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "tushare_sdk_version": sdk_version,
        "files": file_entries,
    }
    manifest_path = staging / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    staging.replace(target)
    return target
