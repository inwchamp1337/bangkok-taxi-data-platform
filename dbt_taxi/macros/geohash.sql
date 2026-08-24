{% macro geohash_encode(lon, lat, precision) %}
{#
  Encode GPS coordinates into a geohash string.

  Uses ClickHouse's built-in geohashEncode function.

  Precision levels:
    4 = ~39km blocks (city-level)
    5 = ~5km blocks  (district-level)
    6 = ~1.2km blocks (neighborhood-level) ← default
    7 = ~150m blocks  (street-level)

  Note: ClickHouse expects (lon, lat) order, NOT (lat, lon).

  Args:
    lon: Longitude column/expression
    lat: Latitude column/expression
    precision: Geohash precision (1-12)

  Returns:
    Geohash string
#}
geohashEncode({{ lon }}, {{ lat }}, {{ precision }})
{% endmacro %}
