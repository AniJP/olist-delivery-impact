-- One row per order: the promise, what actually happened, how the customer reacted, and the
-- features known at checkout. The central table for every analysis in this project.
with orders as (
    select * from {{ ref('stg_olist__orders') }}
),

joined as (
    select
        o.*,
        c.customer_unique_id,
        c.customer_state,
        c.customer_zip_prefix,
        b.n_items, b.n_products, b.n_sellers, b.items_value, b.freight_value, b.weight_kg,
        b.max_item_volume_cm3, b.seller_ship_by_at, b.main_seller_id, b.main_category,
        s.seller_state,
        s.seller_zip_prefix,
        p.payment_value, p.main_payment_type, p.max_installments,
        r.review_id, r.review_score, r.review_created_date, r.review_answered_at, r.has_comment,
        ps.session_number, ps.orders_in_session,
        cz.lat as customer_lat, cz.lng as customer_lng,
        sz.lat as seller_lat, sz.lng as seller_lng
    from orders o
    join {{ ref('stg_olist__customers') }} c using (customer_id)
    left join {{ ref('int_order_baskets') }} b using (order_id)
    left join {{ ref('stg_olist__sellers') }} s on s.seller_id = b.main_seller_id
    left join {{ ref('int_order_payments') }} p using (order_id)
    left join {{ ref('stg_olist__reviews') }} r using (order_id)
    left join {{ ref('int_purchase_sessions') }} ps using (order_id)
    left join {{ ref('stg_olist__zip_locations') }} cz on cz.zip_prefix = c.customer_zip_prefix
    left join {{ ref('stg_olist__zip_locations') }} sz on sz.zip_prefix = s.seller_zip_prefix
)

select
    -- keys
    order_id,
    customer_unique_id,
    main_seller_id                                                    as seller_id,
    order_status,

    -- when
    purchased_at,
    cast(purchased_at as date)                                        as purchase_date,
    date_trunc('month', purchased_at)::date                           as purchase_month,
    dayofweek(purchased_at)                                           as purchase_dow,      -- 0 = Sunday
    hour(purchased_at)                                                as purchase_hour,
    approved_at,
    shipped_at,
    delivered_at,
    estimated_delivery_date,

    -- the promise vs. reality (calendar days)
    date_diff('day', cast(purchased_at as date), estimated_delivery_date)       as promised_days,
    date_diff('day', cast(purchased_at as date), cast(delivered_at as date))    as delivery_days,
    round(epoch(delivered_at - purchased_at) / 86400.0, 3)                      as delivery_days_exact,
    date_diff('day', estimated_delivery_date, cast(delivered_at as date))       as days_late,  -- > 0 = late
    date_diff('day', estimated_delivery_date, cast(delivered_at as date)) > 0   as is_late,
    case
        when delivered_at is null then null
        when date_diff('day', estimated_delivery_date, cast(delivered_at as date)) <= -15 then '1. 15+ days early'
        when date_diff('day', estimated_delivery_date, cast(delivered_at as date)) <= -8  then '2. 8-14 days early'
        when date_diff('day', estimated_delivery_date, cast(delivered_at as date)) <= -1  then '3. 1-7 days early'
        when date_diff('day', estimated_delivery_date, cast(delivered_at as date)) = 0    then '4. on the day'
        when date_diff('day', estimated_delivery_date, cast(delivered_at as date)) <= 3   then '5. 1-3 days late'
        when date_diff('day', estimated_delivery_date, cast(delivered_at as date)) <= 7   then '6. 4-7 days late'
        when date_diff('day', estimated_delivery_date, cast(delivered_at as date)) <= 14  then '7. 8-14 days late'
        else '8. 15+ days late'
    end                                                                         as lateness_bucket,
    round(epoch(shipped_at - purchased_at) / 86400.0, 3)                        as days_to_ship,
    shipped_at > seller_ship_by_at                                              as seller_shipped_late,

    -- the customer's reaction
    review_score,
    review_score is not null                                                    as has_review,
    review_created_date,
    review_answered_at,
    has_comment,
    -- The survey goes out around the *estimated* date, so a late order is often reviewed before it
    -- arrives: the review then rates "my package hasn't come", not the delivered experience.
    review_created_date < cast(delivered_at as date)                            as review_before_delivery,

    -- geography
    customer_state,
    seller_state,
    customer_state = seller_state                                               as same_state,
    round({{ haversine_km('seller_lat', 'seller_lng', 'customer_lat', 'customer_lng') }}, 1) as distance_km,

    -- basket and payment (known at checkout)
    n_items,
    n_products,
    n_sellers,
    items_value,
    freight_value,
    round(freight_value / nullif(items_value + freight_value, 0), 4)            as freight_share,
    weight_kg,
    max_item_volume_cm3,
    main_category,
    payment_value,
    main_payment_type,
    max_installments,

    -- purchase sessions (one checkout can create several orders)
    session_number,
    orders_in_session,
    orders_in_session > 1                                                       as is_split_checkout,

    -- data quality
    (shipped_at < purchased_at or delivered_at < shipped_at)                    as has_timestamp_anomaly,
    order_status = 'delivered'
        and delivered_at is not null
        and n_items is not null
        and not coalesce(shipped_at < purchased_at or delivered_at < shipped_at, false)
        and cast(purchased_at as date) <= cast('{{ var("analysis_end_date") }}' as date)
                                                                                as is_analysis_eligible
from joined
