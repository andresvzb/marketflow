"""
Daily MarketFlow pipeline: ingest OHLCV from yfinance into the bronze S3 layer, then run dbt staging (silver) and gold mart models to produce daily returns.
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

with DAG(
    dag_id="marketflow_stocks_daily",
    description="""Daily MarketFlow pipeline: ingest OHLCV from yfinance into the bronze S3 layer, then run dbt staging (silver) and gold mart models to produce daily returns.""",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["marketflow"],
) as dag:

    ingest_yfinance_ohlcv = PythonOperator(task_id="ingest_yfinance_ohlcv", python_callable=ingest_yfinance_ohlcv)
    dbt_run_staging = BashOperator(task_id="dbt_run_staging", bash_command="dbt run --select stg_stocks__ohlcv --profiles-dir /opt/airflow/dbt")
    dbt_run_gold_returns = BashOperator(task_id="dbt_run_gold_returns", bash_command="dbt run --select mart_stocks__daily_returns --profiles-dir /opt/airflow/dbt")

    # Dependencies
    ingest_yfinance_ohlcv >> dbt_run_staging
    dbt_run_staging >> dbt_run_gold_returns
