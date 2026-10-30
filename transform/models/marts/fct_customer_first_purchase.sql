-- One row per customer: their first purchase session and whether they came back.
-- Used for the retention question ("does a late first delivery stop people from buying again?").
with sessions as (
    select
        ps.customer_unique_id,
        ps.session_number,
        ps.purchase_date,
        f.order_id,
        f.is_late,
        f.days_late,
        f.review_score,
        f.payment_value,
        f.customer_state,
        f.is_analysis_eligible
    from {{ ref('int_purchase_sessions') }} ps
    join {{ ref('fct_orders') }} f using (order_id)
),

first_session as (
    select
        customer_unique_id,
        min(purchase_date)                    as first_purchase_date,
        count(*)                              as first_session_orders,
        bool_or(coalesce(is_late, false))     as first_session_any_late,
        max(days_late)                        as first_session_max_days_late,
        min(review_score)                     as first_session_min_review,
        round(sum(payment_value), 2)          as first_session_value,
        any_value(customer_state)             as customer_state,
        bool_and(is_analysis_eligible)        as first_session_eligible
    from sessions
    where session_number = 1
    group by customer_unique_id
),

second_session as (
    select customer_unique_id, min(purchase_date) as second_purchase_date
    from sessions
    where session_number = 2
    group by customer_unique_id
)

select
    f.*,
    s.second_purchase_date,
    date_diff('day', f.first_purchase_date, s.second_purchase_date)               as days_to_second_purchase,
    coalesce(date_diff('day', f.first_purchase_date, s.second_purchase_date)
             <= {{ var('repeat_window_days') }}, false)                           as repeat_within_window,
    -- Only customers whose first purchase is old enough have a known outcome.
    f.first_purchase_date
        <= cast('{{ var("analysis_end_date") }}' as date) - interval {{ var('repeat_window_days') }} day
                                                                                    as has_full_followup
from first_session f
left join second_session s using (customer_unique_id)
