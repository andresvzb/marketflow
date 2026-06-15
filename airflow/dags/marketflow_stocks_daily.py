"""
Daily MarketFlow pipeline:
  1. Ingest OHLCV from yfinance → Redshift bronze layer
  2. dbt staging (silver): clean and type the raw data
  3. dbt gold: daily returns, moving averages, volatility
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "marketflow",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

DBT_DIR = "/opt/airflow/dbt"


def _ingest():
    from ingestion.load_to_redshift import run
    run()


with DAG(
    dag_id="marketflow_stocks_daily",
    description="Daily OHLCV ingest → dbt silver → dbt gold",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["marketflow"],
) as dag:

    ingest = PythonOperator(
        task_id="ingest_yfinance_ohlcv",
        python_callable=_ingest,
    )

    dbt_staging = BashOperator(
        task_id="dbt_run_staging",
        bash_command=f"dbt run --select stg_stocks__ohlcv --profiles-dir {DBT_DIR} --project-dir {DBT_DIR}",
    )

    dbt_returns = BashOperator(
        task_id="dbt_run_daily_returns",
        bash_command=f"dbt run --select mart_stocks__daily_returns --profiles-dir {DBT_DIR} --project-dir {DBT_DIR}",
    )

    dbt_moving_avgs = BashOperator(
        task_id="dbt_run_moving_averages",
        bash_command=f"dbt run --select mart_stocks__moving_averages --profiles-dir {DBT_DIR} --project-dir {DBT_DIR}",
    )

    dbt_volatility = BashOperator(
        task_id="dbt_run_volatility",
        bash_command=f"dbt run --select mart_stocks__volatility --profiles-dir {DBT_DIR} --project-dir {DBT_DIR}",
    )

    ingest >> dbt_staging >> [dbt_returns, dbt_moving_avgs] >> dbt_volatility
