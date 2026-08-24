"""
Upload extracted CSV files to MinIO (S3-compatible storage).

Organizes files with Hive-style partitioning:
  s3://raw/probe-data/year=YYYY/month=MM/probe_YYYY-MM-DD.csv

Idempotent — skips files that already exist in MinIO.
"""

from __future__ import annotations

import logging
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


def get_minio_client() -> Minio:
    """Create and return a MinIO client."""
    settings = get_settings()
    return Minio(
        endpoint=settings.minio.endpoint,
        access_key=settings.minio.root_user,
        secret_key=settings.minio.root_password,
        secure=settings.minio.secure,
    )


def upload_files_to_minio(csv_files: list[Path], year_month: str) -> list[str]:
    """
    Upload a list of CSV files to MinIO raw bucket.

    Args:
        csv_files: List of local CSV file paths.
        year_month: Target month in YYYYMM format (e.g., "201802").

    Returns:
        List of MinIO object keys that were uploaded.
    """
    settings = get_settings()
    client = get_minio_client()
    bucket = settings.minio.raw_bucket

    # Ensure bucket exists
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        logger.info("Created bucket: %s", bucket)

    year = year_month[:4]
    month = year_month[4:6]
    uploaded_keys: list[str] = []

    for csv_file in csv_files:
        object_key = f"probe-data/year={year}/month={month}/{csv_file.name}"

        # Check if already uploaded
        try:
            stat = client.stat_object(bucket, object_key)
            if stat.size == csv_file.stat().st_size:
                logger.debug("Already in MinIO: %s (size matches)", object_key)
                uploaded_keys.append(object_key)
                continue
        except S3Error:
            pass  # Object doesn't exist, proceed with upload

        # Upload
        file_size = csv_file.stat().st_size
        logger.info("Uploading %s (%.1f MB) → s3://%s/%s", csv_file.name, file_size / (1024 * 1024), bucket, object_key)

        client.fput_object(
            bucket_name=bucket,
            object_name=object_key,
            file_path=str(csv_file),
            content_type="text/csv",
        )

        uploaded_keys.append(object_key)

    logger.info("✅ Uploaded %d files to s3://%s/probe-data/year=%s/month=%s/", len(uploaded_keys), bucket, year, month)
    return uploaded_keys


def upload_quarantine(csv_file: Path, error_report: dict) -> str:
    """
    Upload an invalid data file to the quarantine bucket.

    Args:
        csv_file: Path to the quarantined file.
        error_report: Validation error details.

    Returns:
        MinIO object key of the quarantined file.
    """
    import json

    settings = get_settings()
    client = get_minio_client()
    bucket = settings.minio.quarantine_bucket

    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)

    # Upload the CSV
    object_key = f"invalid/{csv_file.name}"
    client.fput_object(bucket, object_key, str(csv_file), content_type="text/csv")

    # Upload the error report alongside
    report_key = f"invalid/{csv_file.stem}_errors.json"
    report_bytes = json.dumps(error_report, indent=2, default=str).encode("utf-8")

    from io import BytesIO
    client.put_object(bucket, report_key, BytesIO(report_bytes), len(report_bytes), content_type="application/json")

    logger.info("⚠️ Quarantined %s → s3://%s/%s", csv_file.name, bucket, object_key)
    return object_key


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    parser = argparse.ArgumentParser(description="Upload extracted CSVs to MinIO")
    parser.add_argument("--month", required=True, help="Year-month in YYYYMM format")
    args = parser.parse_args()

    from src.ingestion.extractor import list_extracted_files

    files = list_extracted_files(args.month)
    if not files:
        print(f"No extracted files found for {args.month}")
    else:
        upload_files_to_minio(files, args.month)
