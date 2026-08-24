.PHONY: up down restart logs ingest dbt-run dbt-test dbt-docs sample-data test lint setup

# =============================================================================
# Bangkok Taxi Data Platform — Makefile
# =============================================================================

# -- Infrastructure --

up:
	docker compose up -d
	@echo "✅ All services started"
	@echo "   Airflow:    http://localhost:8080"
	@echo "   MinIO:      http://localhost:9001"
	@echo "   Grafana:    http://localhost:3000"
	@echo "   ClickHouse: http://localhost:8123"

down:
	docker compose down

restart:
	docker compose down && docker compose up -d

logs:
	docker compose logs -f $(SERVICE)

# -- Setup --

setup: up
	@echo "⏳ Waiting for services to be healthy..."
	sleep 10
	docker compose exec clickhouse clickhouse-client --password clickhouse_secret \
		--queries-file /docker-entrypoint-initdb.d/setup_clickhouse.sql
	@echo "✅ ClickHouse schema initialized"

# -- Data Pipeline --

sample-data:
	python scripts/generate_sample_data.py
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

dbt-run:
	docker compose exec airflow-scheduler bash -c "cd /opt/dbt_taxi && dbt run"

dbt-test:
	docker compose exec airflow-scheduler bash -c "cd /opt/dbt_taxi && dbt test"

dbt-docs:
	docker compose exec airflow-scheduler bash -c "cd /opt/dbt_taxi && dbt docs generate && dbt docs serve --port 8081"

dbt-debug:
	docker compose exec airflow-scheduler bash -c "cd /opt/dbt_taxi && dbt debug"

# -- Testing --

test:
	pytest tests/ -v --tb=short

test-unit:
	pytest tests/unit/ -v --tb=short

test-integration:
	pytest tests/integration/ -v --tb=short

# -- Code Quality --

lint:
	ruff check src/ tests/ airflow/
	ruff format --check src/ tests/ airflow/

format:
	ruff check --fix src/ tests/ airflow/
	ruff format src/ tests/ airflow/

# -- Utilities --

ch-client:
	docker compose exec clickhouse clickhouse-client --password clickhouse_secret -d taxi

row-count:
	docker compose exec clickhouse clickhouse-client --password clickhouse_secret \
		--query "SELECT count() as total_rows FROM taxi.raw_gps_pings"
