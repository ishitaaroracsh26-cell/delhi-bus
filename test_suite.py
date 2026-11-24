"""
DilliTransit - Comprehensive Test Suite
Validates transit network topology, probe traffic physics calculations,
journey planning algorithms, bidirectional routing, and HTTP REST logic.
"""

import unittest
import json
import io
from transit_data import STOPS, ROUTES, CORRIDORS, AMENITIES
from traffic_model import DelhiBusTrafficModel, haversine_distance_km
from journey_planner import DelhiJourneyPlanner
from otd_client import DelhiOTDClient
from server import DilliTransitRequestHandler

class MockServer:
    """Mock server context for testing request handler logic in sandbox."""
    def __init__(self):
        self.server_name = "localhost"
        self.server_port = 8000

class TestDelhiTransitData(unittest.TestCase):
    def test_stops_integrity(self):
        self.assertGreaterEqual(len(STOPS), 40, "Should have at least 40 authentic Delhi stops")
        for sid, stop in STOPS.items():
            self.assertEqual(sid, stop["id"])
            self.assertTrue(28.4 <= stop["lat"] <= 28.9, f"Stop {sid} latitude out of Delhi bounds: {stop['lat']}")
            self.assertTrue(76.9 <= stop["lon"] <= 77.4, f"Stop {sid} longitude out of Delhi bounds: {stop['lon']}")
            self.assertIn("name", stop)
            self.assertIn("zone", stop)

    def test_routes_integrity(self):
        self.assertGreaterEqual(len(ROUTES), 10, "Should have at least 10 authentic routes")
        for rid, route in ROUTES.items():
            self.assertEqual(rid, route["id"])
            self.assertGreaterEqual(len(route["stops"]), 2, f"Route {rid} has fewer than 2 stops")
            for sid in route["stops"]:
                self.assertIn(sid, STOPS, f"Route {rid} references unknown stop {sid}")
            self.assertGreater(route.get("base_fare", 0), 0)
            self.assertGreater(route.get("frequency_min", 0), 0)

    def test_corridors_integrity(self):
        self.assertGreaterEqual(len(CORRIDORS), 5, "Should have at least 5 major corridors")
        for cid, corridor in CORRIDORS.items():
            self.assertGreater(corridor["free_flow_speed"], 20.0)
            for sid in corridor["stops"]:
                self.assertIn(sid, STOPS, f"Corridor {cid} references unknown stop {sid}")

    def test_amenities_integrity(self):
        self.assertGreaterEqual(len(AMENITIES), 20, "Should have at least 20 transit amenities")
        categories = set(a["category"] for a in AMENITIES.values())
        self.assertTrue({"pink_toilet", "metro", "hospital", "cafe", "cinema"}.issubset(categories),
                        "Must contain all 5 requested amenity categories")
        for aid, am in AMENITIES.items():
            self.assertEqual(aid, am["id"])
            self.assertIn(am["stop_id"], STOPS, f"Amenity {aid} references non-existent stop {am['stop_id']}")
            self.assertTrue(28.4 <= am["lat"] <= 28.9)
            self.assertTrue(76.9 <= am["lon"] <= 77.4)
            self.assertGreater(am.get("distance_m", 0), 0)

class TestTrafficPhysicsModel(unittest.TestCase):
    def setUp(self):
        self.model = DelhiBusTrafficModel()

    def test_haversine_distance(self):
        # Distance between Kashmere Gate and AIIMS is approx 11-12 km
        kg = STOPS["KG_ISBT"]
        aiims = STOPS["AIIMS"]
        dist = haversine_distance_km(kg["lat"], kg["lon"], aiims["lat"], aiims["lon"])
        self.assertTrue(10.0 <= dist <= 13.0, f"Calculated distance {dist} km is unexpected")

    def test_scenario_sensitivity(self):
        # Testing segment metrics between AIIMS and INA_MARKET
        self.model.set_scenario("off_peak")
        metrics_off = self.model.get_segment_metrics("AIIMS", "INA_MARKET")

        self.model.set_scenario("peak_rush")
        metrics_peak = self.model.get_segment_metrics("AIIMS", "INA_MARKET")

        self.assertGreater(metrics_off["current_speed_kmh"], metrics_peak["current_speed_kmh"],
                           "Off-peak speed must be faster than peak rush speed")
        self.assertGreater(metrics_peak["transit_time_min"], metrics_off["transit_time_min"],
                           "Peak rush transit time must be greater than off-peak")

    def test_dwell_time_hub_weight(self):
        # AIIMS is a hub, MOOLCHAND is a regular stop
        metrics_hub = self.model.get_segment_metrics("MOOLCHAND", "AIIMS")
        metrics_non_hub = self.model.get_segment_metrics("AIIMS", "MOOLCHAND")
        self.assertGreater(metrics_hub["dwell_time_min"], metrics_non_hub["dwell_time_min"],
                           "Hub boarding dwell time must be greater than standard stop")

    def test_live_buses_generation(self):
        buses = self.model.generate_live_buses("502")
        self.assertGreaterEqual(len(buses), 2, "Route 502 should have at least 2 active probe buses")
        for b in buses:
            self.assertEqual(b["route_id"], "502")
            self.assertTrue(28.4 <= b["lat"] <= 28.9)
            self.assertTrue(76.9 <= b["lon"] <= 77.4)
            self.assertTrue(0 <= b["heading"] <= 360)
            self.assertIn("DL-1P", b["vehicle_id"])

class TestDelhiJourneyPlanner(unittest.TestCase):
    def setUp(self):
        self.model = DelhiBusTrafficModel()
        self.planner = DelhiJourneyPlanner(self.model)

    def test_direct_journey_planning_forward(self):
        result = self.planner.plan_journey("KG_ISBT", "AIIMS")
        self.assertTrue(result["success"])
        self.assertGreaterEqual(len(result["journeys"]), 1)
        first_journey = result["journeys"][0]
        self.assertEqual(first_journey["type"], "DIRECT")
        self.assertIn("geometry", first_journey)
        self.assertGreaterEqual(len(first_journey["geometry"]), 2)
        self.assertGreater(first_journey["live_duration_min"], 0)
        self.assertGreater(first_journey["fare_inr"], 0)

    def test_direct_journey_planning_return(self):
        # Return direction from MORI_GATE to MEHRAULI (Southbound on 502)
        result = self.planner.plan_journey("MORI_GATE", "MEHRAULI")
        self.assertTrue(result["success"])
        self.assertGreaterEqual(len(result["journeys"]), 1)
        first_journey = result["journeys"][0]
        self.assertEqual(first_journey["type"], "DIRECT")
        self.assertEqual(first_journey["direction"], "Down")

    def test_transfer_journey_planning(self):
        # Cross-city journey: Najafgarh to Anand Vihar ISBT
        result = self.planner.plan_journey("NAJAFGARH", "ANAND_VIHAR")
        self.assertTrue(result["success"])
        self.assertGreaterEqual(len(result["journeys"]), 1)
        has_transfer = any(j["type"] == "1_TRANSFER" for j in result["journeys"])
        self.assertTrue(has_transfer, "Cross-city journey should find transfer options")

    def test_same_stop_rejection(self):
        result = self.planner.plan_journey("AIIMS", "AIIMS")
        self.assertFalse(result["success"])

class TestRequestHandlerLogic(unittest.TestCase):
    def setUp(self):
        self.captured_responses = []

    def mock_send_json(self, handler, status_code, data):
        self.captured_responses.append((status_code, data))

    def create_handler(self, method="GET", path="/api/health", body=b""):
        handler = DilliTransitRequestHandler.__new__(DilliTransitRequestHandler)
        handler.command = method
        handler.path = path
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        handler.server = MockServer()
        handler.client_address = ("127.0.0.1", 12345)
        # Patch send_json
        handler.send_json = lambda status, data, *args, **kwargs: self.mock_send_json(handler, status, data)
        return handler

    def test_health_api(self):
        h = self.create_handler("GET", "/api/health")
        h.handle_health()
        self.assertEqual(len(self.captured_responses), 1)
        status, data = self.captured_responses[0]
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["data_source"]["status"], "SAMPLE")

    def test_stops_api(self):
        h = self.create_handler("GET", "/api/stops")
        h.handle_stops({"q": ["aiims"]})
        self.assertEqual(len(self.captured_responses), 1)
        status, data = self.captured_responses[0]
        self.assertEqual(status, 200)
        self.assertGreaterEqual(data["count"], 1)
        self.assertEqual(data["stops"][0]["id"], "AIIMS")

    def test_plan_api(self):
        h = self.create_handler("GET", "/api/plan")
        h.handle_plan({"origin": ["KG_ISBT"], "destination": ["AIIMS"]})
        self.assertEqual(len(self.captured_responses), 1)
        status, data = self.captured_responses[0]
        self.assertEqual(status, 200)
        self.assertTrue(data["success"])
        self.assertGreaterEqual(len(data["journeys"]), 1)

    def test_routes_api(self):
        h = self.create_handler("GET", "/api/routes")
        h.handle_routes()
        self.assertEqual(len(self.captured_responses), 1)
        status, data = self.captured_responses[0]
        self.assertEqual(status, 200)
        self.assertGreaterEqual(data["count"], 10)

    def test_single_route_api(self):
        h = self.create_handler("GET", "/api/route/502")
        h.handle_single_route("502")
        self.assertEqual(len(self.captured_responses), 1)
        status, data = self.captured_responses[0]
        self.assertEqual(status, 200)
        self.assertEqual(data["route"]["id"], "502")
        self.assertGreaterEqual(len(data["stops"]), 5)

    def test_live_buses_api(self):
        h = self.create_handler("GET", "/api/live-buses")
        h.handle_live_buses({})
        self.assertEqual(len(self.captured_responses), 1)
        status, data = self.captured_responses[0]
        self.assertEqual(status, 200)
        self.assertGreater(data["count"], 0)

    def test_traffic_model_api(self):
        h = self.create_handler("GET", "/api/traffic-model")
        h.handle_traffic_model()
        self.assertEqual(len(self.captured_responses), 1)
        status, data = self.captured_responses[0]
        self.assertEqual(status, 200)
        self.assertIn("mathematical_principles", data)
        self.assertIn("corridors", data)

    def test_scenario_switch_api(self):
        h = self.create_handler("POST", "/api/scenario", body=b'{"scenario": "peak_rush"}')
        h.do_POST()
        self.assertEqual(len(self.captured_responses), 1)
        status, data = self.captured_responses[0]
        self.assertEqual(status, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["scenario"], "peak_rush")

    def test_amenities_api(self):
        h = self.create_handler("GET", "/api/amenities")
        h.handle_amenities({"stop_id": ["AIIMS"]})
        self.assertEqual(len(self.captured_responses), 1)
        status, data = self.captured_responses[0]
        self.assertEqual(status, 200)
        self.assertGreaterEqual(data["count"], 2)
        # Verify AIIMS has Pink Toilet, Hospital, and Metro
        cats = [a["category"] for a in data["amenities"]]
        self.assertIn("pink_toilet", cats)
        self.assertIn("hospital", cats)
        self.assertIn("metro", cats)

    def test_hyperlocal_stop_intelligence(self):
        from hyperlocal_engine import get_stop_hyperlocal_intelligence
        intel = get_stop_hyperlocal_intelligence("KG_ISBT")
        self.assertIn("road_side_pin", intel)
        self.assertIn("metro_exit_gate", intel)
        self.assertIn("landmarks", intel)
        self.assertGreaterEqual(len(intel["landmarks"]), 2)
        self.assertIn("nearest_police", intel)
        self.assertIn("safety_rating", intel)

    def test_ncmc_fare_calculator(self):
        from hyperlocal_engine import calculate_ncmc_fare
        res = calculate_ncmc_fare(base_cash_fare=25, mode="bus")
        self.assertEqual(res["cash_fare_inr"], 25)
        self.assertLess(res["ncmc_fare_inr"], 25)
        self.assertGreater(res["discount_amount_inr"], 0)
        self.assertGreater(res["monthly_savings_inr"], 0)

    def test_bus_bunching_detection(self):
        from hyperlocal_engine import detect_bus_bunching
        fake_buses = [
            {"vehicle_id": "DL-1PD-4521", "crowding_percentage": 88},
            {"vehicle_id": "DL-1PD-4528", "crowding_percentage": 35}
        ]
        bunching = detect_bus_bunching("502", fake_buses)
        self.assertTrue(bunching["detected"])
        self.assertIn("trailing_bus", bunching)

    def test_multimodal_metro_rapidx_journeys(self):
        # Rohini Sec 18 to Saket (Direct Metro Yellow Line connection)
        planner = DelhiJourneyPlanner(DelhiBusTrafficModel())
        result = planner.plan_journey("ROHINI_SEC_18", "SAKET")
        self.assertTrue(result["success"])
        modes = [j.get("mode") for j in result["journeys"]]
        self.assertIn("metro", modes)

        # Check NCMC fare is attached
        for j in result["journeys"]:
            self.assertIn("ncmc_fare", j)
            self.assertIn("bus_bunching", j)
            self.assertIn("crowd_status", j)
            self.assertIn("sos_dispatch", j)

    def test_hyperlocal_api(self):
        h = self.create_handler("GET", "/api/hyperlocal")
        h.handle_hyperlocal({"stop_id": ["AIIMS"]})
        self.assertEqual(len(self.captured_responses), 1)
        status, data = self.captured_responses[0]
        self.assertEqual(status, 200)
        self.assertTrue(data["success"])
        self.assertIn("intelligence", data)
        self.assertIn("road_side_pin", data["intelligence"])

    def test_ncmc_calc_api(self):
        h = self.create_handler("GET", "/api/ncmc-calc")
        h.handle_ncmc_calc({"fare": ["50"], "mode": ["metro"]})
        self.assertEqual(len(self.captured_responses), 1)
        status, data = self.captured_responses[0]
        self.assertEqual(status, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["fare_comparison"]["cash_fare_inr"], 50)
        self.assertEqual(data["fare_comparison"]["ncmc_fare_inr"], 45)

    def test_seat_selection_model(self):
        from seat_model import generate_bus_seat_layout
        layout = generate_bus_seat_layout("502", "DL-1PD-4521", crowd_pct=60, is_saheli_pink=True)
        self.assertEqual(layout["total_seats"], 37)
        pink_seats = [s for s in layout["seating_grid"] if s["zone"] == "female_pink"]
        self.assertEqual(len(pink_seats), 8)
        accessible_seats = [s for s in layout["seating_grid"] if s["zone"] == "accessible_senior"]
        self.assertEqual(len(accessible_seats), 4)

    def test_reserve_seat_logic(self):
        from seat_model import reserve_bus_seat
        res = reserve_bus_seat("502", "DL-1PD-4521", "W1", "Ananya Verma", "Female", "AIIMS")
        self.assertEqual(res["status"], "CONFIRMED")
        self.assertEqual(res["fare_charged_inr"], 0)  # Free Delhi Pink Pass for female commuter
        self.assertTrue(res["is_pink_pass"])
        self.assertIn("anti_chaos_guarantee", res)

    def test_rush_bypass_discovery(self):
        # Peak rush plan where some routes suffer heavy delay
        model = DelhiBusTrafficModel()
        model.set_scenario("peak_rush")
        planner = DelhiJourneyPlanner(model)
        result = planner.plan_journey("KG_ISBT", "AIIMS")
        self.assertTrue(result["success"])
        # Verify journeys have rush bypass alternate tags when delays are severe
        bypasses = [j.get("rush_bypass_alternate") for j in result["journeys"] if j.get("rush_bypass_alternate")]
        self.assertGreaterEqual(len(bypasses), 1)
        self.assertIn("time_saved_min", bypasses[0])

if __name__ == "__main__":
    unittest.main()
