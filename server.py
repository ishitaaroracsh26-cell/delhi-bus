"""
DilliTransit - Delhi Real-Time Bus Traffic Model & Journey Planner
Production-grade HTTP Server built using Python Standard Library (zero external dependencies).
Provides REST APIs for journey planning, GTFS routing, traffic physics modeling, and static web serving.
"""

import http.server
import socketserver
import json
import urllib.parse
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any

from transit_data import STOPS, ROUTES, CORRIDORS, AMENITIES
from traffic_model import DelhiBusTrafficModel
from journey_planner import DelhiJourneyPlanner
from otd_client import DelhiOTDClient
from hyperlocal_engine import (
    get_stop_hyperlocal_intelligence,
    calculate_ncmc_fare,
    generate_sos_dispatch
)
from seat_model import (
    generate_bus_seat_layout,
    reserve_bus_seat
)

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"

traffic_model = DelhiBusTrafficModel()
journey_planner = DelhiJourneyPlanner(traffic_model)
otd_client = DelhiOTDClient()
SERVER_START_TIME = time.time()

class DilliTransitRequestHandler(http.server.BaseHTTPRequestHandler):
    """Multi-threaded REST and static file request handler."""

    def end_headers(self):
        # Enable CORS headers for hackathon evaluation and local testing
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_HEAD(self):
        self.do_GET(head_only=True)

    def send_json(self, status_code: int, data: Any, head_only: bool = False):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def do_GET(self, head_only: bool = False):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. API Endpoints
        if path == "/api/health":
            self.handle_health(head_only=head_only)
        elif path == "/api/stops":
            self.handle_stops(query, head_only=head_only)
        elif path == "/api/plan":
            self.handle_plan(query, head_only=head_only)
        elif path == "/api/routes":
            self.handle_routes(head_only=head_only)
        elif path.startswith("/api/route/"):
            route_id = path.replace("/api/route/", "").strip()
            self.handle_single_route(route_id, head_only=head_only)
        elif path == "/api/live-buses":
            self.handle_live_buses(query, head_only=head_only)
        elif path == "/api/traffic-model":
            self.handle_traffic_model(head_only=head_only)
        elif path == "/api/corridors":
            self.handle_corridors(head_only=head_only)
        elif path == "/api/amenities":
            self.handle_amenities(query, head_only=head_only)
        elif path == "/api/hyperlocal":
            self.handle_hyperlocal(query, head_only=head_only)
        elif path == "/api/ncmc-calc":
            self.handle_ncmc_calc(query, head_only=head_only)
        elif path == "/api/sos":
            self.handle_sos(query, head_only=head_only)
        elif path == "/api/seats":
            self.handle_seats(query, head_only=head_only)
        # 2. Static Web Assets
        else:
            self.serve_static(path, head_only=head_only)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/scenario":
            content_length = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_length)
            try:
                data = json.loads(post_body.decode("utf-8")) if post_body else {}
                scenario = data.get("scenario", "normal")
                traffic_model.set_scenario(scenario)
                self.send_json(200, {
                    "success": True,
                    "scenario": traffic_model.scenario,
                    "message": f"Traffic scenario switched to '{scenario}'",
                    "updated_at": time.time()
                })
            except Exception as e:
                self.send_json(400, {"success": False, "error": str(e)})
        elif path == "/api/reserve-seat":
            content_length = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_length)
            try:
                data = json.loads(post_body.decode("utf-8")) if post_body else {}
                route_id = data.get("route_id", "502")
                fleet_plate = data.get("fleet_plate", "DL-1PD-4521")
                seat_id = data.get("seat_id", "W1")
                name = data.get("passenger_name", "Delhi Commuter")
                gender = data.get("gender", "Female")
                boarding_stop = data.get("boarding_stop", "Kashmere Gate ISBT")

                reservation = reserve_bus_seat(
                    route_id=route_id,
                    fleet_plate=fleet_plate,
                    seat_id=seat_id,
                    passenger_name=name,
                    gender=gender,
                    boarding_stop=boarding_stop
                )
                self.send_json(200, {"success": True, "reservation": reservation})
            except Exception as e:
                self.send_json(400, {"success": False, "error": str(e)})
        else:
            self.send_json(404, {"error": "Endpoint not found"})

    def handle_health(self, head_only: bool = False):
        feed_info = otd_client.get_feed_status()
        self.send_json(200, {
            "status": "healthy",
            "service": "DilliTransit - Delhi Real-Time Bus Traffic Model & Journey Planner",
            "version": "1.0.0",
            "uptime_seconds": int(time.time() - SERVER_START_TIME),
            "data_source": feed_info,
            "counts": {
                "stops": len(STOPS),
                "routes": len(ROUTES),
                "corridors": len(CORRIDORS),
                "amenities": len(AMENITIES)
            },
            "active_scenario": traffic_model.scenario
        }, head_only=head_only)

    def handle_stops(self, query: Dict[str, list], head_only: bool = False):
        q = query.get("q", [""])[0].lower().strip()
        results = []
        for sid, s in STOPS.items():
            if not q or (q in sid.lower() or q in s["name"].lower() or q in s.get("name_hi", "").lower() or q in s.get("zone", "").lower()):
                # Count routes serving this stop
                serving_routes = [r["short_name"] for r in ROUTES.values() if sid in r["stops"]]
                results.append({
                    **s,
                    "serving_routes": serving_routes,
                    "route_count": len(serving_routes)
                })

        # Sort hubs first, then alphabetically
        results.sort(key=lambda x: (not x.get("is_hub", False), x["name"]))
        self.send_json(200, {"count": len(results), "stops": results}, head_only=head_only)

    def handle_plan(self, query: Dict[str, list], head_only: bool = False):
        origin = query.get("origin", [""])[0]
        destination = query.get("destination", [""])[0]

        if not origin or not destination:
            self.send_json(400, {
                "success": False,
                "error": "Missing 'origin' or 'destination' query parameters."
            }, head_only=head_only)
            return

        result = journey_planner.plan_journey(origin, destination)
        result["data_source"] = otd_client.get_feed_status()
        self.send_json(200 if result.get("success") else 404, result, head_only=head_only)

    def handle_routes(self, head_only: bool = False):
        summaries = []
        for rid, r in ROUTES.items():
            summaries.append({
                "id": r["id"],
                "short_name": r["short_name"],
                "long_name": r["long_name"],
                "agency": r["agency"],
                "bus_type": r["bus_type"],
                "stops_count": len(r["stops"]),
                "frequency_min": r.get("frequency_min", 10),
                "operating_hours": r.get("operating_hours", ""),
                "first_stop": STOPS[r["stops"][0]]["name"],
                "last_stop": STOPS[r["stops"][-1]]["name"],
                "color": r.get("color", "#2563eb")
            })
        self.send_json(200, {"count": len(summaries), "routes": summaries}, head_only=head_only)

    def handle_single_route(self, route_id: str, head_only: bool = False):
        route = ROUTES.get(route_id)
        if not route:
            self.send_json(404, {"error": f"Route '{route_id}' not found."}, head_only=head_only)
            return

        stops_detail = []
        geometry = []
        for sid in route["stops"]:
            stop = STOPS.get(sid)
            if stop:
                stops_detail.append(stop)
                geometry.append([stop["lat"], stop["lon"]])

        active_buses = traffic_model.generate_live_buses(route_id)
        self.send_json(200, {
            "route": route,
            "stops": stops_detail,
            "geometry": geometry,
            "active_buses": active_buses
        }, head_only=head_only)

    def handle_live_buses(self, query: Dict[str, list], head_only: bool = False):
        route_id = query.get("route_id", [None])[0]
        buses = traffic_model.generate_live_buses(route_id)
        feed_info = otd_client.get_feed_status()
        self.send_json(200, {
            "timestamp": time.time(),
            "data_source": feed_info,
            "count": len(buses),
            "buses": buses
        }, head_only=head_only)

    def handle_traffic_model(self, head_only: bool = False):
        summary = traffic_model.get_model_summary()
        summary["data_source"] = otd_client.get_feed_status()
        self.send_json(200, summary, head_only=head_only)

    def handle_corridors(self, head_only: bool = False):
        corridor_data = []
        for cid in CORRIDORS.keys():
            corridor_data.append(traffic_model.get_corridor_speed(cid))
        self.send_json(200, {"corridors": corridor_data}, head_only=head_only)

    def handle_amenities(self, query: Dict[str, list], head_only: bool = False):
        stop_id = query.get("stop_id", [""])[0].strip()
        category = query.get("category", [""])[0].strip().lower()
        q = query.get("q", [""])[0].strip().lower()

        results = []
        for aid, am in AMENITIES.items():
            # Filter by stop_id if requested
            if stop_id and am["stop_id"] != stop_id:
                continue
            # Filter by category if requested
            if category and am["category"] != category:
                continue
            # Filter by search query
            if q and not (q in am["name"].lower() or q in am.get("name_hi", "").lower() or q in am["details"].lower() or any(q in t.lower() for t in am.get("tags", []))):
                continue
            results.append(am)

        # Sort: pink_toilet & metro first, then distance
        priority = {"pink_toilet": 1, "metro": 2, "hospital": 3, "cafe": 4, "cinema": 5}
        results.sort(key=lambda a: (priority.get(a["category"], 9), a.get("distance_m", 999)))
        self.send_json(200, {"count": len(results), "amenities": results}, head_only=head_only)

    def handle_hyperlocal(self, query: Dict[str, list], head_only: bool = False):
        stop_id = query.get("stop_id", [""])[0].strip()
        if not stop_id or stop_id not in STOPS:
            self.send_json(400, {"success": False, "error": "Invalid or missing 'stop_id' parameter"}, head_only=head_only)
            return

        intel = get_stop_hyperlocal_intelligence(stop_id)
        stop = STOPS[stop_id]
        self.send_json(200, {
            "success": True,
            "stop_id": stop_id,
            "stop_name": stop["name"],
            "stop_name_hi": stop.get("name_hi", ""),
            "lat": stop["lat"],
            "lon": stop["lon"],
            "zone": stop.get("zone", "Delhi"),
            "intelligence": intel
        }, head_only=head_only)

    def handle_ncmc_calc(self, query: Dict[str, list], head_only: bool = False):
        fare_str = query.get("fare", ["25"])[0]
        mode = query.get("mode", ["bus"])[0]
        try:
            base_fare = int(fare_str)
        except ValueError:
            base_fare = 25

        calc = calculate_ncmc_fare(base_fare, mode=mode)
        self.send_json(200, {"success": True, "fare_comparison": calc}, head_only=head_only)

    def handle_sos(self, query: Dict[str, list], head_only: bool = False):
        stop_id = query.get("stop_id", ["KG_ISBT"])[0]
        fleet = query.get("fleet", ["DL-1PD-4521"])[0]
        route = query.get("route", ["502"])[0]
        stop = STOPS.get(stop_id, STOPS["KG_ISBT"])

        dispatch = generate_sos_dispatch({"route_short_name": route}, stop, fleet)
        self.send_json(200, {"success": True, "sos": dispatch}, head_only=head_only)

    def handle_seats(self, query: Dict[str, list], head_only: bool = False):
        route_id = query.get("route_id", ["502"])[0]
        fleet_plate = query.get("fleet_plate", ["DL-1PD-4521"])[0]
        crowd_str = query.get("crowd_pct", ["50"])[0]
        is_saheli_str = query.get("is_saheli", ["false"])[0]
        try:
            crowd_pct = int(crowd_str)
        except ValueError:
            crowd_pct = 50

        is_saheli = is_saheli_str.lower() in ["true", "1", "yes"]

        layout = generate_bus_seat_layout(
            route_id=route_id,
            fleet_plate=fleet_plate,
            crowd_pct=crowd_pct,
            is_saheli_pink=is_saheli
        )
        self.send_json(200, {"success": True, "seat_map": layout}, head_only=head_only)

    def serve_static(self, path: str, head_only: bool = False):
        if path == "/" or not path:
            file_path = PUBLIC_DIR / "index.html"
        else:
            rel = path.lstrip("/")
            file_path = PUBLIC_DIR / rel

        # Prevent directory traversal attacks
        try:
            resolved = file_path.resolve()
            if not str(resolved).startswith(str(PUBLIC_DIR.resolve())):
                self.send_json(403, {"error": "Forbidden"}, head_only=head_only)
                return
        except Exception:
            self.send_json(400, {"error": "Invalid path"}, head_only=head_only)
            return

        if not file_path.exists() or not file_path.is_file():
            # Fallback to index.html for SPA client-side routes
            file_path = PUBLIC_DIR / "index.html"

        ext = file_path.suffix.lower()
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".ico": "image/x-icon"
        }
        content_type = content_types.get(ext, "application/octet-stream")

        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if not head_only:
                self.wfile.write(content)
        except Exception as e:
            self.send_json(500, {"error": f"Failed to read file: {str(e)}"}, head_only=head_only)

def run_server(port: int = 8000, host: str = "0.0.0.0"):
    server_address = (host, port)
    # Using ThreadingHTTPServer for concurrent non-blocking handling
    httpd = http.server.ThreadingHTTPServer(server_address, DilliTransitRequestHandler)
    print(f"================================================================")
    print(f"  DilliTransit - Delhi Real-Time Bus Traffic Model & Planner    ")
    print(f"================================================================")
    print(f"  Listening on: http://localhost:{port} (http://127.0.0.1:{port})")
    print(f"  Serving files from: {PUBLIC_DIR}")
    print(f"  Network routes loaded: {len(ROUTES)} DTC/DIMTS routes")
    print(f"  Transit stops loaded: {len(STOPS)} Delhi transit hubs")
    print(f"  Traffic model status: {traffic_model.scenario.upper()} mode")
    print(f"================================================================")
    sys.stdout.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server gracefully...")
        httpd.server_close()

if __name__ == "__main__":
    port_env = os.environ.get("PORT", "8000")
    try:
        port = int(port_env)
    except ValueError:
        port = 8000
    host = os.environ.get("HOST", "0.0.0.0")
    run_server(port=port, host=host)
