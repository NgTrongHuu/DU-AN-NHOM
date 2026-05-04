"""
places.py
---------
Cấu hình vùng địa lý + tiện ích hình học cho RidePro.
"""
from __future__ import annotations

import math


RING1_BBOX = {
    "lat_min": 10.745, "lat_max": 10.815,
    "lng_min": 106.620, "lng_max": 106.730,
}

HCMC_LAT = 10.7717
HCMC_LNG = 106.6669


def is_in_ring1(lat: float, lng: float) -> bool:
    return (RING1_BBOX["lat_min"] <= lat <= RING1_BBOX["lat_max"]
            and RING1_BBOX["lng_min"] <= lng <= RING1_BBOX["lng_max"])


def get_default_center() -> tuple[float, float]:
    return (HCMC_LAT, HCMC_LNG)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0088
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))
