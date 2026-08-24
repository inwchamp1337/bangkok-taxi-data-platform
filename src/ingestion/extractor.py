"""
Extract iTIC probe data tar.bz2 archives into daily CSV files.

Each archive contains one CSV file per day. This module:
- Streams decompression to avoid loading the entire archive into memory
- Names output files consistently: probe_YYYY-MM-DD.csv
- Idempotent — skips already extracted files
"""

from __future__ import annotations

import logging
import tarfile
from pathlib import Path

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


def extract_archive(year_month: str) -> list[Path]:
    """
    Extract a tar.bz2 archive into individual daily CSV files.

    Args:
        year_month: Target month in YYYYMM format (e.g., "201802").

    Returns:
        List of paths to extracted CSV files, sorted by date.

    Raises:
        FileNotFoundError: If the archive doesn't exist.
    """
    settings = get_settings()
    archive_path = settings.download_dir / f"PROBE-{year_month}.tar.bz2"

    if not archive_path.exists():
        msg = f"Archive not found: {archive_path}"
        raise FileNotFoundError(msg)

    # Create month-specific extraction directory
    year = year_month[:4]
    month = year_month[4:6]
    output_dir = settings.extract_dir / f"year={year}" / f"month={month}"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Extracting %s → %s", archive_path.name, output_dir)

    extracted_files: list[Path] = []

    with tarfile.open(archive_path, "r:bz2") as tar:
        members = [m for m in tar.getmembers() if m.isfile() and m.name.endswith(".csv")]
        logger.info("Found %d CSV files in archive", len(members))

        for i, member in enumerate(sorted(members, key=lambda m: m.name), 1):
            # Normalize filename: extract date from various naming conventions
            original_name = Path(member.name).name
            output_path = output_dir / _normalize_filename(original_name, year_month)

            if output_path.exists() and output_path.stat().st_size > 0:
                logger.debug("Already extracted: %s", output_path.name)
                extracted_files.append(output_path)
                continue

            # Extract file
            fileobj = tar.extractfile(member)
            if fileobj is None:
                logger.warning("Could not extract %s, skipping", member.name)
                continue

            with open(output_path, "wb") as out:
                while True:
                    chunk = fileobj.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    out.write(chunk)

            size_mb = output_path.stat().st_size / (1024 * 1024)
            logger.info(
                "[%d/%d] Extracted %s (%.1f MB)",
                i,
                len(members),
                output_path.name,
                size_mb,
            )
            extracted_files.append(output_path)

    extracted_files.sort()
    logger.info("✅ Extracted %d files to %s", len(extracted_files), output_dir)
    return extracted_files


def _normalize_filename(original: str, year_month: str) -> str:
    """
    Normalize the CSV filename to a consistent format.

    Various naming patterns from iTIC archives:
    - PROBE-20180201.csv
    - 20180201.csv
    - probe_2018-02-01.csv

    All get normalized to: probe_2018-02-01.csv
    """
    # Strip known prefixes and extensions
    name = original.replace("PROBE-", "").replace("probe_", "").replace(".csv", "")

    # Remove dashes to normalize
    name = name.replace("-", "")

    # Extract date part (should be 8 digits: YYYYMMDD)
    digits = "".join(c for c in name if c.isdigit())

    if len(digits) >= 8:
        date_str = digits[:8]
        return f"probe_{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}.csv"

    # Fallback: use original name
    logger.warning("Could not normalize filename: %s", original)
    return original


def list_extracted_files(year_month: str) -> list[Path]:
    """List all extracted CSV files for a given month."""
    settings = get_settings()
    year = year_month[:4]
    month = year_month[4:6]
    output_dir = settings.extract_dir / f"year={year}" / f"month={month}"

    if not output_dir.exists():
        return []

    return sorted(output_dir.glob("probe_*.csv"))


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    parser = argparse.ArgumentParser(description="Extract iTIC probe data archive")
    parser.add_argument("--month", required=True, help="Year-month in YYYYMM format (e.g., 201802)")
    args = parser.parse_args()

    files = extract_archive(args.month)
    print(f"Extracted {len(files)} files")
