"""
dbt tools — Claude calls these to scaffold dbt models.

Instead of running dbt itself, these tools generate the SQL and YAML files
that make up a dbt project. Claude decides what models are needed based on
the ingested data, then writes them to disk.
"""

import os
from pathlib import Path
from typing import Any

DBT_DIR = Path(__file__).parent.parent.parent / "dbt"

DBT_TOOLS = [
    {
        "name": "scaffold_dbt_source",
        "description": (
            "Create a dbt sources.yml file declaring a raw table in the bronze layer. "
            "This tells dbt where the raw data lives so staging models can reference it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source_name": {
                    "type": "string",
                    "description": "dbt source name, e.g. 'bronze_stocks'",
                },
                "schema": {
                    "type": "string",
                    "description": "Redshift schema where the raw table lives.",
                },
                "table_name": {
                    "type": "string",
                    "description": "Raw table name, e.g. 'raw_ohlcv'",
                },
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Column names to document.",
                },
            },
            "required": ["source_name", "schema", "table_name", "columns"],
        },
    },
    {
        "name": "scaffold_dbt_model",
        "description": (
            "Generate a dbt SQL model file and its schema.yml. "
            "Use this to create staging, intermediate, or mart models."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "layer": {
                    "type": "string",
                    "enum": ["staging", "intermediate", "marts"],
                    "description": "Which dbt layer this model belongs to.",
                },
                "model_name": {
                    "type": "string",
                    "description": "Model name, e.g. 'stg_stocks__ohlcv'",
                },
                "sql": {
                    "type": "string",
                    "description": "The SELECT SQL for this model.",
                },
                "description": {
                    "type": "string",
                    "description": "What this model represents.",
                },
                "columns": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["name", "description"],
                    },
                    "description": "Column documentation.",
                },
            },
            "required": ["layer", "model_name", "sql", "description", "columns"],
        },
    },
]


def _scaffold_dbt_source(
    source_name: str, schema: str, table_name: str, columns: list[str]
) -> str:
    col_lines = "\n".join(f"        - name: {c}" for c in columns)
    content = f"""version: 2

sources:
  - name: {source_name}
    schema: {schema}
    tables:
      - name: {table_name}
        columns:
{col_lines}
"""
    out = DBT_DIR / "models" / "staging" / f"_{source_name}.yml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content)
    return f"Written: {out.relative_to(DBT_DIR.parent)}"


def _scaffold_dbt_model(
    layer: str,
    model_name: str,
    sql: str,
    description: str,
    columns: list[dict],
) -> str:
    # Write the SQL file
    sql_path = DBT_DIR / "models" / layer / f"{model_name}.sql"
    sql_path.parent.mkdir(parents=True, exist_ok=True)
    sql_path.write_text(sql + "\n")

    # Write the schema YAML
    col_lines = "\n".join(
        f"      - name: {c['name']}\n        description: \"{c['description']}\""
        for c in columns
    )
    schema_content = f"""version: 2

models:
  - name: {model_name}
    description: "{description}"
    columns:
{col_lines}
"""
    schema_path = DBT_DIR / "models" / layer / f"_{model_name}.yml"
    schema_path.write_text(schema_content)

    return f"Written: {sql_path.relative_to(DBT_DIR.parent)}, {schema_path.relative_to(DBT_DIR.parent)}"


def dispatch_dbt_tool(name: str, args: dict[str, Any]) -> Any:
    if name == "scaffold_dbt_source":
        return _scaffold_dbt_source(**args)
    if name == "scaffold_dbt_model":
        return _scaffold_dbt_model(**args)
    return f"Unknown dbt tool: {name}"
