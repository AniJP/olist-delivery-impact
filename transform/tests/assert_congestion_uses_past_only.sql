-- Leakage guard: the network snapshot for day d may only count deliveries completed before d.
-- Recompute the 14-day delivered count independently and compare.
with deliveries as (
    select cast(delivered_at as date) as delivered_date
    from {{ ref('fct_orders') }}
    where delivered_at is not null and order_status not in ('canceled', 'unavailable')
),

expected as (
    select c.snapshot_date, count(d.delivered_date) as n
    from {{ ref('int_network_congestion') }} c
    left join deliveries d
        on d.delivered_date <  c.snapshot_date
       and d.delivered_date >= c.snapshot_date - interval 14 day
    group by 1
)

select c.snapshot_date, c.net_delivered_last_14d, e.n
from {{ ref('int_network_congestion') }} c
join expected e using (snapshot_date)
where coalesce(c.net_delivered_last_14d, 0) <> e.n
