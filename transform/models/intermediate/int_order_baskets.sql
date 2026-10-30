-- One row per order describing what was bought and from whom.
with items as (
    select i.*, p.category, p.weight_g, p.volume_cm3
    from {{ ref('stg_olist__order_items') }} i
    left join {{ ref('stg_olist__products') }} p using (product_id)
),

-- The "main" seller and category are those of the most expensive item.
main_item as (
    select order_id, seller_id as main_seller_id, category as main_category
    from items
    qualify row_number() over (partition by order_id order by price desc, order_item_id) = 1
)

select
    i.order_id,
    count(*)                                    as n_items,
    count(distinct i.product_id)                as n_products,
    count(distinct i.seller_id)                 as n_sellers,
    round(sum(i.price), 2)                      as items_value,
    round(sum(i.freight_value), 2)              as freight_value,
    round(sum(coalesce(i.weight_g, 0)) / 1000.0, 3)  as weight_kg,
    max(i.volume_cm3)                           as max_item_volume_cm3,
    min(i.shipping_limit_at)                    as seller_ship_by_at,
    m.main_seller_id,
    m.main_category
from items i
join main_item m using (order_id)
group by i.order_id, m.main_seller_id, m.main_category
