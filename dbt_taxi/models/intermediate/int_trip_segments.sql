{{
  config(
    materialized='incremental',
    engine='MergeTree()',
    order_by='(vehicle_id, ping_at)',
    partition_by='toYYYYMM(ping_at)',
    incremental_strategy='append',
  )
}}

/*
  int_trip_segments — Detect trips via passenger_lamp transitions.

  Logic:
    1. For each vehicle, order pings by time
    2. Use lagInFrame to get the previous ping's vacancy status
    3. A trip START occurs when is_vacant transitions from true → false (pickup)
    4. A trip END occurs when is_vacant transitions from false → true (dropoff)
    5. Use cumulative sum of trip starts to assign trip_group_id
    6. Only keep pings where taxi is occupied (is_vacant = false)
*/

WITH pings_with_lag AS (
    SELECT
        vehicle_id,
        lat,
        lon,
        ping_at,
        speed_kmh,
        is_vacant,
        geohash,
        ping_date,

        -- Previous ping's state for this vehicle
        lagInFrame(is_vacant, 1, true)
            OVER (PARTITION BY vehicle_id ORDER BY ping_at
                  ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
            AS prev_is_vacant,

        -- Previous ping's coordinates
        lagInFrame(lat, 1, 0)
            OVER (PARTITION BY vehicle_id ORDER BY ping_at
                  ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
            AS prev_lat,
        lagInFrame(lon, 1, 0)
            OVER (PARTITION BY vehicle_id ORDER BY ping_at
                  ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
            AS prev_lon,

        -- Time gap from previous ping (seconds)
        dateDiff('second',
            lagInFrame(ping_at, 1, ping_at)
                OVER (PARTITION BY vehicle_id ORDER BY ping_at
                      ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING),
            ping_at
        ) AS gap_seconds

    FROM {{ ref('stg_gps_pings') }}

    {% if is_incremental() %}
    WHERE ping_at > (
        SELECT max(ping_at) - INTERVAL 1 HOUR
        FROM {{ this }}
    )
    {% endif %}
),

trip_boundaries AS (
    SELECT
        *,
        -- Trip starts when: was vacant, now occupied
        CASE WHEN prev_is_vacant = true AND is_vacant = false THEN 1 ELSE 0 END AS is_trip_start,
        -- Trip ends when: was occupied, now vacant
        CASE WHEN prev_is_vacant = false AND is_vacant = true THEN 1 ELSE 0 END AS is_trip_end
    FROM pings_with_lag
),

with_trip_group AS (
    SELECT
        *,
        -- Cumulative sum of trip starts to create trip group IDs
        sum(is_trip_start)
            OVER (PARTITION BY vehicle_id ORDER BY ping_at
                  ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
            AS trip_group_id
    FROM trip_boundaries
)

SELECT
    vehicle_id,
    concat(vehicle_id, '_', toString(trip_group_id)) AS trip_id,
    lat,
    lon,
    ping_at,
    speed_kmh,
    is_vacant,
    geohash,
    ping_date,
    prev_lat,
    prev_lon,
    gap_seconds,
    is_trip_start,
    is_trip_end,
    trip_group_id,

    -- Distance from previous ping (meters) using Haversine
    CASE
        WHEN prev_lat != 0 AND prev_lon != 0 AND gap_seconds < 600
        THEN {{ haversine_distance('prev_lon', 'prev_lat', 'lon', 'lat') }}
        ELSE 0
    END AS segment_distance_m

FROM with_trip_group
WHERE is_vacant = false  -- Only occupied pings (actual trips)
  AND trip_group_id > 0  -- Exclude pings before first trip start
