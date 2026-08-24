# 🚕 Bangkok Taxi Data Engineering Platform

A production-grade **ultra-lean ELT data platform** that processes **100M+ GPS probe records** from Bangkok taxis. This project demonstrates modern data engineering practices: direct S3-to-OLAP ingestion, data quality validation via dbt, dimensional modeling, and interactive pipeline simulation—all running on a lightweight 4-container stack.

Built with real-world data from the [iTIC Foundation](https://www.iticfoundation.org/) (CC-BY 4.0).

---

## 🏗️ Architecture (The Ultra-Lean ELT Stack)

```mermaid
graph LR
    subgraph Control Plane
        UI["FastAPI Control Panel\n(Simulation & Orchestration)"]
    end

    subgraph Data Lake
        MINIO[("MinIO\n(Raw S3 Storage)")]
    end

    subgraph Data Warehouse (ClickHouse)
        CH_RAW[("raw_gps_pings\n(ReplacingMergeTree)")]
        DBT["dbt\n(Data Quality & Transforms)"]
    end

    subgraph Analytics
        GF["Grafana\n3 Dashboards"]
    end

    UI -->|1. Uploads Mock/Real Data| MINIO
    UI -->|2. Triggers S3 Load| CH_RAW
    MINIO -.->|s3() direct read| CH_RAW
    UI -->|3. Triggers Transform| DBT
    CH_RAW --> DBT
    DBT --> GF
```

---

## 📊 Dataset

| Property | Value |
|----------|-------|
| **Source** | [iTIC Open Data Archives](https://itic.longdo.com/opendata/probe-data/) |
| **License** | CC-BY 4.0 |
| **Coverage** | Thailand (focus: Bangkok metro) |
| **Period** | Jan 2017 — Dec 2025 |
| **Volume** | ~1-2.5 GB compressed per month |
| **Records** | 96M–247M per analysis period |
| **Frequency** | Every 1 min (engine on), 3 min (engine off) |

**Schema (7 fields, no header):**
```
VehicleID,gpsvalid,lat,lon,timestamp,speed,passenger_lamp,engine_acc
```

| Field | Type | Description |
|-------|------|-------------|
| `VehicleID` | string | Hashed unique vehicle identifier |
| `gpsvalid` | 0/1 | GPS fix quality (1 = enough satellites) |
| `lat` | float | Latitude (WGS84, 5 decimal places) |
| `lon` | float | Longitude (WGS84, 5 decimal places) |
| `timestamp` | datetime | GPS time (UTC+7 Bangkok) |
| `speed` | int | Speed in km/h |
| `passenger_lamp` | 0/1 | **1 = vacant (light ON)**, 0 = occupied |
| `engine_acc` | 0/1 | Engine switch: 1 = running, 0 = off |

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- ~15 GB free disk space (for 1 month of full data)

### 1. Clone & Configure
```bash
git clone https://github.com/your-username/bangkok-taxi-data-platform.git
cd bangkok-taxi-data-platform
cp .env.example .env
```

### 2. Start Infrastructure
```bash
docker compose up -d
```

This starts the ultra-lean stack (4 containers only):
| Service | URL | Role / Credentials |
|---------|-----|--------------------|
| **Control Panel UI** | **http://127.0.0.1:5000** | **Interactive Mock Simulator & Pipeline Control** |
| **Grafana** | http://127.0.0.1:3000 | Dashboards (`admin` / `grafana_secret`) |
| **MinIO** | http://127.0.0.1:9001 | S3 Data Lake (`minio_admin` / `minio_secret_123`) |
| **ClickHouse** | http://127.0.0.1:8123 | OLAP Database (Native port: 9009) |

---

### 3. One-Click Interactive Demo
Open **[http://127.0.0.1:5000](http://127.0.0.1:5000)** in your browser:
- Select from 5 traffic scenarios:
  - 🚦 **Normal Weekday**: Regular morning/evening rush hour peaks
  - 🌧️ **Monsoon Rain Gridlock**: Average speed drops to 8-15 km/h, 90% occupancy
  - ✈️ **Airport Express Surge**: High-speed highway trips to BKK & DMK
  - 🏮 **Midnight Bangkok**: Late-night nightlife surge in Thonglor, Sukhumvit, RCA
  - ⚠️ **Chaos Engineering Mode**: Injects 5% corrupted records to test dbt validation rules
- Or click **⚡ Run ALL Scenarios** to simulate and load all scenarios sequentially.
- The pipeline will automatically generate data, push to MinIO, ingest into ClickHouse via native `s3()`, and run all dbt models and tests.

---

### 4. View Analytics Dashboards
Open **[http://127.0.0.1:3000](http://127.0.0.1:3000)** ➡️ Dashboards ➡️ Bangkok Taxi folder:
1. **🚕 Fleet Overview**: Active taxis count, empty ratio gauge, speed trends
2. **📍 Hotspot Analysis**: Top pickup/dropoff geohashes, peak demand hours, OD matrix
3. **🚖 Trip Analytics**: Trip duration/distance distributions, average speeds

---

## 🧱 Project Structure

```
bangkok-taxi-data-platform/
├── docker-compose.yml              # Ultra-lean 4-container stack
├── Makefile                        # Developer shortcuts
│
├── src/                            # Python application code
│   ├── config/settings.py          # Pydantic centralized config
│   ├── ingestion/                  # MinIO uploader
│   ├── loaders/                    # ClickHouse ELT loader via s3()
│   └── ui/                         # FastAPI Control Panel
│
├── dbt_taxi/                       # dbt transformation project
│   ├── models/staging/             # stg_gps_pings (clean + filter)
│   ├── models/intermediate/        # Trip detection, sessionization
│   ├── models/marts/               # fact_trips, fact_hourly_metrics
│   └── macros/                     # haversine, geohash
│
├── infrastructure/                 # Docker configs + Grafana provisioning
├── scripts/                        # Mock data generator + DDL
└── tests/                          # Integration tests
```

---

## ⚡ Key Design Decisions (The ELT Migration)

| Decision | Rationale |
|----------|-----------|
| **ELT over ETL** | By dropping Python-based validation (Pandera/Polars) and loading directly from S3 to ClickHouse via the `s3()` table function, ingestion bottlenecks were entirely eliminated. |
| **ReplacingMergeTree** | The `raw_gps_pings` table uses `ReplacingMergeTree(_loaded_at)` to guarantee **idempotency**. Duplicate files loaded by mistake are deduplicated automatically at the database level. |
| **No Airflow (Ultra-Lean)** | Airflow was completely purged to save massive RAM/CPU overhead. Orchestration is now handled entirely by the lightweight FastAPI Control Panel. |
| **dbt for Data Quality** | Data validation (bounding boxes, speed limits, schema checks) is now done inside ClickHouse using dbt, utilizing database compute rather than python memory. |
| **ClickHouse over PostgreSQL** | 100M+ rows with time-series queries — ClickHouse is 10-100x faster for OLAP. |
| **Geohash for spatial analysis** | ~1.2km blocks (precision 6) — good balance of granularity vs cardinality. |

---

## 📄 License

This project is licensed under the MIT License.

**Data attribution**: GPS probe data provided by [iTIC Foundation](https://www.iticfoundation.org/) under [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/).
