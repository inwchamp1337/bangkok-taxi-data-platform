{% macro haversine_distance(lon1, lat1, lon2, lat2) %}
{#
  Calculate the great-circle distance between two GPS points in meters.

  Uses ClickHouse's built-in greatCircleDistance function which implements
  the Haversine formula.

  Note: ClickHouse expects (lon, lat) order, NOT (lat, lon).

  Args:
    lon1: Longitude of point 1 (degrees)
    lat1: Latitude of point 1 (degrees)
    lon2: Longitude of point 2 (degrees)
    lat2: Latitude of point 2 (degrees)

  Returns:
    Distance in meters (Float64)
#}
greatCircleDistance({{ lon1 }}, {{ lat1 }}, {{ lon2 }}, {{ lat2 }})
{% endmacro %}
