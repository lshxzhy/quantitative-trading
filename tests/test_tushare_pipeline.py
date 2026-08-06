from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src.tushare_pipeline import (
    ENDPOINT_SPECS,
    TARGET_INDEX_CODES,
    download_trade_date,
    parse_trade_date,
    validate_frame,
)
from src.update import default_end_date, query_open_dates, resolve_start_date


TRADE_DATE = "20260803"


def frame_for(name: str, rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=ENDPOINT_SPECS[name].fields)


class FakeApi:
    def query(self, api_name: str, fields: str = "", **kwargs: str) -> pd.DataFrame:
        if api_name == "trade_cal":
            return frame_for(
                "trade_cal",
                [
                    {
                        "exchange": "SSE",
                        "cal_date": TRADE_DATE,
                        "is_open": "1",
                        "pretrade_date": "20260731",
                    }
                ],
            )
        if api_name == "stock_basic":
            return frame_for(
                "stock_basic",
                [
                    {"ts_code": "600000.SH", "symbol": "600000", "exchange": "SSE"},
                    {"ts_code": "000001.SZ", "symbol": "000001", "exchange": "SZSE"},
                    {"ts_code": "920992.BJ", "symbol": "920992", "exchange": "BSE"},
                ],
            )
        if api_name in {"daily", "daily_basic", "adj_factor", "stk_limit"}:
            return frame_for(
                api_name,
                [
                    {"ts_code": "600000.SH", "trade_date": TRADE_DATE},
                    {"ts_code": "000001.SZ", "trade_date": TRADE_DATE},
                    {"ts_code": "920992.BJ", "trade_date": TRADE_DATE},
                ],
            )
        if api_name == "suspend_d":
            return frame_for("suspend_d", [])
        if api_name == "index_daily":
            return frame_for(
                "index_daily",
                [{"ts_code": kwargs["ts_code"], "trade_date": TRADE_DATE}],
            )
        raise AssertionError(f"Unexpected API name: {api_name}")


class FakeCalendarApi:
    def query(self, api_name: str, fields: str = "", **kwargs: str) -> pd.DataFrame:
        if api_name != "trade_cal":
            raise AssertionError(f"Unexpected API name: {api_name}")
        return frame_for(
            "trade_cal",
            [
                {
                    "exchange": "SSE",
                    "cal_date": "20260801",
                    "is_open": "0",
                    "pretrade_date": "20260731",
                },
                {
                    "exchange": "SSE",
                    "cal_date": "20260803",
                    "is_open": "1",
                    "pretrade_date": "20260731",
                },
            ],
        )


class ParseDateTests(unittest.TestCase):
    def test_parse_trade_date_accepts_both_supported_formats(self) -> None:
        self.assertEqual(parse_trade_date("2026-08-03"), TRADE_DATE)
        self.assertEqual(parse_trade_date(TRADE_DATE), TRADE_DATE)

    def test_parse_trade_date_rejects_invalid_calendar_date(self) -> None:
        with self.assertRaises(ValueError):
            parse_trade_date("2026-02-30")


class ValidationTests(unittest.TestCase):
    def test_duplicate_keys_are_rejected(self) -> None:
        frame = frame_for(
            "daily",
            [
                {"ts_code": "600000.SH", "trade_date": TRADE_DATE},
                {"ts_code": "600000.SH", "trade_date": TRADE_DATE},
            ],
        )
        with self.assertRaisesRegex(RuntimeError, "duplicate keys"):
            validate_frame("daily", frame, ENDPOINT_SPECS["daily"], TRADE_DATE)

    def test_download_commits_a_complete_trading_day(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            target = download_trade_date(
                api=FakeApi(),
                trade_date=TRADE_DATE,
                data_root=Path(temp_directory),
                sdk_version="test",
            )

            self.assertTrue((target / "manifest.json").is_file())
            self.assertEqual(
                {path.stem for path in target.glob("*.csv")},
                {*ENDPOINT_SPECS},
            )
            indexes = pd.read_csv(target / "index_daily.csv", dtype=str)
            self.assertEqual(set(indexes["ts_code"]), set(TARGET_INDEX_CODES))

    def test_existing_target_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            target = (
                Path(temp_directory) / "raw" / "tushare" / f"trade_date={TRADE_DATE}"
            )
            target.mkdir(parents=True)
            with self.assertRaisesRegex(FileExistsError, "Target directory"):
                download_trade_date(
                    api=FakeApi(),
                    trade_date=TRADE_DATE,
                    data_root=Path(temp_directory),
                    sdk_version="test",
                )


class UpdateTests(unittest.TestCase):
    def test_default_end_date_waits_until_18_china_time(self) -> None:
        timezone = ZoneInfo("Asia/Shanghai")
        before_ready = datetime(2026, 8, 6, 17, 59, tzinfo=timezone)
        after_ready = datetime(2026, 8, 6, 18, 0, tzinfo=timezone)
        self.assertEqual(default_end_date(before_ready), "20260805")
        self.assertEqual(default_end_date(after_ready), "20260806")

    def test_start_date_continues_after_latest_partition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            data_root = Path(temp_directory)
            (data_root / "raw" / "tushare" / "trade_date=20260803").mkdir(parents=True)
            self.assertEqual(resolve_start_date(data_root, None), "20260804")

    def test_open_dates_follow_exchange_calendar(self) -> None:
        self.assertEqual(
            query_open_dates(FakeCalendarApi(), "20260801", "20260803"),
            ["20260803"],
        )


if __name__ == "__main__":
    unittest.main()
