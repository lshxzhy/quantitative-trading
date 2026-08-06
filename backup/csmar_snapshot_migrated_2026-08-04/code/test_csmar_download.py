from __future__ import annotations

import importlib.util
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from winreg import HKEY_CURRENT_USER, OpenKey, QueryValueEx


SCRIPT_PATH = Path(__file__).resolve().parent / "csmar_download.py"
SPEC = importlib.util.spec_from_file_location("data_download", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载 {SCRIPT_PATH}")
DATA_DOWNLOAD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DATA_DOWNLOAD)


def write_zip(path: Path, header: str, rows: list[str]) -> None:
    content = "\n".join([header, *rows, ""]).encode("utf-8-sig")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data.csv", content)


class DateRangeTests(unittest.TestCase):
    def test_split_date_range(self) -> None:
        self.assertEqual(
            DATA_DOWNLOAD.split_date_range(
                date(2020, 1, 1),
                date(2026, 1, 2),
                5,
            ),
            [
                (date(2020, 1, 1), date(2024, 12, 31)),
                (date(2025, 1, 1), date(2026, 1, 2)),
            ],
        )

    def test_cached_chromedriver_matches_installed_chrome_major(self) -> None:
        driver_path = DATA_DOWNLOAD.cached_chromedriver()
        with OpenKey(HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon") as key:
            chrome_version = str(QueryValueEx(key, "version")[0])

        self.assertTrue(driver_path.is_file())
        self.assertEqual(
            driver_path.parent.name.split(".", 1)[0],
            chrome_version.split(".", 1)[0],
        )

    def test_split_date_range_from_leap_day(self) -> None:
        self.assertEqual(
            DATA_DOWNLOAD.split_date_range(
                date(2020, 2, 29),
                date(2026, 3, 1),
                5,
            ),
            [
                (date(2020, 2, 29), date(2025, 2, 27)),
                (date(2025, 2, 28), date(2026, 3, 1)),
            ],
        )


class ArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp_directory.name)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def test_numbered_archives_require_a_continuous_sequence(self) -> None:
        write_zip(self.directory / "1.zip", "Code,Date", ["1,2026-01-01"])
        write_zip(self.directory / "3.zip", "Code,Date", ["1,2026-01-03"])

        with self.assertRaisesRegex(RuntimeError, "ZIP 编号不连续"):
            DATA_DOWNLOAD.numbered_archives(self.directory)

    def test_latest_local_date_reads_all_numbered_archives(self) -> None:
        write_zip(
            self.directory / "1.zip",
            "Stkcd,Trddt",
            ["000001,2026-01-01", "000002,2026-01-03"],
        )
        write_zip(
            self.directory / "2.zip",
            "Stkcd,Trddt",
            ["000001,2026-02-05"],
        )

        self.assertEqual(
            DATA_DOWNLOAD.latest_local_date(self.directory, "Trddt"),
            (date(2026, 2, 5), 3),
        )

    def test_validate_archive_accepts_expected_index_data(self) -> None:
        archive_path = self.directory / "1.zip"
        write_zip(
            archive_path,
            "Indexcd,Idxtrd01,Close",
            [
                "000001,2026-01-02,1",
                "000300,2026-01-05,2",
                "000852,2026-01-05,3",
                "000905,2026-01-05,4",
            ],
        )

        DATA_DOWNLOAD.validate_archive(
            archive_path,
            "Indexcd",
            "Idxtrd01",
            date(2026, 1, 1),
            date(2026, 1, 5),
            {"000001", "000300", "000852", "000905"},
        )

    def test_validate_archive_exposes_wrong_codes(self) -> None:
        archive_path = self.directory / "1.zip"
        write_zip(
            archive_path,
            "Indexcd,Idxtrd01",
            ["000001,2026-01-05"],
        )

        with self.assertRaisesRegex(RuntimeError, "指数代码不符"):
            DATA_DOWNLOAD.validate_archive(
                archive_path,
                "Indexcd",
                "Idxtrd01",
                date(2026, 1, 1),
                date(2026, 1, 5),
                {"000001", "000300"},
            )

    def test_validate_archive_exposes_missing_fields(self) -> None:
        archive_path = self.directory / "1.zip"
        write_zip(archive_path, "Indexcd,Close", ["000001,1"])

        with self.assertRaisesRegex(RuntimeError, "缺少 Indexcd 或 Idxtrd01 字段"):
            DATA_DOWNLOAD.validate_archive(
                archive_path,
                "Indexcd",
                "Idxtrd01",
                date(2026, 1, 1),
                date(2026, 1, 5),
            )


if __name__ == "__main__":
    unittest.main()
