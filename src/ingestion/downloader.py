"""
Download iTIC probe data archives from the public open data repository.

Downloads PROBE-YYYYMM.tar.bz2 files with:
- Resumable downloads (HTTP Range headers)
- MD5 checksum verification
- Idempotent — skips already downloaded + verified files
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import httpx

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


def _build_archive_url(year_month: str) -> str:
    """Build the download URL for a given YYYYMM string."""
    settings = get_settings()
    return f"{settings.itic.base_url}/PROBE-{year_month}.tar.bz2"


def _build_checksum_url(year: str) -> str:
    """Build the URL for the MD5 checksum file for a given year."""
    settings = get_settings()
    return f"{settings.itic.base_url}/md5sums-{year}.txt"


def fetch_expected_md5(year_month: str) -> str | None:
    """
    Fetch the expected MD5 checksum for a given month's archive.

    Returns None if checksum file is unavailable.
    """
    year = year_month[:4]
    url = _build_checksum_url(year)

    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()

        filename = f"PROBE-{year_month}.tar.bz2"
        for line in response.text.strip().splitlines():
            parts = line.strip().split()
            if len(parts) == 2 and filename in parts[1]:
                return parts[0]

        logger.warning("Checksum for %s not found in %s", filename, url)
        return None

    except httpx.HTTPError as exc:
        logger.warning("Could not fetch checksum file: %s", exc)
        return None


def compute_file_md5(filepath: Path) -> str:
    """Compute MD5 hash of a file using chunked reading."""
    md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            md5.update(chunk)
    return md5.hexdigest()


def download_archive(year_month: str) -> Path:
    """
    Download a monthly probe data archive from iTIC.

    Args:
        year_month: Target month in YYYYMM format (e.g., "201802").

    Returns:
        Path to the downloaded archive file.

    Raises:
        httpx.HTTPError: If the download fails.
        ValueError: If MD5 checksum doesn't match.
    """
    settings = get_settings()
    settings.ensure_dirs()

    url = _build_archive_url(year_month)
    dest = settings.download_dir / f"PROBE-{year_month}.tar.bz2"

    # Check if already downloaded and verified
    if dest.exists():
        expected_md5 = fetch_expected_md5(year_month)
        if expected_md5:
            actual_md5 = compute_file_md5(dest)
            if actual_md5 == expected_md5:
                logger.info("Archive %s already exists and checksum matches, skipping", dest.name)
                return dest
            logger.warning("Existing file checksum mismatch, re-downloading")
        else:
            logger.info("Archive %s already exists (no checksum to verify), skipping", dest.name)
            return dest

    logger.info("Downloading %s → %s", url, dest)

    # Support resume via Range header
    headers = {}
    mode = "wb"
    downloaded = 0

    if dest.exists():
        downloaded = dest.stat().st_size
        headers["Range"] = f"bytes={downloaded}-"
        mode = "ab"
        logger.info("Resuming download from byte %d", downloaded)

    with httpx.Client(timeout=httpx.Timeout(30.0, read=300.0), follow_redirects=True) as client:
        with client.stream("GET", url, headers=headers) as response:
            # If server doesn't support Range, start fresh
            if response.status_code == 200 and downloaded > 0:
                mode = "wb"
                downloaded = 0

            response.raise_for_status()

            total = int(response.headers.get("content-length", 0)) + downloaded

            with open(dest, mode) as f:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):  # 1MB chunks
                    f.write(chunk)
                    downloaded += len(chunk)

                    # Progress logging every 100MB
                    if downloaded % (100 * 1024 * 1024) < (1024 * 1024):
                        pct = (downloaded / total * 100) if total > 0 else 0
                        logger.info("Progress: %.1f%% (%d MB / %d MB)", pct, downloaded // (1024 * 1024), total // (1024 * 1024))

    # Verify checksum
    expected_md5 = fetch_expected_md5(year_month)
    if expected_md5:
        actual_md5 = compute_file_md5(dest)
        if actual_md5 != expected_md5:
            msg = f"MD5 mismatch for {dest.name}: expected={expected_md5}, actual={actual_md5}"
            raise ValueError(msg)
        logger.info("✅ Checksum verified for %s", dest.name)
    else:
        logger.warning("⚠️ No checksum available for %s, skipping verification", dest.name)

    logger.info("✅ Downloaded %s (%.1f MB)", dest.name, dest.stat().st_size / (1024 * 1024))
    return dest


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    parser = argparse.ArgumentParser(description="Download iTIC probe data")
    parser.add_argument("--month", required=True, help="Year-month in YYYYMM format (e.g., 201802)")
    args = parser.parse_args()

    download_archive(args.month)
