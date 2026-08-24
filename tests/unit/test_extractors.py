"""
Unit tests for the archive extractor module.

Tests cover:
- Filename normalization logic
- Handling of various iTIC naming conventions
"""

from __future__ import annotations

import pytest

from src.ingestion.extractor import _normalize_filename


class TestFilenameNormalization:
    """Test the filename normalization function."""

    def test_standard_itic_format(self):
        """Standard iTIC format: PROBE-20180201.csv → probe_2018-02-01.csv"""
        result = _normalize_filename("PROBE-20180201.csv", "201802")
        assert result == "probe_2018-02-01.csv"

    def test_date_only_format(self):
        """Date-only format: 20180201.csv → probe_2018-02-01.csv"""
        result = _normalize_filename("20180201.csv", "201802")
        assert result == "probe_2018-02-01.csv"

    def test_already_normalized(self):
        """Already normalized: probe_2018-02-01.csv → probe_2018-02-01.csv"""
        result = _normalize_filename("probe_2018-02-01.csv", "201802")
        assert result == "probe_2018-02-01.csv"

    def test_lowercase_probe(self):
        """Lowercase probe prefix: probe_20180201.csv → probe_2018-02-01.csv"""
        result = _normalize_filename("probe_20180201.csv", "201802")
        assert result == "probe_2018-02-01.csv"

    def test_different_month(self):
        """Different month: PROBE-20181231.csv → probe_2018-12-31.csv"""
        result = _normalize_filename("PROBE-20181231.csv", "201812")
        assert result == "probe_2018-12-31.csv"

    def test_no_digits_fallback(self):
        """Files without 8 digits fall back to original name."""
        result = _normalize_filename("readme.csv", "201802")
        assert result == "readme.csv"
