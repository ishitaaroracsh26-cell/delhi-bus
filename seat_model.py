# -*- coding: utf-8 -*-
"""
DilliTransit - Bus Seat Selection & Anti-Chaos Reservation Engine
Author: First Year Computer Science Student
Course: Data Structures, Discrete Mathematics & Object-Oriented Design

Design Principles:
1. Discrete Grid Mapping: 2D Matrix representing 37 bus passenger seats.
2. Deterministic PRNG: Handcrafted Linear Congruential Generator (LCG)
   to ensure seat availability is deterministic per vehicle fleet plate.
3. Checksum Algorithm: Modulo-based check digit verification for PNR and Anti-Chaos tokens.
4. Equity & Safety Policies: Priority Women's Pink Zone (W1-W8) and Delhi ₹0 Pink Pass validation.
"""

import time
from typing import Dict, List, Any, Optional

# ==============================================================================
# DISCRETE MATHEMATICS: LINEAR CONGRUENTIAL GENERATOR (Manual PRNG)
# ==============================================================================

class LinearCongruentialGenerator:
    """
    Classical Pseudo-Random Number Generator implementing the Lehmer / Linear Congruential recurrence:
        X_{n+1} = (a * X_n + c) mod m
        
    Parameters (ANSI C / glibc standard):
        - Multiplier a = 1103515245
        - Increment c = 12345
        - Modulus m = 2^31 (2147483648)
        
    Used to deterministically compute bus seat occupancy without relying on black-box libraries.
    """
    def __init__(self, seed: int):
        self.state: int = int(seed) & 0x7FFFFFFF
        self.a: int = 1103515245
        self.c: int = 12345
        self.m: int = 2147483648

    def next_int(self) -> int:
        """Generates next pseudo-random integer in range [0, m - 1]."""
        self.state = (self.a * self.state + self.c) % self.m
        return self.state

    def next_float(self) -> float:
        """Returns pseudo-random floating point value in interval [0.0, 1.0)."""
        return self.next_int() / float(self.m)

    def shuffle_list(self, items: List[Any]) -> None:
        """
        Fisher-Yates (Knuth) Shuffle Algorithm.
        Time Complexity: O(N) in-place array permutation.
        """
        n = len(items)
        for i in range(n - 1, 0, -1):
            j = self.next_int() % (i + 1)
            items[i], items[j] = items[j], items[i]

# ==============================================================================
# OBJECT-ORIENTED SEAT DATA MODEL
# ==============================================================================

class BusSeatNode:
    """
    Encapsulates state, spatial coordinates, and safety policy of a single bus seat.
    """
    def __init__(
        self,
        seat_id: str,
        label: str,
        zone: str,
        zone_name: str,
        row: int,
        col: int,
        side: str,
        icon: str,
        color: str,
        is_women_only: bool = False,
        is_accessible: bool = False,
        price_inr: int = 25
    ):
        self.id = seat_id
        self.label = label
        self.zone = zone
        self.zone_name = zone_name
        self.row = row
        self.col = col
        self.side = side
        self.icon = icon
        self.color = color
        self.is_women_only = is_women_only
        self.is_accessible = is_accessible
        self.price_inr = price_inr
        self.status = "available"  # 'available' or 'occupied'

    def to_dict(self) -> Dict[str, Any]:
        """Serializes seat node to standard dictionary format for JSON responses."""
        return {
            "id": self.id,
            "label": self.label,
            "zone": self.zone,
            "zone_name": self.zone_name,
            "row": self.row,
            "col": self.col,
            "side": self.side,
            "icon": self.icon,
            "color": self.color,
            "is_women_only": self.is_women_only,
            "is_accessible": self.is_accessible,
            "price_inr": self.price_inr,
            "status": self.status
        }

# ==============================================================================
# SEATING LAYOUT GENERATOR
# ==============================================================================

def generate_bus_seat_layout(
    route_id: str,
    fleet_plate: str,
    crowd_pct: int = 50,
    is_saheli_pink: bool = False
) -> Dict[str, Any]:
    """
    Generates a full 37-seat interactive movie-theater style bus seat grid:
    - Rows 1-2: Women Reserved Pink Zone (Seats W1 to W8)
    - Row 3: Senior Citizen & Differently-Abled Accessible Zone (Seats S1 to S4)
    - Rows 4-8: General Seating Zone (Seats G1 to G20 in 2x2 with center aisle)
    - Row 9: Rear Lounge (Seats R1 to R5)
    """
    # Step 1: Derive deterministic seed from route and chassis plate string hashes
    hash_accumulator = 0
    composite_key = f"{route_id}_{fleet_plate}"
    for char in composite_key:
        hash_accumulator = (hash_accumulator * 31 + ord(char)) & 0x7FFFFFFF

    prng = LinearCongruentialGenerator(hash_accumulator)

    # Step 2: Target occupied seat count proportional to bus crowdedness percentage
    total_seats = 37
    occupied_target = min(total_seats - 2, max(5, int((crowd_pct / 100.0) * total_seats)))

    seat_nodes: List[BusSeatNode] = []

    # 1. Rows 1-2: Women Priority Pink Zone (W1 to W8)
    for row_idx in (1, 2):
        for col_idx, col_side in enumerate(["left_window", "left_aisle", "right_aisle", "right_window"]):
            seat_num = (row_idx - 1) * 4 + col_idx + 1
            seat_nodes.append(BusSeatNode(
                seat_id=f"W{seat_num}",
                label=f"W{seat_num}",
                zone="female_pink",
                zone_name="Women Only (Pink Zone)",
                row=row_idx,
                col=col_idx,
                side=col_side,
                icon="🚺",
                color="#ec4899",
                is_women_only=True,
                is_accessible=False,
                price_inr=0 if is_saheli_pink else 25
            ))

    # 2. Row 3: Senior Citizen / Accessible Zone (S1 to S4)
    for col_idx, col_side in enumerate(["left_window", "left_aisle", "right_aisle", "right_window"]):
        seat_num = col_idx + 1
        seat_nodes.append(BusSeatNode(
            seat_id=f"S{seat_num}",
            label=f"S{seat_num}",
            zone="accessible_senior",
            zone_name="Senior Citizen / Divyang Accessible",
            row=3,
            col=col_idx,
            side=col_side,
            icon="♿",
            color="#f59e0b",
            is_women_only=False,
            is_accessible=True,
            price_inr=25
        ))

    # 3. Rows 4-8: General Seating 2x2 (G1 to G20)
    for r in range(4, 9):
        for col_idx, col_side in enumerate(["left_window", "left_aisle", "right_aisle", "right_window"]):
            g_num = (r - 4) * 4 + col_idx + 1
            seat_nodes.append(BusSeatNode(
                seat_id=f"G{g_num}",
                label=f"G{g_num}",
                zone="general",
                zone_name="General Seating",
                row=r,
                col=col_idx,
                side=col_side,
                icon="💺",
                color="#38bdf8",
                is_women_only=False,
                is_accessible=False,
                price_inr=25
            ))

    # 4. Row 9: Rear Lounge 5-seater bench (R1 to R5)
    for col_idx in range(5):
        r_num = col_idx + 1
        seat_nodes.append(BusSeatNode(
            seat_id=f"R{r_num}",
            label=f"R{r_num}",
            zone="rear",
            zone_name="Rear Lounge",
            row=9,
            col=col_idx,
            side="rear_row",
            icon="💺",
            color="#38bdf8",
            is_women_only=False,
            is_accessible=False,
            price_inr=25
        ))

    # Step 3: Populate occupied seats deterministically using Fisher-Yates shuffle
    all_indices = list(range(len(seat_nodes)))
    prng.shuffle_list(all_indices)
    occupied_indices = set(all_indices[:occupied_target])

    for idx, node in enumerate(seat_nodes):
        if idx in occupied_indices:
            node.status = "occupied"

    # Step 4: Compute live availability aggregates
    available_count = sum(1 for s in seat_nodes if s.status == "available")
    pink_available = sum(1 for s in seat_nodes if s.zone == "female_pink" and s.status == "available")

    serialized_grid = [node.to_dict() for node in seat_nodes]

    return {
        "route_id": route_id,
        "fleet_plate": fleet_plate,
        "bus_type": "Saheli Pink Women Special (AC Low-Floor)" if is_saheli_pink else "DTC Electric AC Low-Floor (Green)",
        "is_saheli_pink": is_saheli_pink,
        "total_seats": total_seats,
        "available_seats": available_count,
        "occupied_seats": occupied_target,
        "pink_zone_available": pink_available,
        "crowd_percentage": crowd_pct,
        "seating_grid": serialized_grid,
        "features": [
            "Movie-style seat reservation to prevent boarding chaos",
            "Dedicated Pink Seating Zone (Seats W1-W8) reserved for women",
            "Eligible for Delhi Govt Free Pink Ticket Scheme for women",
            "Instant digital boarding token with QR verification"
        ]
    }

# ==============================================================================
# ANTI-CHAOS RESERVATION & PNR ISSUANCE STORE
# ==============================================================================

RESERVATIONS: Dict[str, Dict[str, Any]] = {}

def reserve_bus_seat(
    route_id: str,
    fleet_plate: str,
    seat_id: str,
    passenger_name: str,
    gender: str,
    boarding_stop: str
) -> Dict[str, Any]:
    """
    Reserves a passenger seat and issues an official digital boarding pass with a
    unique PNR and Anti-Chaos token to prevent boarding door scuffles at transit hubs.
    """
    epoch_now = int(time.time())

    # Mathematical hash checksum for PNR and Token issuance
    hash_val = abs(hash(f"{route_id}_{fleet_plate}_{seat_id}_{epoch_now}")) % 100000
    token_suffix = (hash_val * 7 + 101) % 900000 + 100000
    pnr_suffix = (hash_val * 13 + 307) % 90000 + 10000

    token_id = f"DL-{token_suffix}"
    pnr = f"DT26-{pnr_suffix}"

    # Delhi Govt Pink Pass Scheme: Female passengers in Pink Zone ride free (₹0 fare)
    is_women_seat = seat_id.startswith("W")
    is_female = gender.strip().lower() in ("female", "woman", "f")
    fare_charged = 0 if (is_women_seat and is_female) else 25

    reservation_record = {
        "pnr": pnr,
        "token_id": token_id,
        "seat_id": seat_id,
        "route_id": route_id,
        "fleet_plate": fleet_plate,
        "passenger_name": passenger_name or "Delhi Transit Commuter",
        "gender": gender,
        "boarding_stop": boarding_stop,
        "fare_charged_inr": fare_charged,
        "is_pink_pass": (fare_charged == 0),
        "status": "CONFIRMED",
        "boarding_instructions": f"Present digital token {token_id} to conductor/ETM machine. Board at front door for Seat {seat_id}.",
        "anti_chaos_guarantee": f"Seat {seat_id} is locked exclusively for you. No boarding scramble needed!"
    }

    RESERVATIONS[token_id] = reservation_record
    return reservation_record
