{{
  config(
    materialized='table',
    engine='ReplacingMergeTree()',
    order_by='(vehicle_id)',
  )
}}

/*
  dim_taxi — Taxi dimension with per-vehicle statistics.

  Provides a summary profile for each taxi in the dataset.
*/

SELECT
    vehicle_id,

    -- Activity period
    min(ping_at) AS first_seen_at,
    max(ping_at) AS last_seen_at,
    dateDiff('day', min(ping_at), max(ping_at)) AS active_days_span,

    -- Volume
    count() AS total_pings,
    uniqExact(ping_date) AS days_active,

    -- Trip behavior
    countIf(is_vacant = false) AS occupied_pings,
    countIf(is_vacant = true) AS vacant_pings,
    round(countIf(is_vacant = true) / count(), 4) AS vacancy_rate,

    -- Speed profile
    round(avg(speed_kmh), 1) AS avg_speed_kmh,
    max(speed_kmh) AS max_speed_kmh,

    -- Geography
    round(avg(lat), 5) AS avg_lat,
    round(avg(lon), 5) AS avg_lon

FROM {{ ref('stg_gps_pings') }}
GROUP BY vehicle_id
