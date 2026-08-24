{{
  config(
    materialized='incremental',
    engine='MergeTree()',
    order_by='(pickup_at, vehicle_id)',
    partition_by='toYYYYMM(pickup_at)',
    incremental_strategy='append',
  )
}}

/*
  fact_trips — Completed taxi trips with full metrics.

  Aggregates trip segments from int_trip_segments into complete trips.
  Each row = one complete trip (pickup → dropoff).
*/

SELECT
    trip_id,
    vehicle_id,

    -- Pickup details
    min(ping_at) AS pickup_at,
    argMin(lat, ping_at) AS pickup_lat,
    argMin(lon, ping_at) AS pickup_lon,
    argMin(geohash, ping_at) AS pickup_geohash,

    -- Dropoff details
    max(ping_at) AS dropoff_at,
    argMax(lat, ping_at) AS dropoff_lat,
    argMax(lon, ping_at) AS dropoff_lon,
    argMax(geohash, ping_at) AS dropoff_geohash,

    -- Trip metrics
    dateDiff('minute', min(ping_at), max(ping_at)) AS duration_minutes,
    round(sum(segment_distance_m) / 1000, 2) AS distance_km,
    round(avg(speed_kmh), 1) AS avg_speed_kmh,
    max(speed_kmh) AS max_speed_kmh,
    count() AS ping_count,

    -- Direct distance (straight line pickup → dropoff)
    round(
        {{ haversine_distance(
            'argMin(lon, ping_at)',
            'argMin(lat, ping_at)',
            'argMax(lon, ping_at)',
            'argMax(lat, ping_at)'
        ) }} / 1000,
        2
    ) AS direct_distance_km,

    -- Date for partitioning
    toDate(min(ping_at)) AS trip_date

FROM {{ ref('int_trip_segments') }}

{% if is_incremental() %}
WHERE ping_at > (
    SELECT max(pickup_at) - INTERVAL 1 HOUR
    FROM {{ this }}
)
{% endif %}

GROUP BY trip_id, vehicle_id

-- Filter out implausible trips
HAVING
    duration_minutes BETWEEN 1 AND 180          -- 1 min to 3 hours
    AND distance_km BETWEEN 0.1 AND 100         -- 100m to 100km
    AND ping_count >= 3                          -- At least 3 GPS pings
    AND avg_speed_kmh < 120                      -- Reasonable average speed
