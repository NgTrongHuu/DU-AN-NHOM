"""
backend.py
----------
Lớp `BackendManager` + thiết lập Flask app cho RidePro.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from threading import Lock

from flask import Flask, jsonify, render_template, request

import places
import external_api
import pricing
import weather_api
import traffic_api


HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "history.json")
MAX_HISTORY      = 200
MAX_RECENT_PLACES = 6


class BackendManager:

    def __init__(self) -> None:
        self._history_lock = Lock()
        self.center = places.get_default_center()

    def _load_history_raw(self) -> list[dict]:
        if not os.path.exists(HISTORY_FILE):
            return []
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save_history_raw(self, history: list[dict]) -> None:
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history[-MAX_HISTORY:], f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def add_ride_to_history(self, ride: dict) -> None:
        if not ride.get("pickup") or not ride.get("dest"):
            return
        with self._history_lock:
            history = self._load_history_raw()
            history.append(ride)
            self._save_history_raw(history)

    def get_full_history(self) -> list[dict]:
        with self._history_lock:
            history = self._load_history_raw()
        return list(reversed(history))

    def get_recent_places(self) -> list[dict]:
        history = self.get_full_history()
        if not history:
            return []
        seen: set[str] = set()
        result: list[dict] = []
        for ride in history:
            for role, addr in (("dest", ride.get("dest")),
                               ("pickup", ride.get("pickup"))):
                if not addr:
                    continue
                key = addr.strip().lower()
                if key in seen:
                    continue
                seen.add(key)
                result.append({
                    "icon": "dest" if role == "dest" else "pickup",
                    "name": "Điểm đến" if role == "dest" else "Điểm đón",
                    "addr": addr.strip(),
                })
                if len(result) >= MAX_RECENT_PLACES:
                    return result
        return result

    def get_stats(self) -> dict:
        history = self.get_full_history()
        trips       = len(history)
        savings     = sum(int(r.get("savings", 0) or 0) for r in history)
        total_spent = sum(int(r.get("total", 0) or 0) for r in history)
        total_km    = round(sum(float(r.get("distance_km", 0) or 0) for r in history), 1)
        return {
            "trips":       trips,
            "rating":      5.0,
            "savings":     savings,
            "total_spent": total_spent,
            "total_km":    total_km,
        }


def setup_backend() -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    manager = BackendManager()

    @app.route("/")
    def index():
        return render_template(
            "frontend.html",
            recent_places=manager.get_recent_places(),
            stats=manager.get_stats(),
            map_center=list(manager.center),
            ring1=places.RING1_BBOX,
        )

    @app.route("/static/manifest.json")
    def pwa_manifest():
        from flask import send_from_directory
        return send_from_directory("static", "manifest.json",
                                   mimetype="application/manifest+json")

    @app.route("/static/sw.js")
    def pwa_sw():
        from flask import send_from_directory
        return send_from_directory("static", "sw.js",
                                   mimetype="application/javascript")

    @app.route("/api/places", methods=["GET"])
    def api_places():
        q     = request.args.get("q", "").strip()
        limit = max(1, min(20, int(request.args.get("limit", 8))))
        items, source = external_api.search(q, limit)
        return jsonify({"ok": True, "data": items, "source": source})

    @app.route("/api/nearest", methods=["GET"])
    def api_nearest():
        try:
            lat = float(request.args.get("lat"))
            lng = float(request.args.get("lng"))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Toạ độ không hợp lệ."}), 400
        place, source = external_api.reverse(lat, lng)
        if not place:
            msg = ("Ngoài Vành đai 1." if source == "outside"
                   else "Không tra được địa chỉ.")
            return jsonify({"ok": False, "error": msg, "source": source}), 400
        return jsonify({"ok": True, "data": place, "source": source})

    @app.route("/api/route", methods=["POST"])
    def api_route():
        data    = request.get_json(silent=True) or {}
        raw_pts = data.get("points") or []
        try:
            coords = [(float(p["lat"]), float(p["lng"])) for p in raw_pts]
        except (KeyError, TypeError, ValueError):
            return jsonify({"ok": False, "error": "Dữ liệu điểm không hợp lệ."}), 400
        if len(coords) < 2:
            return jsonify({"ok": False, "error": "Cần ít nhất 2 điểm."}), 400
        result, source = external_api.route(coords)
        result["source"] = source
        return jsonify(result)

    @app.route("/api/conditions", methods=["GET"])
    def api_conditions():
        try:
            lat = request.args.get("pickup_lat", type=float)
            lng = request.args.get("pickup_lng", type=float)
        except (TypeError, ValueError):
            lat = lng = None
        weather_score, weather_info = weather_api.get_weather_score()
        traffic_score, traffic_info = traffic_api.get_traffic_score()
        demand_score,  demand_info  = traffic_api.get_demand_score()
        pickup_score,  pickup_info  = traffic_api.get_pickup_difficulty_score(lat, lng)
        return jsonify({"ok": True, "data": {
            "weather": weather_info,
            "traffic": traffic_info,
            "demand":  demand_info,
            "pickup":  pickup_info,
            "time_of_day": {
                "score":     pricing.time_of_day_score(),
                "scale_max": 10,
                "hour":      datetime.now().hour,
            },
        }})

    @app.route("/api/pricing", methods=["POST"])
    def api_pricing():
        data   = request.get_json(silent=True) or {}
        result = pricing.compute_total_fare(
            vehicle=str(data.get("vehicle", "bike")),
            distance_km=float(data.get("distance_km", 0) or 0),
            pickup_lat=data.get("pickup_lat"),
            pickup_lng=data.get("pickup_lng"),
            insurance_level=int(data.get("insurance_level", 0) or 0),
            tip=int(data.get("tip", 0) or 0),
            promo_code=data.get("promo_code"),
        )
        return jsonify({"ok": True, "data": result})

    @app.route("/api/recent-places", methods=["GET"])
    def api_recent_places():
        return jsonify({"ok": True, "data": manager.get_recent_places()})

    @app.route("/api/history", methods=["GET"])
    def api_history():
        return jsonify({"ok": True, "data": manager.get_full_history()})

    @app.route("/api/stats", methods=["GET"])
    def api_stats():
        return jsonify({"ok": True, "data": manager.get_stats()})

    @app.route("/api/book", methods=["POST"])
    def api_book():
        data            = request.get_json(silent=True) or {}
        pickup          = str(data.get("pickup", "")).strip()
        dest            = str(data.get("dest", "")).strip()
        stop            = str(data.get("stop", "")).strip()
        vehicle         = str(data.get("vehicle", "bike"))
        distance_km     = float(data.get("distance_km", 0) or 0)
        tip             = int(data.get("tip", 0) or 0)
        insurance_level = int(data.get("insurance_level", 0) or 0)
        payment         = str(data.get("payment", "cash"))
        promo_code      = data.get("promo_code")
        phone           = str(data.get("phone", "")).strip()
        note            = str(data.get("note", "")).strip()

        pickup_coord = data.get("pickup_coord") or {}
        try:
            pickup_lat = float(pickup_coord.get("lat")) if pickup_coord else None
            pickup_lng = float(pickup_coord.get("lng")) if pickup_coord else None
        except (TypeError, ValueError):
            pickup_lat = pickup_lng = None

        fare    = pricing.compute_total_fare(
            vehicle=vehicle, distance_km=distance_km,
            pickup_lat=pickup_lat, pickup_lng=pickup_lng,
            insurance_level=insurance_level, tip=tip,
            promo_code=promo_code,
        )
        savings = pricing.calc_savings(vehicle, distance_km)

        ride = {
            "pickup":          pickup,
            "dest":            dest,
            "stop":            stop,
            "pickup_coord":    pickup_coord,
            "dest_coord":      data.get("dest_coord"),
            "stop_coord":      data.get("stop_coord"),
            "vehicle":         vehicle,
            "vehicle_label":   fare["vehicle_label"],
            "distance_km":     distance_km,
            "tip":             tip,
            "insurance_level": insurance_level,
            "payment":         payment,
            "promo_code":      (promo_code or "").strip().upper() or None,
            "promo_discount":  fare["promo"]["discount"],
            "phone":           phone,
            "note":            note,
            "fare":            fare,
            "total":           fare["total"],
            "savings":         savings,
            "timestamp":       datetime.now().isoformat(timespec="seconds"),
        }
        manager.add_ride_to_history(ride)

        return jsonify({
            "ok":      True,
            "message": "Đặt xe thành công! Tài xế sẽ liên lạc với bạn trong giây lát.",
            "ride":    ride,
        })

    return app
