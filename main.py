"""
MarketFlow CLI — talk to the agent from the terminal.

Usage:
    uv run python main.py "provision S3 buckets for the dev environment"
    uv run python main.py "scaffold dbt staging models for OHLCV stock data"
    uv run python main.py "create a daily Airflow DAG for the stocks pipeline"
"""

import sys

from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

console = Console()


def main():
    if len(sys.argv) < 2:
        console.print("[bold red]Usage:[/bold red] python main.py \"<your instruction>\"")
        console.print("\n[dim]Examples:[/dim]")
        console.print('  python main.py "provision S3 buckets for dev"')
        console.print('  python main.py "scaffold dbt models for stock OHLCV data"')
        console.print('  python main.py "create a daily ingestion DAG for yfinance"')
        sys.exit(1)

    user_message = " ".join(sys.argv[1:])

    # Import here so dotenv loads first
    from agent.agent import run_agent
    run_agent(user_message)


if __name__ == "__main__":
    main()
