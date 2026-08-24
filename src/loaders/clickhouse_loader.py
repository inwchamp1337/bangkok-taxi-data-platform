"""
Load validated GPS probe data into ClickHouse.

Features:
- Chunked loading (configurable batch size) to manage memory
- Idempotent: checks partition existence before loading
- Tracks lineage via _loaded_at and _source_file metadata columns
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import clickhouse_connect
import polars as pl

from src.config.settings import get_settings
from src.validation.schemas import COLUMN_NAMES

logger = logging.getLogger(__name__)


def get_clickhouse_client():
    """Create and return a ClickHouse client."""
    settings = get_settings()
    return clickhouse_connect.get_client(
        host=settings.clickhouse.host,
        port=settings.clickhouse.port,
        username=settings.clickhouse.user,
        password=settings.clickhouse.password,
        database=settings.clickhouse.db,
    )


def check_data_exists(client, source_file: str) -> bool:
    """Check if data from a specific source file has already been loaded."""
    result = client.query(
        "SELECT count() FROM raw_gps_pings WHERE _source_file = {source_file:String}",
        parameters={"source_file": source_file},
    )
    count = result.result_rows[0][0] if result.result_rows else 0
    return count > 0


def load_dataframe_to_clickhouse(
    df: pl.DataFrame,
    source_file: str,
    batch_size: int | None = None,
) -> int:
    """
    Load a validated Polars DataFrame into ClickHouse raw_gps_pings table.

    Args:
        df: Validated DataFrame with GPS ping data.
        source_file: Original source filename (for lineage tracking).
        batch_size: Number of rows per INSERT batch. Defaults to config value.

    Returns:
        Total number of rows inserted.
    """
    settings = get_settings()
    client = get_clickhouse_client()
    batch_size = batch_size or settings.batch_size

    # Check idempotency
    if check_data_exists(client, source_file):
        logger.info("Data from %s already loaded, skipping", source_file)
        return 0

    # Ensure timestamp is datetime and add metadata columns
    now = datetime.now()
    if df["timestamp"].dtype == pl.Utf8:
        df = df.with_columns(
            pl.col("timestamp").str.to_datetime("%Y-%m-%d %H:%M:%S", strict=False)
        )

    df = df.with_columns([
        pl.lit(now).alias("_loaded_at"),
        pl.lit(source_file).alias("_source_file"),
    ])

    # Prepare column order matching the ClickHouse table
    ch_columns = [
        "vehicle_id",
        "gps_valid",
        "lat",
        "lon",
        "timestamp",
        "speed",
        "passenger_lamp",
        "engine_acc",
        "_loaded_at",
        "_source_file",
    ]

    total_rows = len(df)
    inserted = 0

    logger.info("Loading %d rows from %s into ClickHouse (batch_size=%d)", total_rows, source_file, batch_size)

    for start in range(0, total_rows, batch_size):
        end = min(start + batch_size, total_rows)
        batch = df.slice(start, end - start)

        # Convert to list of lists for clickhouse-connect
        data = []
        for row in batch.iter_rows():
            # row order: vehicle_id, gps_valid, lat, lon, timestamp, speed, passenger_lamp, engine_acc, _loaded_at, _source_file
            data.append(list(row))

        client.insert(
            table="raw_gps_pings",
            data=data,
            column_names=ch_columns,
        )

        inserted += len(data)
        pct = inserted / total_rows * 100
        logger.info("  Inserted %d / %d rows (%.1f%%)", inserted, total_rows, pct)

    logger.info("✅ Loaded %d rows from %s into ClickHouse", inserted, source_file)
    return inserted


def load_csv_file(filepath: Path) -> int:
    """
    Read, validate, and load a single CSV file into ClickHouse.

    This is the high-level entry point that combines validation + loading.

    Args:
        filepath: Path to the CSV file.

    Returns:
        Number of valid rows inserted.
    """
    from src.validation.validators import validate_file

    valid_df, invalid_df, report = validate_file(filepath)

    if len(invalid_df) > 0:
        logger.warning(
            "⚠️ %d invalid rows in %s (%.1f%% invalid rate)",
            len(invalid_df),
            filepath.name,
            100 - report.valid_pct,
        )

    if len(valid_df) == 0:
        logger.error("No valid rows in %s, skipping load", filepath.name)
        return 0

    return load_dataframe_to_clickhouse(valid_df, source_file=filepath.name)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    parser = argparse.ArgumentParser(description="Load probe data into ClickHouse")
    parser.add_argument("--file", help="Path to a specific CSV file")
    parser.add_argument("--month", help="Year-month in YYYYMM format to load all files")
    args = parser.parse_args()

    if args.file:
        rows = load_csv_file(Path(args.file))
        print(f"Loaded {rows} rows")
    elif args.month:
        from src.ingestion.extractor import list_extracted_files

        files = list_extracted_files(args.month)
        total = 0
        for f in files:
            total += load_csv_file(f)
        print(f"Total loaded: {total} rows from {len(files)} files")
    else:
        print("Specify --file or --month")
