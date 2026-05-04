"""
pricing.py
----------
TOÀN BỘ LOGIC TÍNH GIÁ chuyến xe của RidePro.

Thiết kế theo yêu cầu: mỗi yếu tố được quy ra THANG ĐIỂM SỐ (ví dụ 0-10) và
có ĐƠN GIÁ TRÊN MỖI ĐIỂM. Giá yếu tố đó = score × giá-mỗi-điểm. Cuối cùng
hàm `compute_total_fare()` cộng dồn tất cả lại để ra giá chuyến xe.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl

import weather_api
import traffic_api


# ===========================================================================
# 1) BẢNG GIÁ THEO LOẠI XE
# ===========================================================================
VEHICLE_TABLE: dict[str, dict[str, Any]] = {
    "bike": {
        "label": "GrabBike",
        "opening_fee": 10_000,
        "per_km":      6_000,
        "eco_ref":     None,
    },
    "car4": {
        "label": "GrabCar 4 chỗ",
        "opening_fee": 20_000,
        "per_km":      12_000,
        "eco_ref":     None,
    },
    "car7": {
        "label": "GrabCar 7 chỗ",
        "opening_fee": 25_000,
        "per_km":      18_000,
        "eco_ref":     None,
    },
    "bike_eco": {
        "label": "GrabBike Tiết kiệm",
        "opening_fee": 7_000,
        "per_km":      4_500,
        "eco_ref":     "bike",
    },
    "ev": {
        "label": "Xe điện",
        "opening_fee": 9_000,
        "per_km":      5_500,
        "eco_ref":     "bike",
    },
    "car_eco": {
        "label": "GrabCar Tiết kiệm",
        "opening_fee": 15_000,
        "per_km":      9_500,
        "eco_ref":     "car4",
    },
}


# ===========================================================================
# 2) THANG ĐIỂM & ĐƠN GIÁ MỖI ĐIỂM CHO TỪNG YẾU TỐ
# ===========================================================================
RATE_PER_POINT = {
    "weather":   1_500,
    "traffic":   1_200,
    "demand":    2_000,
    "time":      1_500,
    "pickup":    2_000,
}

VEHICLE_FACTOR = {
    "bike": 1.0, "bike_eco": 0.9,
    "ev":   1.0,
    "car4": 1.6, "car_eco": 1.5,
    "car7": 2.0,
}

INSURANCE_TABLE = {
    0: {"label": "Không mua bảo hiểm", "fee": 0},
    1: {"label": "Bảo hiểm cơ bản",    "fee": 5_000},
    2: {"label": "Bảo hiểm cao cấp",   "fee": 12_000},
}


# ===========================================================================
# 3) HÀM TÍNH TIỀN CHO TỪNG YẾU TỐ
# ===========================================================================
def fee_distance(distance_km: float, vehicle: str) -> dict:
    v = VEHICLE_TABLE.get(vehicle, VEHICLE_TABLE["bike"])
    fee = round(float(distance_km) * v["per_km"])
    return {
        "label":          f"Khoảng cách ({v['label']})",
        "score":          round(float(distance_km), 2),
        "scale_max":      None,
        "rate_per_point": v["per_km"],
        "fee":            fee,
        "note":           f"{distance_km:.2f} km × {v['per_km']:,}đ/km",
    }


def fee_opening(vehicle: str) -> dict:
    v = VEHICLE_TABLE.get(vehicle, VEHICLE_TABLE["bike"])
    return {
        "label":          f"Phí mở cửa ({v['label']})",
        "score":          1,
        "scale_max":      None,
        "rate_per_point": v["opening_fee"],
        "fee":            v["opening_fee"],
        "note":           "Phí cố định khi bắt đầu chuyến",
    }


def fee_weather(weather_score: int, vehicle: str) -> dict:
    rate   = RATE_PER_POINT["weather"]
    factor = VEHICLE_FACTOR.get(vehicle, 1.0)
    fee    = round(weather_score * rate * factor)
    return {
        "label":          "Thời tiết",
        "score":          weather_score,
        "scale_max":      10,
        "rate_per_point": rate,
        "fee":            fee,
        "note":           f"{weather_score}/10 × {rate:,}đ × {factor:.1f}",
    }


def fee_traffic(traffic_score: int, vehicle: str) -> dict:
    rate   = RATE_PER_POINT["traffic"]
    factor = VEHICLE_FACTOR.get(vehicle, 1.0)
    fee    = round(traffic_score * rate * factor)
    return {
        "label":          "Giao thông",
        "score":          traffic_score,
        "scale_max":      10,
        "rate_per_point": rate,
        "fee":            fee,
        "note":           f"{traffic_score}/10 × {rate:,}đ × {factor:.1f}",
    }


def fee_demand(demand_score: int, vehicle: str) -> dict:
    rate   = RATE_PER_POINT["demand"]
    factor = VEHICLE_FACTOR.get(vehicle, 1.0)
    fee    = round(demand_score * rate * factor)
    return {
        "label":          "Mức cầu (giờ đặt xe)",
        "score":          demand_score,
        "scale_max":      10,
        "rate_per_point": rate,
        "fee":            fee,
        "note":           f"{demand_score}/10 × {rate:,}đ × {factor:.1f}",
    }


def time_of_day_score(now: datetime | None = None) -> int:
    now = now or datetime.now()
    h = now.hour
    if 0 <= h < 5:   return 8
    if h == 5:       return 3
    if h == 6:       return 1
    if 7 <= h < 21:  return 0
    if h == 21:      return 2
    if 22 <= h < 24: return 6
    return 0


def fee_time(now: datetime | None = None, vehicle: str = "bike") -> dict:
    score  = time_of_day_score(now)
    rate   = RATE_PER_POINT["time"]
    factor = VEHICLE_FACTOR.get(vehicle, 1.0)
    fee    = round(score * rate * factor)
    h      = (now or datetime.now()).hour
    return {
        "label":          f"Giờ trong ngày ({h:02d}:00)",
        "score":          score,
        "scale_max":      10,
        "rate_per_point": rate,
        "fee":            fee,
        "note":           f"{score}/10 × {rate:,}đ × {factor:.1f}",
    }


def fee_pickup(pickup_score: int, vehicle: str) -> dict:
    rate   = RATE_PER_POINT["pickup"]
    factor = VEHICLE_FACTOR.get(vehicle, 1.0)
    fee    = round(pickup_score * rate * factor)
    return {
        "label":          "Độ khó đón khách",
        "score":          pickup_score,
        "scale_max":      5,
        "rate_per_point": rate,
        "fee":            fee,
        "note":           f"{pickup_score}/5 × {rate:,}đ × {factor:.1f}",
    }


def fee_insurance(level: int) -> dict:
    cfg = INSURANCE_TABLE.get(int(level), INSURANCE_TABLE[0])
    return {
        "label":          "Bảo hiểm chuyến đi",
        "score":          int(level),
        "scale_max":      2,
        "rate_per_point": None,
        "fee":            cfg["fee"],
        "note":           cfg["label"],
    }


def fee_tip(tip: int) -> dict:
    tip = max(0, int(tip or 0))
    return {
        "label":          "Tip cho tài xế",
        "score":          tip,
        "scale_max":      None,
        "rate_per_point": 1,
        "fee":            tip,
        "note":           "Tip do bạn chọn, đi 100% cho tài xế",
    }


# ===========================================================================
# 4) FUZZY LOGIC SURCHARGE — dùng 100% cấu trúc scikit-fuzzy (tham khảo)
# ===========================================================================
# Cache control system để không khởi tạo lại mỗi lần gọi
_fuzzy_ctrl_cache: ctrl.ControlSystem | None = None


def _get_fuzzy_ctrl() -> ctrl.ControlSystem:
    """Xây dựng và cache hệ thống điều khiển mờ (chỉ tạo một lần)."""
    global _fuzzy_ctrl_cache
    if _fuzzy_ctrl_cache is not None:
        return _fuzzy_ctrl_cache

    # ==========================================
    # KHỞI TẠO BIẾN ĐẦU VÀO
    # ==========================================
    weather = ctrl.Antecedent(np.arange(0, 11, 1), 'weather')    # 0–10
    traffic = ctrl.Antecedent(np.arange(0, 101, 1), 'traffic')   # 0–100 %
    pickup  = ctrl.Antecedent(np.arange(0, 6, 1),  'pickup')     # 0–5

    # ==========================================
    # KHỞI TẠO BIẾN ĐẦU RA
    # ==========================================
    surcharge = ctrl.Consequent(np.arange(0, 1001, 1), 'surcharge')

    # ==========================================
    # ĐỊNH NGHĨA TẬP MỜ (MEMBERSHIP FUNCTIONS)
    # ==========================================
    # 1. Weather (Thời tiết: 0=Tốt, 5=TB, 10=Xấu)
    weather['low']    = fuzz.trimf(weather.universe, [0, 0, 4])
    weather['medium'] = fuzz.trimf(weather.universe, [3, 5, 7])
    weather['high']   = fuzz.trapmf(weather.universe, [6, 8, 10, 10])

    # 2. Traffic (Lưu lượng giao thông: 0–100 %)
    traffic['low']    = fuzz.trimf(traffic.universe,  [0,  0,  30])
    traffic['medium'] = fuzz.trimf(traffic.universe,  [20, 45, 70])
    traffic['high']   = fuzz.trapmf(traffic.universe, [60, 80, 100, 100])

    # 3. Pickup (Độ khó đón khách: 0–5)
    pickup['low']    = fuzz.trimf(pickup.universe,  [0, 0, 2])
    pickup['medium'] = fuzz.trimf(pickup.universe,  [1, 2, 4])
    pickup['high']   = fuzz.trapmf(pickup.universe, [3, 4, 5, 5])

    # 4. Surcharge (Phụ phí: 0–1.000đ)
    surcharge['none']   = fuzz.trimf(surcharge.universe,  [0,   0,   300])
    surcharge['medium'] = fuzz.trimf(surcharge.universe,  [200, 500, 800])
    surcharge['high']   = fuzz.trapmf(surcharge.universe, [700, 1000, 1000, 1000])

    # ==========================================
    # THIẾT LẬP 27 LUẬT MỜ — TẤT CẢ TỔ HỢP
    # ==========================================
    rule1  = ctrl.Rule(weather['low']    & traffic['low']    & pickup['low'],    surcharge['none'])
    rule2  = ctrl.Rule(weather['low']    & traffic['low']    & pickup['medium'], surcharge['none'])
    rule3  = ctrl.Rule(weather['low']    & traffic['low']    & pickup['high'],   surcharge['medium'])
    rule4  = ctrl.Rule(weather['low']    & traffic['medium'] & pickup['low'],    surcharge['none'])
    rule5  = ctrl.Rule(weather['low']    & traffic['medium'] & pickup['medium'], surcharge['medium'])
    rule6  = ctrl.Rule(weather['low']    & traffic['medium'] & pickup['high'],   surcharge['medium'])
    rule7  = ctrl.Rule(weather['low']    & traffic['high']   & pickup['low'],    surcharge['medium'])
    rule8  = ctrl.Rule(weather['low']    & traffic['high']   & pickup['medium'], surcharge['medium'])
    rule9  = ctrl.Rule(weather['low']    & traffic['high']   & pickup['high'],   surcharge['high'])
    rule10 = ctrl.Rule(weather['medium'] & traffic['low']    & pickup['low'],    surcharge['none'])
    rule11 = ctrl.Rule(weather['medium'] & traffic['low']    & pickup['medium'], surcharge['medium'])
    rule12 = ctrl.Rule(weather['medium'] & traffic['low']    & pickup['high'],   surcharge['medium'])
    rule13 = ctrl.Rule(weather['medium'] & traffic['medium'] & pickup['low'],    surcharge['medium'])
    rule14 = ctrl.Rule(weather['medium'] & traffic['medium'] & pickup['medium'], surcharge['medium'])
    rule15 = ctrl.Rule(weather['medium'] & traffic['medium'] & pickup['high'],   surcharge['medium'])
    rule16 = ctrl.Rule(weather['medium'] & traffic['high']   & pickup['low'],    surcharge['medium'])
    rule17 = ctrl.Rule(weather['medium'] & traffic['high']   & pickup['medium'], surcharge['high'])
    rule18 = ctrl.Rule(weather['medium'] & traffic['high']   & pickup['high'],   surcharge['high'])
    rule19 = ctrl.Rule(weather['high']   & traffic['low']    & pickup['low'],    surcharge['medium'])
    rule20 = ctrl.Rule(weather['high']   & traffic['low']    & pickup['medium'], surcharge['medium'])
    rule21 = ctrl.Rule(weather['high']   & traffic['low']    & pickup['high'],   surcharge['high'])
    rule22 = ctrl.Rule(weather['high']   & traffic['medium'] & pickup['low'],    surcharge['medium'])
    rule23 = ctrl.Rule(weather['high']   & traffic['medium'] & pickup['medium'], surcharge['high'])
    rule24 = ctrl.Rule(weather['high']   & traffic['medium'] & pickup['high'],   surcharge['high'])
    rule25 = ctrl.Rule(weather['high']   & traffic['high']   & pickup['low'],    surcharge['high'])
    rule26 = ctrl.Rule(weather['high']   & traffic['high']   & pickup['medium'], surcharge['high'])
    rule27 = ctrl.Rule(weather['high']   & traffic['high']   & pickup['high'],   surcharge['high'])

    # ==========================================
    # HỆ THỐNG ĐIỀU KHIỂN
    # ==========================================
    _fuzzy_ctrl_cache = ctrl.ControlSystem([
        rule1,  rule2,  rule3,  rule4,  rule5,  rule6,  rule7,  rule8,  rule9,
        rule10, rule11, rule12, rule13, rule14, rule15, rule16, rule17, rule18,
        rule19, rule20, rule21, rule22, rule23, rule24, rule25, rule26, rule27,
    ])
    return _fuzzy_ctrl_cache


def fuzzy_surcharge(*, weather_score: int, traffic_score: int,
                    pickup_score: int) -> dict:
    """
    Tính phụ phí dựa trên Fuzzy Logic (scikit-fuzzy).

    Ba yếu tố đầu vào:
      - weather_score : 0–10  (thời tiết)
      - traffic_score : 0–10  (giao thông — tự động quy đổi sang 0–100 %)
      - pickup_score  : 0–5   (độ khó đón)

    Đầu ra: phụ phí 0 / 500 / 1.000đ (làm tròn về mức gần nhất).
    """
    # Quy đổi traffic 0-10 → 0-100 để khớp với định nghĩa tập mờ (tham khảo)
    traffic_pct = float(traffic_score) * 10.0
    w_val = float(max(0, min(10, weather_score)))
    p_val = float(max(0, min(5,  pickup_score)))

    try:
        sim = ctrl.ControlSystemSimulation(_get_fuzzy_ctrl())
        sim.input['weather'] = w_val
        sim.input['traffic'] = traffic_pct
        sim.input['pickup']  = p_val
        sim.compute()
        raw_fee = sim.output['surcharge']
    except Exception:
        raw_fee = 0.0

    # Làm tròn về bậc thang 0 / 500 / 1.000
    if raw_fee >= 750:
        fee = 1_000
    elif raw_fee >= 250:
        fee = 500
    else:
        fee = 0

    if fee == 1_000:
        note = f"Thời tiết {weather_score}/10 • Giao thông {traffic_score}/10 • Đón khách {pickup_score}/5 → cả 3 yếu tố cao"
    elif fee == 500:
        note = f"Thời tiết {weather_score}/10 • Giao thông {traffic_score}/10 • Đón khách {pickup_score}/5 → yếu tố trung bình"
    else:
        note = f"Thời tiết {weather_score}/10 • Giao thông {traffic_score}/10 • Đón khách {pickup_score}/5 → điều kiện tốt"

    return {
        "label":          "Phụ phí thu thêm" if fee > 0 else "Phụ phí thu thêm",
        "score":          fee,
        "scale_max":      None,
        "rate_per_point": None,
        "fee":            fee,
        "note":           note,
    }


def calc_savings(vehicle: str, distance_km: float) -> int:
    eco_ref = VEHICLE_TABLE.get(vehicle, {}).get("eco_ref")
    if not eco_ref:
        return 0
    eco    = (VEHICLE_TABLE[vehicle]["opening_fee"]
              + round(distance_km * VEHICLE_TABLE[vehicle]["per_km"]))
    normal = (VEHICLE_TABLE[eco_ref]["opening_fee"]
              + round(distance_km * VEHICLE_TABLE[eco_ref]["per_km"]))
    return max(0, normal - eco)


# ===========================================================================
# 5) HÀM TỔNG — gọi hết các hàm trên & ra giá cuối cùng
# ===========================================================================
def compute_total_fare(*, vehicle: str = "bike",
                       distance_km: float = 0.0,
                       pickup_lat: float | None = None,
                       pickup_lng: float | None = None,
                       insurance_level: int = 0,
                       tip: int = 0,
                       promo_code: str | None = None,
                       now: datetime | None = None) -> dict:
    now = now or datetime.now()

    weather_score, weather_info = weather_api.get_weather_score()
    traffic_score, traffic_info = traffic_api.get_traffic_score(now)
    demand_score,  demand_info  = traffic_api.get_demand_score(now)
    pickup_score,  pickup_info  = traffic_api.get_pickup_difficulty_score(
        pickup_lat, pickup_lng)

    items = [
        fee_opening(vehicle),
        fee_distance(distance_km, vehicle),
        fee_weather(weather_score, vehicle),
        fee_traffic(traffic_score, vehicle),
        fee_demand(demand_score, vehicle),
        fee_time(now, vehicle),
        fee_pickup(pickup_score, vehicle),
        fuzzy_surcharge(
            weather_score=weather_score,
            traffic_score=traffic_score,
            pickup_score=pickup_score,
        ),
        fee_insurance(insurance_level),
        fee_tip(tip),
    ]

    subtotal = sum(it["fee"] for it in items)

    promo_discount = 0
    promo_label    = None
    if promo_code:
        code = promo_code.strip().upper()
        if code == "RIDEPRO10":
            promo_discount = round(subtotal * 0.10)
            promo_label    = "Giảm 10% (RIDEPRO10)"
        elif code == "NEW20":
            promo_discount = min(20_000, round(subtotal * 0.20))
            promo_label    = "Giảm 20% tối đa 20K (NEW20)"
        elif code == "FREESHIP5K":
            promo_discount = 5_000
            promo_label    = "Giảm 5.000đ (FREESHIP5K)"

    total   = max(0, subtotal - promo_discount)
    savings = calc_savings(vehicle, distance_km)

    eta_pickup_min = max(2, 3 + int(traffic_score / 2) + int(pickup_score))
    eta_trip_min   = max(5, int(distance_km * 2.5) + int(traffic_score))

    return {
        "vehicle":       vehicle,
        "vehicle_label": VEHICLE_TABLE.get(vehicle, {}).get("label", vehicle),
        "distance_km":   round(float(distance_km), 2),
        "items":         items,
        "subtotal":      subtotal,
        "promo": {
            "code":     (promo_code or "").strip().upper() or None,
            "label":    promo_label,
            "discount": promo_discount,
        },
        "total":              total,
        "savings_vs_normal":  savings,
        "eta_pickup_min":     eta_pickup_min,
        "eta_trip_min":       eta_trip_min,
        "factors": {
            "weather": weather_info,
            "traffic": traffic_info,
            "demand":  demand_info,
            "pickup":  pickup_info,
            "time_of_day": {
                "score":     time_of_day_score(now),
                "scale_max": 10,
                "hour":      now.hour,
            },
        },
    }
