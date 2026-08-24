FROM apache/airflow:2.9.3-python3.11

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Install Python dependencies
COPY pyproject.toml /opt/airflow/pyproject.toml
RUN pip install --no-cache-dir \
    clickhouse-connect>=0.7.0 \
    minio>=7.2.0 \
    pandera>=0.20.0 \
    polars>=1.0.0 \
    httpx>=0.27.0 \
    pydantic-settings>=2.0.0 \
    python-dotenv>=1.0.0 \
    structlog>=24.0.0 \
    dbt-clickhouse>=1.8.0 \
    fastapi>=0.110.0 \
    uvicorn>=0.30.0 \
    pytest>=8.0.0 \
    pytest-cov>=5.0.0

# Set working directory
WORKDIR /opt/airflow
