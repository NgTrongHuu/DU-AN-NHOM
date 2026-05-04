"""
external_api.py
---------------
Tích hợp 3 dịch vụ MIỄN PHÍ dựa trên OpenStreetMap (không cần API key):
  * Photon    – autocomplete địa chỉ
  * Nominatim – reverse geocode
  * OSRM      – tìm đường thật theo phố
"""
from __future__ import annotations

from functools import lru_cache
from typing import Tuple

import requests

import places


PHOTON_URL    = "https://photon.komoot.io/api"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
OSRM_URL      = "https://router.project-osrm.org/route/v1/driving"

USER_AGENT = "RidePro-Demo/1.0 (educational ride-hailing demo)"
TIMEOUT_S  = 6

_PHOTON_BBOX = (
    f"{places.RING1_BBOX['lng_min']},"
    f"{places.RING1_BBOX['lat_min']},"
    f"{places.RING1_BBOX['lng_max']},"
    f"{places.RING1_BBOX['lat_max']}"
)
_LAT_BIAS, _LNG_BIAS = places.get_default_center()


def _photon_feat_to_place(feat: dict) -> dict | None:
    coords = feat.get("geometry", {}).get("coordinates")
    if not coords or len(coords) < 2:
        return None
    lng, lat = float(coords[0]), float(coords[1])
    if not places.is_in_ring1(lat, lng):
        return None
    p    = feat.get("properties", {})
    name = (p.get("name") or p.get("street") or p.get("type") or "Địa điểm").strip()
    parts: list[str] = []
    if p.get("housenumber"):
        parts.append(str(p["housenumber"]))
    if p.get("street") and p.get("street") != name:
        parts.append(p["street"])
    if p.get("district"):
        parts.append(p["district"])
    elif p.get("city"):
        parts.append(p["city"])
    elif p.get("state"):
        parts.append(p["state"])
    addr = ", ".join(parts) or "TP.HCM"
    return {"name": name, "addr": addr, "lat": lat, "lng": lng}


def _nominatim_to_place(data: dict, click_lat: float, click_lng: float) -> dict:
    addr_obj = data.get("address", {}) or {}
    name = (
        data.get("name")
        or addr_obj.get("amenity")
        or addr_obj.get("shop")
        or addr_obj.get("building")
        or addr_obj.get("road")
        or "Vị trí trên bản đồ"
    )
    parts: list[str] = []
    if addr_obj.get("house_number"):
        parts.append(addr_obj["house_number"])
    if addr_obj.get("road"):
        parts.append(addr_obj["road"])
    if addr_obj.get("suburb"):
        parts.append(addr_obj["suburb"])
    if addr_obj.get("city_district"):
        parts.append(addr_obj["city_district"])
    elif addr_obj.get("district"):
        parts.append(addr_obj["district"])
    addr_str = ", ".join(parts) or (data.get("display_name", "")[:120] or "TP.HCM")
    try:
        lat = float(data.get("lat", click_lat))
        lng = float(data.get("lon", click_lng))
    except (TypeError, ValueError):
        lat, lng = click_lat, click_lng
    return {"name": name.strip(), "addr": addr_str.strip(), "lat": lat, "lng": lng}


@lru_cache(maxsize=512)
def _search_cached(q_lower: str, limit: int) -> Tuple[Tuple[dict, ...], str]:
    try:
        params = {
            "q": q_lower, "limit": limit,
            "lat": _LAT_BIAS, "lon": _LNG_BIAS,
            "bbox": _PHOTON_BBOX, "lang": "default",
        }
        r = requests.get(PHOTON_URL, params=params,
                         headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S)
        r.raise_for_status()
        feats = (r.json() or {}).get("features") or []
    except Exception:
        return tuple(), "error"
    out: list[dict] = []
    seen: set[tuple] = set()
    for f in feats:
        p = _photon_feat_to_place(f)
        if not p:
            continue
        key = (p["name"], round(p["lat"], 5), round(p["lng"], 5))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
        if len(out) >= limit:
            break
    return tuple(out), "photon"


def search(q: str, limit: int = 8) -> Tuple[list[dict], str]:
    q = (q or "").strip()
    if not q:
        return [], "empty"
    limit = max(1, min(20, int(limit)))
    items, source = _search_cached(q.lower(), limit)
    return list(items), source


@lru_cache(maxsize=2048)
def _reverse_cached_raw(lat_5: float, lng_5: float) -> dict | None:
    try:
        params = {
            "lat": lat_5, "lon": lng_5,
            "format": "json", "zoom": 18, "addressdetails": 1,
            "accept-language": "vi",
        }
        r = requests.get(NOMINATIM_URL, params=params,
                         headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and "lat" in data:
            return data
    except Exception:
        pass
    return None


def reverse(lat: float, lng: float) -> Tuple[dict | None, str]:
    if not places.is_in_ring1(lat, lng):
        return None, "outside"
    data = _reverse_cached_raw(round(lat, 5), round(lng, 5))
    if not data:
        return None, "error"
    place = _nominatim_to_place(data, lat, lng)
    place["distance_km"] = round(
        places.haversine_km(lat, lng, place["lat"], place["lng"]), 3
    )
    return place, "nominatim"


_route_cache: dict[tuple, dict] = {}
_ROUTE_CACHE_MAX = 256


def route(points: list[Tuple[float, float]]) -> Tuple[dict, str]:
    for lat, lng in points:
        if not places.is_in_ring1(lat, lng):
            return ({"ok": False,
                     "error": "Điểm nằm ngoài Vành đai 1 TP.HCM.",
                     "distance_km": 0, "polyline": []}, "validation")
    key = tuple((round(lat, 5), round(lng, 5)) for lat, lng in points)
    if key in _route_cache:
        return dict(_route_cache[key]), "cache"
    try:
        coords = ";".join(f"{lng},{lat}" for lat, lng in points)
        r = requests.get(f"{OSRM_URL}/{coords}",
                         params={"overview": "full", "geometries": "geojson"},
                         headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            raise RuntimeError("OSRM không tìm được đường")
        rt = data["routes"][0]
        polyline = [[float(c[1]), float(c[0])]
                    for c in rt.get("geometry", {}).get("coordinates", [])]
        result = {
            "ok": True,
            "distance_km":  round(rt.get("distance", 0) / 1000, 2),
            "duration_min": round(rt.get("duration", 0) / 60, 1),
            "polyline": polyline,
        }
        _route_cache[key] = result
        if len(_route_cache) > _ROUTE_CACHE_MAX:
            _route_cache.pop(next(iter(_route_cache)))
        return dict(result), "osrm"
    except Exception:
        return ({"ok": False,
                 "error": "Không kết nối được dịch vụ tìm đường (OSRM).",
                 "distance_km": 0, "polyline": []}, "error")
