-- Olist creates a separate order per seller, so one checkout can produce several "orders" for the
-- same person on the same day. Treating those as repeat purchases would inflate retention, so orders
-- are grouped into purchase sessions: same customer_unique_id, same calendar day.
with orders as (
    select o.order_id, o.purchased_at, c.customer_unique_id
    from {{ ref('stg_olist__orders') }} o
    join {{ ref('stg_olist__customers') }} c using (customer_id)
)

select
    order_id,
    customer_unique_id,
    purchased_at,
    cast(purchased_at as date)                                         as purchase_date,
    dense_rank() over (partition by customer_unique_id
                       order by cast(purchased_at as date))            as session_number,
    count(*) over (partition by customer_unique_id, cast(purchased_at as date)) as orders_in_session
from orders
