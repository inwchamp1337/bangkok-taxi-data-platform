/*
  Test: Assert all speed values are non-negative after staging.
  Negative speeds indicate data corruption or parsing errors.
*/

SELECT
    vehicle_id,
    speed_kmh,
    ping_at
FROM {{ ref('stg_gps_pings') }}
WHERE speed_kmh < 0
LIMIT 10
