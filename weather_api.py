"""
weather_api.py
--------------
Lấy thời tiết REAL-TIME tại TP.HCM từ Open-Meteo (miễn phí, không cần API key).
Có cache 5 phút.
"""
from __future__ import annotations

import time
import requests

import places


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S      = 6
CACHE_TTL_SEC  = 300

_WMO_BADNESS = {
    0: 0, 1: 1, 2: 2, 3: 3,
    45: 4, 48: 4,
    51: 4, 53: 5, 55: 6,
    61: 5, 63: 7, 65: 9,
    66: 7, 67: 9,
    71: 5, 73: 7, 75: 9, 77: 5,
    80: 5, 81: 7, 82: 9,
    85: 6, 86: 8,
    95: 9, 96: 10, 99: 10,
}


def _wmo_text(code: int) -> str:
    table = {
        0: "Trời quang", 1: "Ít mây", 2: "Có mây", 3: "Nhiều mây",
        45: "Sương mù", 48: "Sương mù đóng băng",
        51: "Mưa phùn nhẹ", 53: "Mưa phùn vừa", 55: "Mưa phùn dày",
        61: "Mưa nhẹ", 63: "Mưa vừa", 65: "Mưa to",
        66: "Mưa đông nhẹ", 67: "Mưa đông to",
        71: "Tuyết nhẹ", 73: "Tuyết vừa", 75: "Tuyết to", 77: "Hạt tuyết",
        80: "Mưa rào nhẹ", 81: "Mưa rào vừa", 82: "Mưa rào dữ dội",
        85: "Tuyết rào nhẹ", 86: "Tuyết rào nặng",
        95: "Dông", 96: "Dông kèm mưa đá nhẹ", 99: "Dông kèm mưa đá to",
    }
    return table.get(code, "Không rõ")


_cache: dict = {"ts": 0.0, "data": None}


def _fetch_open_meteo() -> dict | None:
    try:
        params = {
            "latitude":  places.HCMC_LAT,
            "longitude": places.HCMC_LNG,
            "current":   "temperature_2m,relative_humidity_2m,precipitation,"
                         "weather_code,wind_speed_10m,visibility",
            "timezone":  "Asia/Ho_Chi_Minh",
            "wind_speed_unit": "kmh",
        }
        r = requests.get(OPEN_METEO_URL, params=params, timeout=TIMEOUT_S)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _score_from_data(data: dict) -> tuple[int, dict]:
    cur      = data.get("current", {}) if isinstance(data, dict) else {}
    temp     = float(cur.get("temperature_2m", 30) or 30)
    humidity = float(cur.get("relative_humidity_2m", 70) or 70)
    precip   = float(cur.get("precipitation", 0) or 0)
    code     = int(cur.get("weather_code", 0) or 0)
    wind     = float(cur.get("wind_speed_10m", 0) or 0)
    vis_m    = float(cur.get("visibility", 10000) or 10000)

    if precip <= 0:    precip_score = 0
    elif precip <= 1:  precip_score = 2
    elif precip <= 3:  precip_score = 4
    elif precip <= 7:  precip_score = 6
    elif precip <= 15: precip_score = 8
    else:              precip_score = 10

    code_score = _WMO_BADNESS.get(code, 3)

    if   wind < 10:  wind_score = 0
    elif wind < 20:  wind_score = 2
    elif wind < 30:  wind_score = 4
    elif wind < 45:  wind_score = 6
    elif wind < 60:  wind_score = 8
    else:            wind_score = 10

    if   vis_m >= 10000: vis_score = 0
    elif vis_m >= 5000:  vis_score = 2
    elif vis_m >= 2000:  vis_score = 5
    elif vis_m >= 1000:  vis_score = 7
    else:                vis_score = 10

    raw   = (precip_score * 0.35 + code_score * 0.30
             + wind_score * 0.15 + vis_score * 0.20)
    score = int(round(max(0, min(10, raw))))

    info = {
        "score":              score,
        "scale_max":          10,
        "temperature_c":      round(temp, 1),
        "humidity_pct":       round(humidity),
        "precipitation_mm":   round(precip, 2),
        "wind_kmh":           round(wind, 1),
        "visibility_km":      round(vis_m / 1000, 1),
        "weather_code":       code,
        "weather_text":       _wmo_text(code),
        "source":             "open-meteo",
        "score_parts": {
            "precip": precip_score, "code": code_score,
            "wind":   wind_score,   "vis":  vis_score,
        },
    }
    return score, info


def _fallback_random_weather() -> tuple[int, dict]:
    return 2, {
        "score": 2, "scale_max": 10,
        "temperature_c": 31.0, "humidity_pct": 75,
        "precipitation_mm": 0.0, "wind_kmh": 10.0,
        "visibility_km": 10.0,
        "weather_code": 1, "weather_text": "Ít mây (giả định)",
        "source": "fallback",
    }


def get_weather_score() -> tuple[int, dict]:
    now = time.time()
    if _cache["data"] and (now - _cache["ts"] < CACHE_TTL_SEC):
        cached = _cache["data"]
        return cached["score"], dict(cached)
    data = _fetch_open_meteo()
    if data is None:
        score, info = _fallback_random_weather()
    else:
        score, info = _score_from_data(data)
    _cache["ts"]   = now
    _cache["data"] = info
    return score, dict(info)
