"""
MarketFlow Dashboard — reads from Redshift gold layer and visualizes results.
Run with: uv run streamlit run dashboard/app.py
"""

import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import redshift_connector
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="MarketFlow",
    page_icon="📈",
    layout="wide",
)

# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_resource
def get_connection():
    return redshift_connector.connect(
        host=os.environ["REDSHIFT_HOST"],
        port=5439,
        database="dev",
        user=os.environ["REDSHIFT_USER"],
        password=os.environ["REDSHIFT_PASSWORD"],
        ssl=True,
        sslmode="require",
    )


def _query(sql: str) -> pd.DataFrame:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return pd.DataFrame(rows, columns=cols)


@st.cache_data(ttl=3600)
def load_returns() -> pd.DataFrame:
    return _query("""
        select ticker, trading_date, close_price,
               daily_return_pct, daily_log_return
        from bronze_gold.mart_stocks__daily_returns
        order by ticker, trading_date
    """)


@st.cache_data(ttl=3600)
def load_moving_averages() -> pd.DataFrame:
    return _query("""
        select ticker, trading_date, close_price, sma_7, sma_30, price_to_sma_30
        from bronze_gold.mart_stocks__moving_averages
        order by ticker, trading_date
    """)


@st.cache_data(ttl=3600)
def load_volatility() -> pd.DataFrame:
    return _query("""
        select ticker, trading_date,
               annualized_volatility_30d,
               annualized_volatility_7d,
               golden_cross_signal
        from bronze_gold.mart_stocks__volatility
        order by ticker, trading_date
    """)


@st.cache_data(ttl=3600)
def load_sector_performance() -> pd.DataFrame:
    return _query("""
        select sector, trading_date,
               avg_daily_return_pct,
               breadth_pct,
               ticker_count,
               best_return_pct,
               worst_return_pct
        from bronze_gold.mart_stocks__sector_performance
        order by sector, trading_date
    """)


# ── Load data ─────────────────────────────────────────────────────────────────

with st.spinner("Loading data from Redshift..."):
    returns_df = load_returns()
    ma_df = load_moving_averages()
    vol_df = load_volatility()
    sector_df = load_sector_performance()

latest_date = returns_df["trading_date"].max()
tickers = sorted(returns_df["ticker"].unique())

# ── Header ────────────────────────────────────────────────────────────────────

st.title("📈 MarketFlow")
st.caption(f"Data as of {latest_date} · {len(tickers)} stocks · built on AWS Redshift + dbt")

# ── Section 1: Today's Signals ────────────────────────────────────────────────

st.header("Today's Signals")

latest_vol = vol_df[vol_df["trading_date"] == latest_date].copy()
latest_ma = ma_df[ma_df["trading_date"] == latest_date][["ticker", "close_price", "sma_30", "price_to_sma_30"]]
latest_returns = returns_df[returns_df["trading_date"] == latest_date][["ticker", "daily_return_pct"]]

signals = (
    latest_vol
    .merge(latest_ma, on="ticker")
    .merge(latest_returns, on="ticker")
)

signals["vs_30d_avg"] = (signals["price_to_sma_30"] - 1) * 100
signals["vol_30d_pct"] = signals["annualized_volatility_30d"] * 100
signals["return_pct"] = signals["daily_return_pct"] * 100
signals["golden_cross"] = signals["golden_cross_signal"].map({1: "✅ Yes", 0: "—"})

display = signals[[
    "ticker", "close_price", "return_pct", "vs_30d_avg", "vol_30d_pct", "golden_cross"
]].rename(columns={
    "ticker": "Ticker",
    "close_price": "Close ($)",
    "return_pct": "Day Return (%)",
    "vs_30d_avg": "vs 30d Avg (%)",
    "vol_30d_pct": "30d Vol (ann.%)",
    "golden_cross": "Golden Cross",
}).sort_values("vs 30d Avg (%)", ascending=False)

st.dataframe(
    display.style
        .format({
            "Close ($)": "${:.2f}",
            "Day Return (%)": "{:+.2f}%",
            "vs 30d Avg (%)": "{:+.1f}%",
            "30d Vol (ann.%)": "{:.1f}%",
        })
        .map(lambda v: "color: #2ecc71" if isinstance(v, float) and v > 0 else
                       "color: #e74c3c" if isinstance(v, float) and v < 0 else "",
             subset=["Day Return (%)", "vs 30d Avg (%)"]),
    use_container_width=True,
    hide_index=True,
)

# ── Section 2: Cumulative Returns ─────────────────────────────────────────────

st.header("Cumulative Returns")

default_tickers = ["AAPL", "MSFT", "NVDA", "GOOGL", "META"]
selected_tickers = st.multiselect(
    "Select tickers",
    options=tickers,
    default=[t for t in default_tickers if t in tickers],
)

if selected_tickers:
    cum_df = returns_df[returns_df["ticker"].isin(selected_tickers)].copy()
    cum_df["daily_return_pct"] = cum_df["daily_return_pct"].fillna(0)
    cum_df = cum_df.sort_values(["ticker", "trading_date"])
    cum_df["cumulative_return"] = cum_df.groupby("ticker")["daily_return_pct"].transform(
        lambda x: (1 + x).cumprod() - 1
    ) * 100

    fig_cum = px.line(
        cum_df,
        x="trading_date",
        y="cumulative_return",
        color="ticker",
        labels={"trading_date": "", "cumulative_return": "Cumulative Return (%)", "ticker": ""},
        template="plotly_dark",
    )
    fig_cum.add_hline(y=0, line_dash="dot", line_color="gray")
    fig_cum.update_layout(legend=dict(orientation="h", y=1.05))
    st.plotly_chart(fig_cum, use_container_width=True)
else:
    st.info("Select at least one ticker above.")

# ── Section 3: Price vs Moving Averages ───────────────────────────────────────

st.header("Price vs Moving Averages")

col1, _ = st.columns([1, 3])
with col1:
    selected = st.selectbox("Select ticker", tickers, index=tickers.index("NVDA") if "NVDA" in tickers else 0)

ticker_ma = ma_df[ma_df["ticker"] == selected]

fig_ma = go.Figure()
fig_ma.add_trace(go.Scatter(x=ticker_ma["trading_date"], y=ticker_ma["close_price"],
                             name="Close", line=dict(color="#ffffff", width=1.5)))
fig_ma.add_trace(go.Scatter(x=ticker_ma["trading_date"], y=ticker_ma["sma_7"],
                             name="7d SMA", line=dict(color="#3498db", dash="dot")))
fig_ma.add_trace(go.Scatter(x=ticker_ma["trading_date"], y=ticker_ma["sma_30"],
                             name="30d SMA", line=dict(color="#e67e22", dash="dot")))
fig_ma.update_layout(
    template="plotly_dark",
    xaxis_title="",
    yaxis_title="Price ($)",
    legend=dict(orientation="h", y=1.05),
)
st.plotly_chart(fig_ma, use_container_width=True)

# ── Section 4: Volatility ─────────────────────────────────────────────────────

st.header("Annualized Volatility (30-day rolling)")

latest_vol_chart = latest_vol[["ticker", "annualized_volatility_30d"]].copy()
latest_vol_chart["vol_pct"] = latest_vol_chart["annualized_volatility_30d"] * 100
latest_vol_chart = latest_vol_chart.sort_values("vol_pct", ascending=True)

fig_vol = px.bar(
    latest_vol_chart,
    x="vol_pct",
    y="ticker",
    orientation="h",
    labels={"vol_pct": "Annualized Volatility (%)", "ticker": ""},
    template="plotly_dark",
    color="vol_pct",
    color_continuous_scale="RdYlGn_r",
)
fig_vol.update_coloraxes(showscale=False)
st.plotly_chart(fig_vol, use_container_width=True)

# ── Section 5: Sector Performance ────────────────────────────────────────────

st.header("Sector Performance")

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Cumulative Return by Sector")
    sector_cum = sector_df.copy()
    sector_cum["avg_daily_return_pct"] = sector_cum["avg_daily_return_pct"].fillna(0)
    sector_cum = sector_cum.sort_values(["sector", "trading_date"])
    sector_cum["cumulative_return"] = sector_cum.groupby("sector")["avg_daily_return_pct"].transform(
        lambda x: (1 + x).cumprod() - 1
    ) * 100

    fig_sector_cum = px.line(
        sector_cum,
        x="trading_date",
        y="cumulative_return",
        color="sector",
        labels={"trading_date": "", "cumulative_return": "Cumulative Return (%)", "sector": ""},
        template="plotly_dark",
    )
    fig_sector_cum.add_hline(y=0, line_dash="dot", line_color="gray")
    fig_sector_cum.update_layout(legend=dict(orientation="h", y=1.1, font=dict(size=10)))
    st.plotly_chart(fig_sector_cum, use_container_width=True)

with col_b:
    st.subheader("Today's Sector Breadth")
    latest_sector = sector_df[sector_df["trading_date"] == sector_df["trading_date"].max()].copy()
    latest_sector["return_pct"] = latest_sector["avg_daily_return_pct"] * 100
    latest_sector = latest_sector.sort_values("return_pct", ascending=True)

    fig_sector_bar = px.bar(
        latest_sector,
        x="return_pct",
        y="sector",
        orientation="h",
        color="return_pct",
        color_continuous_scale="RdYlGn",
        labels={"return_pct": "Avg Return (%)", "sector": ""},
        template="plotly_dark",
        custom_data=["breadth_pct", "ticker_count"],
    )
    fig_sector_bar.update_traces(
        hovertemplate="<b>%{y}</b><br>Avg return: %{x:.2f}%<br>Breadth: %{customdata[0]:.0f}% advancing<br>Tickers: %{customdata[1]}<extra></extra>"
    )
    fig_sector_bar.update_coloraxes(showscale=False)
    st.plotly_chart(fig_sector_bar, use_container_width=True)

st.caption("Pipeline: yfinance → S3 → Redshift (bronze) → dbt staging (silver) → dbt marts (gold)")
