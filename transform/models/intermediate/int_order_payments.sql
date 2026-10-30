-- One row per order: total paid and the dominant payment method.
select
    order_id,
    round(sum(payment_value), 2)                                   as payment_value,
    arg_max(payment_type, payment_value)                           as main_payment_type,
    max(payment_installments)                                      as max_installments,
    count(distinct payment_type)                                   as n_payment_types
from {{ ref('stg_olist__payments') }}
group by order_id
