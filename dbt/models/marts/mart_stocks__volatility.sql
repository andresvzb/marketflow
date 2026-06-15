{{
    config(
        materialized='incremental',
        unique_key=['ticker', 'trading_date'],
        incremental_strategy='merge'
    )
}}

-- Depends on daily returns for log returns; depends on moving averages for SMAs.
-- Volatility here = annualized rolling stddev of log returns (industry standard).

with returns as (

    select
        ticker,
        trading_date,
        close_price,
        daily_log_return
    from {{ ref('mart_stocks__daily_returns') }}

    {% if is_incremental() %}
    where trading_date >= (
        select dateadd(day, -30, max(trading_date))
        from {{ this }}
    )
    {% endif %}

),

moving_avgs as (

    select
        ticker,
        trading_date,
        sma_7,
        sma_30
    from {{ ref('mart_stocks__moving_averages') }}

)

select
    r.ticker,
    r.trading_date,
    r.close_price,
    m.sma_7,
    m.sma_30,

    -- Rolling 30-day stddev of log returns, annualized (×√252 trading days/year)
    stddev(r.daily_log_return) over (
        partition by r.ticker
        order by r.trading_date
        rows between 29 preceding and current row
    ) * sqrt(252)                       as annualized_volatility_30d,

    -- Rolling 7-day stddev, annualized
    stddev(r.daily_log_return) over (
        partition by r.ticker
        order by r.trading_date
        rows between 6 preceding and current row
    ) * sqrt(252)                       as annualized_volatility_7d,

    -- Golden cross signal: 1 when 7d SMA crosses above 30d SMA (bullish)
    case
        when m.sma_7 > m.sma_30 then 1
        else 0
    end                                 as golden_cross_signal

from returns r
left join moving_avgs m
    on r.ticker = m.ticker
    and r.trading_date = m.trading_date
