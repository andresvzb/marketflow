{{
    config(
        materialized='incremental',
        unique_key=['ticker', 'trading_date'],
        incremental_strategy='merge'
    )
}}

with daily as (

    select
        ticker,
        trading_date,
        close_price
    from {{ ref('stg_stocks__ohlcv') }}

    {% if is_incremental() %}
    -- Pull 30 extra days back so the rolling windows have enough history
    where trading_date >= (
        select dateadd(day, -30, max(trading_date))
        from {{ this }}
    )
    {% endif %}

)

select
    ticker,
    trading_date,
    close_price,

    avg(close_price) over (
        partition by ticker
        order by trading_date
        rows between 6 preceding and current row
    )                                   as sma_7,

    avg(close_price) over (
        partition by ticker
        order by trading_date
        rows between 29 preceding and current row
    )                                   as sma_30,

    -- Price relative to each moving average (1.0 = at the MA, >1 = above)
    case
        when avg(close_price) over (
            partition by ticker
            order by trading_date
            rows between 6 preceding and current row
        ) > 0
        then close_price / avg(close_price) over (
            partition by ticker
            order by trading_date
            rows between 6 preceding and current row
        )
        else null
    end                                 as price_to_sma_7,

    case
        when avg(close_price) over (
            partition by ticker
            order by trading_date
            rows between 29 preceding and current row
        ) > 0
        then close_price / avg(close_price) over (
            partition by ticker
            order by trading_date
            rows between 29 preceding and current row
        )
        else null
    end                                 as price_to_sma_30

from daily
