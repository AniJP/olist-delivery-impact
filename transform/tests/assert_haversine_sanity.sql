-- São Paulo to Rio de Janeiro is ~361 km as the crow flies (great-circle distance).
select distance
from (select {{ haversine_km(-23.5505, -46.6333, -22.9068, -43.1729) }} as distance)
where abs(distance - 361) > 3
