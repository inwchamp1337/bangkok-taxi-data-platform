{{
  config(
    materialized='table',
    engine='MergeTree()',
    order_by='(date_key)',
  )
}}

/*
  dim_time — Date dimension covering all dates in the dataset.

  Enables time-based joins and filtering without recalculating
  date attributes in every query.
*/

WITH date_range AS (
    SELECT
        min(ping_date) AS min_date,
        max(ping_date) AS max_date
    FROM {{ ref('stg_gps_pings') }}
),

date_series AS (
    SELECT
        arrayJoin(
            arrayMap(
                x -> toDate(min_date) + x,
                range(toUInt32(dateDiff('day', min_date, max_date) + 1))
            )
        ) AS date_key
    FROM date_range
)

SELECT
    date_key,
    toYear(date_key) AS year,
    toMonth(date_key) AS month,
    toDayOfMonth(date_key) AS day_of_month,
    toDayOfWeek(date_key) AS day_of_week,  -- 1=Monday, 7=Sunday
    toDayOfYear(date_key) AS day_of_year,
    toISOWeek(date_key) AS iso_week,

    -- Human-readable
    formatDateTime(date_key, '%W') AS day_name,
    formatDateTime(date_key, '%M') AS month_name,

    -- Flags
    toDayOfWeek(date_key) IN (6, 7) AS is_weekend,
    toMonth(date_key) IN (4) AND toDayOfMonth(date_key) IN (13, 14, 15) AS is_songkran,

    -- Quarter
    toQuarter(date_key) AS quarter,
    concat('Q', toString(toQuarter(date_key)), ' ', toString(toYear(date_key))) AS quarter_label

FROM date_series
