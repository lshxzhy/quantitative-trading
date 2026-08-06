from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

import pandas as pd


TARGET_INDEX_CODES = ("000001.SH", "000300.SH", "000852.SH", "000905.SH")
BSE_OPEN_DATE = date(2021, 11, 15)
STOCK_KEYS = ("trade_date", "ts_code")
INDEX_KEYS = ("trade_date", "ts_code")


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


STOCK_COLUMNS = (
    "trade_date",
    *ENDPOINT_SPECS["stock_basic"].fields,
    *(
        field
        for field in ENDPOINT_SPECS["daily"].fields
        if field not in {"ts_code", "trade_date"}
    ),
    *(
        "daily_basic_close" if field == "close" else field
        for field in ENDPOINT_SPECS["daily_basic"].fields
        if field not in {"ts_code", "trade_date"}
    ),
    "adj_factor",
    "limit_pre_close",
    "up_limit",
    "down_limit",
    "suspend_timing",
    "suspend_type",
)
INDEX_COLUMNS = ENDPOINT_SPECS["index_daily"].fields
STOCK_STRING_COLUMNS = ("trade_date", "ts_code", "symbol", "list_date", "delist_date")
STOCK_NUMERIC_COLUMNS = (
    *(
        field
        for field in ENDPOINT_SPECS["daily"].fields
        if field not in {"ts_code", "trade_date"}
    ),
    *(
        "daily_basic_close" if field == "close" else field
        for field in ENDPOINT_SPECS["daily_basic"].fields
        if field not in {"ts_code", "trade_date"}
    ),
    "adj_factor",
    "limit_pre_close",
    "up_limit",
    "down_limit",
)
INDEX_NUMERIC_COLUMNS = tuple(
    field for field in INDEX_COLUMNS if field not in {"ts_code", "trade_date"}
)


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
        duplicates = frame.loc[
            frame.duplicated(list(spec.keys), keep=False), list(spec.keys)
        ]
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
    suffixes = set(frame["ts_code"].astype(str).str.rsplit(".", n=1).str[-1])
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


def _joined_values(values: pd.Series) -> object:
    cleaned = sorted(
        {
            str(value).strip()
            for value in values
            if pd.notna(value) and str(value).strip()
        }
    )
    return "|".join(cleaned) if cleaned else pd.NA


def _aggregate_suspensions(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["ts_code", "trade_date", "suspend_timing", "suspend_type"]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    return (
        frame.loc[:, columns]
        .groupby(["ts_code", "trade_date"], as_index=False, sort=True, dropna=False)
        .agg(
            suspend_timing=("suspend_timing", _joined_values),
            suspend_type=("suspend_type", _joined_values),
        )
    )


def _validate_equal_numeric_columns(
    frame: pd.DataFrame,
    left_column: str,
    right_column: str,
) -> None:
    comparable = frame[left_column].notna() & frame[right_column].notna()
    if not comparable.any():
        return
    left = pd.to_numeric(frame.loc[comparable, left_column], errors="raise")
    right = pd.to_numeric(frame.loc[comparable, right_column], errors="raise")
    mismatch = (left - right).abs() > 1e-8
    if mismatch.any():
        rows = frame.loc[
            left.index[mismatch],
            ["trade_date", "ts_code", left_column, right_column],
        ]
        raise RuntimeError(
            f"{left_column} and {right_column} disagree: "
            f"{rows.head(10).to_dict(orient='records')}"
        )


def _normalize_stock_types(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in STOCK_STRING_COLUMNS:
        result[column] = result[column].astype("string")
    for column in STOCK_NUMERIC_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="raise")
    return result


def _normalize_index_types(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in ("trade_date", "ts_code"):
        result[column] = result[column].astype("string")
    for column in INDEX_NUMERIC_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="raise")
    return result


def build_stocks_frame(
    frames: Mapping[str, pd.DataFrame], trade_date: str
) -> pd.DataFrame:
    trade_date = parse_trade_date(trade_date)
    required = {
        "stock_basic",
        "daily",
        "daily_basic",
        "adj_factor",
        "stk_limit",
        "suspend_d",
    }
    missing = sorted(required - set(frames))
    if missing:
        raise RuntimeError(f"Missing stock input frames: {missing}")

    base = frames["stock_basic"].copy()
    if base["ts_code"].duplicated().any():
        raise RuntimeError("stock_basic has duplicate ts_code values")
    base.insert(0, "trade_date", trade_date)

    daily_basic = frames["daily_basic"].rename(
        columns={"close": "daily_basic_close"}
    )
    limits = frames["stk_limit"].rename(columns={"pre_close": "limit_pre_close"})
    suspensions = _aggregate_suspensions(frames["suspend_d"])

    result = base.merge(
        frames["daily"], on=["trade_date", "ts_code"], how="left", validate="one_to_one"
    )
    for addition in (daily_basic, frames["adj_factor"], limits, suspensions):
        result = result.merge(
            addition,
            on=["trade_date", "ts_code"],
            how="left",
            validate="one_to_one",
        )

    result = _normalize_stock_types(result.loc[:, STOCK_COLUMNS])
    result = result.sort_values(list(STOCK_KEYS), kind="stable").reset_index(drop=True)
    _validate_equal_numeric_columns(result, "close", "daily_basic_close")
    _validate_equal_numeric_columns(result, "pre_close", "limit_pre_close")
    validate_stock_table(result)
    return result


def build_indexes_frame(
    frames: Mapping[str, pd.DataFrame], trade_date: str
) -> pd.DataFrame:
    trade_date = parse_trade_date(trade_date)
    if "index_daily" not in frames:
        raise RuntimeError("Missing index_daily input frame")
    result = _normalize_index_types(frames["index_daily"].loc[:, INDEX_COLUMNS])
    actual_dates = set(result["trade_date"].astype(str))
    if actual_dates != {trade_date}:
        raise RuntimeError(
            f"index_daily returned dates {sorted(actual_dates)}, expected {trade_date}"
        )
    result = result.sort_values(list(INDEX_KEYS), kind="stable").reset_index(drop=True)
    validate_index_table(result)
    return result


def _validate_dates(values: pd.Series, name: str) -> None:
    text = values.astype("string")
    invalid_shape = ~text.str.fullmatch(r"\d{8}", na=False)
    if invalid_shape.any():
        raise RuntimeError(f"{name} contains invalid YYYYMMDD values")
    parsed = pd.to_datetime(text, format="%Y%m%d", errors="coerce")
    if parsed.isna().any():
        raise RuntimeError(f"{name} contains invalid calendar dates")


def validate_stock_table(frame: pd.DataFrame) -> None:
    if tuple(frame.columns) != STOCK_COLUMNS:
        raise RuntimeError("stocks columns do not match the version 1 schema")
    if frame.empty:
        raise RuntimeError("stocks is empty")
    if frame.duplicated(list(STOCK_KEYS)).any():
        raise RuntimeError("stocks has duplicate trade_date + ts_code keys")
    _validate_dates(frame["trade_date"], "stocks.trade_date")
    expected_order = frame.sort_values(list(STOCK_KEYS), kind="stable").index
    if not expected_order.equals(frame.index):
        raise RuntimeError("stocks is not sorted by trade_date and ts_code")
    for trade_date, group in frame.groupby("trade_date", sort=False):
        validate_market_coverage(group, str(trade_date), "stocks")
    _validate_equal_numeric_columns(frame, "close", "daily_basic_close")
    _validate_equal_numeric_columns(frame, "pre_close", "limit_pre_close")


def validate_index_table(frame: pd.DataFrame) -> None:
    if tuple(frame.columns) != INDEX_COLUMNS:
        raise RuntimeError("indexes columns do not match the version 1 schema")
    if frame.empty:
        raise RuntimeError("indexes is empty")
    if frame.duplicated(list(INDEX_KEYS)).any():
        raise RuntimeError("indexes has duplicate trade_date + ts_code keys")
    _validate_dates(frame["trade_date"], "indexes.trade_date")
    expected_order = frame.sort_values(list(INDEX_KEYS), kind="stable").index
    if not expected_order.equals(frame.index):
        raise RuntimeError("indexes is not sorted by trade_date and ts_code")
    expected_codes = set(TARGET_INDEX_CODES)
    for trade_date, group in frame.groupby("trade_date", sort=False):
        actual_codes = set(group["ts_code"].astype(str))
        if len(group) != len(expected_codes) or actual_codes != expected_codes:
            raise RuntimeError(
                f"indexes for {trade_date} contain {sorted(actual_codes)}, "
                f"expected {sorted(expected_codes)}"
            )


def validate_tables(stocks: pd.DataFrame, indexes: pd.DataFrame) -> None:
    validate_stock_table(stocks)
    validate_index_table(indexes)
    stock_dates = set(stocks["trade_date"].astype(str))
    index_dates = set(indexes["trade_date"].astype(str))
    if stock_dates != index_dates:
        raise RuntimeError(
            "stocks and indexes do not contain the same complete trading dates"
        )
