with source as (

    select * from {{ source('bronze_stocks', 'raw_ohlcv') }}

),

renamed as (

    select
        upper(trim(ticker))            as ticker,
        cast(date as date)             as trading_date,
        cast(open as decimal(18, 4))   as open_price,
        cast(high as decimal(18, 4))   as high_price,
        cast(low as decimal(18, 4))    as low_price,
        cast(close as decimal(18, 4))  as close_price,
        cast(adjusted_close as decimal(18, 4)) as adjusted_close_price,
        cast(volume as bigint)         as volume
    from source
    where ticker is not null
      and date is not null

)

select * from renamed
