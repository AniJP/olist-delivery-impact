-- The same idea as int_network_congestion, per destination state: average delivery time of
-- orders to that state delivered in the 30 days before the snapshot day.
{% set lookback = 30 %}

with orders as (
    select customer_state, cast(delivered_at as date) as delivered_date, delivery_days_exact
    from {{ ref('fct_orders') }}
    where delivered_at is not null and customer_state is not null
),

spine as (
    select cast(d as date) as snapshot_date, st.customer_state
    from range(
        (select min(cast(purchased_at as date)) from {{ ref('fct_orders') }}),
        (select max(cast(purchased_at as date)) from {{ ref('fct_orders') }}) + interval 1 day,
        interval 1 day
    ) t(d)
    cross join (select distinct customer_state from orders) st
),

daily as (
    select customer_state, delivered_date, count(*) as n, sum(delivery_days_exact) as days_sum
    from orders
    group by 1, 2
)

select
    s.snapshot_date,
    s.customer_state,
    sum(d.n) over w                                             as state_delivered_last_30d,
    sum(d.days_sum) over w / nullif(sum(d.n) over w, 0)         as state_delivery_days_last_30d
from spine s
left join daily d on d.customer_state = s.customer_state and d.delivered_date = s.snapshot_date
window w as (
    partition by s.customer_state order by s.snapshot_date
    rows between {{ lookback }} preceding and 1 preceding
)
