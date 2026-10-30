-- One point per zip-code prefix: the median of its geolocation samples, ignoring the few points
-- that fall outside Brazil's bounding box (bad geocodes).
select
    cast(geolocation_zip_code_prefix as integer)   as zip_prefix,
    median(geolocation_lat)                        as lat,
    median(geolocation_lng)                        as lng,
    mode(geolocation_state)                        as state,
    count(*)                                       as n_points
from {{ source('olist', 'geolocation') }}
where geolocation_lat between -34.0 and 5.3
  and geolocation_lng between -74.0 and -34.0
group by 1
