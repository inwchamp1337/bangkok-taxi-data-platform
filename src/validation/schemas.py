"""
Pandera schemas for validating iTIC GPS probe data.

The iTIC CSV format (no header) has 7 fields:
  VehicleID, gpsvalid, lat, lon, timestamp, speed, passenger_lamp, engine_acc

See: http://traffic.longdo.com/docs/probedata-format
"""

from __future__ import annotations

import pandera.polars as pa

# Column names to assign when reading the headerless CSV
COLUMN_NAMES = [
    "vehicle_id",
    "gps_valid",
    "lat",
    "lon",
    "timestamp",
    "speed",
    "passenger_lamp",
    "engine_acc",
]

# Thailand bounding box (generous)
THAILAND_LAT_MIN = 5.0
THAILAND_LAT_MAX = 21.0
THAILAND_LON_MIN = 97.0
THAILAND_LON_MAX = 106.0

# Bangkok metropolitan area bounding box (for filtering)
BKK_LAT_MIN = 13.4
BKK_LAT_MAX = 14.3
BKK_LON_MIN = 100.2
BKK_LON_MAX = 101.0


class GpsPingSchema(pa.DataFrameModel):
    """
    Validation schema for raw GPS ping records.

    Validates data quality rules:
    - GPS validity flag must be 0 or 1
    - Coordinates must fall within Thailand
    - Speed must be non-negative and reasonable (0-300 km/h)
    - Binary flags must be 0 or 1
    """

    vehicle_id: str = pa.Field(nullable=False, description="Unique hashed vehicle identifier")

    gps_valid: int = pa.Field(
        ge=0, le=1,
        nullable=False,
        description="GPS fix quality: 1 = valid GPS fix",
    )

    lat: float = pa.Field(
        ge=THAILAND_LAT_MIN,
        le=THAILAND_LAT_MAX,
        nullable=False,
        description="Latitude (decimal degrees, WGS84)",
    )

    lon: float = pa.Field(
        ge=THAILAND_LON_MIN,
        le=THAILAND_LON_MAX,
        nullable=False,
        description="Longitude (decimal degrees, WGS84)",
    )

    speed: int = pa.Field(
        ge=0, le=300,
        nullable=False,
        description="Speed in km/h",
    )

    passenger_lamp: int = pa.Field(
        ge=0, le=1,
        nullable=False,
        description="Taxi vacancy light: 1 = vacant (light ON), 0 = occupied",
    )

    engine_acc: int = pa.Field(
        ge=0, le=1,
        nullable=False,
        description="Engine accessory switch: 1 = engine ON, 0 = engine OFF",
    )

    class Config:
        """Schema configuration."""

        coerce = True
        strict = "filter"  # Filter out invalid rows instead of raising
