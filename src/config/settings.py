"""
Centralized configuration using Pydantic Settings.

All configuration is loaded from environment variables (or .env file).
Each module imports `settings` from here instead of reading os.environ directly.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class MinIOSettings(BaseSettings):
    """MinIO / S3-compatible storage configuration."""

    model_config = SettingsConfigDict(env_prefix="MINIO_")

    endpoint: str = "localhost:9000"
    root_user: str = "minio_admin"
    root_password: str = "minio_secret_123"
    raw_bucket: str = "raw"
    quarantine_bucket: str = "quarantine"
    secure: bool = False


class ClickHouseSettings(BaseSettings):
    """ClickHouse OLAP warehouse configuration."""

    model_config = SettingsConfigDict(env_prefix="CLICKHOUSE_")

    host: str = "localhost"
    port: int = 8123
    native_port: int = 9000
    user: str = "default"
    password: str = "clickhouse_secret"
    db: str = "taxi"


class ITICSettings(BaseSettings):
    """iTIC data source configuration."""

    model_config = SettingsConfigDict(env_prefix="ITIC_")

    base_url: str = "https://itic.longdo.com/opendata/probe-data"


class AppSettings(BaseSettings):
    """Top-level application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Sub-configs
    minio: MinIOSettings = MinIOSettings()
    clickhouse: ClickHouseSettings = ClickHouseSettings()
    itic: ITICSettings = ITICSettings()

    # Paths
    data_dir: Path = Path("data")
    download_dir: Path = Path("data/downloads")
    extract_dir: Path = Path("data/extracted")
    sample_dir: Path = Path("data/sample")

    # Processing
    batch_size: int = 100_000  # rows per ClickHouse insert batch
    validation_sample_rate: float = 1.0  # 1.0 = validate all rows

    def ensure_dirs(self) -> None:
        """Create data directories if they don't exist."""
        for d in [self.data_dir, self.download_dir, self.extract_dir, self.sample_dir]:
            d.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Get cached application settings singleton."""
    settings = AppSettings()
    settings.ensure_dirs()
    return settings
