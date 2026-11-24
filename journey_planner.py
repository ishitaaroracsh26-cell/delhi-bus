# -*- coding: utf-8 -*-
"""
DilliTransit - Multi-Modal Delhi Bus Journey Planner
Author: First Year Computer Science Student
Course: Data Structures & Algorithms (CS102) - Graph Theory & Shortest Path

Key Data Structures & Algorithms:
1. Adjacency List Graph (G = (V, E)):
   - Vertices (V): 52 Delhi transit hubs and metro stations.
   - Directed Weighted Edges (E): Transit segments with travel time and mode weights.
2. Dijkstra's Algorithm (Priority Queue / Min-Heap):
   - Computes single-source shortest path with transfer penalties.
   - Time Complexity: O((V + E) log V)
   - Space Complexity: O(V + E)
3. Multi-Criteria Ranking:
   - Evaluates journeys based on physical delay, crowdedness, NCMC discounts,
     and Saheli Pink Women Special eligibility.
"""

import math
import heapq
from typing import Dict, List, Any, Optional, Tuple, Set
from transit_data import STOPS, ROUTES, CORRIDORS, AMENITIES
from traffic_model import DelhiBusTrafficModel, haversine_distance_km
from hyperlocal_engine import (
    get_stop_hyperlocal_intelligence,
    calculate_ncmc_fare,
    detect_bus_bunching,
    generate_sos_dispatch
)

# ==============================================================================
# GRAPH DATA STRUCTURES (Adjacency List & Edge Representation)
# ==============================================================================

class TransitGraphEdge:
    """
    Represents a directed link between two transit nodes in the network graph.
    Edge weight is a function of physical distance, travel speed, and transfer friction.
    """
    def __init__(
        self,
        from_id: str,
        to_id: str,
        route_id: str,
        mode: str,
        distance_km: float,
        base_time_min: float,
        fare_inr: int
    ):
        self.from_id = from_id
        self.to_id = to_id
        self.route_id = route_id
        self.mode = mode
        self.distance_km = distance_km
        self.base_time_min = base_time_min
        self.fare_inr = fare_inr

    def __repr__(self) -> str:
        return f"Edge({self.from_id} -> {self.to_id} via {self.route_id})"


class TransitGraphNode:
    """
    Represents a vertex in the transit network graph (Hub or Stop).
    """
    def __init__(self, stop_id: str, name: str, lat: float, lon: float, is_hub: bool = False):
        self.stop_id = stop_id
        self.name = name
        self.lat = lat
        self.lon = lon
        self.is_hub = is_hub
        self.outgoing_edges: List[TransitGraphEdge] = []

    def add_edge(self, edge: TransitGraphEdge) -> None:
        self.outgoing_edges.append(edge)


class MultimodalTransitGraph:
    """
    Multimodal Directed Network Graph representing Delhi's integrated transport grid.
    Built manually using an Adjacency List representation.
    """
    def __init__(self):
        self.nodes: Dict[str, TransitGraphNode] = {}
        self.adjacency_list: Dict[str, List[TransitGraphEdge]] = {}
        self._construct_graph()

    def _construct_graph(self) -> None:
        """Initializes nodes from STOPS and creates edges from ROUTES."""
        # 1. Populate graph nodes (Vertices)
        for sid, s in STOPS.items():
            node = TransitGraphNode(
                stop_id=sid,
                name=s["name"],
                lat=s["lat"],
                lon=s["lon"],
                is_hub=s.get("is_hub", False)
            )
            self.nodes[sid] = node
            self.adjacency_list[sid] = []

        # 2. Add edges from transit route stop sequences
        for rid, route in ROUTES.items():
            stops = route.get("stops", [])
            mode = route.get("mode", "bus")
            fare = route.get("base_fare", 15)
            speed = 36.0 if mode in ("metro", "rapidx") else 22.0

            for i in range(len(stops) - 1):
                u, v = stops[i], stops[i + 1]
                node_u, node_v = self.nodes.get(u), self.nodes.get(v)
                if node_u and node_v:
                    dist = haversine_distance_km(node_u.lat, node_u.lon, node_v.lat, node_v.lon)
                    base_time = (dist / speed) * 60.0

                    # Forward Edge
                    edge_fwd = TransitGraphEdge(u, v, rid, mode, dist, base_time, fare)
                    self.adjacency_list[u].append(edge_fwd)
                    node_u.add_edge(edge_fwd)

                    # Return Edge (for bidirectional transit corridors)
                    edge_rev = TransitGraphEdge(v, u, rid, mode, dist, base_time, fare)
                    self.adjacency_list[v].append(edge_rev)
                    node_v.add_edge(edge_rev)

    def find_dijkstra_path(self, origin_id: str, dest_id: str) -> Optional[Dict[str, Any]]:
        """
        Dijkstra's Algorithm using Binary Min-Heap (heapq).
        Computes single-source shortest path minimizing cumulative travel time with transfer penalties.
        Time Complexity: O((V + E) log V)
        """
        if origin_id not in self.nodes or dest_id not in self.nodes:
            return None

        # Min-heap priority queue: stores tuples of (cumulative_cost, current_node, previous_route_id)
        pq: List[Tuple[float, str, Optional[str]]] = [(0.0, origin_id, None)]
        best_cost: Dict[str, float] = {origin_id: 0.0}
        predecessor: Dict[str, Tuple[str, TransitGraphEdge]] = {}

        while pq:
            curr_cost, u, last_route = heapq.heappop(pq)

            if curr_cost > best_cost.get(u, float("inf")):
                continue

            if u == dest_id:
                break

            for edge in self.adjacency_list.get(u, []):
                v = edge.to_id
                # Apply 5-minute penalty if transferring between different transit lines
                transfer_penalty = 5.0 if (last_route is not None and last_route != edge.route_id) else 0.0
                new_cost = curr_cost + edge.base_time_min + transfer_penalty

                if new_cost < best_cost.get(v, float("inf")):
                    best_cost[v] = new_cost
                    predecessor[v] = (u, edge)
                    heapq.heappush(pq, (new_cost, v, edge.route_id))

        if dest_id not in predecessor and origin_id != dest_id:
            return None

        # Reconstruct path by backtracking from destination
        path_edges: List[TransitGraphEdge] = []
        curr = dest_id
        while curr != origin_id:
            if curr not in predecessor:
                break
            prev_node, edge_used = predecessor[curr]
            path_edges.append(edge_used)
            curr = prev_node

        path_edges.reverse()
        return {
            "origin": origin_id,
            "destination": dest_id,
            "total_time_min": round(best_cost.get(dest_id, 0.0), 1),
            "edges_count": len(path_edges),
            "edges": path_edges
        }

# ==============================================================================
# DELHI JOURNEY PLANNER ENGINE
# ==============================================================================

class DelhiJourneyPlanner:
    """
    Journey planning engine specifically optimized for Delhi's bus network (DTC & DIMTS).
    Computes bidirectional direct routes, transfer connections, walking segments, and live traffic-adjusted ETAs.
    """
    def __init__(self, traffic_model: DelhiBusTrafficModel):
        self.traffic_model = traffic_model
        # Graph representation of multimodal network
        self.network_graph = MultimodalTransitGraph()

    def find_nearest_stop(self, lat: float, lon: float, max_radius_km: float = 3.0) -> Optional[Dict[str, Any]]:
        """Find the closest transit stop to a given GPS coordinate using Haversine calculation."""
        nearest = None
        min_dist = float("inf")
        for stop_id, stop in STOPS.items():
            dist = haversine_distance_km(lat, lon, stop["lat"], stop["lon"])
            if dist < min_dist and dist <= max_radius_km:
                min_dist = dist
                nearest = {**stop, "distance_to_stop_km": round(dist, 2)}
        return nearest

    def resolve_stop(self, stop_id_or_name: str) -> Optional[Dict[str, Any]]:
        """Resolve a stop ID or query string to a valid stop object."""
        if not stop_id_or_name:
            return None
        # Exact ID match
        if stop_id_or_name in STOPS:
            return STOPS[stop_id_or_name]
        # Case-insensitive substring match
        query = stop_id_or_name.lower().strip()
        for stop_id, stop in STOPS.items():
            if query == stop_id.lower() or query in stop["name"].lower() or query in stop.get("name_hi", "").lower():
                return stop
        return None

    def plan_journey(self, origin_key: str, dest_key: str) -> Dict[str, Any]:
        """
        Main journey planning entry point:
        Returns ranked list of candidate journeys with full physics metrics and geometries.
        """
        origin_stop = self.resolve_stop(origin_key)
        dest_stop = self.resolve_stop(dest_key)

        if not origin_stop or not dest_stop:
            return {
                "success": False,
                "error": "Please select a valid origin and destination in Delhi.",
                "journeys": []
            }

        if origin_stop["id"] == dest_stop["id"]:
            return {
                "success": False,
                "error": "Origin and destination stops are the same.",
                "journeys": []
            }

        journeys: List[Dict[str, Any]] = []

        # 1. Search Direct Routes (Both Directions + Circular Loops)
        direct_journeys = self._find_direct_journeys(origin_stop, dest_stop)
        journeys.extend(direct_journeys)

        # 2. Search 1-Transfer Routes (Interchange at Delhi Hubs)
        transfer_journeys = self._find_transfer_journeys(origin_stop, dest_stop)
        journeys.extend(transfer_journeys)

        # 3. Sort journeys (Fastest first, with direct preference)
        journeys.sort(key=lambda j: (j["transfers_count"], j["live_duration_min"]))

        # Identify Saheli Pink Bus Journeys & Rush Bypass Alternate Routes
        if journeys:
            fastest_journey = journeys[0]
            journeys[0]["tags"] = ["Recommended", "Fastest"]

            # Find cheapest
            cheapest = min(journeys, key=lambda j: j["fare_inr"])
            if "tags" in cheapest and "Fastest" not in cheapest["tags"]:
                cheapest["tags"].append("Most Economical")
            elif "tags" not in cheapest:
                cheapest["tags"] = ["Most Economical"]

            for j in journeys:
                # 1. Saheli Pink Bus (महिला विशेष) tagging: ~30% of electric bus fleet
                is_pink = (j.get("mode") == "bus" and ("Electric" in j.get("bus_type", "") or hash(j["journey_id"]) % 3 == 0))
                j["is_saheli_pink"] = is_pink
                if is_pink:
                    j["saheli_pink_badge"] = "🌸 Saheli Pink Women Special (महिला विशेष)"
                    j["saheli_benefits"] = "Female conductor/marshal on board • Delhi Govt ₹0 Free Pink Pass Scheme • Seats W1-W8 Reserved"

                # 2. Rush Bypass Alternate Discovery
                # If this journey suffers delay >= 6 mins and isn't already the fastest:
                delay = j.get("traffic_delay_min", 0)
                if (delay >= 6 or j.get("congestion_level") == "High") and j["journey_id"] != fastest_journey["journey_id"]:
                    time_saved = j["live_duration_min"] - fastest_journey["live_duration_min"]
                    if time_saved >= 6:
                        j["rush_bypass_alternate"] = {
                            "has_alternate": True,
                            "title": f"⚡ Rush Bypass: Switch to {fastest_journey['route_short_name']}",
                            "recommended_journey_id": fastest_journey["journey_id"],
                            "recommended_route_name": fastest_journey["route_short_name"],
                            "time_saved_min": time_saved,
                            "fastest_duration_min": fastest_journey["live_duration_min"],
                            "congested_duration_min": j["live_duration_min"],
                            "reason": f"Heavy bottleneck delay on current corridor (+{delay}m).",
                            "advice": f"Avoid {j.get('congestion_status', 'congestion')}. Board {fastest_journey['route_short_name']} to reach {time_saved} minutes earlier!"
                        }

        return {
            "success": True,
            "origin": origin_stop,
            "destination": dest_stop,
            "journeys_count": len(journeys),
            "journeys": journeys,
            "traffic_scenario": self.traffic_model.scenario
        }

    def _find_direct_journeys(self, origin: Dict[str, Any], dest: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identify all routes that connect origin directly to destination in either direction."""
        directs = []
        origin_id = origin["id"]
        dest_id = dest["id"]

        for route_id, route in ROUTES.items():
            stops = route["stops"]
            if origin_id in stops and dest_id in stops:
                orig_idx = stops.index(origin_id)
                dest_idx = stops.index(dest_id)

                if orig_idx < dest_idx:
                    # Forward direction
                    sub_stops_ids = stops[orig_idx : dest_idx + 1]
                    journey = self._build_single_leg_journey(route, sub_stops_ids, origin, dest, direction="Up")
                    directs.append(journey)
                elif orig_idx > dest_idx:
                    # Reverse / Return direction
                    sub_stops_ids = stops[dest_idx : orig_idx + 1][::-1]
                    journey = self._build_single_leg_journey(route, sub_stops_ids, origin, dest, direction="Down")
                    directs.append(journey)
                elif route_id in ["TMS", "OMS"]:
                    # Circular routes loop around Delhi
                    sub_stops_ids = stops[orig_idx:] + stops[1 : dest_idx + 1]
                    if len(sub_stops_ids) <= len(stops):
                        journey = self._build_single_leg_journey(route, sub_stops_ids, origin, dest, direction="Loop")
                        directs.append(journey)

        return directs

    def _build_single_leg_journey(
        self,
        route: Dict[str, Any],
        stop_ids: List[str],
        origin: Dict[str, Any],
        dest: Dict[str, Any],
        direction: str = "Up"
    ) -> Dict[str, Any]:
        """Construct full journey metrics for a single transit leg."""
        total_distance_km = 0.0
        scheduled_transit_min = 0.0
        live_transit_min = 0.0
        dwell_min = 0.0
        segments = []
        path_stops = []
        geometry = []

        cumulative_offset = 0.0

        for i in range(len(stop_ids)):
            curr_stop = STOPS[stop_ids[i]]
            stop_amenities = [a for a in AMENITIES.values() if a["stop_id"] == curr_stop["id"]]
            stop_hyperlocal = get_stop_hyperlocal_intelligence(curr_stop["id"])
            path_stops.append({
                "id": curr_stop["id"],
                "name": curr_stop["name"],
                "name_hi": curr_stop.get("name_hi", ""),
                "lat": curr_stop["lat"],
                "lon": curr_stop["lon"],
                "is_hub": curr_stop.get("is_hub", False),
                "arrival_offset_min": round(cumulative_offset, 1),
                "amenities": stop_amenities,
                "hyperlocal": stop_hyperlocal
            })
            geometry.append([curr_stop["lat"], curr_stop["lon"]])

            if i < len(stop_ids) - 1:
                next_stop_id = stop_ids[i + 1]
                metrics = self.traffic_model.get_segment_metrics(
                    curr_stop["id"],
                    next_stop_id,
                    route.get("corridors", [])
                )
                segments.append(metrics)
                total_distance_km += metrics["distance_km"]
                scheduled_transit_min += metrics["free_flow_time_min"]
                live_transit_min += metrics["transit_time_min"]
                dwell_min += metrics["dwell_time_min"]
                cumulative_offset += metrics["total_segment_time_min"]

        total_live_min = round(live_transit_min + dwell_min, 1)
        total_sched_min = round(scheduled_transit_min + dwell_min, 1)
        delay_min = max(0.0, round(total_live_min - total_sched_min, 1))

        # Congestion classification
        avg_speed = (total_distance_km / (live_transit_min / 60.0)) if live_transit_min > 0 else 25.0
        if delay_min <= 2.0:
            congestion_level = "Low"
            congestion_status = "Smooth corridor flow"
            badge_color = "#10b981"
        elif delay_min <= 8.0:
            congestion_level = "Moderate"
            congestion_status = f"+{delay_min:.0f}m traffic slowdown"
            badge_color = "#f59e0b"
        else:
            congestion_level = "High"
            congestion_status = f"+{delay_min:.0f}m heavy bottleneck delay"
            badge_color = "#ef4444"

        fare = route.get("base_fare", 15)
        if total_distance_km > 15:
            fare = min(fare + 10, 25)
        elif total_distance_km > 8:
            fare = min(fare + 5, 20)

        mode = route.get("mode", "bus")
        is_ac = route.get("is_ac", False)
        is_wheelchair = route.get("is_wheelchair_accessible", True)

        co2_saved_kg = round(total_distance_km * 0.11, 2)
        journey_id = f"direct_{route['id']}_{origin['id']}_{dest['id']}"

        # Fetch simulated or real live buses along this route
        active_buses = self.traffic_model.generate_live_buses(route["id"])

        # Aggregate amenities count
        all_amenities = []
        for s in path_stops:
            all_amenities.extend(s.get("amenities", []))
        amenities_summary = {
            "pink_toilets": len([a for a in all_amenities if a["category"] == "pink_toilet"]),
            "metro": len([a for a in all_amenities if a["category"] == "metro"]),
            "hospitals": len([a for a in all_amenities if a["category"] == "hospital"]),
            "cafes": len([a for a in all_amenities if a["category"] == "cafe"]),
            "cinemas": len([a for a in all_amenities if a["category"] == "cinema"]),
            "police": len([a for a in all_amenities if a["category"] == "police"]),
            "total": len(all_amenities)
        }

        # NCMC Smart Card Fare & Savings
        ncmc_data = calculate_ncmc_fare(fare, mode=mode, is_ac=is_ac)

        # Real-Time Bus-Bunching Detection
        bunching_data = detect_bus_bunching(route["id"], active_buses)

        # Crowdedness Meter
        crowd_pct = active_buses[0].get("crowding_percentage", 58) if active_buses else 54
        if crowd_pct < 45:
            crowd_level = "Low"
            crowd_status = f"Seats Available ({crowd_pct}%)"
            crowd_color = "#10b981"
        elif crowd_pct <= 75:
            crowd_level = "Moderate"
            crowd_status = f"Standing Room Only ({crowd_pct}%)"
            crowd_color = "#f59e0b"
        else:
            crowd_level = "High"
            crowd_status = f"Heavy Crowding ({crowd_pct}%)"
            crowd_color = "#ef4444"

        # Fleet Plate & Live SOS Dispatch Generator
        fleet_plate = active_buses[0].get("vehicle_id", f"DL-1PD-{(hash(route['id']) % 8000) + 1000}") if active_buses else f"DL-1PD-{(hash(route['id']) % 7000) + 2000}"
        sos_data = generate_sos_dispatch(
            {"route_short_name": route["short_name"]},
            path_stops[0],
            fleet_plate
        )

        return {
            "journey_id": journey_id,
            "type": "DIRECT",
            "direction": direction,
            "mode": mode,
            "transfers_count": 0,
            "route_id": route["id"],
            "route_short_name": route["short_name"],
            "route_long_name": route["long_name"],
            "agency": route["agency"],
            "bus_type": route["bus_type"],
            "color": route.get("color", "#2563eb"),
            "fare_inr": fare,
            "ncmc_fare": ncmc_data,
            "bus_bunching": bunching_data,
            "crowd_level": crowd_level,
            "crowd_percentage": crowd_pct,
            "crowd_status": crowd_status,
            "crowd_color": crowd_color,
            "is_ac": is_ac,
            "is_wheelchair_accessible": is_wheelchair,
            "night_safety_rating": 4.9 if mode in ["metro", "rapidx"] else 4.7,
            "live_fleet_number": fleet_plate,
            "sos_dispatch": sos_data,
            "total_distance_km": round(total_distance_km, 1),
            "scheduled_duration_min": int(round(total_sched_min)),
            "live_duration_min": int(round(total_live_min)),
            "traffic_delay_min": int(round(delay_min)),
            "congestion_level": congestion_level,
            "congestion_status": congestion_status,
            "badge_color": badge_color,
            "avg_speed_kmh": round(avg_speed, 1),
            "carbon_saved_kg": co2_saved_kg,
            "next_bus_in_min": int((hash(journey_id) % 7) + 2),
            "frequency_min": route.get("frequency_min", 10),
            "geometry": geometry,
            "stops": path_stops,
            "segments": segments,
            "active_buses_count": len(active_buses),
            "amenities_summary": amenities_summary,
            "legs": [
                {
                    "leg_type": "TRANSIT",
                    "mode": mode,
                    "route_id": route["id"],
                    "route_name": route["short_name"],
                    "agency": route["agency"],
                    "bus_type": route["bus_type"],
                    "color": route.get("color", "#2563eb"),
                    "from_stop": path_stops[0],
                    "to_stop": path_stops[-1],
                    "stops_count": len(path_stops),
                    "duration_min": int(round(total_live_min)),
                    "distance_km": round(total_distance_km, 1)
                }
            ]
        }

    def _find_transfer_journeys(self, origin: Dict[str, Any], dest: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find optimal 1-transfer itineraries connecting origin to destination via an intermediate transit hub."""
        transfers = []
        origin_id = origin["id"]
        dest_id = dest["id"]

        # Eligible transfer hubs in Delhi
        hub_candidates = [
            sid for sid, s in STOPS.items()
            if s.get("is_hub", False) and sid != origin_id and sid != dest_id
        ]

        found_pairs = set()

        for hub_id in hub_candidates:
            hub_stop = STOPS[hub_id]

            # Route 1: Origin -> Hub (Forward or Reverse)
            leg1_routes = []
            for r1_id, r1 in ROUTES.items():
                stops1 = r1["stops"]
                if origin_id in stops1 and hub_id in stops1:
                    i_orig = stops1.index(origin_id)
                    i_hub = stops1.index(hub_id)
                    if i_orig < i_hub:
                        leg1_routes.append((r1, stops1[i_orig : i_hub + 1], "Up"))
                    elif i_orig > i_hub:
                        leg1_routes.append((r1, stops1[i_hub : i_orig + 1][::-1], "Down"))

            if not leg1_routes:
                continue

            # Route 2: Hub -> Destination (Forward or Reverse)
            leg2_routes = []
            for r2_id, r2 in ROUTES.items():
                stops2 = r2["stops"]
                if hub_id in stops2 and dest_id in stops2:
                    i_hub2 = stops2.index(hub_id)
                    i_dest = stops2.index(dest_id)
                    if i_hub2 < i_dest:
                        leg2_routes.append((r2, stops2[i_hub2 : i_dest + 1], "Up"))
                    elif i_hub2 > i_dest:
                        leg2_routes.append((r2, stops2[i_dest : i_hub2 + 1][::-1], "Down"))

            if not leg2_routes:
                continue

            # Pick best route pair for this hub
            for r1, r1_stops, dir1 in leg1_routes[:2]:
                for r2, r2_stops, dir2 in leg2_routes[:2]:
                    if r1["id"] == r2["id"]:
                        continue # Skip trivial direct
                    pair_key = f"{r1['id']}->{hub_id}->{r2['id']}"
                    if pair_key in found_pairs:
                        continue
                    found_pairs.add(pair_key)

                    journey = self._build_transfer_journey(
                        r1, r1_stops, dir1,
                        r2, r2_stops, dir2,
                        origin, hub_stop, dest
                    )
                    transfers.append(journey)
                    if len(transfers) >= 5:
                        break
                if len(transfers) >= 5:
                    break

        return transfers

    def _build_transfer_journey(
        self,
        r1: Dict[str, Any],
        r1_stops: List[str],
        dir1: str,
        r2: Dict[str, Any],
        r2_stops: List[str],
        dir2: str,
        origin: Dict[str, Any],
        hub: Dict[str, Any],
        dest: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Construct full journey metrics for a 2-leg transfer itinerary."""
        leg1 = self._build_single_leg_journey(r1, r1_stops, origin, hub, direction=dir1)
        leg2 = self._build_single_leg_journey(r2, r2_stops, hub, dest, direction=dir2)

        # Interchange walk & wait buffer
        transfer_buffer_min = 6.0  # average waiting / platform interchange at Delhi hubs

        total_live_min = leg1["live_duration_min"] + transfer_buffer_min + leg2["live_duration_min"]
        total_sched_min = leg1["scheduled_duration_min"] + 5.0 + leg2["scheduled_duration_min"]
        total_distance_km = round(leg1["total_distance_km"] + leg2["total_distance_km"], 1)
        total_delay_min = leg1["traffic_delay_min"] + leg2["traffic_delay_min"]

        combined_fare = leg1["fare_inr"] + leg2["fare_inr"]

        combined_geom = leg1["geometry"] + leg2["geometry"][1:]
        journey_id = f"transfer_{r1['id']}_{hub['id']}_{r2['id']}"

        combined_stops = leg1["stops"] + leg2["stops"][1:]
        total_amenities = []
        for s in combined_stops:
            total_amenities.extend(s.get("amenities", []))
        amenities_summary = {
            "pink_toilets": len([a for a in total_amenities if a["category"] == "pink_toilet"]),
            "metro": len([a for a in total_amenities if a["category"] == "metro"]),
            "hospitals": len([a for a in total_amenities if a["category"] == "hospital"]),
            "cafes": len([a for a in total_amenities if a["category"] == "cafe"]),
            "cinemas": len([a for a in total_amenities if a["category"] == "cinema"]),
            "police": len([a for a in total_amenities if a["category"] == "police"]),
            "total": len(total_amenities)
        }

        # Multimodal transfer classification
        modes = [r1.get("mode", "bus"), r2.get("mode", "bus")]
        if "metro" in modes or "rapidx" in modes:
            journey_mode = "multimodal"
        else:
            journey_mode = "bus"

        is_ac = leg1.get("is_ac", False) or leg2.get("is_ac", False)
        is_wheelchair = leg1.get("is_wheelchair_accessible", True) and leg2.get("is_wheelchair_accessible", True)

        # Unified NCMC Smart Card Fare
        ncmc_data = calculate_ncmc_fare(combined_fare, mode=journey_mode, is_ac=is_ac)

        # Inherit bunching & crowd status
        bunching_data = leg1.get("bus_bunching", {"detected": False, "alert": "Normal frequency"})
        crowd_level = leg1.get("crowd_level", "Moderate")
        crowd_pct = leg1.get("crowd_percentage", 60)
        crowd_status = leg1.get("crowd_status", f"Standing Room Only ({crowd_pct}%)")
        crowd_color = leg1.get("crowd_color", "#f59e0b")

        fleet_plate = leg1.get("live_fleet_number", "DL-1PD-4521")
        sos_data = generate_sos_dispatch(
            {"route_short_name": f"{r1['short_name']} ➔ {r2['short_name']}"},
            combined_stops[0],
            fleet_plate
        )

        return {
            "journey_id": journey_id,
            "type": "1_TRANSFER",
            "transfers_count": 1,
            "mode": journey_mode,
            "transfer_hub": hub,
            "route_id": f"{r1['short_name']} + {r2['short_name']}",
            "route_short_name": f"{r1['short_name']} ➔ {r2['short_name']}",
            "route_long_name": f"Via {hub['name']} Interchange",
            "agency": f"{r1['agency']} / {r2['agency']}",
            "bus_type": f"{r1['bus_type']} & {r2['bus_type']}",
            "color": r1.get("color", "#2563eb"),
            "fare_inr": combined_fare,
            "ncmc_fare": ncmc_data,
            "bus_bunching": bunching_data,
            "crowd_level": crowd_level,
            "crowd_percentage": crowd_pct,
            "crowd_status": crowd_status,
            "crowd_color": crowd_color,
            "is_ac": is_ac,
            "is_wheelchair_accessible": is_wheelchair,
            "night_safety_rating": 4.8,
            "live_fleet_number": fleet_plate,
            "sos_dispatch": sos_data,
            "total_distance_km": total_distance_km,
            "scheduled_duration_min": int(round(total_sched_min)),
            "live_duration_min": int(round(total_live_min)),
            "traffic_delay_min": int(round(total_delay_min)),
            "congestion_level": "Moderate" if total_delay_min > 5 else "Low",
            "congestion_status": f"1 Transfer at {hub['name']} (+{int(total_delay_min)}m delay)",
            "badge_color": "#8b5cf6",
            "carbon_saved_kg": round(total_distance_km * 0.11, 2),
            "next_bus_in_min": leg1["next_bus_in_min"],
            "geometry": combined_geom,
            "stops": combined_stops,
            "amenities_summary": amenities_summary,
            "legs": [
                {
                    "leg_type": "TRANSIT",
                    "leg_num": 1,
                    "route_id": r1["id"],
                    "route_name": r1["short_name"],
                    "agency": r1["agency"],
                    "bus_type": r1["bus_type"],
                    "color": r1.get("color", "#2563eb"),
                    "from_stop": leg1["stops"][0],
                    "to_stop": leg1["stops"][-1],
                    "stops_count": len(leg1["stops"]),
                    "duration_min": leg1["live_duration_min"],
                    "distance_km": leg1["total_distance_km"]
                },
                {
                    "leg_type": "TRANSFER",
                    "hub_name": hub["name"],
                    "duration_min": int(transfer_buffer_min),
                    "walk_distance_m": 120
                },
                {
                    "leg_type": "TRANSIT",
                    "leg_num": 2,
                    "route_id": r2["id"],
                    "route_name": r2["short_name"],
                    "agency": r2["agency"],
                    "bus_type": r2["bus_type"],
                    "color": r2.get("color", "#7c3aed"),
                    "from_stop": leg2["stops"][0],
                    "to_stop": leg2["stops"][-1],
                    "stops_count": len(leg2["stops"]),
                    "duration_min": leg2["live_duration_min"],
                    "distance_km": leg2["total_distance_km"]
                }
            ]
        }
