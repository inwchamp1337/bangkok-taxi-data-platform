"""
Data validation engine for iTIC GPS probe data.

Validates CSV files against the GpsPingSchema and produces:
- Validated output (clean rows)
- Quarantined output (invalid rows)
- Validation report (metrics + failure breakdown)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import polars as pl

from src.validation.schemas import COLUMN_NAMES, THAILAND_LAT_MAX, THAILAND_LAT_MIN, THAILAND_LON_MAX, THAILAND_LON_MIN

logger = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    """Summary of a validation run."""

    source_file: str
    validated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    failure_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def valid_pct(self) -> float:
        """Percentage of valid rows."""
        if self.total_rows == 0:
            return 0.0
        return self.valid_rows / self.total_rows * 100

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "source_file": self.source_file,
            "validated_at": self.validated_at,
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "invalid_rows": self.invalid_rows,
            "valid_pct": round(self.valid_pct, 2),
            "failure_reasons": self.failure_reasons,
        }


def read_probe_csv(filepath: Path) -> pl.DataFrame:
    """
    Read an iTIC probe CSV file (no header) into a Polars DataFrame.

    The CSV has 7 or 8 columns depending on the year/format.
    We handle both cases gracefully.
    """
    try:
        df = pl.read_csv(
            filepath,
            has_header=False,
            new_columns=COLUMN_NAMES[:8],  # Try 8 columns first
            infer_schema_length=10000,
            ignore_errors=True,
            truncate_ragged_lines=True,
        )
    except Exception:
        # Fallback: try with 7 columns
        df = pl.read_csv(
            filepath,
            has_header=False,
            new_columns=COLUMN_NAMES[:7],
            infer_schema_length=10000,
            ignore_errors=True,
            truncate_ragged_lines=True,
        )
        # Add missing column with default
        if "engine_acc" not in df.columns:
            df = df.with_columns(pl.lit(1).alias("engine_acc"))

    # Ensure we have exactly the expected columns
    for col in COLUMN_NAMES:
        if col not in df.columns:
            if col in ("gps_valid", "passenger_lamp", "engine_acc"):
                df = df.with_columns(pl.lit(0).alias(col))
            elif col in ("speed",):
                df = df.with_columns(pl.lit(0).alias(col))

    return df.select(COLUMN_NAMES)


def validate_dataframe(df: pl.DataFrame, source_file: str) -> tuple[pl.DataFrame, pl.DataFrame, ValidationReport]:
    """
    Validate a Polars DataFrame against data quality rules.

    Instead of using Pandera directly (which has limited Polars support for
    row-level filtering), we apply validation rules as Polars expressions
    for maximum performance on large datasets.

    Args:
        df: Input DataFrame with raw GPS pings.
        source_file: Name of the source file for the report.

    Returns:
        Tuple of (valid_df, invalid_df, report).
    """
    report = ValidationReport(source_file=source_file, total_rows=len(df))

    # Cast types safely
    df = df.with_columns([
        pl.col("vehicle_id").cast(pl.Utf8),
        pl.col("gps_valid").cast(pl.Int32, strict=False).fill_null(0),
        pl.col("lat").cast(pl.Float64, strict=False),
        pl.col("lon").cast(pl.Float64, strict=False),
        pl.col("timestamp").cast(pl.Utf8),
        pl.col("speed").cast(pl.Int32, strict=False).fill_null(0),
        pl.col("passenger_lamp").cast(pl.Int32, strict=False).fill_null(0),
        pl.col("engine_acc").cast(pl.Int32, strict=False).fill_null(0),
    ])

    # Define validation rules
    rules = {
        "null_vehicle_id": pl.col("vehicle_id").is_null() | (pl.col("vehicle_id").str.len_chars() == 0),
        "invalid_gps_valid": ~pl.col("gps_valid").is_in([0, 1]),
        "lat_out_of_range": (pl.col("lat") < THAILAND_LAT_MIN) | (pl.col("lat") > THAILAND_LAT_MAX) | pl.col("lat").is_null(),
        "lon_out_of_range": (pl.col("lon") < THAILAND_LON_MIN) | (pl.col("lon") > THAILAND_LON_MAX) | pl.col("lon").is_null(),
        "null_timestamp": pl.col("timestamp").is_null() | (pl.col("timestamp").str.len_chars() == 0),
        "speed_out_of_range": (pl.col("speed") < 0) | (pl.col("speed") > 300),
        "invalid_passenger_lamp": ~pl.col("passenger_lamp").is_in([0, 1]),
        "invalid_engine_acc": ~pl.col("engine_acc").is_in([0, 1]),
    }

    # Compute combined invalid mask
    any_invalid = pl.lit(False)
    for rule_name, rule_expr in rules.items():
        violation_count = df.select(rule_expr.sum()).item()
        if violation_count > 0:
            report.failure_reasons[rule_name] = int(violation_count)
            logger.info("  Rule '%s': %d violations", rule_name, violation_count)
        any_invalid = any_invalid | rule_expr

    # Split valid and invalid
    valid_df = df.filter(~any_invalid)
    invalid_df = df.filter(any_invalid)

    report.valid_rows = len(valid_df)
    report.invalid_rows = len(invalid_df)

    logger.info(
        "Validation: %d total → %d valid (%.1f%%) + %d invalid",
        report.total_rows,
        report.valid_rows,
        report.valid_pct,
        report.invalid_rows,
    )

    return valid_df, invalid_df, report


def validate_file(filepath: Path) -> tuple[pl.DataFrame, pl.DataFrame, ValidationReport]:
    """
    Read and validate a single CSV file.

    Args:
        filepath: Path to the CSV file.

    Returns:
        Tuple of (valid_df, invalid_df, report).
    """
    logger.info("Validating %s", filepath.name)
    df = read_probe_csv(filepath)
    return validate_dataframe(df, source_file=filepath.name)


if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    parser = argparse.ArgumentParser(description="Validate iTIC probe data")
    parser.add_argument("--file", required=True, help="Path to CSV file")
    args = parser.parse_args()

    valid, invalid, report = validate_file(Path(args.file))
    print(json.dumps(report.to_dict(), indent=2))
    print(f"\nValid rows: {len(valid)}, Invalid rows: {len(invalid)}")
