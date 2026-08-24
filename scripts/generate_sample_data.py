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
    "siam": (13.7460, 100.5348),        # Siam Paragon
    "centralworld": (13.7466, 100.5392),# CentralWorld
    "silom": (13.7285, 100.5342),       # Silom Financial District
    "sathorn": (13.7230, 100.5285),     # Sathorn Square CBD
    "asok": (13.7372, 100.5604),        # Sukhumvit / Asok / Terminal 21
    "thonglor": (13.7337, 100.5840),    # Thonglor / Ekkamai Nightlife
    "ekkamai": (13.7190, 100.5855),     # Ekkamai Gateway
    "rca": (13.7516, 100.5786),         # RCA Entertainment District
    "victory_mon": (13.7649, 100.5383), # Victory Monument Transit Hub
    "chatuchak": (13.8000, 100.5508),   # Chatuchak Weekend Market & BTS
    "suvarnabhumi": (13.6900, 100.7501),# Suvarnabhumi Airport (BKK)
    "don_mueang": (13.9130, 100.6068),  # Don Mueang Airport (DMK)
    "iconsiam": (13.7267, 100.5108),    # ICONSIAM / Charoen Nakhon
    "grand_palace": (13.7500, 100.4914),# Grand Palace / Sanam Luang
    "khaosan": (13.7588, 100.4975),     # Khaosan Road
    "yaowarat": (13.7412, 100.5085),    # Yaowarat Chinatown
    "bang_sue": (13.8040, 100.5401),    # Krung Thep Aphiwat Central Station
    "ari": (13.7797, 100.5447),         # Ari / Phahonyothin
    "mega_bangna": (13.6682, 100.6477), # Mega Bangna
    "ladprao": (13.8164, 100.5606),     # Central Ladprao
    "rama3": (13.6872, 100.5312),       # Rama 3 Riverside
    "wongwian_yai": (13.7226, 100.4947),# Wongwian Yai
    "pinklao": (13.7778, 100.4764),     # Central Pinklao
    "huai_khwang": (13.7788, 100.5746), # Huai Khwang Market
    "on_nut": (13.7056, 100.6015),      # On Nut / Sukhumvit 77
    "saphan_taksin": (13.7190, 100.5135),# Saphan Taksin Pier
    "rajamangala": (13.7554, 100.6222), # Rajamangala Stadium
    "kasetsart": (13.8479, 100.5700),   # Kasetsart University
    "bangkapi": (13.7656, 100.6425),    # The Mall Bangkapi
    "seacon": (13.6942, 100.6475)       # Seacon Square Srinakarin
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
    speed_bias: str = "normal",
    vacancy_bias: str = "balanced",
    target_speed: float | None = None,
    target_vacancy_pct: float | None = None,
    ping_interval_secs: int = 60,
) -> list[list]:
    """
    Generate a full day of GPS pings for one taxi under a specific scenario and exact numerical targets.
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
        start_pt = random.choice([BANGKOK_HOTSPOTS["thonglor"], BANGKOK_HOTSPOTS["rca"], BANGKOK_HOTSPOTS["silom"]])
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

        # Calculate speed
        if not engine_on:
            speed = 0
        elif target_speed is not None and target_speed > 0:
            # Custom exact speed target with natural +- 25% variation
            speed = max(0, int(random.gauss(target_speed, target_speed * 0.25)))
        elif scenario == "rain" or speed_bias == "congested":
            # Gridlock: 5 to 25 km/h max
            speed = 0 if random.random() < 0.4 else random.randint(4, 22)
        elif scenario == "airport" or speed_bias == "fast":
            # Fast highway trips
            speed = random.randint(65, 115) if random.random() < 0.6 else random.randint(25, 60)
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
        jitter_step = int(ping_interval_secs * random.uniform(0.85, 1.15))
        step_secs = jitter_step if engine_on else jitter_step * 3
        current_time += timedelta(seconds=max(5, step_secs))

        # Movement simulation
        if speed > 0:
            move_factor = speed / 60 * 0.001
            lat += base_heading_lat * move_factor + random.uniform(-0.0002, 0.0002)
            lon += base_heading_lon * move_factor + random.uniform(-0.0002, 0.0002)
            lat = max(13.4, min(14.3, lat))
            lon = max(100.2, min(101.0, lon))

        # State transitions (pickup / dropoff) with exact or bias targets
        if target_vacancy_pct is not None:
            # Desired vacant fraction v = target_vacancy_pct / 100
            # Markov chain steady-state: v = drop / (pickup + drop)
            # Fix drop = 0.05 -> pickup = 0.05 * (1 - v) / v
            v = max(0.05, min(0.95, target_vacancy_pct / 100.0))
            dropoff_prob = 0.05
            pickup_prob = max(0.01, min(0.5, 0.05 * (1.0 - v) / v))
        elif vacancy_bias == "high_demand":
            pickup_prob = 0.25
            dropoff_prob = 0.02
        elif vacancy_bias == "low_demand":
            pickup_prob = 0.04
            dropoff_prob = 0.12
        else:
            pickup_prob = 0.15 if (scenario == "rain" or is_rush_hour) else 0.08
            dropoff_prob = 0.03 if scenario == "airport" else 0.05

        if is_vacant and random.random() < pickup_prob:
            is_vacant = False
            # Route towards next destination
            if scenario == "airport":
                dest = random.choice([BANGKOK_HOTSPOTS["suvarnabhumi"], BANGKOK_HOTSPOTS["don_mueang"], BANGKOK_HOTSPOTS["asok"]])
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
    dates_list: list[datetime] | None = None,
    scenario: str = "normal",
    scenario_mix: dict[str, float] | None = None,
    speed_bias: str = "normal",
    vacancy_bias: str = "balanced",
    target_speed: float | None = None,
    target_vacancy_pct: float | None = None,
    ping_interval_secs: int = 60,
    chaos_rate: float = 0.05,
) -> list[Path]:
    """
    Generate sample GPS data files for Bangkok taxis with customizable scenarios and exact numeric targets.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if dates_list:
        dates_to_generate = dates_list
    else:
        if start_date is None:
            start_date = datetime(2018, 2, 1)
        dates_to_generate = [start_date + timedelta(days=i) for i in range(num_days)]

    vehicles = [generate_vehicle_id() for _ in range(num_taxis)]
    generated_files = []

    # Prepare scenario distribution if mix is specified
    available_scenarios = ["normal", "rain", "airport", "nightlife", "chaos"]
    if scenario_mix and sum(scenario_mix.values()) > 0:
        weights = [scenario_mix.get(s, 0.0) for s in available_scenarios]
    else:
        weights = [1.0 if s == scenario else 0.0 for s in available_scenarios]

    logger.info("🚕 Generating %d taxis across %d dates [TargetSpeed: %s, VacancyPct: %s, Interval: %ds]",
                num_taxis, len(dates_to_generate), str(target_speed), str(target_vacancy_pct), ping_interval_secs)

    for current_date in dates_to_generate:
        date_str = current_date.strftime("%Y-%m-%d")
        filepath = output_dir / f"probe_{scenario}_{date_str}.csv"

        all_rows = []
        for vehicle_id in vehicles:
            # Assign scenario per taxi based on mix
            taxi_scenario = random.choices(available_scenarios, weights=weights, k=1)[0] if weights else scenario
            
            if taxi_scenario == "nightlife":
                start_hour, end_hour = 20, 4
            else:
                start_hour = random.randint(5, 9)
                end_hour = random.randint(18, 23)

            rows = generate_taxi_day(
                vehicle_id=vehicle_id,
                date=current_date,
                scenario=taxi_scenario,
                start_hour=start_hour,
                end_hour=end_hour,
                chaos_rate=chaos_rate if taxi_scenario == "chaos" else 0.0,
                speed_bias=speed_bias,
                vacancy_bias=vacancy_bias,
                target_speed=target_speed,
                target_vacancy_pct=target_vacancy_pct,
                ping_interval_secs=ping_interval_secs,
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
