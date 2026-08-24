"""
Integration test for the full data pipeline.

Tests the end-to-end flow using sample data:
  1. Generate sample CSV
  2. Validate the data
  3. Check validation report accuracy

Note: This test does NOT require Docker services.
It tests the Python pipeline logic only.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from scripts.generate_sample_data import generate_sample_data
from src.validation.validators import validate_file


@pytest.fixture
def sample_data_dir(tmp_path) -> Path:
    """Generate sample data in a temporary directory."""
    output_dir = tmp_path / "sample"
    generate_sample_data(
        output_dir=output_dir,
        num_taxis=5,
        num_days=1,
        start_date=datetime(2018, 2, 1),
    )
    return output_dir


class TestSampleDataGeneration:
    """Test the sample data generator."""

    def test_generates_files(self, sample_data_dir):
        """Generator should create CSV files."""
        csv_files = list(sample_data_dir.glob("*.csv"))
        assert len(csv_files) == 1

    def test_file_not_empty(self, sample_data_dir):
        """Generated files should have content."""
        csv_files = list(sample_data_dir.glob("*.csv"))
        for f in csv_files:
            assert f.stat().st_size > 0


class TestSampleDataValidation:
    """Test that generated sample data passes validation."""

    def test_sample_data_mostly_valid(self, sample_data_dir):
        """Sample data should have > 90% valid rows."""
        csv_files = list(sample_data_dir.glob("*.csv"))
        assert len(csv_files) > 0

        valid, invalid, report = validate_file(csv_files[0])
        assert report.valid_pct > 90.0, f"Valid percentage too low: {report.valid_pct}%"

    def test_sample_data_has_expected_columns(self, sample_data_dir):
        """Validated data should have all expected columns."""
        import polars as pl

        from src.validation.schemas import COLUMN_NAMES
        from src.validation.validators import read_probe_csv

        csv_files = list(sample_data_dir.glob("*.csv"))
        df = read_probe_csv(csv_files[0])

        for col in COLUMN_NAMES:
            assert col in df.columns, f"Missing column: {col}"

    def test_report_to_dict_serializable(self, sample_data_dir):
        """Validation report should serialize to dict without errors."""
        import json

        csv_files = list(sample_data_dir.glob("*.csv"))
        _, _, report = validate_file(csv_files[0])

        serialized = json.dumps(report.to_dict())
        assert len(serialized) > 0
