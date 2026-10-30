-- A second purchase must happen on a later day than the first (same-day orders are one checkout).
select customer_unique_id
from {{ ref('fct_customer_first_purchase') }}
where second_purchase_date is not null and second_purchase_date <= first_purchase_date
