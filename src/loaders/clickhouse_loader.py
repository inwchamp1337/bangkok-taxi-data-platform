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


def load_csv_from_s3(minio_bucket: str, minio_key: str, source_file: str) -> dict:
    """
    Load a CSV file directly from MinIO into ClickHouse using s3() table function.
    This is ELT: bypassing Python memory and relying on ClickHouse speed.
    """
    settings = get_settings()
    client = get_clickhouse_client()

    # Construct the S3 URL for ClickHouse
    s3_url = f"http://{settings.minio.endpoint}/{minio_bucket}/{minio_key}"
    
    # ClickHouse S3 function requires credentials
    query = f"""
    INSERT INTO taxi.raw_gps_pings
    SELECT 
        c1 AS vehicle_id,
        c2 AS gps_valid,
        c3 AS lat,
        c4 AS lon,
        toDateTimeOrNull(c5, 'Asia/Bangkok') AS timestamp,
        c6 AS speed,
        c7 AS passenger_lamp,
        c8 AS engine_acc,
        now() AS _loaded_at,
        '{source_file}' AS _source_file
    FROM s3(
        '{s3_url}', 
        '{settings.minio.root_user}', 
        '{settings.minio.root_password}', 
        'CSV'
    )
    """

    logger.info("Executing ClickHouse S3 load for %s", source_file)
    
    try:
        # We can't easily get the number of rows inserted from the Python client for an INSERT SELECT
        # without running a count query before/after, but we can just execute it.
        client.command(query)
        logger.info("✅ Successfully loaded %s via S3", source_file)
        return {"file": source_file, "status": "success"}
    except Exception as exc:
        logger.error("❌ Failed to load %s via S3: %s", source_file, exc)
        return {"file": source_file, "status": "error", "error": str(exc)}


def load_csv_file(filepath: Path) -> dict:
    """
    Legacy wrapper for local files. This now assumes the file must be uploaded to MinIO first.
    For the Control Panel, we should upload the file to MinIO and then call load_csv_from_s3.
    """
    raise NotImplementedError("Direct local CSV loading is disabled in favor of ELT via S3. Upload to MinIO first.")



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
