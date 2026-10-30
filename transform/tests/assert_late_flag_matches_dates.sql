-- is_late must agree with the dates it is derived from.
select order_id
from {{ ref('fct_orders') }}
where delivered_at is not null
  and is_late <> (cast(delivered_at as date) > estimated_delivery_date)
