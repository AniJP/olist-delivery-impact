-- Daily snapshot of how the delivery network was performing, as seen at the start of each day.
-- An order placed on day d is joined to the row for d, which only uses deliveries completed on
-- days before d and purchases made before d.
{% set lookback_delivered = 14 %}
{% set lookback_backlog = 60 %}

with orders as (
    select
        order_id,
        customer_state,
        purchase_date,
        cast(delivered_at as date) as delivered_date,
        delivery_days_exact,
        is_late,
        order_status
    from {{ ref('fct_orders') }}
    where order_status not in ('canceled', 'unavailable')
),

spine as (
    select cast(d as date) as snapshot_date
    from range(
        (select min(purchase_date) from orders),
        (select max(purchase_date) from orders) + interval 1 day,
        interval 1 day
    ) t(d)
),

delivered_daily as (
    select delivered_date, count(*) as n, sum(delivery_days_exact) as days_sum, sum(is_late::int) as late_n
    from orders
    where delivered_date is not null
    group by 1
),

purchased_daily as (
    select purchase_date, count(*) as n
    from orders
    group by 1
),

rolling as (
    select
        s.snapshot_date,
        sum(d.n)        over w_deliv as recent_delivered,
        sum(d.days_sum) over w_deliv as recent_days_sum,
        sum(d.late_n)   over w_deliv as recent_late,
        sum(p.n)        over w_week  as purchases_last_7d
    from spine s
    left join delivered_daily d on d.delivered_date = s.snapshot_date
    left join purchased_daily p on p.purchase_date = s.snapshot_date
    window
        w_deliv as (order by s.snapshot_date rows between {{ lookback_delivered }} preceding and 1 preceding),
        w_week  as (order by s.snapshot_date rows between 7 preceding and 1 preceding)
),

-- Orders bought in the last 60 days that had not arrived by the start of the snapshot day.
backlog as (
    select s.snapshot_date, count(o.order_id) as open_orders
    from spine s
    left join orders o
        on o.purchase_date <  s.snapshot_date
       and o.purchase_date >= s.snapshot_date - interval {{ lookback_backlog }} day
       and (o.delivered_date is null or o.delivered_date >= s.snapshot_date)
    group by 1
)

select
    r.snapshot_date,
    r.recent_delivered                                          as net_delivered_last_14d,
    r.recent_days_sum / nullif(r.recent_delivered, 0)           as net_delivery_days_last_14d,
    r.recent_late::double / nullif(r.recent_delivered, 0)       as net_late_rate_last_14d,
    coalesce(r.purchases_last_7d, 0)                            as net_purchases_last_7d,
    b.open_orders                                               as net_open_orders
from rolling r
join backlog b using (snapshot_date)
