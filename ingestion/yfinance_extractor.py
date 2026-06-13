"""
Ingestion: yfinance → S3 bronze layer

Pulls daily OHLCV data for a list of tickers and lands it as parquet
in s3://marketflow-bronze-dev/stocks/ohlcv/date=YYYY-MM-DD/
"""

import os
from datetime import date, timedelta
from io import BytesIO

import boto3
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

BUCKET = os.getenv("S3_BUCKET_PREFIX", "marketflow") + "-bronze-" + os.getenv("ENVIRONMENT", "dev")

DEFAULT_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "BAC", "GS"]


def fetch_ohlcv(tickers: list[str], start: date, end: date) -> pd.DataFrame:
    raw = yf.download(
        tickers=tickers,
        start=start.isoformat(),
        end=end.isoformat(),
        auto_adjust=False,
        progress=False,
        group_by="ticker",
    )

    frames = []
    for ticker in tickers:
        try:
            df = raw[ticker].copy() if len(tickers) > 1 else raw.copy()
            df = df.dropna(subset=["Close"])
            df["ticker"] = ticker
            df = df.reset_index().rename(columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Adj Close": "adjusted_close",
                "Volume": "volume",
            })
            df = df[["ticker", "date", "open", "high", "low", "close", "adjusted_close", "volume"]]
            frames.append(df)
        except KeyError:
            print(f"  Warning: no data for {ticker}")

    if not frames:
        raise ValueError("No data returned for any ticker")

    return pd.concat(frames, ignore_index=True)


def upload_to_bronze(df: pd.DataFrame, partition_date: date) -> str:
    s3 = boto3.client("s3")
    key = f"stocks/ohlcv/date={partition_date.isoformat()}/data.parquet"

    buffer = BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    buffer.seek(0)

    s3.put_object(Bucket=BUCKET, Key=key, Body=buffer.getvalue())
    return f"s3://{BUCKET}/{key}"


def run(
    tickers: list[str] | None = None,
    start: date | None = None,
    end: date | None = None,
) -> str:
    tickers = tickers or DEFAULT_TICKERS
    end = end or date.today()
    start = start or (end - timedelta(days=365))

    print(f"Fetching OHLCV: {len(tickers)} tickers | {start} → {end}")
    df = fetch_ohlcv(tickers, start, end)
    print(f"  Rows fetched: {len(df):,}")

    partition_date = end - timedelta(days=1)
    s3_path = upload_to_bronze(df, partition_date)
    print(f"  Uploaded: {s3_path}")
    return s3_path


if __name__ == "__main__":
    run()
