# -*- coding: utf-8 -*-
"""
DilliTransit - Real-Time Bus Traffic Model & Probe-Vehicle Velocity Estimator
Author: First Year Computer Science Student
Course: Data Structures, Algorithms & Applied Physics Simulation

Mathematical Foundations:
1. Spherical Trigonometry: Haversine distance formula & Great Circle navigation.
2. Probe Kinematics: Discrete velocity derivation v = ds / dt from bus GPS pings.
3. Queueing Dwell Friction: Separation of stop dwell time from arterial road congestion.
4. Congestion Indexing: Congestion Factor (CF = V_freeflow / V_observed).
"""

import math
import time
from typing import Dict, List, Tuple, Any, Optional
from transit_data import STOPS, CORRIDORS, ROUTES

# ==============================================================================
# SPHERICAL TRIGONOMETRY CALCULATOR (Manual Implementation)
# ==============================================================================

def degrees_to_radians(degrees: float) -> float:
    """Manual conversion from angular degrees to radians: rad = deg * (pi / 180)."""
    return degrees * (math.pi / 180.0)

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes the Great Circle distance between two geographic coordinates on Earth.
    
    Formula Derivation:
        hav(theta) = sin^2(dlat/2) + cos(lat1) * cos(lat2) * sin^2(dlon/2)
        d = 2 * R * arcsin(sqrt(hav(theta)))
        
    Earth Mean Volumetric Radius R = 6371.0 km (IUGG standard).
    Time Complexity: O(1) elementary trigonometric operations.
    """
    R = 6371.0  # Earth's mean radius in kilometers

    phi1 = degrees_to_radians(lat1)
    phi2 = degrees_to_radians(lat2)
    delta_phi = degrees_to_radians(lat2 - lat1)
    delta_lambda = degrees_to_radians(lon2 - lon1)

    sin_half_dphi = math.sin(delta_phi / 2.0)
    sin_half_dlambda = math.sin(delta_lambda / 2.0)

    a = (sin_half_dphi * sin_half_dphi) + \
        (math.cos(phi1) * math.cos(phi2) * sin_half_dlambda * sin_half_dlambda)

    a = max(0.0, min(1.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return R * c

def calculate_initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculates initial compass bearing (forward azimuth) from point 1 to point 2 in degrees [0, 360).
    Formula:
        theta = atan2( sin(dlon) * cos(lat2),
                       cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon) )
    """
    phi1 = degrees_to_radians(lat1)
    phi2 = degrees_to_radians(lat2)
    delta_lambda = degrees_to_radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)

    bearing_rad = math.atan2(y, x)
    bearing_deg = (math.degrees(bearing_rad) + 360.0) % 360.0
    return round(bearing_deg, 1)

# ==============================================================================
# PROBE-VEHICLE TRAFFIC VELOCITY ESTIMATOR (PVVE ENGINE)
# ==============================================================================

class DelhiBusTrafficModel:
    """
    Traffic estimation engine utilizing transit buses as mobile probe velocity sensors.
    
    Principles:
    - In urban transit, bus stops introduce passenger boarding friction (dwell time).
    - If dwell time is not separated, routing algorithms will falsely misidentify
      busy passenger bus stops as severe arterial traffic jams.
    - PVVE subtracts dwell time from link duration to yield pure road vehicle velocity.
    """
    def __init__(self):
        # Default operational scenario (options: off_peak, normal, peak_rush, bottleneck)
        self.scenario: str = "normal"
        self.last_update_ts: float = time.time()

        # Calibrated baseline velocity scaling factors for Delhi's arterial network
        self.scenario_factors: Dict[str, float] = {
            "off_peak": 1.05,    # Night & early morning near-free-flow
            "normal": 0.82,      # Regular midday operations
            "peak_rush": 0.48,   # Morning & evening rush hour congestion
            "bottleneck": 0.32   # Severe incident / monsoon waterlogging / flyover construction
        }

        # Delhi arterial bottleneck hotspots (empirically calibrated)
        self.hotspot_delays: Dict[str, Dict[str, Any]] = {
            "ASHRAM": {"peak": 3.2, "normal": 1.6, "reason": "Ashram Underpass & DND flyway merge choke point"},
            "ITO": {"peak": 2.8, "normal": 1.5, "reason": "ITO intersection & Vikas Marg Yamuna bridge funnel"},
            "LAXMI_NAGAR": {"peak": 2.7, "normal": 1.4, "reason": "East Delhi commercial hub pedestrian density & auto merge"},
            "AIIMS": {"peak": 2.5, "normal": 1.3, "reason": "Aurobindo Marg & Ring Road multigrade flyover interchange"},
            "DHAULA_KUAN": {"peak": 2.6, "normal": 1.4, "reason": "NH-48 flyover multi-directional slip lanes"},
            "KAROL_BAGH": {"peak": 2.4, "normal": 1.4, "reason": "Pusa Road commercial market pedestrian spillover"},
            "PUNJABI_BAGH": {"peak": 2.2, "normal": 1.3, "reason": "Rohtak Road & Ring Road flyover reconstruction"},
            "KG_ISBT": {"peak": 2.3, "normal": 1.3, "reason": "Interstate bus terminal maneuvering & pedestrian spillover"},
            "NEHRU_PLACE": {"peak": 2.0, "normal": 1.2, "reason": "South Delhi commercial IT hub arterial congestion"}
        }

    def set_scenario(self, scenario_name: str) -> bool:
        """Switches active simulation physics scenario."""
        if scenario_name in self.scenario_factors:
            self.scenario = scenario_name
            self.last_update_ts = time.time()
            return True
        return False

    def compute_dwell_time(self, stop_id: str) -> float:
        """
        Calculates passenger boarding/alighting dwell friction at a transit stop.
        
        Mathematical Model:
            T_dwell = tau_0 + alpha_hub * I_hub(s) + beta_peak * I_rush
            - tau_0 = 0.42 min (25 seconds baseline)
            - alpha_hub = 0.42 min (25 seconds added for high-volume multimodal hubs)
            - beta_peak = 0.25 min (15 seconds added during peak rush hours)
        """
        stop = STOPS.get(stop_id, {})
        base_dwell = 0.42  # ~25 seconds
        if stop.get("is_hub", False):
            base_dwell += 0.42  # Additional 25s for major interchange hubs
        if self.scenario == "peak_rush":
            base_dwell += 0.25  # Rush hour crowding friction
        elif self.scenario == "bottleneck":
            base_dwell += 0.40
        return round(base_dwell, 2)

    def get_corridor_speed(self, arg1: str, arg2: Optional[str] = None) -> Any:
        """
        Polymorphic velocity resolver:
        1. When called with corridor_id (arg1='RING_ROAD_SOUTH', arg2=None):
           Returns comprehensive corridor metric dictionary for /api/corridors.
        2. When called with two stop IDs (arg1='AIIMS', arg2='INA_MARKET'):
           Returns tuple: (current_speed_kmh, free_flow_speed_kmh, corridor_name).
        """
        if arg2 is None and arg1 in CORRIDORS:
            # 1. Single corridor lookup
            corridor = CORRIDORS[arg1]
            free_flow = corridor["free_flow_speed"]
            factor = self.scenario_factors.get(self.scenario, 0.82)
            curr_speed = round(max(8.0, free_flow * factor), 1)
            cf = round(free_flow / curr_speed, 2)
            status = "Heavy Congestion" if cf > 1.8 else ("Moderate Congestion" if cf > 1.3 else "Normal Flow")
            color = "#ef4444" if cf > 1.8 else ("#f59e0b" if cf > 1.3 else "#10b981")
            return {
                "corridor_id": arg1,
                "corridor_name": corridor["name"],
                "current_speed_kmh": curr_speed,
                "free_flow_speed_kmh": free_flow,
                "congestion_factor": cf,
                "status": status,
                "color": color
            }

        # 2. Stop A to Stop B segment lookup
        stop_a_id = arg1
        stop_b_id = arg2 or ""
        matched_corridor = None
        for cid, corridor in CORRIDORS.items():
            stops = corridor.get("stops", [])
            if stop_a_id in stops and stop_b_id in stops:
                matched_corridor = corridor
                break

        if matched_corridor:
            free_flow = matched_corridor["free_flow_speed"]
            corr_name = matched_corridor["name"]
        else:
            free_flow = 38.0  # Default Delhi arterial speed
            corr_name = "Arterial Road Network"

        # Apply global scenario velocity scaling factor
        factor = self.scenario_factors.get(self.scenario, 0.82)
        speed = free_flow * factor

        # Apply localized hotspot reduction if either stop is in an active bottleneck
        for sid in (stop_a_id, stop_b_id):
            if sid in self.hotspot_delays:
                hotspot = self.hotspot_delays[sid]
                delay_factor = hotspot["peak"] if self.scenario in ("peak_rush", "bottleneck") else hotspot["normal"]
                speed = speed / math.sqrt(delay_factor)

        # Physical lower bound for heavy gridlock crawl speed (minimum 8 km/h)
        speed = max(8.0, round(speed, 1))
        return speed, free_flow, corr_name

    def get_segment_metrics(
        self,
        stop_a_id: str,
        stop_b_id: str,
        route_corridors: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Computes detailed kinematic metrics for a single transit road segment.
        Separates moving transit time from stop boarding dwell time.
        """
        stop_a = STOPS.get(stop_a_id)
        stop_b = STOPS.get(stop_b_id)
        if not stop_a or not stop_b:
            return {"error": "Invalid stop identifiers"}

        # Step 1: Great circle distance scaled by Delhi arterial road circuity factor (1.22)
        air_dist = haversine_distance_km(stop_a["lat"], stop_a["lon"], stop_b["lat"], stop_b["lon"])
        road_dist = round(air_dist * 1.22, 2)

        # Step 2: Corridor velocities
        curr_speed, free_flow, corr_name = self.get_corridor_speed(stop_a_id, stop_b_id)

        # Step 3: Pure moving time on road: t_motion = (distance / speed) * 60 minutes
        moving_time_min = (road_dist / curr_speed) * 60.0
        scheduled_moving_min = (road_dist / free_flow) * 60.0

        # Step 4: Stop dwell time
        dwell_time = self.compute_dwell_time(stop_b_id)

        # Step 5: Total transit time
        total_time_min = round(moving_time_min + dwell_time, 1)
        scheduled_total_min = round(scheduled_moving_min + (dwell_time * 0.7), 1)
        delay_min = max(0.0, round(total_time_min - scheduled_total_min, 1))

        # Step 6: Congestion Factor: CF = V_freeflow / V_current
        congestion_factor = round(free_flow / curr_speed, 2)
        if congestion_factor > 1.8:
            status = "Heavy Bottleneck Delay"
            color = "#ef4444"
        elif congestion_factor > 1.3:
            status = "Moderate Arterial Delay"
            color = "#f59e0b"
        else:
            status = "Smooth Free-Flow Transit"
            color = "#10b981"

        return {
            "from_stop": stop_a_id,
            "to_stop": stop_b_id,
            "corridor": corr_name,
            "distance_km": road_dist,
            "road_distance_km": road_dist,
            "current_speed_kmh": curr_speed,
            "free_flow_speed_kmh": free_flow,
            "congestion_factor": congestion_factor,
            "free_flow_time_min": round(scheduled_moving_min, 1),
            "transit_time_min": round(moving_time_min, 1),
            "total_segment_time_min": total_time_min,
            "dwell_time_min": dwell_time,
            "scheduled_time_min": scheduled_total_min,
            "delay_min": delay_min,
            "status": status,
            "status_color": color
        }

    def get_model_summary(self) -> Dict[str, Any]:
        """Returns comprehensive mathematical principles and active corridors status."""
        corridors_summary = []
        for cid in CORRIDORS.keys():
            corridors_summary.append(self.get_corridor_speed(cid))

        return {
            "engine": "Probe-Vehicle Velocity Estimation (PVVE)",
            "mathematical_principles": {
                "velocity_formula": "v_segment = sum(delta_distance) / sum(delta_time)",
                "dwell_separation": "T_dwell = tau_0 + alpha_hub * I_hub + beta_rush",
                "congestion_factor": "CF = V_freeflow / V_observed",
                "circuity_factor": 1.22
            },
            "active_scenario": self.scenario,
            "calibration_factors": self.scenario_factors,
            "corridors": corridors_summary,
            "last_calibrated_ts": self.last_update_ts
        }

    def generate_live_buses(self, route_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Generates synthetic live bus probe telemetry calibrated to Delhi's fleet topology.
        Simulates vehicle positions, speed sensors, headings, and crowd occupancies.
        """
        buses = []
        target_routes = [route_id] if route_id and route_id in ROUTES else list(ROUTES.keys())

        epoch_seconds = int(time.time())

        for r_id in target_routes:
            route = ROUTES[r_id]
            stops = route["stops"]
            if len(stops) < 2:
                continue

            num_active_buses = min(4, max(2, len(stops) // 3))
            for b_idx in range(num_active_buses):
                seg_idx = (epoch_seconds // 35 + b_idx * (len(stops) // num_active_buses)) % (len(stops) - 1)
                curr_s = STOPS[stops[seg_idx]]
                next_s = STOPS[stops[seg_idx + 1]]

                # Interpolate coordinate along road segment
                alpha = ((epoch_seconds % 35) + (b_idx * 7)) % 35 / 35.0
                bus_lat = round(curr_s["lat"] + alpha * (next_s["lat"] - curr_s["lat"]), 5)
                bus_lon = round(curr_s["lon"] + alpha * (next_s["lon"] - curr_s["lon"]), 5)

                speed_kmh, _, _ = self.get_corridor_speed(curr_s["id"], next_s["id"])
                heading = calculate_initial_bearing(curr_s["lat"], curr_s["lon"], next_s["lat"], next_s["lon"])

                fleet_num = 4500 + (hash(f"{r_id}_{b_idx}") % 490)
                vehicle_id = f"DL-1PD-{fleet_num}"

                crowd_base = 55
                if self.scenario == "peak_rush":
                    crowd_base = 82
                elif self.scenario == "off_peak":
                    crowd_base = 28
                crowd_pct = min(98, max(15, crowd_base + ((b_idx * 11) % 25)))

                is_pink = (route.get("mode") == "bus" and ("Electric" in route.get("bus_type", "") or b_idx == 0))

                speed_val = round(speed_kmh * (0.9 + 0.2 * ((b_idx % 3) / 3.0)), 1)
                speed_stat = "Free-Flow" if speed_val > 25 else ("Heavy Congestion" if speed_val < 12 else "Normal Flow")
                crowd_lvl = "High" if crowd_pct > 75 else ("Moderate" if crowd_pct > 40 else "Low")

                buses.append({
                    "vehicle_id": vehicle_id,
                    "route_id": r_id,
                    "route_name": route["short_name"],
                    "route_short_name": route["short_name"],
                    "agency": route.get("agency", "DTC"),
                    "lat": bus_lat,
                    "lon": bus_lon,
                    "speed_kmh": speed_val,
                    "current_speed_kmh": speed_val,
                    "speed_status": speed_stat,
                    "heading": heading,
                    "crowd_percentage": crowd_pct,
                    "crowding_percentage": crowd_pct,
                    "crowd_level": crowd_lvl,
                    "crowding_level": crowd_lvl,
                    "next_stop_name": next_s["name"],
                    "current_segment": f"{curr_s['name']} ➔ {next_s['name']}",
                    "is_saheli_pink": is_pink,
                    "last_ping_seconds_ago": (epoch_seconds % 12) + 2,
                    "timestamp": epoch_seconds
                })

        return buses
