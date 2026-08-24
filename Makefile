.PHONY: up down restart reset logs setup demo sample-data ingest validate load dbt-deps dbt-run dbt-test dbt-docs dbt-debug test test-unit test-integration lint format ch-client row-count help

# =============================================================================
# Bangkok Taxi Data Platform — Makefile
# =============================================================================
# All operations run in Docker so no local Python or dbt installation is required.
# =============================================================================

# -- Infrastructure --

up:
	docker compose up -d
	@echo "✅ All services started"
	@echo "   Airflow:    http://localhost:8080 (admin / admin)"
	@echo "   MinIO:      http://localhost:9001 (minio_admin / minio_secret_123)"
	@echo "   Grafana:    http://localhost:3000 (admin / grafana_secret)"
	@echo "   ClickHouse: http://localhost:8123"

down:
	docker compose down

restart:
	docker compose down && docker compose up -d

logs:
	docker compose logs -f $(SERVICE)

# -- Setup & Full Reset --

setup: up
	@echo "⏳ Waiting for ClickHouse to be healthy..."
	@docker compose exec clickhouse clickhouse-client --password clickhouse_secret \
		--queries-file /docker-entrypoint-initdb.d/setup_clickhouse.sql
	@echo "✅ ClickHouse schema initialized"

reset:
	@echo "⚠️ Resetting all volumes and containers..."
	docker compose down -v --remove-orphans
	docker compose up -d
	@echo "⏳ Waiting for services..."
	sleep 5
	@docker compose exec clickhouse clickhouse-client --password clickhouse_secret \
		--queries-file /docker-entrypoint-initdb.d/setup_clickhouse.sql
	@echo "✅ Platform completely reset & re-initialized fresh"

# -- One-Command Demo (Mock Data Init) --

demo: setup
	@echo ""
	@echo "================================================================="
	@echo "🚕 Step 1/4: Generating realistic sample Bangkok taxi GPS data..."
	@echo "================================================================="
	docker compose exec airflow-scheduler python scripts/generate_sample_data.py --taxis 50 --days 3
	@echo ""
	@echo "================================================================="
	@echo "⚡ Step 2/4: Validating and loading data into ClickHouse..."
	@echo "================================================================="
	docker compose exec airflow-scheduler python -m src.loaders.clickhouse_loader --file data/sample/probe_2018-02-01.csv
	@echo ""
	@echo "================================================================="
	@echo "🔄 Step 3/4: Running dbt transformations (staging → int → marts)..."
	@echo "================================================================="
	docker compose exec -w /opt/dbt_taxi airflow-scheduler dbt deps
	docker compose exec -w /opt/dbt_taxi airflow-scheduler dbt run
	@echo ""
	@echo "================================================================="
	@echo "🧪 Step 4/4: Running dbt data quality tests..."
	@echo "================================================================="
	docker compose exec -w /opt/dbt_taxi airflow-scheduler dbt test
	@echo ""
	@echo "================================================================="
	@echo "🎉 DEMO READY!"
	@echo "   Open Grafana: http://localhost:3000 (admin / grafana_secret)"
	@echo "   Dashboards:   Bangkok Taxi -> Fleet Overview, Hotspots, Trips"
	@echo "================================================================="

# -- Data Pipeline --

sample-data:
	docker compose exec airflow-scheduler python scripts/generate_sample_data.py --taxis $(or $(TAXIS),50) --days $(or $(DAYS),3)
	@echo "✅ Sample data generated in data/sample/"

ingest:
	@echo "🚕 Ingesting month: $(MONTH)"
	docker compose exec airflow-scheduler python -m src.ingestion.downloader --month $(MONTH)
	docker compose exec airflow-scheduler python -m src.ingestion.extractor --month $(MONTH)
	docker compose exec airflow-scheduler python -m src.ingestion.uploader --month $(MONTH)

validate:
	docker compose exec airflow-scheduler python -m src.validation.validators --month $(MONTH)

load:
	docker compose exec airflow-scheduler python -m src.loaders.clickhouse_loader --month $(MONTH)

# -- dbt --

dbt-deps:
	docker compose exec -w /opt/dbt_taxi airflow-scheduler dbt deps

dbt-run:
	docker compose exec -w /opt/dbt_taxi airflow-scheduler dbt run

dbt-test:
	docker compose exec -w /opt/dbt_taxi airflow-scheduler dbt test

dbt-docs:
	docker compose exec -w /opt/dbt_taxi airflow-scheduler dbt docs generate
	@echo "Docs generated in /opt/dbt_taxi/target/"

dbt-debug:
	docker compose exec -w /opt/dbt_taxi airflow-scheduler dbt debug

# -- Testing --

test:
	docker compose exec airflow-scheduler pytest tests/ -v --tb=short

test-unit:
	docker compose exec airflow-scheduler pytest tests/unit/ -v --tb=short

test-integration:
	docker compose exec airflow-scheduler pytest tests/integration/ -v --tb=short

# -- Code Quality --

lint:
	docker compose exec airflow-scheduler ruff check src/ tests/ airflow/
	docker compose exec airflow-scheduler ruff format --check src/ tests/ airflow/

format:
	docker compose exec airflow-scheduler ruff check --fix src/ tests/ airflow/
	docker compose exec airflow-scheduler ruff format src/ tests/ airflow/

# -- Utilities --

ch-client:
	docker compose exec clickhouse clickhouse-client --password clickhouse_secret -d taxi

row-count:
	docker compose exec clickhouse clickhouse-client --password clickhouse_secret -d taxi \
		--query "SELECT 'raw_gps_pings' AS table, count() AS rows FROM raw_gps_pings UNION ALL SELECT 'stg_gps_pings', count() FROM stg_gps_pings UNION ALL SELECT 'fact_trips', count() FROM fact_trips UNION ALL SELECT 'fact_hourly_metrics', count() FROM fact_hourly_metrics"

help:
	@echo "Bangkok Taxi Data Engineering Platform Commands:"
	@echo "  make up          - Start all Docker services"
	@echo "  make down        - Stop all Docker services"
	@echo "  make setup       - Initialize ClickHouse schemas"
	@echo "  make demo        - One-command setup: Generate mock data -> Validate -> Load -> dbt -> Test"
	@echo "  make reset       - Wipe all volumes and start completely fresh"
	@echo "  make sample-data - Generate mock GPS probe data"
	@echo "  make dbt-run     - Run dbt transformations"
	@echo "  make dbt-test    - Run dbt tests"
	@echo "  make test        - Run pytest suite inside container"
	@echo "  make row-count   - Check row count across pipeline tables in ClickHouse"
	@echo "  make ch-client   - Open interactive ClickHouse CLI"
