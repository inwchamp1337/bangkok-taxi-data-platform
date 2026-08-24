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
        return {
            "status": "success" if res.returncode == 0 else "error",
            "returncode": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
        }
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
        return {
            "status": "success" if res.returncode == 0 else "error",
            "returncode": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
        }
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

async def live_stream_worker(interval: int):
    global LIVE_FLEET
    client = get_clickhouse_client()
    base_lat, base_lon = 13.7563, 100.5018
    
    # Initialize 50 live taxis if empty
    if not LIVE_FLEET:
        for i in range(50):
            LIVE_FLEET.append({
                "id": f"live_taxi_{i:03d}_{random.randint(100,999)}",
                "lat": base_lat + random.uniform(-0.08, 0.08),
                "lon": base_lon + random.uniform(-0.08, 0.08),
                "route": [],
                "route_idx": 0,
                "speed": random.randint(10, 60),
                "vacant": random.choice([0, 1])
            })
            
    while True:
        try:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows_to_insert = []
            
            for v in LIVE_FLEET:
                # If no route or finished route, fetch a new one
                if not v.get("route") or v["route_idx"] >= len(v["route"]) - 1:
                    dest_lat = base_lat + random.uniform(-0.1, 0.1)
                    dest_lon = base_lon + random.uniform(-0.1, 0.1)
                    coords = await fetch_osrm_route(v["lon"], v["lat"], dest_lon, dest_lat)
                    if coords:
                        v["route"] = coords
                        v["route_idx"] = 0
                    else:
                        # Fallback random walk
                        v["lat"] += random.uniform(-0.001, 0.001)
                        v["lon"] += random.uniform(-0.001, 0.001)
                
                # Advance along route
                if v.get("route") and v["route_idx"] < len(v["route"]) - 1:
                    # Advance points based on speed
                    step = max(1, v["speed"] // 15)
                    v["route_idx"] = min(len(v["route"]) - 1, v["route_idx"] + step)
                    next_point = v["route"][v["route_idx"]]
                    v["lon"], v["lat"] = next_point[0], next_point[1]
                
                # Keep within bounds
                v["lat"] = max(13.4, min(14.3, v["lat"]))
                v["lon"] = max(100.2, min(101.0, v["lon"]))

                if random.random() < 0.05:
                    v["vacant"] = 1 - v["vacant"]
                    v["speed"] = random.randint(10, 80)
                
                rows_to_insert.append([
                    v["id"], 1, v["lat"], v["lon"], now_str, v["speed"], v["vacant"], 1, now_str, "live_stream"
                ])
                
            client.insert(
                'taxi.raw_gps_pings', 
                rows_to_insert, 
                column_names=['vehicle_id', 'gps_valid', 'lat', 'lon', 'timestamp', 'speed', 'passenger_lamp', 'engine_acc', '_loaded_at', '_source_file']
            )
            logger.info(f"Live stream injected {len(rows_to_insert)} rows (interval={interval}s)")
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
