"""
FastAPI Control Panel & Simulation Engine for Bangkok Taxi Data Engineering Platform.

Serves the interactive web UI and coordinates data generation, validation,
ClickHouse loading, and dbt transformation runs.
"""

from __future__ import annotations

import asyncio
import httpx
import logging
import random
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from scripts.generate_sample_data import generate_sample_data
from src.config.settings import get_settings
from src.loaders.clickhouse_loader import get_clickhouse_client, load_csv_file

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("control-panel")

app = FastAPI(
    title="Bangkok Taxi DE Platform Control Panel",
    description="Interactive control plane for mock data generation, pipeline execution, and scenario testing",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class GenerateRequest(BaseModel):
    num_taxis: int = Field(default=50, ge=5, le=1000, description="Number of active taxis in fleet")
    num_days: int = Field(default=3, ge=1, le=14, description="Number of simulation days")
    scenario: str = Field(default="normal", description="Scenario: normal, rain, airport, nightlife, chaos")
    chaos_rate: float = Field(default=0.05, ge=0.0, le=0.5, description="Anomaly rate for chaos mode")
    start_date: str = Field(default="2018-02-01", description="Simulation start date (YYYY-MM-DD)")


class PipelineRunRequest(BaseModel):
    num_taxis: int = 50
    num_days: int = 3
    scenario: str = "normal"
    chaos_rate: float = 0.05
    start_date: str = "2018-02-01"


class CustomSimulationRequest(BaseModel):
    mode: str = "daily"  # "daily" | "monthly"
    start_date: str = "2018-02-01"
    num_days: int = 3
    year_month: str = "2018-02"
    num_taxis: int = 50
    scenario_mix: dict[str, float] = Field(default_factory=lambda: {"normal": 1.0, "rain": 0.0, "airport": 0.0, "nightlife": 0.0, "chaos": 0.0})
    speed_bias: str = "normal"  # "normal" | "congested" | "fast"
    vacancy_bias: str = "balanced"  # "balanced" | "high_demand" | "low_demand"
    overwrite: bool = True
    chaos_rate: float = 0.05


@app.get("/")
async def serve_index():
    """Serve the main web UI."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_path)


@app.get("/api/status")
async def get_system_status() -> dict[str, Any]:
    """Get real-time status of ClickHouse tables, sample files, and metrics."""
    settings = get_settings()
    table_counts: dict[str, int] = {}
    ch_connected = False

    try:
        client = get_clickhouse_client()
        tables = [
            "raw_gps_pings",
            "stg_gps_pings",
            "fact_trips",
            "fact_hourly_metrics",
            "dim_taxi",
            "dim_time",
        ]
        for tbl in tables:
            try:
                res = client.query(f"SELECT count() FROM {tbl}")
                table_counts[tbl] = res.result_rows[0][0] if res.result_rows else 0
            except Exception:
                table_counts[tbl] = 0
        ch_connected = True
    except Exception as exc:
        logger.warning("ClickHouse status check failed: %s", exc)

    # Sample data files
    sample_files = []
    sample_dir = settings.sample_dir
    total_sample_rows = 0
    if sample_dir.exists():
        for f in sorted(sample_dir.glob("*.csv")):
            line_count = sum(1 for _ in open(f))
            sample_files.append({
                "filename": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "rows": line_count,
            })
            total_sample_rows += line_count

    return {
        "timestamp": datetime.now().isoformat(),
        "clickhouse": {
            "connected": ch_connected,
            "tables": table_counts,
            "total_raw_rows": table_counts.get("raw_gps_pings", 0),
            "total_trips": table_counts.get("fact_trips", 0),
        },
        "sample_data": {
            "file_count": len(sample_files),
            "total_rows": total_sample_rows,
            "files": sample_files,
        },
        "services": {
            "airflow": "http://127.0.0.1:8080",
            "grafana": "http://127.0.0.1:3000",
            "minio": "http://127.0.0.1:9001",
            "clickhouse": "http://127.0.0.1:8123",
        },
    }


@app.post("/api/generate")
async def generate_mock_data(req: GenerateRequest) -> dict[str, Any]:
    """Generate mock Bangkok taxi GPS probe data based on selected scenario."""
    settings = get_settings()
    try:
        start = datetime.strptime(req.start_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid start_date format (YYYY-MM-DD)")

    logger.info("Generating data with scenario: %s (%d taxis, %d days)", req.scenario, req.num_taxis, req.num_days)

    files = generate_sample_data(
        output_dir=settings.sample_dir,
        num_taxis=req.num_taxis,
        num_days=req.num_days,
        start_date=start,
        scenario=req.scenario,
        chaos_rate=req.chaos_rate,
    )

    total_rows = sum(sum(1 for _ in open(f)) for f in files)
    return {
        "status": "success",
        "message": f"Generated {len(files)} files with {total_rows:,} records",
        "scenario": req.scenario,
        "files": [f.name for f in files],
        "total_rows": total_rows,
    }


@app.post("/api/load")
async def load_to_clickhouse() -> dict[str, Any]:
    """Validate and load all generated sample files into ClickHouse."""
    from src.ingestion.uploader import upload_files_to_minio
    from src.loaders.clickhouse_loader import load_csv_from_s3

    settings = get_settings()
    sample_dir = settings.sample_dir
    files = sorted(sample_dir.glob("*.csv"))

    if not files:
        raise HTTPException(status_code=400, detail="No sample CSV files found in data/sample/. Generate data first.")

    total_loaded = 0
    file_reports = []

    # Upload all to MinIO first (we'll just use a mock year_month for now)
    year_month = "201802"
    uploaded_keys = upload_files_to_minio(files, year_month)

    # Now load them using ClickHouse S3 integration (ELT)
    for f, key in zip(files, uploaded_keys):
        res = load_csv_from_s3(
            minio_bucket=settings.minio.raw_bucket,
            minio_key=key,
            source_file=f.name
        )
        # We don't have accurate row counts natively from INSERT SELECT without extra queries,
        # so we'll just record success and estimate based on local file for the UI.
        est_rows = sum(1 for _ in open(f))
        if res["status"] == "success":
            total_loaded += est_rows
        file_reports.append({"file": f.name, "rows_loaded": est_rows if res["status"] == "success" else 0})

    return {
        "status": "success",
        "message": f"Loaded estimated {total_loaded:,} records into ClickHouse via S3",
        "files_processed": len(files),
        "total_loaded": total_loaded,
        "details": file_reports,
    }


@app.post("/api/dbt/run")
async def trigger_dbt_run() -> dict[str, Any]:
    """Execute dbt run (staging -> intermediate -> marts) inside ClickHouse."""
    dbt_dir = Path("/opt/dbt_taxi")
    if not dbt_dir.exists():
        dbt_dir = Path("dbt_taxi")

    try:
        res = subprocess.run(
            ["dbt", "run"],
            cwd=str(dbt_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if res.returncode != 0:
            err_msg = (res.stderr or res.stdout or "dbt run failed").strip()
            logger.error(f"dbt run failed: {err_msg}")
            raise HTTPException(status_code=500, detail=err_msg[-400:])
            
        return {
            "status": "success",
            "message": "dbt models built successfully",
            "returncode": res.returncode,
            "stdout": res.stdout,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/dbt/test")
async def trigger_dbt_test() -> dict[str, Any]:
    """Execute dbt data quality tests."""
    dbt_dir = Path("/opt/dbt_taxi")
    if not dbt_dir.exists():
        dbt_dir = Path("dbt_taxi")

    try:
        res = subprocess.run(
            ["dbt", "test"],
            cwd=str(dbt_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if res.returncode != 0:
            err_msg = (res.stderr or res.stdout or "dbt test failed").strip()
            logger.error(f"dbt test failed: {err_msg}")
            raise HTTPException(status_code=500, detail=err_msg[-400:])
            
        return {
            "status": "success",
            "message": "dbt tests passed successfully",
            "returncode": res.returncode,
            "stdout": res.stdout,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/pipeline/run-all")
async def run_full_mock_pipeline(req: PipelineRunRequest) -> dict[str, Any]:
    """One-click full pipeline: Generate mock data -> Validate & Load -> dbt Run -> dbt Test."""
    # 1. Generate
    gen_res = await generate_mock_data(GenerateRequest(**req.model_dump()))

    # 2. Load
    load_res = await load_to_clickhouse()

    # 3. dbt run
    dbt_run_res = await trigger_dbt_run()

    # 4. dbt test
    dbt_test_res = await trigger_dbt_test()

    return {
        "status": "success" if dbt_test_res["status"] == "success" else "partial_success",
        "generate": gen_res,
        "load": load_res,
        "dbt_run": dbt_run_res,
        "dbt_test": dbt_test_res,
    }


@app.post("/api/pipeline/run-all-scenarios")
async def run_all_scenarios_pipeline(req: PipelineRunRequest) -> dict[str, Any]:
    """Simulate EVERY scenario sequentially."""
    scenarios = ["normal", "rain", "airport", "nightlife", "chaos"]
    
    total_generated = 0
    total_loaded = 0
    
    for scn in scenarios:
        logger.info("Running pipeline for scenario: %s", scn)
        
        # Override scenario in request
        scenario_req = GenerateRequest(
            num_taxis=req.num_taxis,
            num_days=req.num_days,
            scenario=scn,
            chaos_rate=0.05 if scn == "chaos" else 0.0,
            start_date=req.start_date
        )
        
        gen_res = await generate_mock_data(scenario_req)
        total_generated += gen_res["total_rows"]
        
    # Load everything after generating
    load_res = await load_to_clickhouse()
    total_loaded += load_res["total_loaded"]
    
    # 3. dbt run
    dbt_run_res = await trigger_dbt_run()

    # 4. dbt test
    dbt_test_res = await trigger_dbt_test()

    return {
        "status": "success" if dbt_test_res["status"] == "success" else "partial_success",
        "scenarios_run": scenarios,
        "total_generated": total_generated,
        "total_loaded": total_loaded,
        "dbt_run": dbt_run_res,
        "dbt_test": dbt_test_res,
    }


@app.post("/api/pipeline/custom-run")
async def run_custom_simulation_pipeline(req: CustomSimulationRequest) -> dict[str, Any]:
    """Execute custom manual simulation: Daily/Monthly granularity, custom traffic/demand modifiers, overwrite/append."""
    import calendar
    settings = get_settings()

    # 1. Handle Overwrite option
    if req.overwrite:
        logger.info("Overwrite requested — resetting database and sample files...")
        await reset_all_data()

    # 2. Compute date list based on mode
    dates_list: list[datetime] = []
    if req.mode == "monthly":
        try:
            parts = req.year_month.split("-")
            year, month = int(parts[0]), int(parts[1])
            _, max_days = calendar.monthrange(year, month)
            dates_list = [datetime(year, month, d) for d in range(1, max_days + 1)]
            logger.info("Monthly Mode: Simulating full month %04d-%02d (%d days)", year, month, len(dates_list))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid year_month format (YYYY-MM): {e}")
    else:  # daily
        try:
            start = datetime.strptime(req.start_date, "%Y-%m-%d")
            dates_list = [start + timedelta(days=i) for i in range(max(1, req.num_days))]
            logger.info("Daily Mode: Simulating %d days starting from %s", len(dates_list), req.start_date)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid start_date format (YYYY-MM-DD): {e}")

    # 3. Generate Custom Mock Data
    files = generate_sample_data(
        output_dir=settings.sample_dir,
        num_taxis=req.num_taxis,
        dates_list=dates_list,
        scenario_mix=req.scenario_mix,
        speed_bias=req.speed_bias,
        vacancy_bias=req.vacancy_bias,
        chaos_rate=req.chaos_rate,
    )

    total_rows = sum(sum(1 for _ in open(f)) for f in files)
    gen_res = {
        "status": "success",
        "message": f"Generated {len(files)} files with {total_rows:,} records",
        "files_count": len(files),
        "total_rows": total_rows,
        "mode": req.mode,
    }

    # 4. Load into ClickHouse
    load_res = await load_to_clickhouse()

    # 5. Execute dbt
    dbt_dir = Path("/opt/dbt_taxi") if Path("/opt/dbt_taxi").exists() else Path("dbt_taxi")
    dbt_cmd = ["dbt", "run", "--full-refresh"] if req.overwrite else ["dbt", "run"]
    
    try:
        proc = subprocess.run(dbt_cmd, cwd=str(dbt_dir), capture_output=True, text=True, timeout=180)
        dbt_run_res = {
            "status": "success" if proc.returncode == 0 else "error",
            "message": "dbt models refreshed successfully" if proc.returncode == 0 else "dbt run failed",
            "stdout": proc.stdout,
        }
        if proc.returncode != 0:
            logger.error(f"Custom dbt run failed: {proc.stderr or proc.stdout}")
    except Exception as exc:
        dbt_run_res = {"status": "error", "message": str(exc)}

    # 6. Run dbt test
    dbt_test_res = await trigger_dbt_test()

    return {
        "status": "success" if dbt_run_res.get("status") == "success" else "partial_success",
        "mode": req.mode,
        "days_simulated": len(dates_list),
        "overwrite": req.overwrite,
        "generate": gen_res,
        "load": load_res,
        "dbt_run": dbt_run_res,
        "dbt_test": dbt_test_res,
    }

@app.get("/api/fleet/locations")
async def get_fleet_locations() -> dict[str, Any]:
    """Fetch the latest known location of each taxi for live mapping."""
    try:
        client = get_clickhouse_client()
        query = """
        SELECT 
            vehicle_id, 
            argMax(lat, timestamp) as lat, 
            argMax(lon, timestamp) as lon, 
            argMax(speed, timestamp) as speed, 
            argMax(passenger_lamp, timestamp) as passenger_lamp,
            max(timestamp) as last_seen
        FROM taxi.raw_gps_pings
        GROUP BY vehicle_id
        ORDER BY last_seen DESC
        LIMIT 500
        """
        res = client.query(query)
        
        vehicles = []
        for row in res.result_rows:
            vehicles.append({
                "vehicle_id": row[0],
                "lat": row[1],
                "lon": row[2],
                "speed": row[3],
                "passenger_lamp": row[4],
                "last_seen": row[5].isoformat() if hasattr(row[5], "isoformat") else str(row[5])
            })
            
        return {
            "status": "success",
            "count": len(vehicles),
            "data": vehicles
        }
    except Exception as exc:
        logger.error("Failed to fetch fleet locations: %s", exc)
        return {"status": "error", "message": str(exc), "count": 0, "data": []}

# --- Live Streaming Mode ---
LIVE_TASK = None
LIVE_FLEET = []

async def fetch_osrm_route(lon1, lat1, lon2, lat2):
    url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("routes") and len(data["routes"]) > 0:
                    return data["routes"][0]["geometry"]["coordinates"]
    except Exception as e:
        logger.warning(f"OSRM Error: {e}")
    return None

import time

async def run_dbt_background():
    """Run dbt in the background so Live Stream data appears in Grafana."""
    dbt_dir = Path("/opt/dbt_taxi")
    if not dbt_dir.exists():
        dbt_dir = Path("dbt_taxi")
    try:
        proc = await asyncio.create_subprocess_exec(
            "dbt", "run",
            cwd=str(dbt_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
    except Exception as e:
        logger.error(f"Background dbt run failed: {e}")

# Bangkok Landmark Hotspots for realistic trip generation
BANGKOK_LANDMARKS = [
    {"name": "Siam Paragon", "lat": 13.7460, "lon": 100.5348},
    {"name": "CentralWorld", "lat": 13.7466, "lon": 100.5392},
    {"name": "Silom / Sala Daeng", "lat": 13.7285, "lon": 100.5342},
    {"name": "Sathorn Square", "lat": 13.7230, "lon": 100.5285},
    {"name": "Asok / Terminal 21", "lat": 13.7372, "lon": 100.5604},
    {"name": "Thong Lo (Sukhumvit 55)", "lat": 13.7337, "lon": 100.5840},
    {"name": "Ekkamai Gateway", "lat": 13.7190, "lon": 100.5855},
    {"name": "RCA Nightlife", "lat": 13.7516, "lon": 100.5786},
    {"name": "Victory Monument", "lat": 13.7649, "lon": 100.5383},
    {"name": "Chatuchak Weekend Market", "lat": 13.8000, "lon": 100.5508},
    {"name": "Suvarnabhumi Airport (BKK)", "lat": 13.6900, "lon": 100.7501},
    {"name": "Don Mueang Airport (DMK)", "lat": 13.9130, "lon": 100.6068},
    {"name": "ICONSIAM", "lat": 13.7267, "lon": 100.5108},
    {"name": "Grand Palace / Sanam Luang", "lat": 13.7500, "lon": 100.4914},
    {"name": "Khaosan Road", "lat": 13.7588, "lon": 100.4975},
    {"name": "Yaowarat Chinatown", "lat": 13.7412, "lon": 100.5085},
    {"name": "Krung Thep Aphiwat Central Station", "lat": 13.8040, "lon": 100.5401},
    {"name": "Ari / La Villa", "lat": 13.7797, "lon": 100.5447},
    {"name": "Mega Bangna", "lat": 13.6682, "lon": 100.6477},
    {"name": "Central Ladprao", "lat": 13.8164, "lon": 100.5606},
    {"name": "Rama 3 Riverside", "lat": 13.6872, "lon": 100.5312},
    {"name": "Wongwian Yai", "lat": 13.7226, "lon": 100.4947},
    {"name": "Central Pinklao", "lat": 13.7778, "lon": 100.4764},
    {"name": "Huai Khwang Market", "lat": 13.7788, "lon": 100.5746},
    {"name": "On Nut / Sukhumvit 77", "lat": 13.7056, "lon": 100.6015},
    {"name": "Saphan Taksin Pier", "lat": 13.7190, "lon": 100.5135},
    {"name": "Rajamangala Stadium", "lat": 13.7554, "lon": 100.6222},
    {"name": "Kasetsart University", "lat": 13.8479, "lon": 100.5700},
    {"name": "The Mall Bangkapi", "lat": 13.7656, "lon": 100.6425},
    {"name": "Seacon Square Srinakarin", "lat": 13.6942, "lon": 100.6475}
]

async def live_stream_worker(interval: int):
    global LIVE_FLEET
    client = get_clickhouse_client()
    
    # Initialize 60 live taxis distributed across Bangkok landmarks
    if not LIVE_FLEET:
        for i in range(60):
            origin = random.choice(BANGKOK_LANDMARKS)
            dest = random.choice([l for l in BANGKOK_LANDMARKS if l["name"] != origin["name"]])
            lat = origin["lat"] + random.uniform(-0.003, 0.003)
            lon = origin["lon"] + random.uniform(-0.003, 0.003)
            
            LIVE_FLEET.append({
                "id": f"bkk_taxi_{i:03d}_{random.randint(100,999)}",
                "origin_name": origin["name"],
                "dest_name": dest["name"],
                "lat": lat,
                "lon": lon,
                "dest_lat": dest["lat"] + random.uniform(-0.003, 0.003),
                "dest_lon": dest["lon"] + random.uniform(-0.003, 0.003),
                "route": [],
                "route_idx": 0,
                "speed": random.randint(20, 60),
                "vacant": random.choice([0, 1])
            })
            
    loop_count = 0
    while True:
        try:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows_to_insert = []
            
            for v in LIVE_FLEET:
                # If no route or finished route, fetch a new route to a random Bangkok landmark
                if not v.get("route") or v["route_idx"] >= len(v["route"]) - 1:
                    new_dest = random.choice([l for l in BANGKOK_LANDMARKS if l["name"] != v.get("dest_name")])
                    v["origin_name"] = v.get("dest_name", "Bangkok")
                    v["dest_name"] = new_dest["name"]
                    v["dest_lat"] = new_dest["lat"] + random.uniform(-0.003, 0.003)
                    v["dest_lon"] = new_dest["lon"] + random.uniform(-0.003, 0.003)
                    
                    coords = await fetch_osrm_route(v["lon"], v["lat"], v["dest_lon"], v["dest_lat"])
                    if coords:
                        v["route"] = coords
                        v["route_idx"] = 0
                        v["vacant"] = random.choice([0, 1])
                        v["speed"] = random.randint(25, 75)
                    else:
                        # Fallback small movement towards destination
                        d_lat = (v["dest_lat"] - v["lat"]) * 0.05
                        d_lon = (v["dest_lon"] - v["lon"]) * 0.05
                        v["lat"] += d_lat + random.uniform(-0.0005, 0.0005)
                        v["lon"] += d_lon + random.uniform(-0.0005, 0.0005)
                
                # Advance along route
                if v.get("route") and v["route_idx"] < len(v["route"]) - 1:
                    # Advance points based on speed and interval
                    step = max(1, int(v["speed"] * (interval / 5.0) / 10))
                    v["route_idx"] = min(len(v["route"]) - 1, v["route_idx"] + step)
                    next_point = v["route"][v["route_idx"]]
                    v["lon"], v["lat"] = next_point[0], next_point[1]
                
                # Keep within Bangkok metropolitan bounding box
                v["lat"] = max(13.4, min(14.3, v["lat"]))
                v["lon"] = max(100.2, min(101.0, v["lon"]))

                # Realistic traffic speed variations
                v["speed"] = max(5, min(90, v["speed"] + random.randint(-5, 5)))
                
                rows_to_insert.append([
                    v["id"], 1, v["lat"], v["lon"], now_str, v["speed"], v["vacant"], 1, now_str, "live_stream"
                ])
                
            client.insert(
                'taxi.raw_gps_pings', 
                rows_to_insert, 
                column_names=['vehicle_id', 'gps_valid', 'lat', 'lon', 'timestamp', 'speed', 'passenger_lamp', 'engine_acc', '_loaded_at', '_source_file']
            )
            logger.info(f"Live stream injected {len(rows_to_insert)} rows across Bangkok landmarks (interval={interval}s)")
            
            # Automatically trigger dbt run every ~20 seconds to update Grafana
            loop_count += interval
            if loop_count >= 20:
                loop_count = 0
                logger.info("Triggering background dbt run to update Grafana...")
                asyncio.create_task(run_dbt_background())
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Live stream error: {e}")
            
        await asyncio.sleep(interval)

class StreamStartRequest(BaseModel):
    interval: int = 5

@app.post("/api/stream/start")
async def start_stream(req: StreamStartRequest):
    global LIVE_TASK
    if LIVE_TASK is None or LIVE_TASK.done():
        LIVE_TASK = asyncio.create_task(live_stream_worker(req.interval))
        return {"status": "success", "message": f"Live stream started ({req.interval}s)"}
    return {"status": "success", "message": "Live stream already running"}

@app.post("/api/stream/stop")
async def stop_stream():
    global LIVE_TASK
    if LIVE_TASK and not LIVE_TASK.done():
        LIVE_TASK.cancel()
        LIVE_TASK = None
        return {"status": "success", "message": "Live stream stopped"}
    return {"status": "success", "message": "Live stream not running"}

@app.get("/api/stream/status")
async def stream_status():
    global LIVE_TASK
    is_running = LIVE_TASK is not None and not LIVE_TASK.done()
    return {"status": "success", "is_running": is_running}

@app.post("/api/reset")
async def reset_database() -> dict[str, Any]:
    """Truncate ClickHouse tables and clear sample directory."""
    settings = get_settings()
    cleared_tables = []

    try:
        client = get_clickhouse_client()
        tables = [
            "raw_gps_pings",
            "stg_gps_pings",
            "int_trip_segments",
            "int_taxi_sessions",
            "fact_trips",
            "fact_hourly_metrics",
            "dim_taxi",
            "dim_time",
        ]
        for tbl in tables:
            try:
                client.command(f"TRUNCATE TABLE IF EXISTS {tbl}")
                cleared_tables.append(tbl)
            except Exception:
                pass
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ClickHouse truncate failed: {exc}")

    # Remove local sample files
    sample_dir = settings.sample_dir
    removed_files = 0
    if sample_dir.exists():
        for f in sample_dir.glob("*.csv"):
            f.unlink()
            removed_files += 1

    return {
        "status": "success",
        "message": f"Truncated {len(cleared_tables)} tables and removed {removed_files} mock files",
        "cleared_tables": cleared_tables,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.ui.app:app", host="0.0.0.0", port=5000, reload=True)
