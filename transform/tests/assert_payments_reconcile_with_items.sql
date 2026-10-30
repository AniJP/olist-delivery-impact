{{ config(severity='warn', warn_if='>300') }}
-- Payments should equal items + freight. A few hundred orders don't (vouchers, interest on
-- instalments); more than that would point to a join bug.
select order_id, payment_value, items_value + freight_value as basket_total
from {{ ref('fct_orders') }}
where payment_value is not null and items_value is not null
  and abs(payment_value - (items_value + freight_value)) > 1
