-- Singular test: flag rows where the absolute daily return exceeds 50%.
-- A move this large almost always means bad data (split not adjusted, feed error, etc.).
-- This test FAILS (returns rows) if any such records exist.

select
    ticker,
    trading_date,
    close_price,
    prev_close,
    daily_return_pct
from {{ ref('mart_stocks__daily_returns') }}
where abs(daily_return_pct) > 0.5
  and prev_close is not null
