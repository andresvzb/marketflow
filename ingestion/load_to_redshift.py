"""
Load bronze data from S3 parquet into Redshift.

Creates the bronze schema and raw_ohlcv table if they don't exist,
then loads data directly from the yfinance extractor.
"""

import os
import time
from datetime import date, timedelta

import redshift_connector
from dotenv import load_dotenv

from ingestion.yfinance_extractor import fetch_ohlcv

load_dotenv()

_CONNECT_PARAMS = {
    "port": 5439,
    "database": "dev",
    "ssl": True,
    "sslmode": "require",
}


def get_connection():
    params = {
        **_CONNECT_PARAMS,
        "host": os.environ["REDSHIFT_HOST"],
        "user": os.environ["REDSHIFT_USER"],
        "password": os.environ["REDSHIFT_PASSWORD"],
    }
    # Redshift Serverless can take a moment to resume from pause — retry up to 3 times
    for attempt in range(3):
        try:
            return redshift_connector.connect(**params)
        except redshift_connector.error.InterfaceError:
            if attempt == 2:
                raise
            print(f"  Redshift not ready (attempt {attempt + 1}/3), retrying in 10s...")
            time.sleep(10)


def setup_bronze_schema(cursor):
    cursor.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.raw_ohlcv (
            ticker          VARCHAR(20),
            "date"          DATE,
            "open"          DECIMAL(18, 4),
            high            DECIMAL(18, 4),
            low             DECIMAL(18, 4),
            "close"         DECIMAL(18, 4),
            adjusted_close  DECIMAL(18, 4),
            volume          BIGINT,
            loaded_at       TIMESTAMP DEFAULT GETDATE()
        )
    """)
    print("  Bronze schema and raw_ohlcv table ready.")


def load_ohlcv(cursor, tickers: list[str], start: date, end: date):
    df = fetch_ohlcv(tickers, start, end)
    print(f"  Fetched {len(df):,} rows from yfinance.")

    # Delete existing rows for the date range to avoid duplicates
    cursor.execute(
        "DELETE FROM bronze.raw_ohlcv WHERE date >= %s AND date < %s",
        (start.isoformat(), end.isoformat()),
    )

    # Batch insert
    rows = [
        (
            row.ticker,
            row.date.date() if hasattr(row.date, "date") else row.date,
            float(row.open) if row.open is not None else None,
            float(row.high) if row.high is not None else None,
            float(row.low) if row.low is not None else None,
            float(row.close) if row.close is not None else None,
            float(row.adjusted_close) if row.adjusted_close is not None else None,
            int(row.volume) if row.volume is not None else None,
        )
        for row in df.itertuples()
    ]

    sql = """INSERT INTO bronze.raw_ohlcv
             (ticker, "date", "open", high, low, "close", adjusted_close, volume)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
    batch_size = 500
    for i in range(0, len(rows), batch_size):
        cursor.executemany(sql, rows[i : i + batch_size])
    print(f"  Inserted {len(rows):,} rows into bronze.raw_ohlcv.")


def run(
    tickers: list[str] | None = None,
    days: int = 365,
):
    tickers = tickers or [
        # Technology
        "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMD", "ORCL", "CRM", "ADBE", "INTC",
        # Financials
        "JPM", "BAC", "GS", "MS", "WFC", "V", "MA", "BLK",
        # Healthcare
        "JNJ", "UNH", "PFE", "ABBV", "LLY", "MRK", "ABT",
        # Energy
        "XOM", "CVX", "COP", "SLB", "EOG",
        # Consumer Discretionary
        "HD", "MCD", "SBUX", "NKE", "AMZN",
        # Consumer Staples
        "WMT", "KO", "PEP", "PG", "COST",
        # Industrials
        "CAT", "HON", "BA", "GE", "UPS",
        # Utilities & Real Estate
        "NEE", "DUK", "AMT", "PLD", "SPG",
    ]
    end = date.today()
    start = end - timedelta(days=days)

    print(f"Connecting to Redshift...")
    conn = get_connection()
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        print("Setting up bronze schema...")
        setup_bronze_schema(cursor)

        print(f"Loading OHLCV data: {len(tickers)} tickers | {start} → {end}")
        load_ohlcv(cursor, tickers, start, end)

        conn.commit()
        print("Done.")
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    run()
