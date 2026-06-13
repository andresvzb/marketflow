"""
Airflow tools — Claude calls these to generate DAG files.

We generate Python DAG code as a string and write it to airflow/dags/.
Claude decides the schedule, tasks, and dependencies based on the pipeline.
"""

from pathlib import Path
from typing import Any

DAGS_DIR = Path(__file__).parent.parent.parent / "airflow" / "dags"

AIRFLOW_TOOLS = [
    {
        "name": "generate_airflow_dag",
        "description": (
            "Generate a Python Airflow DAG file for a data pipeline. "
            "The DAG will be written to airflow/dags/. "
            "Use this after setting up S3 and dbt models to wire the full pipeline."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dag_id": {
                    "type": "string",
                    "description": "Unique DAG ID, e.g. 'marketflow_stocks_daily'",
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable description of what this DAG does.",
                },
                "schedule": {
                    "type": "string",
                    "description": "Cron expression or @daily / @hourly preset.",
                    "default": "@daily",
                },
                "tasks": {
                    "type": "array",
                    "description": "Ordered list of tasks in this DAG.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "string"},
                            "type": {
                                "type": "string",
                                "enum": ["python", "bash", "dbt_run"],
                                "description": "Task type.",
                            },
                            "command_or_callable": {
                                "type": "string",
                                "description": (
                                    "For bash: shell command string. "
                                    "For dbt_run: dbt model selector (e.g. 'stg_stocks+'). "
                                    "For python: name of the Python callable to import."
                                ),
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "task_ids this task depends on.",
                            },
                        },
                        "required": ["task_id", "type", "command_or_callable"],
                    },
                },
            },
            "required": ["dag_id", "description", "tasks"],
        },
    },
]


def _generate_airflow_dag(
    dag_id: str,
    description: str,
    tasks: list[dict],
    schedule: str = "@daily",
) -> str:
    DAGS_DIR.mkdir(parents=True, exist_ok=True)

    task_lines = []
    dep_lines = []

    for t in tasks:
        tid = t["task_id"]
        cmd = t["command_or_callable"]
        ttype = t["type"]

        if ttype == "bash":
            task_lines.append(
                f'    {tid} = BashOperator(task_id="{tid}", bash_command={cmd!r})'
            )
        elif ttype == "dbt_run":
            task_lines.append(
                f'    {tid} = BashOperator(task_id="{tid}", '
                f'bash_command="dbt run --select {cmd} --profiles-dir /opt/airflow/dbt")'
            )
        elif ttype == "python":
            task_lines.append(
                f'    {tid} = PythonOperator(task_id="{tid}", python_callable={cmd})'
            )

        for dep in t.get("depends_on", []):
            dep_lines.append(f"    {dep} >> {tid}")

    task_block = "\n".join(task_lines)
    dep_block = "\n".join(dep_lines) if dep_lines else "    pass  # no dependencies"

    dag_code = f'''"""
{description}
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

default_args = {{
    "owner": "marketflow",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}}

with DAG(
    dag_id="{dag_id}",
    description="""{description}""",
    schedule="{schedule}",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["marketflow"],
) as dag:

{task_block}

    # Dependencies
{dep_block}
'''

    out = DAGS_DIR / f"{dag_id}.py"
    out.write_text(dag_code)
    return f"Written: {out.relative_to(DAGS_DIR.parent.parent)}"


def dispatch_airflow_tool(name: str, args: dict[str, Any]) -> Any:
    if name == "generate_airflow_dag":
        return _generate_airflow_dag(**args)
    return f"Unknown Airflow tool: {name}"
