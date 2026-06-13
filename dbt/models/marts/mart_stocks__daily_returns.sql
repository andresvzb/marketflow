with ohlcv as (

    select
        symbol,
        trade_date,
        open,
        high,
        low,
        close,
        volume
    from {{ ref('stg_stocks__ohlcv') }}

),

with_prior_close as (

    select
        symbol,
        trade_date,
        close,
        lag(close) over (
            partition by symbol
            order by trade_date
        ) as prev_close
    from ohlcv

)

select
    symbol,
    trade_date,
    close,
    prev_close,
    close - prev_close as price_change,
    case
        when prev_close is not null and prev_close <> 0
            then (close - prev_close) / prev_close
        else null
    end as daily_return_pct,
    ln(close / nullif(prev_close, 0)) as daily_log_return
from with_prior_close
order by symbol, trade_date
