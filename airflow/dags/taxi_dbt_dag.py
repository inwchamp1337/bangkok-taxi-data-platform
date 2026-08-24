"""
Bangkok Taxi dbt Transformation DAG.

Runs dbt models in layer order:
  1. Install dependencies (dbt deps)
  2. Run staging models
  3. Run intermediate models
  4. Run mart models
  5. Run dbt tests

Can be triggered by:
  - The taxi_ingestion DAG (after load completes)
  - Manual trigger

Schedule: None (triggered by upstream DAG)
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.decorators import dag
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

DBT_PROJECT_DIR = "/opt/dbt_taxi"
DBT_CMD = f"cd {DBT_PROJECT_DIR} && dbt"


@dag(
    dag_id="taxi_dbt_transform",
    default_args=default_args,
    description="Run dbt transformations: staging → intermediate → marts",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["taxi", "dbt", "transform"],
    doc_md=__doc__,
)
def taxi_dbt_dag():
    """dbt transformation DAG."""

    dbt_deps = BashOperator(
        task_id="dbt_deps",
        bash_command=f"{DBT_CMD} deps",
    )

    dbt_run_staging = BashOperator(
        task_id="dbt_run_staging",
        bash_command=f"{DBT_CMD} run --select staging",
    )

    dbt_run_intermediate = BashOperator(
        task_id="dbt_run_intermediate",
        bash_command=f"{DBT_CMD} run --select intermediate",
    )

    dbt_run_marts = BashOperator(
        task_id="dbt_run_marts",
        bash_command=f"{DBT_CMD} run --select marts",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"{DBT_CMD} test",
    )

    dbt_docs = BashOperator(
        task_id="dbt_docs_generate",
        bash_command=f"{DBT_CMD} docs generate",
    )

    # Linear dependency chain
    dbt_deps >> dbt_run_staging >> dbt_run_intermediate >> dbt_run_marts >> dbt_test >> dbt_docs


# Instantiate the DAG
taxi_dbt_dag()
