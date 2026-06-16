{{
    config(
        materialized='incremental',
        unique_key=['sector', 'trading_date'],
        incremental_strategy='merge',
    )
}}

with daily_returns as (
    select *
    from {{ ref('mart_stocks__daily_returns') }}
    {% if is_incremental() %}
    where trading_date >= (select dateadd(day, -1, max(trading_date)) from {{ this }})
    {% endif %}
),

sectors as (
    select ticker, sector, industry
    from {{ ref('ticker_sectors') }}
),

joined as (
    select
        s.sector,
        s.industry,
        d.trading_date,
        d.ticker,
        d.close_price,
        d.daily_return_pct,
        d.daily_log_return
    from daily_returns d
    inner join sectors s on d.ticker = s.ticker
),

sector_agg as (
    select
        sector,
        trading_date,
        count(distinct ticker)                          as ticker_count,
        avg(daily_return_pct)                           as avg_daily_return_pct,
        avg(daily_log_return)                           as avg_log_return,
        sum(case when daily_return_pct > 0 then 1 else 0 end) as advancing_count,
        sum(case when daily_return_pct < 0 then 1 else 0 end) as declining_count,
        max(daily_return_pct)                           as best_return_pct,
        min(daily_return_pct)                           as worst_return_pct,
        stddev(daily_return_pct)                        as return_dispersion
    from joined
    group by sector, trading_date
)

select
    sector,
    trading_date,
    ticker_count,
    avg_daily_return_pct,
    avg_log_return,
    advancing_count,
    declining_count,
    best_return_pct,
    worst_return_pct,
    return_dispersion,
    round(
        advancing_count::float / nullif(ticker_count, 0) * 100,
        1
    )                                                   as breadth_pct
from sector_agg
