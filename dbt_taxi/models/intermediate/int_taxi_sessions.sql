{{
  config(
    materialized='incremental',
    engine='MergeTree()',
    order_by='(vehicle_id, session_start)',
    partition_by='toYYYYMM(session_start)',
    incremental_strategy='append',
  )
}}

/*
  int_taxi_sessions — Sessionize GPS pings by vehicle + time gaps.

  A new session starts when:
    - Gap between consecutive pings > 10 minutes
    - Engine state changes (engine turns on/off)

  Each session gets a unique ID for downstream analysis
  (e.g., calculating active hours, idle time).
*/

WITH pings_with_gap AS (
    SELECT
        vehicle_id,
        ping_at,
        speed_kmh,
        is_vacant,
        is_engine_on,
        lat,
        lon,
        geohash,

        -- Time gap from previous ping
        dateDiff('second',
            lagInFrame(ping_at, 1, ping_at)
                OVER (PARTITION BY vehicle_id ORDER BY ping_at
                      ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING),
            ping_at
        ) AS gap_seconds,

        -- Previous engine state
        lagInFrame(is_engine_on, 1, is_engine_on)
            OVER (PARTITION BY vehicle_id ORDER BY ping_at
                  ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
            AS prev_engine_on

    FROM {{ ref('stg_gps_pings') }}

    {% if is_incremental() %}
    WHERE ping_at > (
        SELECT max(session_start) - INTERVAL 1 HOUR
        FROM {{ this }}
    )
    {% endif %}
),

session_boundaries AS (
    SELECT
        *,
        CASE
            WHEN gap_seconds > {{ var('session_gap_minutes') }} * 60 THEN 1
            WHEN is_engine_on != prev_engine_on THEN 1
            ELSE 0
        END AS is_new_session
    FROM pings_with_gap
),

with_session_id AS (
    SELECT
        *,
        sum(is_new_session)
            OVER (PARTITION BY vehicle_id ORDER BY ping_at
                  ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
            AS session_num
    FROM session_boundaries
)

SELECT
    vehicle_id,
    concat(vehicle_id, '_s', toString(session_num)) AS session_id,
    min(ping_at) AS session_start,
    max(ping_at) AS session_end,
    dateDiff('minute', min(ping_at), max(ping_at)) AS session_duration_minutes,
    count() AS ping_count,
    avg(speed_kmh) AS avg_speed_kmh,
    max(speed_kmh) AS max_speed_kmh,
    countIf(is_vacant = true) AS vacant_pings,
    countIf(is_vacant = false) AS occupied_pings,
    any(is_engine_on) AS engine_on

FROM with_session_id
GROUP BY vehicle_id, session_id
HAVING ping_count >= 2  -- Filter out single-ping sessions
