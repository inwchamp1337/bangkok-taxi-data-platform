"""
Bangkok Taxi Ingestion DAG.

Orchestrates the full data pipeline from download to ClickHouse load:
  1. Download monthly archive from iTIC
  2. Extract tar.bz2 → daily CSV files
  3. Upload CSVs to MinIO (raw zone)
  4. Validate data quality
  5. Load valid data into ClickHouse
  6. Trigger dbt transformation

Parameters:
  - year_month: Target month in YYYYMM format (e.g., "201802")

Schedule: Manual trigger (no automatic schedule)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

logger = logging.getLogger(__name__)

default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


@dag(
    dag_id="taxi_ingestion",
    default_args=default_args,
    description="Ingest Bangkok taxi GPS data from iTIC → MinIO → ClickHouse",
    schedule=None,  # Manual trigger only
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["taxi", "ingestion"],
    params={"year_month": "201802"},
    doc_md=__doc__,
)
def taxi_ingestion_dag():
    """Main ingestion DAG."""

    @task()
    def download_archive(**context) -> str:
        """Download the monthly archive from iTIC."""
        from src.ingestion.downloader import download_archive as dl

        year_month = context["params"]["year_month"]
        logger.info("Starting download for month: %s", year_month)

        filepath = dl(year_month)
        return str(filepath)

    @task()
    def extract_csv_files(archive_path: str, **context) -> list[str]:
        """Extract tar.bz2 archive into daily CSV files."""
        from src.ingestion.extractor import extract_archive

        year_month = context["params"]["year_month"]
        logger.info("Extracting archive for month: %s", year_month)

        files = extract_archive(year_month)
        return [str(f) for f in files]

    @task()
    def upload_to_minio(csv_paths: list[str], **context) -> list[str]:
        """Upload extracted CSVs to MinIO raw bucket."""
        from src.ingestion.uploader import upload_files_to_minio

        year_month = context["params"]["year_month"]
        paths = [Path(p) for p in csv_paths]
        logger.info("Uploading %d files to MinIO", len(paths))

        keys = upload_files_to_minio(paths, year_month)
        return keys

    @task()
    def validate_and_load(csv_paths: list[str]) -> dict:
        """Validate data quality and load valid rows into ClickHouse."""
        from src.loaders.clickhouse_loader import load_csv_file

        total_loaded = 0
        total_files = len(csv_paths)
        reports = []

        for i, csv_path in enumerate(csv_paths, 1):
            filepath = Path(csv_path)
            logger.info("[%d/%d] Processing %s", i, total_files, filepath.name)

            rows = load_csv_file(filepath)
            total_loaded += rows
            reports.append({"file": filepath.name, "rows_loaded": rows})

        summary = {
            "total_files": total_files,
            "total_rows_loaded": total_loaded,
            "files": reports,
        }

        logger.info("✅ Pipeline complete: loaded %d rows from %d files", total_loaded, total_files)
        return summary

    # Define task dependencies
    archive = download_archive()
    csvs = extract_csv_files(archive)
    minio_keys = upload_to_minio(csvs)
    load_result = validate_and_load(csvs)

    # Chain: upload to MinIO happens in parallel with validate_and_load
    # But trigger dbt only after loading is complete
    trigger_dbt = TriggerDagRunOperator(
        task_id="trigger_dbt",
        trigger_dag_id="taxi_dbt_transform",
        wait_for_completion=False,
    )

    load_result >> trigger_dbt


# Instantiate the DAG
taxi_ingestion_dag()
