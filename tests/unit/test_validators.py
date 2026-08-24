"""
Unit tests for the data validation module.

Tests cover:
- Schema validation rules (coordinates, speed, binary flags)
- Edge cases (null values, out-of-range, boundary values)
- Validation report accuracy
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from src.validation.validators import ValidationReport, validate_dataframe


class TestValidationRules:
    """Test individual validation rules."""

    def _make_df(self, overrides: dict | None = None) -> pl.DataFrame:
        """Create a valid DataFrame with optional field overrides."""
        base = {
            "vehicle_id": ["abc123"],
            "gps_valid": [1],
            "lat": [13.75],
            "lon": [100.50],
            "timestamp": ["2018-02-01 08:00:00"],
            "speed": [30],
            "passenger_lamp": [1],
            "engine_acc": [1],
        }
        if overrides:
            base.update(overrides)
        return pl.DataFrame(base)

    def test_valid_row_passes(self):
        """A fully valid row should pass all validation rules."""
        df = self._make_df()
        valid, invalid, report = validate_dataframe(df, "test.csv")

        assert len(valid) == 1
        assert len(invalid) == 0
        assert report.valid_rows == 1
        assert report.invalid_rows == 0

    def test_lat_out_of_thailand_rejected(self):
        """Latitude outside Thailand (5-21) should be rejected."""
        df = self._make_df({"lat": [55.0]})  # Somewhere in Europe
        valid, invalid, report = validate_dataframe(df, "test.csv")

        assert len(valid) == 0
        assert len(invalid) == 1
        assert "lat_out_of_range" in report.failure_reasons

    def test_lon_out_of_thailand_rejected(self):
        """Longitude outside Thailand (97-106) should be rejected."""
        df = self._make_df({"lon": [140.0]})  # Japan
        valid, invalid, report = validate_dataframe(df, "test.csv")

        assert len(valid) == 0
        assert len(invalid) == 1
        assert "lon_out_of_range" in report.failure_reasons

    def test_negative_speed_rejected(self):
        """Negative speed should be rejected."""
        df = self._make_df({"speed": [-10]})
        valid, invalid, report = validate_dataframe(df, "test.csv")

        assert len(valid) == 0
        assert len(invalid) == 1
        assert "speed_out_of_range" in report.failure_reasons

    def test_excessive_speed_rejected(self):
        """Speed > 300 km/h should be rejected."""
        df = self._make_df({"speed": [350]})
        valid, invalid, report = validate_dataframe(df, "test.csv")

        assert len(valid) == 0
        assert len(invalid) == 1
        assert "speed_out_of_range" in report.failure_reasons

    def test_invalid_gps_valid_rejected(self):
        """gps_valid must be 0 or 1."""
        df = self._make_df({"gps_valid": [5]})
        valid, invalid, report = validate_dataframe(df, "test.csv")

        assert len(valid) == 0
        assert len(invalid) == 1
        assert "invalid_gps_valid" in report.failure_reasons

    def test_invalid_passenger_lamp_rejected(self):
        """passenger_lamp must be 0 or 1."""
        df = self._make_df({"passenger_lamp": [3]})
        valid, invalid, report = validate_dataframe(df, "test.csv")

        assert len(valid) == 0
        assert len(invalid) == 1
        assert "invalid_passenger_lamp" in report.failure_reasons

    def test_invalid_engine_acc_rejected(self):
        """engine_acc must be 0 or 1."""
        df = self._make_df({"engine_acc": [9]})
        valid, invalid, report = validate_dataframe(df, "test.csv")

        assert len(valid) == 0
        assert len(invalid) == 1
        assert "invalid_engine_acc" in report.failure_reasons

    def test_boundary_lat_valid(self):
        """Boundary latitude values (5.0 and 21.0) should be accepted."""
        df = self._make_df({"lat": [5.0]})
        valid, _, _ = validate_dataframe(df, "test.csv")
        assert len(valid) == 1

        df = self._make_df({"lat": [21.0]})
        valid, _, _ = validate_dataframe(df, "test.csv")
        assert len(valid) == 1

    def test_zero_speed_valid(self):
        """Speed of 0 (stopped) should be valid."""
        df = self._make_df({"speed": [0]})
        valid, _, _ = validate_dataframe(df, "test.csv")
        assert len(valid) == 1

    def test_gps_invalid_zero_accepted(self):
        """gps_valid = 0 should be accepted (it's a valid value, just not a valid fix)."""
        df = self._make_df({"gps_valid": [0]})
        valid, _, _ = validate_dataframe(df, "test.csv")
        assert len(valid) == 1


class TestValidationReport:
    """Test the ValidationReport dataclass."""

    def test_report_percentages(self):
        """Report should calculate correct percentages."""
        report = ValidationReport(source_file="test.csv", total_rows=100, valid_rows=95, invalid_rows=5)
        assert report.valid_pct == 95.0

    def test_report_zero_rows(self):
        """Report with zero rows should not divide by zero."""
        report = ValidationReport(source_file="test.csv")
        assert report.valid_pct == 0.0

    def test_report_to_dict(self):
        """Report should serialize to dict correctly."""
        report = ValidationReport(
            source_file="test.csv",
            total_rows=100,
            valid_rows=95,
            invalid_rows=5,
            failure_reasons={"lat_out_of_range": 3, "speed_out_of_range": 2},
        )
        d = report.to_dict()
        assert d["source_file"] == "test.csv"
        assert d["valid_pct"] == 95.0
        assert len(d["failure_reasons"]) == 2


class TestMixedData:
    """Test validation with mixed valid and invalid data."""

    def test_mixed_batch(self):
        """DataFrame with both valid and invalid rows should split correctly."""
        df = pl.DataFrame({
            "vehicle_id": ["taxi1", "taxi2", "taxi3", "taxi4"],
            "gps_valid": [1, 1, 1, 1],
            "lat": [13.75, 55.0, 13.80, 13.90],         # Row 2 invalid lat
            "lon": [100.50, 100.50, 140.0, 100.60],      # Row 3 invalid lon
            "timestamp": [
                "2018-02-01 08:00:00",
                "2018-02-01 09:00:00",
                "2018-02-01 10:00:00",
                "2018-02-01 11:00:00",
            ],
            "speed": [30, 40, 50, 350],                   # Row 4 invalid speed
            "passenger_lamp": [1, 0, 1, 0],
            "engine_acc": [1, 1, 1, 1],
        })

        valid, invalid, report = validate_dataframe(df, "test.csv")

        assert len(valid) == 1   # Only taxi1 is fully valid
        assert len(invalid) == 3
        assert report.total_rows == 4
        assert report.valid_rows == 1
        assert report.invalid_rows == 3
