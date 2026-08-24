{{
  config(
    materialized='incremental',
    engine='MergeTree()',
    order_by='(vehicle_id, ping_at)',
    partition_by='toYYYYMM(ping_at)',
    incremental_strategy='append',
    unique_key='(vehicle_id, ping_at)',
  )
}}

/*
  stg_gps_pings — Cleaned GPS pings within Bangkok metropolitan area.

  Filters:
    - Only valid GPS fixes (gps_valid = 1)
    - Coordinates within Bangkok metro bounding box
    - Speed within reasonable range (0-200 km/h)

  Adds:
    - Renamed columns for clarity
    - Time dimension columns (hour, day_of_week, date)
    - Boolean vacancy flag
    - Geohash for spatial aggregation
*/

SELECT
    vehicle_id,
    lat,
    lon,
    timestamp                          AS ping_at,
    speed                              AS speed_kmh,

    -- Status flags (cast to boolean-like UInt8)
    passenger_lamp = 1                 AS is_vacant,
    engine_acc = 1                     AS is_engine_on,

    -- Time dimensions
    toHour(timestamp)                  AS hour_of_day,
    toDayOfWeek(timestamp)             AS day_of_week,
    toDate(timestamp)                  AS ping_date,

    -- Spatial
    {{ geohash_encode('lon', 'lat', var('geohash_precision')) }} AS geohash,

    -- Lineage
    _source_file

FROM {{ source('raw', 'raw_gps_pings') }}

WHERE
    gps_valid = 1
    AND lat BETWEEN {{ var('bkk_lat_min') }} AND {{ var('bkk_lat_max') }}
    AND lon BETWEEN {{ var('bkk_lon_min') }} AND {{ var('bkk_lon_max') }}
    AND speed BETWEEN 0 AND 200

{% if is_incremental() %}
    AND timestamp > (
        SELECT max(ping_at) - INTERVAL 1 HOUR
        FROM {{ this }}
    )
{% endif %}
