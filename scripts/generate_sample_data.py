"""
Generate realistic Bangkok taxi GPS sample data with customizable traffic scenarios.

Produces CSV files in the exact iTIC probe data format:
  VehicleID,gpsvalid,lat,lon,timestamp,speed,passenger_lamp,engine_acc

Supported Scenarios:
  - normal: Standard weekday traffic with morning/evening rush hours.
  - rain: Monsoon heavy rain gridlock (low speeds 5-20 km/h, high taxi occupancy).
  - airport: High-speed corridor trips between Suvarnabhumi / Don Mueang & downtown.
  - nightlife: Late night surge (21:00 - 04:00) in Sukhumvit, Thonglor, RCA, Silom.
  - chaos: Chaos engineering mode injecting 5% corrupted records to test quarantine & dbt tests.
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
BANGKOK_HOTSPOTS = {
    "siam": (13.7563, 100.5018),        # Siam Paragon / CentralWorld
    "silom": (13.7311, 100.5231),       # Silom Financial District
    "sukhumvit": (13.7366, 100.5636),   # Sukhumvit / Asok / Nana
    "thonglor": (13.7337, 100.5840),    # Thonglor / Ekkamai Nightlife
    "rca": (13.7516, 100.5786),         # RCA Entertainment District
    "victory_mon": (13.7469, 100.5349), # Victory Monument Transit Hub
    "chatuchak": (13.7999, 100.5530),   # Chatuchak Weekend Market & BTS
    "suvarnabhumi": (13.6900, 100.7501),# Suvarnabhumi Airport (BKK)
    "don_mueang": (13.9130, 100.6068),  # Don Mueang Airport (DMK)
    "sathorn": (13.7178, 100.5101),     # Sathorn CBD
    "huai_khwang": (13.7649, 100.5685), # Huai Khwang / Ratchada
    "bang_na": (13.6513, 100.4943),     # Bang Na Gateway
    "ratchathewi": (13.7580, 100.4979), # Ratchathewi
    "din_daeng": (13.7633, 100.5382),   # Din Daeng Expressways
}

HOTSPOT_COORDS = list(BANGKOK_HOTSPOTS.values())


def generate_vehicle_id() -> str:
    """Generate a realistic-looking hashed vehicle ID like iTIC data."""
    raw = f"taxi_{random.randint(1000, 9999)}_{random.randint(1, 10000)}_{random.random()}"
    return hashlib.sha1(raw.encode()).hexdigest()[:27]


def jitter(value: float, amount: float = 0.005) -> float:
    """Add small random noise to a coordinate."""
    return value + random.uniform(-amount, amount)


def generate_taxi_day(
    vehicle_id: str,
    date: datetime,
    scenario: str = "normal",
    start_hour: int = 6,
    end_hour: int = 22,
    chaos_rate: float = 0.05,
) -> list[list]:
    """
    Generate a full day of GPS pings for one taxi under a specific scenario.
    """
    rows = []
    current_time = date.replace(hour=start_hour, minute=random.randint(0, 30), second=random.randint(0, 59))
    end_time = date.replace(hour=end_hour, minute=random.randint(0, 59), second=59)
    if end_hour < start_hour:  # Overnight shift (e.g. 21:00 to 05:00)
        end_time += timedelta(days=1)

    # Pick initial location based on scenario
    if scenario == "airport":
        start_pt = random.choice([BANGKOK_HOTSPOTS["suvarnabhumi"], BANGKOK_HOTSPOTS["don_mueang"], BANGKOK_HOTSPOTS["siam"]])
    elif scenario == "nightlife":
        start_pt = random.choice([BANGKOK_HOTSPOTS["thonglor"], BANGKOK_HOTSPOTS["rca"], BANGKOK_HOTSPOTS["sukhumvit"], BANGKOK_HOTSPOTS["silom"]])
    else:
        start_pt = random.choice(HOTSPOT_COORDS)

    lat = jitter(start_pt[0], 0.01)
    lon = jitter(start_pt[1], 0.01)
    is_vacant = True
    engine_on = True

    base_heading_lat = random.uniform(-0.0005, 0.0005)
    base_heading_lon = random.uniform(-0.0005, 0.0005)

    while current_time < end_time:
        # Scenario adjustments
        hour = current_time.hour
        is_rush_hour = hour in (7, 8, 9, 17, 18, 19)

        # GPS fix validity
        gps_valid = 1 if random.random() < 0.99 else 0

        # Calculate speed by scenario
        if not engine_on:
            speed = 0
        elif scenario == "rain":
            # Gridlock: 5 to 25 km/h max
            speed = 0 if random.random() < 0.35 else random.randint(5, 25)
        elif scenario == "airport":
            # Fast highway trips
            speed = random.randint(65, 110) if random.random() < 0.55 else random.randint(15, 50)
        elif scenario == "nightlife":
            # Midnight cruising vs expressways
            speed = random.randint(25, 75)
        else:  # normal
            if is_rush_hour:
                speed = 0 if random.random() < 0.30 else random.randint(8, 35)
            elif random.random() < 0.15:
                speed = random.randint(60, 95)  # Tollway / Expressway
            else:
                speed = random.randint(15, 55)

        # Chaos mode: inject deliberate errors
        if scenario == "chaos" and random.random() < chaos_rate:
            anomaly_type = random.choice(["out_of_bounds", "extreme_speed", "invalid_flag", "corrupt_coord"])
            if anomaly_type == "out_of_bounds":
                rec_lat, rec_lon = 52.5200, 13.4050  # Berlin
            elif anomaly_type == "extreme_speed":
                speed = random.randint(350, 999)
                rec_lat, rec_lon = lat, lon
            elif anomaly_type == "invalid_flag":
                gps_valid = 99
                rec_lat, rec_lon = lat, lon
            else:
                rec_lat, rec_lon = -999.0, 999.0
        else:
            rec_lat = round(lat, 5)
            rec_lon = round(lon, 5)

        # Record the GPS ping (iTIC 7-field CSV format)
        rows.append([
            vehicle_id,
            gps_valid,
            rec_lat,
            rec_lon,
            current_time.strftime("%Y-%m-%d %H:%M:%S"),
            speed,
            1 if is_vacant else 0,
            1 if engine_on else 0,
        ])

        # Step time
        step_secs = random.randint(50, 70) if engine_on else random.randint(160, 200)
        current_time += timedelta(seconds=step_secs)

        # Movement simulation
        if speed > 0:
            move_factor = speed / 60 * 0.001
            lat += base_heading_lat * move_factor + random.uniform(-0.0002, 0.0002)
            lon += base_heading_lon * move_factor + random.uniform(-0.0002, 0.0002)
            lat = max(13.4, min(14.3, lat))
            lon = max(100.2, min(101.0, lon))

        # State transitions (pickup / dropoff)
        pickup_prob = 0.15 if (scenario == "rain" or is_rush_hour) else 0.08
        dropoff_prob = 0.03 if scenario == "airport" else 0.05

        if is_vacant and random.random() < pickup_prob:
            is_vacant = False
            # Route towards next destination
            if scenario == "airport":
                dest = random.choice([BANGKOK_HOTSPOTS["suvarnabhumi"], BANGKOK_HOTSPOTS["don_mueang"], BANGKOK_HOTSPOTS["sukhumvit"]])
            elif scenario == "nightlife":
                dest = random.choice([BANGKOK_HOTSPOTS["thonglor"], BANGKOK_HOTSPOTS["rca"], BANGKOK_HOTSPOTS["silom"]])
            else:
                dest = random.choice(HOTSPOT_COORDS)
            base_heading_lat = (dest[0] - lat) * 0.01
            base_heading_lon = (dest[1] - lon) * 0.01

        elif not is_vacant and random.random() < dropoff_prob:
            is_vacant = True
            base_heading_lat = random.uniform(-0.0005, 0.0005)
            base_heading_lon = random.uniform(-0.0005, 0.0005)

        # Rest break (engine off)
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
    scenario: str = "normal",
    chaos_rate: float = 0.05,
) -> list[Path]:
    """
    Generate sample GPS data files for Bangkok taxis with a selected scenario.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if start_date is None:
        start_date = datetime(2018, 2, 1)

    vehicles = [generate_vehicle_id() for _ in range(num_taxis)]
    generated_files = []

    logger.info("🚕 Generating %d taxis across %d days [Scenario: %s]", num_taxis, num_days, scenario)

    for day_offset in range(num_days):
        current_date = start_date + timedelta(days=day_offset)
        date_str = current_date.strftime("%Y-%m-%d")
        filepath = output_dir / f"probe_{scenario}_{date_str}.csv"

        all_rows = []
        for vehicle_id in vehicles:
            if scenario == "nightlife":
                start_hour, end_hour = 20, 4
            else:
                start_hour = random.randint(5, 9)
                end_hour = random.randint(18, 23)

            rows = generate_taxi_day(
                vehicle_id=vehicle_id,
                date=current_date,
                scenario=scenario,
                start_hour=start_hour,
                end_hour=end_hour,
                chaos_rate=chaos_rate,
            )
            all_rows.extend(rows)

        all_rows.sort(key=lambda r: r[4])

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(all_rows)

        size_mb = filepath.stat().st_size / (1024 * 1024)
        logger.info("  → %s: %d rows (%.1f MB)", filepath.name, len(all_rows), size_mb)
        generated_files.append(filepath)

    total_rows = sum(len(open(f).readlines()) for f in generated_files)
    logger.info("✅ Generated %d files, %d total records in %s", len(generated_files), total_rows, output_dir)
    return generated_files


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate Bangkok Taxi GPS data with scenario simulation")
    parser.add_argument("--taxis", type=int, default=50, help="Number of taxis (default: 50)")
    parser.add_argument("--days", type=int, default=3, help="Number of days (default: 3)")
    parser.add_argument("--output", type=str, default="data/sample", help="Output directory")
    parser.add_argument("--start-date", type=str, default="2018-02-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--scenario", type=str, default="normal", choices=["normal", "rain", "airport", "nightlife", "chaos"], help="Traffic scenario preset")
    parser.add_argument("--chaos-rate", type=float, default=0.05, help="Rate of invalid records in chaos mode (0.0 to 1.0)")
    args = parser.parse_args()

    start = datetime.strptime(args.start_date, "%Y-%m-%d")
    generate_sample_data(
        output_dir=Path(args.output),
        num_taxis=args.taxis,
        num_days=args.days,
        start_date=start,
        scenario=args.scenario,
        chaos_rate=args.chaos_rate,
    )
