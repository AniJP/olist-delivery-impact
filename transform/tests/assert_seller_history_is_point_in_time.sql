-- Leakage guard: an order's seller history can only include that seller's orders that were both
-- purchased and delivered before it. Any order whose prior count exceeds the number of the
-- seller's earlier purchases has looked into the future.
with o as (
    select order_id, seller_id, purchased_at from {{ ref('fct_orders') }}
),

earlier_purchases as (
    select cur.order_id, count(prev.order_id) as n_earlier
    from o cur
    left join o prev on prev.seller_id = cur.seller_id and prev.purchased_at < cur.purchased_at
    group by cur.order_id
)

select f.order_id, f.seller_prior_orders, e.n_earlier
from {{ ref('fct_order_features') }} f
join earlier_purchases e using (order_id)
where f.seller_prior_orders > e.n_earlier
