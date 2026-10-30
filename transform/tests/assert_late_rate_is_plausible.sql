{{ config(severity='warn') }}
-- Sanity check on the headline metric: Olist's late rate is ~7%. A value far outside 2-25% means a
-- join or date bug, not a business change.
select late_rate
from (
    select avg(is_late::int) as late_rate
    from {{ ref('fct_orders') }}
    where is_analysis_eligible
)
where late_rate not between 0.02 and 0.25
