"""
Load bronze data from S3 parquet into Redshift.

Creates the bronze schema and raw_ohlcv table if they don't exist,
then loads data directly from the yfinance extractor.
"""

import os
from datetime import date, timedelta

import redshift_connector
from dotenv import load_dotenv

from ingestion.yfinance_extractor import fetch_ohlcv

load_dotenv()


def get_connection():
    return redshift_connector.connect(
        host=os.environ["REDSHIFT_HOST"],
        port=5439,
        database="dev",
        user=os.environ["REDSHIFT_USER"],
        password=os.environ["REDSHIFT_PASSWORD"],
    )


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

    cursor.executemany(
        """INSERT INTO bronze.raw_ohlcv
           (ticker, "date", "open", high, low, "close", adjusted_close, volume)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        rows,
    )
    print(f"  Inserted {len(rows):,} rows into bronze.raw_ohlcv.")


def run(
    tickers: list[str] | None = None,
    days: int = 365,
):
    tickers = tickers or ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "BAC", "GS"]
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
