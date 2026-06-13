"""
MarketFlow Agent — Claude-powered orchestrator.

The agent receives a natural-language command (e.g. "provision S3 buckets for dev")
and uses tool use to plan and execute the right AWS / dbt / Airflow actions.

How tool use works:
  1. We send Claude a message + a list of tool definitions.
  2. Claude replies with a `tool_use` content block naming the tool + args it wants to call.
  3. We execute the real function locally and send back a `tool_result` block.
  4. Repeat until Claude returns a plain `text` response — that's the final answer.
"""

import json
from typing import Any

import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from agent.tools.aws_tools import AWS_TOOLS, dispatch_aws_tool
from agent.tools.dbt_tools import DBT_TOOLS, dispatch_dbt_tool
from agent.tools.airflow_tools import AIRFLOW_TOOLS, dispatch_airflow_tool

console = Console()

MODEL = "claude-opus-4-8"

ALL_TOOLS = AWS_TOOLS + DBT_TOOLS + AIRFLOW_TOOLS

SYSTEM_PROMPT = """You are MarketFlow's infrastructure and data engineering agent.

Your job is to help provision AWS infrastructure, scaffold dbt models, and create
Airflow DAGs for a financial data platform built on a medallion architecture:
  - Bronze: raw data landed in S3 (parquet)
  - Silver: cleaned/typed tables in Redshift (via dbt staging models)
  - Gold: business-level aggregations in Redshift (via dbt mart models)

When given a task:
1. Think through what needs to happen step by step.
2. Use the available tools to carry out each step.
3. Confirm what was done and what the next logical step would be.

Always be explicit about what you're creating, why, and how it fits the architecture."""


def run_agent(user_message: str) -> str:
    """Run the agent loop for a single user command."""
    client = anthropic.Anthropic()

    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

    console.print(Panel(f"[bold cyan]User:[/bold cyan] {user_message}", expand=False))

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            messages=messages,
        )

        # Collect any tool calls from this response
        tool_results = []

        for block in response.content:
            if block.type == "thinking":
                console.print(f"[dim]Thinking... ({len(block.thinking)} chars)[/dim]")

            elif block.type == "text":
                console.print(Panel(f"[bold green]Agent:[/bold green] {block.text}", expand=False))

            elif block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input

                console.print(f"\n[bold yellow]Tool call:[/bold yellow] {tool_name}")
                console.print(
                    Syntax(json.dumps(tool_input, indent=2), "json", theme="monokai")
                )

                result = _dispatch_tool(tool_name, tool_input)

                console.print(f"[bold blue]Result:[/bold blue] {result}\n")
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": str(result)}
                )

        # If Claude called tools, append the full assistant turn + all results, then loop
        if tool_results:
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            continue

        # No tool calls — we're done
        final_text = next(
            (b.text for b in response.content if b.type == "text"), ""
        )
        return final_text


def _dispatch_tool(name: str, args: dict[str, Any]) -> Any:
    """Route a tool call to the right module."""
    if name in {t["name"] for t in AWS_TOOLS}:
        return dispatch_aws_tool(name, args)
    if name in {t["name"] for t in DBT_TOOLS}:
        return dispatch_dbt_tool(name, args)
    if name in {t["name"] for t in AIRFLOW_TOOLS}:
        return dispatch_airflow_tool(name, args)
    return f"Unknown tool: {name}"
