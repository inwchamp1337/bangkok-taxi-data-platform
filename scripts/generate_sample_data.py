"""
Generate realistic Bangkok taxi GPS sample data for development and testing.

Produces CSV files in the exact iTIC probe data format:
  VehicleID,gpsvalid,lat,lon,timestamp,speed,passenger_lamp,engine_acc

Features:
  - Realistic Bangkok coordinates (Silom, Sukhumvit, Chatuchak, etc.)
  - Realistic speed patterns (0 at stops, 20-60 in city, 60-100 on expressway)
  - Passenger lamp transitions (pickup/dropoff cycles)
  - Engine on/off patterns (shift start/end)
  - Configurable: number of taxis, duration, output size

Default output: ~100K rows for fast pipeline testing.
"""

from __future__ import annotations

import csv
import hashlib
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Bangkok area landmarks for realistic starting points
BANGKOK_HOTSPOTS = [
    (13.7563, 100.5018),   # Siam Paragon
    (13.7311, 100.5231),   # Silom
    (13.7366, 100.5636),   # Sukhumvit / Nana
    (13.7469, 100.5349),   # Victory Monument
    (13.7999, 100.5530),   # Chatuchak
    (13.6900, 100.7501),   # Suvarnabhumi Airport
    (13.9130, 100.6068),   # Don Mueang Airport
    (13.7248, 100.4930),   # BTS National Stadium
    (13.7649, 100.5685),   # Huai Khwang
    (13.7178, 100.5101),   # Sathorn
    (13.7580, 100.4979),   # Ratchathewi
    (13.7633, 100.5382),   # Din Daeng
    (13.8430, 100.5593),   # Lak Si
    (13.6513, 100.4943),   # Bang Na
]


def generate_vehicle_id() -> str:
    """Generate a realistic-looking hashed vehicle ID like iTIC data."""
    raw = f"taxi_{random.randint(1000, 9999)}_{random.randint(1, 100)}"
    return hashlib.sha1(raw.encode()).hexdigest()[:27]


def jitter(value: float, amount: float = 0.005) -> float:
    """Add small random noise to a coordinate."""
    return value + random.uniform(-amount, amount)


def generate_taxi_day(
    vehicle_id: str,
    date: datetime,
    start_hour: int = 6,
    end_hour: int = 22,
) -> list[list]:
    """
    Generate a full day of GPS pings for one taxi.

    Simulates:
    - Shift start (engine on) and end (engine off)
    - Driving between hotspots
    - Pickup/dropoff cycles with realistic durations
    - Speed variations (stopped, city, expressway)
    - 1-minute intervals when engine on, 3-minute when off
    """
    rows = []
    current_time = date.replace(hour=start_hour, minute=random.randint(0, 30))
    end_time = date.replace(hour=end_hour, minute=random.randint(0, 59))

    # Start at a random hotspot
    lat, lon = random.choice(BANGKOK_HOTSPOTS)
    lat = jitter(lat, 0.01)
    lon = jitter(lon, 0.01)
    is_vacant = True
    engine_on = True

    # Movement parameters
    base_heading_lat = random.uniform(-0.0005, 0.0005)
    base_heading_lon = random.uniform(-0.0005, 0.0005)

    while current_time < end_time:
        # GPS valid (99% of the time)
        gps_valid = 1 if random.random() < 0.99 else 0

        # Speed based on state
        if not engine_on:
            speed = 0
        elif random.random() < 0.15:
            speed = 0  # Stopped at red light / traffic
        elif random.random() < 0.1:
            speed = random.randint(60, 100)  # Expressway
        else:
            speed = random.randint(10, 55)  # City driving

        # Record the ping
        rows.append([
            vehicle_id,
            gps_valid,
            round(lat, 5),
            round(lon, 5),
            current_time.strftime("%Y-%m-%d %H:%M:%S"),
            speed,
            1 if is_vacant else 0,
            1 if engine_on else 0,
        ])

        # Advance time (1 min engine on, 3 min engine off)
        if engine_on:
            interval = timedelta(seconds=random.randint(50, 70))
        else:
            interval = timedelta(seconds=random.randint(160, 200))
        current_time += interval

        # Move position if driving
        if speed > 0:
            move_factor = speed / 60 * 0.001  # Rough movement per minute
            lat += base_heading_lat * move_factor + random.uniform(-0.0002, 0.0002)
            lon += base_heading_lon * move_factor + random.uniform(-0.0002, 0.0002)

            # Keep within Bangkok bounds
            lat = max(13.4, min(14.3, lat))
            lon = max(100.2, min(101.0, lon))

        # State transitions
        if is_vacant and random.random() < 0.08:
            # Pick up passenger
            is_vacant = False
            # Move toward a destination hotspot
            dest = random.choice(BANGKOK_HOTSPOTS)
            base_heading_lat = (dest[0] - lat) * 0.01
            base_heading_lon = (dest[1] - lon) * 0.01

        elif not is_vacant and random.random() < 0.05:
            # Drop off passenger
            is_vacant = True
            # New random heading
            base_heading_lat = random.uniform(-0.0005, 0.0005)
            base_heading_lon = random.uniform(-0.0005, 0.0005)

        # Occasional break (engine off for 15-30 min)
        if engine_on and random.random() < 0.005:
            engine_on = False
        elif not engine_on and random.random() < 0.3:
            engine_on = True

    return rows


def generate_sample_data(
    output_dir: Path,
    num_taxis: int = 50,
    num_days: int = 3,
    start_date: datetime | None = None,
) -> list[Path]:
    """
    Generate sample GPS data files.

    Args:
        output_dir: Directory to write CSV files.
        num_taxis: Number of distinct taxis to simulate.
        num_days: Number of days to generate.
        start_date: First day of data.

    Returns:
        List of generated CSV file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if start_date is None:
        start_date = datetime(2018, 2, 1)

    # Generate vehicle IDs
    vehicles = [generate_vehicle_id() for _ in range(num_taxis)]
    generated_files = []

    for day_offset in range(num_days):
        current_date = start_date + timedelta(days=day_offset)
        date_str = current_date.strftime("%Y-%m-%d")
        filepath = output_dir / f"probe_{date_str}.csv"

        logger.info("Generating data for %s (%d taxis)", date_str, num_taxis)

        all_rows = []
        for vehicle_id in vehicles:
            # Each taxi works a shift (random start/end hours)
            start_hour = random.randint(4, 10)
            end_hour = random.randint(18, 23)
            rows = generate_taxi_day(vehicle_id, current_date, start_hour, end_hour)
            all_rows.extend(rows)

        # Sort by timestamp for realism
        all_rows.sort(key=lambda r: r[4])

        # Write CSV
        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(all_rows)

        size_mb = filepath.stat().st_size / (1024 * 1024)
        logger.info("  → %s: %d rows (%.1f MB)", filepath.name, len(all_rows), size_mb)
        generated_files.append(filepath)

    total_rows = sum(1 for f in generated_files for _ in open(f))
    logger.info("✅ Generated %d files, ~%d total rows", len(generated_files), total_rows)
    return generated_files


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate sample Bangkok taxi GPS data")
    parser.add_argument("--taxis", type=int, default=50, help="Number of taxis (default: 50)")
    parser.add_argument("--days", type=int, default=3, help="Number of days (default: 3)")
    parser.add_argument("--output", type=str, default="data/sample", help="Output directory")
    parser.add_argument("--start-date", type=str, default="2018-02-01", help="Start date (YYYY-MM-DD)")
    args = parser.parse_args()

    start = datetime.strptime(args.start_date, "%Y-%m-%d")
    generate_sample_data(
        output_dir=Path(args.output),
        num_taxis=args.taxis,
        num_days=args.days,
        start_date=start,
    )
