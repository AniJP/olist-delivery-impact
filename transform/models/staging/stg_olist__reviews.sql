-- One review per order. 0.5% of orders received more than one survey answer; keep the latest.
-- (The same review_id can also be attached to several orders bought together; that's expected.)
with ranked as (
    select
        *,
        row_number() over (
            partition by order_id
            order by cast(review_answer_timestamp as timestamp) desc, review_id
        ) as rn
    from {{ source('olist', 'order_reviews') }}
)

select
    order_id,
    review_id,
    cast(review_score as integer)                         as review_score,
    cast(review_creation_date as date)                    as review_created_date,
    cast(review_answer_timestamp as timestamp)            as review_answered_at,
    nullif(trim(review_comment_title), '') is not null    as has_comment_title,
    nullif(trim(review_comment_message), '') is not null  as has_comment,
    review_comment_message                                as comment_text
from ranked
where rn = 1
