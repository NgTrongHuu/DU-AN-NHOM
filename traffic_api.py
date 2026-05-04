"""
traffic_api.py
--------------
Mô phỏng tình trạng giao thông & nhu cầu tại TP.HCM theo thời gian thực.
Có cache ngắn để 2 request liên tiếp ra cùng kết quả.
"""
from __future__ import annotations

import random
import time
from datetime import datetime

import places


_CACHE_TTL    = 60.0
_traffic_cache: dict = {"ts": 0.0, "data": None}
_demand_cache:  dict = {"ts": 0.0, "data": None}
_pickup_cache:  dict[tuple, dict] = {}


def _hour_traffic_baseline(h: int) -> int:
    if 0 <= h < 5:    return 1
    if h == 5:        return 2
    if h == 6:        return 5
    if 7 <= h <= 8:   return 9
    if h == 9:        return 6
    if 10 <= h <= 11: return 5
    if h == 12:       return 6
    if 13 <= h <= 16: return 5
    if h == 17:       return 8
    if 18 <= h <= 19: return 9
    if h == 20:       return 6
    if h == 21:       return 4
    if h == 22:       return 3
    if h == 23:       return 2
    return 3


def _hour_demand_baseline(h: int) -> int:
    if 0 <= h < 4:    return 8
    if h == 4:        return 6
    if h == 5:        return 4
    if h == 6:        return 5
    if 7 <= h <= 8:   return 7
    if h == 9:        return 5
    if 10 <= h <= 11: return 3
    if h == 12:       return 5
    if 13 <= h <= 16: return 3
    if h == 17:       return 7
    if 18 <= h <= 19: return 8
    if h == 20:       return 6
    if h == 21:       return 5
    if h == 22:       return 6
    if h == 23:       return 7
    return 5


def _jitter(base: int, spread: int, lo: int, hi: int) -> int:
    val = base + random.randint(-spread, spread)
    return max(lo, min(hi, val))


def _traffic_text(score: int) -> str:
    if score <= 1: return "Đường rất thông thoáng"
    if score <= 3: return "Thông thoáng"
    if score <= 5: return "Lưu thông bình thường"
    if score <= 7: return "Đông xe, di chuyển chậm"
    if score <= 8: return "Tắc đường nhẹ"
    return "Tắc đường nặng"


def get_traffic_score(now: datetime | None = None) -> tuple[int, dict]:
    t = time.time()
    if _traffic_cache["data"] and (t - _traffic_cache["ts"] < _CACHE_TTL):
        cached = _traffic_cache["data"]
        return cached["score"], dict(cached)
    now   = now or datetime.now()
    base  = _hour_traffic_baseline(now.hour)
    score = _jitter(base, 2, 0, 10)
    info  = {
        "score": score, "scale_max": 10,
        "hour": now.hour, "baseline": base,
        "text": _traffic_text(score), "source": "simulated",
    }
    _traffic_cache["ts"]   = t
    _traffic_cache["data"] = info
    return score, dict(info)


def _demand_text(score: int) -> str:
    if score <= 2: return "Ít người đặt xe"
    if score <= 4: return "Nhu cầu thấp"
    if score <= 6: return "Nhu cầu vừa"
    if score <= 8: return "Nhu cầu cao"
    return "Nhu cầu rất cao (đặt xe khó)"


def get_demand_score(now: datetime | None = None) -> tuple[int, dict]:
    t = time.time()
    if _demand_cache["data"] and (t - _demand_cache["ts"] < _CACHE_TTL):
        cached = _demand_cache["data"]
        return cached["score"], dict(cached)
    now   = now or datetime.now()
    base  = _hour_demand_baseline(now.hour)
    score = _jitter(base, 2, 0, 10)
    info  = {
        "score": score, "scale_max": 10,
        "hour": now.hour, "baseline": base,
        "text": _demand_text(score), "source": "simulated",
    }
    _demand_cache["ts"]   = t
    _demand_cache["data"] = info
    return score, dict(info)


def get_pickup_difficulty_score(lat: float | None,
                                lng: float | None) -> tuple[int, dict]:
    if lat is None or lng is None:
        score = 2
        return score, {
            "score": score, "scale_max": 5,
            "text": "Không rõ vị trí đón — ước lượng độ khó trung bình",
            "source": "simulated",
        }
    key = (round(lat, 3), round(lng, 3))
    t   = time.time()
    if key in _pickup_cache and (t - _pickup_cache[key]["ts"] < _CACHE_TTL):
        cached = _pickup_cache[key]["data"]
        return cached["score"], dict(cached)

    d_center = places.haversine_km(lat, lng, 10.7724, 106.6987)
    if   d_center < 1.0: base = 4
    elif d_center < 2.5: base = 3
    elif d_center < 4.0: base = 2
    elif d_center < 6.0: base = 1
    else:                base = 0
    score = max(0, min(5, base + random.choice([-1, 0, 0, 0, 1])))

    text = {
        0: "Khu vực dễ đón, không cản trở",
        1: "Đường thoáng, dễ tấp xe",
        2: "Đông trung bình, đón bình thường",
        3: "Khu vực đông, đón chậm hơn",
        4: "Khu trung tâm, khó tìm chỗ tấp",
        5: "Cực kỳ đông (TTTM/sân bay)",
    }[score]

    info = {
        "score": score, "scale_max": 5,
        "distance_to_center_km": round(d_center, 2),
        "text": text, "source": "simulated",
    }
    _pickup_cache[key] = {"ts": t, "data": info}
    return score, dict(info)
