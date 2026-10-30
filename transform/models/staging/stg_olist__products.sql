select
    p.product_id,
    p.product_category_name                                       as category_pt,
    coalesce(t.product_category_name_english,
             patch.product_category_name_english,
             p.product_category_name, 'unknown')                  as category,
    try_cast(p.product_weight_g as double)                         as weight_g,
    try_cast(p.product_length_cm as double)
        * try_cast(p.product_height_cm as double)
        * try_cast(p.product_width_cm as double)                   as volume_cm3,
    try_cast(p.product_photos_qty as integer)                      as photos_qty,
    -- (sic) Olist's column names are misspelled "lenght"
    try_cast(p.product_description_lenght as integer)              as description_length
from {{ source('olist', 'products') }} p
left join {{ source('olist', 'category_translation') }} t
    on t.product_category_name = p.product_category_name
left join {{ ref('category_translation_patch') }} patch
    on patch.product_category_name = p.product_category_name
