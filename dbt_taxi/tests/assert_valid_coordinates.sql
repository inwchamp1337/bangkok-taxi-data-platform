/*
  Test: Assert all coordinates are within the Bangkok metropolitan bounding box.
  This test validates that the staging model filter is working correctly.
*/

SELECT
    vehicle_id,
    lat,
    lon,
    ping_at
FROM {{ ref('stg_gps_pings') }}
WHERE
    lat < {{ var('bkk_lat_min') }}
    OR lat > {{ var('bkk_lat_max') }}
    OR lon < {{ var('bkk_lon_min') }}
    OR lon > {{ var('bkk_lon_max') }}
LIMIT 10
