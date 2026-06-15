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

),

with_prior_close as (

    select
        ticker,
        trading_date,
        close_price,
        lag(close_price) over (
            partition by ticker
            order by trading_date
        ) as prev_close
    from ohlcv

)

select
    ticker,
    trading_date,
    close_price,
    prev_close,
    close_price - prev_close as price_change,
    case
        when prev_close is not null and prev_close <> 0
            then (close_price - prev_close) / prev_close
        else null
    end as daily_return_pct,
    ln(cast(close_price as float) / nullif(cast(prev_close as float), 0)) as daily_log_return
from with_prior_close
order by ticker, trading_date
