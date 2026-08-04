"""Archived merge utility for the CSMAR ZIP snapshot."""

from __future__ import annotations

import argparse
import codecs
import csv
import io
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_ROOT = PROJECT_ROOT / "raw"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "processed"
CSV_ENCODINGS = ("utf-8-sig", "gb18030", "gbk")
BATCH_SIZE = 50_000


@dataclass(frozen=True)
class DatasetConfig:
    kind: str
    input_dir: Path
    output_file: Path
    code_column: str
    date_column: str


def log(message: str) -> None:
    print(f"[merge] {message}", flush=True)


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def numeric_zip_sort_key(path: Path) -> tuple[int, str]:
    if path.stem.isdigit():
        return int(path.stem), path.name

    return 10**9, path.name


def detect_member_encoding(archive: zipfile.ZipFile, member_name: str) -> str:
    with archive.open(member_name) as binary_file:
        sample = binary_file.read(65536)

    for encoding in CSV_ENCODINGS:
        try:
            decoder = codecs.getincrementaldecoder(encoding)()
            decoder.decode(sample, final=False)
            return encoding
        except UnicodeDecodeError:
            continue

    raise RuntimeError(f"{member_name} encoding is not supported")


def csv_members(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as archive:
        return [name for name in archive.namelist() if name.lower().endswith(".csv")]


def open_csv_reader(zip_path: Path, member_name: str) -> tuple[zipfile.ZipFile, csv.DictReader]:
    archive = zipfile.ZipFile(zip_path)
    encoding = detect_member_encoding(archive, member_name)
    binary_file = archive.open(member_name)
    text_file = io.TextIOWrapper(binary_file, encoding=encoding, newline="")
    reader = csv.DictReader(text_file)
    return archive, reader


def create_table(connection: sqlite3.Connection, fieldnames: list[str]) -> None:
    if len(fieldnames) != len(set(fieldnames)):
        raise RuntimeError("CSV header contains duplicate field names")

    columns_sql = ", ".join(f"{quote_identifier(field)} TEXT NOT NULL" for field in fieldnames)
    unique_sql = ", ".join(quote_identifier(field) for field in fieldnames)
    connection.execute(f"CREATE TABLE merged ({columns_sql}, UNIQUE ({unique_sql}))")


def insert_rows(
    connection: sqlite3.Connection,
    config: DatasetConfig,
    zip_path: Path,
    member_name: str,
    expected_fieldnames: list[str] | None,
) -> tuple[list[str], int]:
    archive, reader = open_csv_reader(zip_path, member_name)
    try:
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise RuntimeError(f"{zip_path.name}:{member_name} has no CSV header")
        if config.code_column not in fieldnames or config.date_column not in fieldnames:
            raise RuntimeError(
                f"{zip_path.name}:{member_name} missing {config.code_column} or {config.date_column}"
            )
        if expected_fieldnames is not None and fieldnames != expected_fieldnames:
            raise RuntimeError(f"{zip_path.name}:{member_name} header differs from earlier CSV files")

        placeholders = ", ".join("?" for _ in fieldnames)
        columns_sql = ", ".join(quote_identifier(field) for field in fieldnames)
        insert_sql = f"INSERT OR IGNORE INTO merged ({columns_sql}) VALUES ({placeholders})"

        rows: list[tuple[str, ...]] = []
        read_count = 0
        for row in reader:
            if None in row:
                raise RuntimeError(f"{zip_path.name}:{member_name} has more columns than its header")

            rows.append(tuple(row.get(field, "") or "" for field in fieldnames))
            read_count += 1
            if len(rows) >= BATCH_SIZE:
                connection.executemany(insert_sql, rows)
                rows.clear()

        if rows:
            connection.executemany(insert_sql, rows)

        return fieldnames, read_count
    finally:
        archive.close()


def import_dataset(connection: sqlite3.Connection, config: DatasetConfig) -> tuple[list[str], int]:
    zip_paths = sorted(config.input_dir.glob("*.zip"), key=numeric_zip_sort_key)
    if not zip_paths:
        raise RuntimeError(f"No zip files found in {config.input_dir}")

    fieldnames: list[str] | None = None
    total_read = 0
    for zip_path in zip_paths:
        members = csv_members(zip_path)
        if not members:
            raise RuntimeError(f"{zip_path.name} contains no CSV files")

        for member_name in members:
            if fieldnames is None:
                archive, reader = open_csv_reader(zip_path, member_name)
                try:
                    if not reader.fieldnames:
                        raise RuntimeError(f"{zip_path.name}:{member_name} has no CSV header")
                    fieldnames = reader.fieldnames
                    if config.code_column not in fieldnames or config.date_column not in fieldnames:
                        raise RuntimeError(
                            f"{zip_path.name}:{member_name} missing "
                            f"{config.code_column} or {config.date_column}"
                        )
                    create_table(connection, fieldnames)
                finally:
                    archive.close()

            fieldnames, read_count = insert_rows(
                connection,
                config,
                zip_path,
                member_name,
                fieldnames,
            )
            total_read += read_count
            log(f"{config.kind}: imported {zip_path.name}:{member_name} ({read_count} rows)")

    if fieldnames is None:
        raise RuntimeError(f"No readable CSV files found in {config.input_dir}")

    return fieldnames, total_read


def export_dataset(
    connection: sqlite3.Connection,
    config: DatasetConfig,
    fieldnames: list[str],
) -> int:
    config.output_file.parent.mkdir(parents=True, exist_ok=True)
    temp_output = config.output_file.with_name(config.output_file.name + ".tmp")
    temp_output.unlink(missing_ok=True)

    select_columns = ", ".join(quote_identifier(field) for field in fieldnames)
    order_columns = [config.code_column, config.date_column]
    order_columns.extend(field for field in fieldnames if field not in set(order_columns))
    order_sql = ", ".join(quote_identifier(field) for field in order_columns)

    row_count = 0
    with temp_output.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.writer(output_file, lineterminator="\n")
        writer.writerow(fieldnames)
        cursor = connection.execute(f"SELECT {select_columns} FROM merged ORDER BY {order_sql}")
        while True:
            rows = cursor.fetchmany(BATCH_SIZE)
            if not rows:
                break
            writer.writerows(rows)
            row_count += len(rows)

    temp_output.replace(config.output_file)
    return row_count


def merge_dataset(config: DatasetConfig) -> None:
    log(f"{config.kind}: reading {config.input_dir}")
    config.output_file.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"merge_{config.kind}_", dir=config.output_file.parent) as temp_dir:
        database_path = Path(temp_dir) / "merge.sqlite"
        connection = sqlite3.connect(database_path)
        try:
            connection.execute("PRAGMA journal_mode = OFF")
            connection.execute("PRAGMA synchronous = OFF")
            connection.execute("PRAGMA temp_store = FILE")

            fieldnames, total_read = import_dataset(connection, config)
            unique_count = connection.execute("SELECT COUNT(*) FROM merged").fetchone()[0]
            log(f"{config.kind}: read {total_read} rows, kept {unique_count} unique rows")

            index_sql = (
                "CREATE INDEX merged_sort_idx ON merged "
                f"({quote_identifier(config.code_column)}, {quote_identifier(config.date_column)})"
            )
            connection.execute(index_sql)

            output_count = export_dataset(connection, config, fieldnames)
        finally:
            connection.close()

    log(f"{config.kind}: wrote {output_count} rows to {config.output_file}")


def dataset_configs(raw_root: Path, output_dir: Path) -> dict[str, DatasetConfig]:
    return {
        "stocks": DatasetConfig(
            kind="stocks",
            input_dir=raw_root / "stocks",
            output_file=output_dir / "stocks.csv",
            code_column="Stkcd",
            date_column="Trddt",
        ),
        "indexes": DatasetConfig(
            kind="indexes",
            input_dir=raw_root / "indexes",
            output_file=output_dir / "indexes.csv",
            code_column="Indexcd",
            date_column="Idxtrd01",
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge CSMAR raw zip files into sorted CSV files.")
    parser.add_argument(
        "--kind",
        choices=("all", "stocks", "indexes"),
        default="all",
        help="Dataset to merge. Defaults to all.",
    )
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=DEFAULT_RAW_ROOT,
        help="Root directory containing raw stocks/ and indexes/ zip folders.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for merged CSV outputs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configs = dataset_configs(args.raw_root.resolve(), args.output_dir.resolve())
    selected_kinds = ("stocks", "indexes") if args.kind == "all" else (args.kind,)

    for kind in selected_kinds:
        merge_dataset(configs[kind])


if __name__ == "__main__":
    main()
