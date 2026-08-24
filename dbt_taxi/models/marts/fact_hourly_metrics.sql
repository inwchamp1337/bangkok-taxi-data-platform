{{
  config(
    materialized='incremental',
    engine='SummingMergeTree()',
    order_by='(hour_start)',
    partition_by='toYYYYMM(hour_start)',
    incremental_strategy='append',
  )
}}

/*
  fact_hourly_metrics — Pre-aggregated hourly fleet metrics.

  Designed for fast Grafana dashboard queries.
  Uses SummingMergeTree for efficient merge of overlapping aggregations.
*/

SELECT
    toStartOfHour(ping_at) AS hour_start,
    toDate(ping_at) AS metric_date,
    toHour(ping_at) AS hour_of_day,
    toDayOfWeek(ping_at) AS day_of_week,

    -- Fleet metrics
    uniqExact(vehicle_id) AS total_active_taxis,
    uniqExactIf(vehicle_id, is_vacant = false) AS total_occupied_taxis,
    uniqExactIf(vehicle_id, is_vacant = true) AS total_vacant_taxis,

    -- Ping counts
    count() AS total_pings,
    countIf(is_vacant = false) AS occupied_pings,
    countIf(is_vacant = true) AS vacant_pings,

    -- Speed metrics
    round(avg(speed_kmh), 1) AS avg_speed_kmh,
    round(median(speed_kmh), 1) AS median_speed_kmh,
    max(speed_kmh) AS max_speed_kmh,

    -- Derived metrics
    round(
        countIf(is_vacant = true) / count(),
        4
    ) AS empty_taxi_ratio

FROM {{ ref('stg_gps_pings') }}

{% if is_incremental() %}
WHERE ping_at > (
    SELECT max(hour_start) - INTERVAL 1 HOUR
    FROM {{ this }}
)
{% endif %}

GROUP BY hour_start, metric_date, hour_of_day, day_of_week
