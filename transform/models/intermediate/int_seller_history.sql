-- Point-in-time seller track record for every order: what was already *known* about the seller
-- at the moment the customer checked out. Only orders delivered strictly before this order's
-- purchase timestamp count, so the features never peek at the future (no leakage).
with orders as (
    select
        order_id,
        seller_id,
        purchased_at,
        delivered_at,
        delivery_days_exact,
        days_to_ship,
        is_late
    from {{ ref('fct_orders') }}
),

finished as (
    select *
    from orders
    where delivered_at is not null
      and not coalesce(days_to_ship < 0 or delivered_at < purchased_at, false)
)

select
    cur.order_id,
    count(prev.order_id)                          as seller_prior_orders,
    avg(prev.delivery_days_exact)                 as seller_prior_delivery_days,
    avg(prev.days_to_ship)                        as seller_prior_days_to_ship,
    avg(prev.is_late::int)                        as seller_prior_late_rate,
    max(prev.delivered_at)                        as seller_last_delivery_at
from orders cur
left join finished prev
    on prev.seller_id = cur.seller_id
   and prev.delivered_at < cur.purchased_at
group by cur.order_id
