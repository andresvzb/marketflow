{{
    config(
        materialized='incremental',
        unique_key=['ticker', 'trading_date'],
        incremental_strategy='merge'
    )
}}

with ohlcv as (

    select
        ticker,
        trading_date,
        open_price,
        high_price,
        low_price,
        close_price,
        volume
    from {{ ref('stg_stocks__ohlcv') }}

    {% if is_incremental() %}
    -- On incremental runs, only pull dates we haven't processed yet,
    -- plus one extra day back so LAG() has a previous close to work with.
    where trading_date >= (
        select dateadd(day, -1, max(trading_date))
        from {{ this }}
    )
    {% endif %}

),

with_prior_close as (

    select
        ticker,
        trading_date,
        open_price,
        high_price,
        low_price,
        close_price,
        volume,
        lag(close_price) over (
            partition by ticker
            order by trading_date
        ) as prev_close
    from ohlcv

)

select
    ticker,
    trading_date,
    open_price,
    high_price,
    low_price,
    close_price,
    volume,
    prev_close,
    close_price - prev_close                                                as price_change,
    case
        when prev_close is not null and prev_close <> 0
            then (close_price - prev_close) / prev_close
        else null
    end                                                                     as daily_return_pct,
    ln(cast(close_price as float) / nullif(cast(prev_close as float), 0))  as daily_log_return
from with_prior_close
