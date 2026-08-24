-- =============================================================================
-- Bangkok Taxi Data Platform — ClickHouse Schema
-- =============================================================================
-- Run once to initialize the database and tables.
-- Idempotent: uses IF NOT EXISTS everywhere.
-- =============================================================================

-- Create database
CREATE DATABASE IF NOT EXISTS taxi;

-- =============================================================================
-- RAW LAYER — Landing zone for ingested data
-- =============================================================================

CREATE TABLE IF NOT EXISTS taxi.raw_gps_pings
(
    vehicle_id      String         COMMENT 'Hashed unique vehicle identifier',
    gps_valid       UInt8          COMMENT '1 = valid GPS fix, 0 = insufficient satellites',
    lat             Float64        COMMENT 'Latitude (WGS84, decimal degrees)',
    lon             Float64        COMMENT 'Longitude (WGS84, decimal degrees)',
    timestamp       DateTime('Asia/Bangkok') COMMENT 'GPS timestamp in Bangkok time (UTC+7)',
    speed           UInt16         COMMENT 'Speed in km/h',
    passenger_lamp  UInt8          COMMENT 'Vacancy light: 1 = vacant (light ON), 0 = occupied',
    engine_acc      UInt8          COMMENT 'Engine switch: 1 = running, 0 = off',

    -- Metadata columns for lineage
    _loaded_at      DateTime       DEFAULT now()  COMMENT 'When this row was loaded',
    _source_file    String         DEFAULT ''     COMMENT 'Source CSV filename'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (vehicle_id, timestamp)
SETTINGS index_granularity = 8192;


-- =============================================================================
-- STAGING VIEWS — Used by dbt, but pre-create for manual queries
-- =============================================================================

-- Convenience view: only valid GPS pings within Bangkok metro area
CREATE OR REPLACE VIEW taxi.v_bangkok_pings AS
SELECT
    vehicle_id,
    lat,
    lon,
    timestamp,
    speed,
    passenger_lamp,
    engine_acc,
    toHour(timestamp) AS hour_of_day,
    toDayOfWeek(timestamp) AS day_of_week,
    passenger_lamp = 1 AS is_vacant
FROM taxi.raw_gps_pings
WHERE gps_valid = 1
  AND lat BETWEEN 13.4 AND 14.3
  AND lon BETWEEN 100.2 AND 101.0;


-- =============================================================================
-- ANALYTICS HELPERS — Quick ad-hoc query support
-- =============================================================================

-- Hourly taxi counts (materialized view for fast dashboard queries)
CREATE MATERIALIZED VIEW IF NOT EXISTS taxi.mv_hourly_taxi_count
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(hour_start)
ORDER BY (hour_start)
AS
SELECT
    toStartOfHour(timestamp) AS hour_start,
    uniqExact(vehicle_id) AS active_taxis,
    countIf(passenger_lamp = 0) AS occupied_pings,
    countIf(passenger_lamp = 1) AS vacant_pings,
    count() AS total_pings,
    avg(speed) AS avg_speed
FROM taxi.raw_gps_pings
WHERE gps_valid = 1
GROUP BY hour_start;
