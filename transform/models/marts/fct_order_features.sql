-- One row per order with everything a model may use at checkout, plus the label.
-- Feature columns are point-in-time: seller history and network congestion only use information
-- available before the purchase timestamp (see int_seller_history, int_network_congestion).
with orders as (
    select * from {{ ref('fct_orders') }}
    where order_status not in ('canceled', 'unavailable')
)

select
    -- keys and split
    o.order_id,
    o.seller_id,
    o.purchased_at,
    o.purchase_date,

    -- label
    o.order_status,
    o.delivered_at,
    o.delivery_days,                                             -- calendar days, same unit as the promise
    o.delivery_days_exact,
    o.estimated_delivery_date,
    o.is_late,
    o.is_analysis_eligible,
    -- Still in transit when the dataset was extracted: the true delivery time is longer than this.
    case when o.delivered_at is null and o.order_status = 'shipped'
         then round(epoch(cast('{{ var("data_snapshot_at") }}' as timestamp) - o.purchased_at) / 86400.0, 3)
    end                                                          as censored_at_days,

    -- the incumbent promise (Olist's own estimate, also known at checkout)
    o.promised_days,

    -- order
    o.customer_state,
    o.seller_state,
    o.seller_state || '>' || o.customer_state                    as route,
    o.same_state,
    o.distance_km,
    o.n_items,
    o.n_sellers,
    o.items_value,
    o.freight_value,
    o.freight_share,
    o.weight_kg,
    o.max_item_volume_cm3,
    o.main_category,
    o.main_payment_type,
    o.max_installments,
    o.purchase_dow,
    o.purchase_hour,

    -- seller track record at checkout
    h.seller_prior_orders,
    h.seller_prior_delivery_days,
    h.seller_prior_days_to_ship,
    h.seller_prior_late_rate,
    date_diff('day', h.seller_last_delivery_at, o.purchased_at)  as days_since_seller_last_delivery,

    -- network state at checkout
    n.net_delivery_days_last_14d,
    n.net_late_rate_last_14d,
    n.net_purchases_last_7d,
    n.net_open_orders,
    s.state_delivery_days_last_30d,
    s.state_delivered_last_30d
from orders o
left join {{ ref('int_seller_history') }} h using (order_id)
left join {{ ref('int_network_congestion') }} n on n.snapshot_date = o.purchase_date
left join {{ ref('int_state_congestion') }} s
    on s.snapshot_date = o.purchase_date and s.customer_state = o.customer_state
