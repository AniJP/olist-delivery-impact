-- Orders used in analysis must have a sane timeline.
select order_id, purchased_at, shipped_at, delivered_at
from {{ ref('fct_orders') }}
where is_analysis_eligible
  and (delivered_at < purchased_at or delivered_at is null)
