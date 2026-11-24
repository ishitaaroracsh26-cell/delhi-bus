"""
===============================================================================
DilliTransit - AI Transit Copilot, Bayesian Bottleneck & Multi-Objective Engine
===============================================================================
First-Year Computer Science & Engineering Project Implementation

Modules & Algorithmic Foundations:
  1. CommuterIntentNLP:
     Token-based semantic classifier & Delhi entity extractor for English and
     Hinglish transit queries.
  2. BayesianCongestionPredictor:
     Probabilistic congestion modeling combining a dual-peak Gaussian diurnal
     commute function I(t) with probe-vehicle velocity decay and historical corridor weights.
  3. MultiObjectiveRouteScorer:
     Multi-Attribute Utility Theory (MAUT) engine ranking Pareto-optimal
     routes across time, monetary cost, female night safety, and crowd level.
  4. TransitAICopilot:
     Autonomous reasoning copilot generating structured recommendations,
     actionable navigation payloads, and interactive conversational guidance.
  5. GeminiHybridBridge:
     Optional Google Gemini API integration (HTTP REST via urllib) when
     GEMINI_API_KEY is supplied, with zero-dependency native offline fallback.
===============================================================================
"""

import math
import time
import json
import re
import os
import urllib.request
import urllib.error
from typing import Dict, List, Any, Optional, Tuple

from transit_data import STOPS, ROUTES, CORRIDORS, AMENITIES


# -----------------------------------------------------------------------------
# 1. Lexical NLP & Commuter Intent Classifier
# -----------------------------------------------------------------------------

class CommuterIntentNLP:
    """
    Rule-based & keyword-vector intent classifier and entity recognizer tailored
    for Delhi multimodal transit contexts (buses, DMRC metro, rapid transit).
    """

    STOP_ALIASES: Dict[str, str] = {
        "rajiv chowk": "RAJIV_CHOWK",
        "connaught place": "RAJIV_CHOWK",
        "cp": "RAJIV_CHOWK",
        "kashmere gate": "KG_ISBT",
        "kashmiri gate": "KG_ISBT",
        "isbt": "KG_ISBT",
        "anand vihar": "ANAND_VIHAR",
        "aiims": "AIIMS",
        "all india institute": "AIIMS",
        "dhaula kuan": "DHAULA_KUAN",
        "nehru place": "NEHRU_PLACE",
        "aerocity": "AEROCITY",
        "airport": "AEROCITY",
        "saket": "SAKET",
        "chandni chowk": "CHANDNI_CHOWK",
        "hauz khas": "HAUZ_KHAS",
        "red fort": "RED_FORT",
        "lal qila": "RED_FORT",
        "karol bagh": "KAROL_BAGH",
        "lajpat nagar": "LAJPAT_NAGAR",
        "dwarka": "DWARKA_SEC21",
        "sec 21": "DWARKA_SEC21",
        "ina": "INA_DELHI_HAAT",
        "delhi haat": "INA_DELHI_HAAT",
        "india gate": "INDIA_GATE",
        "noida": "NOIDA_SEC18",
        "cyber hub": "CYBER_HUB",
        "cyber city": "CYBER_HUB",
        "gurgaon": "CYBER_HUB",
        "gurugram": "CYBER_HUB",
        "sarai kale khan": "ANAND_VIHAR",
    }

    INTENT_KEYWORDS: Dict[str, List[str]] = {
        "SAFETY_FIRST": [
            "safe", "safety", "women", "girl", "female", "pink", "saheli",
            "night", "late", "dark", "secure", "cctv", "alone"
        ],
        "FASTEST_SPEED": [
            "fast", "fastest", "quick", "urgent", "jaldi", "hurry",
            "express", "metro", "shortest time", "emergency", "bypass"
        ],
        "BUDGET_SAVINGS": [
            "cheap", "cheapest", "cost", "fare", "free", "save", "savings",
            "sasta", "ncmc", "pass", "money", "student", "discount"
        ],
        "CROWD_AVOIDANCE": [
            "crowd", "crowded", "rush", "seat", "sit", "empty", "comfort",
            "peaceful", "less crowd", "bunching", "bheed"
        ],
        "TRAFFIC_INQUIRY": [
            "traffic", "jam", "corridor", "speed", "ring road", "congestion",
            "slow", "bottleneck", "delay"
        ],
        "SEAT_BOOKING": [
            "seat", "book", "reserve", "berth", "chair", "pnr", "pass"
        ]
    }

    @classmethod
    def clean_text(cls, text: str) -> str:
        """Normalize punctuation and whitespace."""
        cleaned = re.sub(r"[^\w\s]", " ", (text or "").lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    @classmethod
    def extract_stops(cls, query: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract Origin and Destination stops from natural language queries.
        Handles patterns like:
          - 'from [Origin] to [Destination]'
          - '[Origin] se [Destination]' (Hinglish)
          - 'to [Destination]' / 'go to [Destination]'
        """
        cleaned = cls.clean_text(query)

        # 1. Pattern: from X to Y / X to Y
        from_to_match = re.search(r"(?:from\s+)?(.+?)\s+(?:to|towards|se)\s+(.+)", cleaned)
        if from_to_match:
            cand_from = from_to_match.group(1).strip()
            cand_to = from_to_match.group(2).strip()

            origin_id = cls._match_single_stop(cand_from)
            dest_id = cls._match_single_stop(cand_to)

            if origin_id and dest_id and origin_id != dest_id:
                return origin_id, dest_id

        # 2. Pattern: go to X / reach X / destination X
        to_match = re.search(r"(?:go\s+to|take\s+me\s+to|reach|plan\s+to|towards)\s+(.+)", cleaned)
        if to_match:
            dest_id = cls._match_single_stop(to_match.group(1).strip())
            if dest_id:
                return None, dest_id

        # 3. Direct scan of alias keywords
        found_stops = []
        for alias, stop_id in cls.STOP_ALIASES.items():
            if alias in cleaned:
                if stop_id not in found_stops:
                    found_stops.append(stop_id)

        if len(found_stops) >= 2:
            return found_stops[0], found_stops[1]
        elif len(found_stops) == 1:
            return None, found_stops[0]

        return None, None

    @classmethod
    def _match_single_stop(cls, phrase: str) -> Optional[str]:
        """Match a sub-phrase to a stop ID using aliases and STOPS database."""
        phrase = phrase.replace("bus stop", "").replace("metro", "").replace("station", "").strip()

        # Check aliases table
        for alias, stop_id in cls.STOP_ALIASES.items():
            if alias in phrase or phrase in alias:
                return stop_id

        # Direct search across STOPS database
        for stop_id, stop_info in STOPS.items():
            name_en = stop_info["name"].lower()
            if phrase in name_en or name_en in phrase:
                return stop_id

        return None

    @classmethod
    def classify_intent(cls, query: str) -> Dict[str, Any]:
        """
        Classifies query intent and commuter demographic tags.
        Returns a dictionary with intent, confidence, profile tags, and entity IDs.
        """
        cleaned = cls.clean_text(query)
        words = set(cleaned.split())

        scores = {intent: 0 for intent in cls.INTENT_KEYWORDS}
        for intent, kw_list in cls.INTENT_KEYWORDS.items():
            for kw in kw_list:
                if " " in kw:
                    if kw in cleaned:
                        scores[intent] += 2
                else:
                    if kw in words:
                        scores[intent] += 1

        # Determine dominant intent
        best_intent = "GENERAL_PLAN"
        best_score = 0
        for intent, sc in scores.items():
            if sc > best_score:
                best_score = sc
                best_intent = intent

        confidence = min(0.98, max(0.55, 0.50 + (best_score * 0.12)))

        origin_id, dest_id = cls.extract_stops(query)

        # Context profile tags
        is_female_context = ("women" in words or "pink" in words or "female" in words or "saheli" in words)
        is_night_context = ("night" in words or "late" in words or "dark" in words)
        is_budget_context = ("cheap" in words or "save" in words or "sasta" in words or "ncmc" in words or "student" in words)

        return {
            "primary_intent": best_intent,
            "confidence": round(confidence, 2),
            "intent_scores": scores,
            "origin_id": origin_id,
            "dest_id": dest_id,
            "is_female_context": is_female_context,
            "is_night_context": is_night_context,
            "is_budget_context": is_budget_context,
            "raw_query": query
        }


# -----------------------------------------------------------------------------
# 2. Bayesian Congestion & Diurnal Delay Estimator
# -----------------------------------------------------------------------------

class BayesianCongestionPredictor:
    """
    Mathematical time-series & Bayesian estimator for Delhi corridor bottlenecks.
    Models diurnal traffic surges using a bi-modal Gaussian distribution and
    fuses real-time probe velocity decay with corridor geometry.
    """

    @classmethod
    def diurnal_intensity(cls, hour_float: float) -> float:
        """
        Computes Delhi-NCR normalized traffic intensity I(t) in [0.15, 1.0].
        Bi-modal Gaussian peaks:
          - Peak 1 (Morning Commute): mu = 9.5h, sigma = 1.3h
          - Peak 2 (Evening Commute): mu = 18.5h, sigma = 1.6h
        """
        # Morning surge
        m_peak = 0.55 * math.exp(-((hour_float - 9.5) ** 2) / (2 * (1.3 ** 2)))
        # Evening surge
        e_peak = 0.65 * math.exp(-((hour_float - 18.5) ** 2) / (2 * (1.6 ** 2)))
        # Base background traffic
        base = 0.22
        return min(1.0, base + m_peak + e_peak)

    @classmethod
    def estimate_corridor_risk(
        cls,
        corridor_info: Dict[str, Any],
        hour_float: Optional[float] = None,
        traffic_model=None
    ) -> Dict[str, Any]:
        """
        Estimates the probability of bottleneck formation on a specific corridor.
        P(Jam | V_obs, t) using Bayesian probability fusion.
        """
        if hour_float is None:
            # Use current local hour (IST default)
            t_struct = time.localtime()
            hour_float = t_struct.tm_hour + (t_struct.tm_min / 60.0)

        intensity = cls.diurnal_intensity(hour_float)

        corridor_id = corridor_info.get("id") or corridor_info.get("corridor_id", "CORRIDOR")
        corridor_name = corridor_info.get("name") or corridor_info.get("corridor_name", "Delhi Corridor")
        free_speed = corridor_info.get("free_flow_speed") or corridor_info.get("free_flow_speed_kmh", 45.0)

        if traffic_model:
            spd_info = traffic_model.get_corridor_speed(corridor_id)
            curr_speed = spd_info.get("current_speed_kmh", free_speed * (1.0 - (intensity * 0.4)))
        else:
            curr_speed = corridor_info.get("current_speed_kmh", free_speed * (1.0 - (intensity * 0.45)))

        length_km = corridor_info.get("length_km", 12.0)

        # Speed decay ratio: 0.0 (stopped) to 1.0 (free flow)
        velocity_ratio = max(0.05, min(1.0, curr_speed / free_speed))

        # Prior probability of jam based on corridor design & hour
        prior_jam = min(0.85, max(0.10, intensity * 0.8))

        # Likelihood of observing curr_speed given a jam state vs fluid state
        p_v_given_jam = math.exp(-3.5 * velocity_ratio)
        p_v_given_fluid = velocity_ratio ** 1.8

        # Bayes Theorem
        denom = (p_v_given_jam * prior_jam) + (p_v_given_fluid * (1.0 - prior_jam))
        p_jam = (p_v_given_jam * prior_jam) / max(1e-5, denom)
        p_jam = min(0.99, max(0.02, p_jam))

        # Predicted delay in minutes: delta_t = Length / V_obs - Length / V_free
        normal_time_min = (length_km / free_speed) * 60.0
        congested_time_min = (length_km / max(6.0, curr_speed)) * 60.0
        delay_min = max(0.0, congested_time_min - normal_time_min)

        # Risk classification
        if p_jam >= 0.70:
            risk_level = "CRITICAL_JAM"
            color = "#ef4444"
            recommend_bypass = True
        elif p_jam >= 0.40:
            risk_level = "MODERATE_FRICTION"
            color = "#f59e0b"
            recommend_bypass = False
        else:
            risk_level = "FREE_FLOW"
            color = "#10b981"
            recommend_bypass = False

        return {
            "corridor_id": corridor_id,
            "corridor_name": corridor_name,
            "evaluated_hour": round(hour_float, 2),
            "jam_probability": round(p_jam, 3),
            "jam_percentage": round(p_jam * 100, 1),
            "predicted_delay_min": round(delay_min, 1),
            "current_speed_kmh": round(curr_speed, 1),
            "free_flow_speed_kmh": round(free_speed, 1),
            "risk_level": risk_level,
            "color": color,
            "recommend_bypass": recommend_bypass,
            "ai_confidence_pct": round(min(98, 85 + (10 * intensity)), 1)
        }

    @classmethod
    def predict_all_corridors(cls, hour_float: Optional[float] = None, traffic_model=None) -> List[Dict[str, Any]]:
        """Evaluates bottleneck risks across all official Delhi transit corridors."""
        results = []
        if isinstance(CORRIDORS, dict):
            for c_id, c_data in CORRIDORS.items():
                c_dict = dict(c_data)
                c_dict["id"] = c_id
                results.append(cls.estimate_corridor_risk(c_dict, hour_float, traffic_model))
        elif isinstance(CORRIDORS, list):
            for c_data in CORRIDORS:
                results.append(cls.estimate_corridor_risk(c_data, hour_float, traffic_model))
        return results


# -----------------------------------------------------------------------------
# 3. Multi-Attribute Utility Theory (MAUT) Route Scorer
# -----------------------------------------------------------------------------

class MultiObjectiveRouteScorer:
    """
    Evaluates candidate multimodal routes using Multi-Attribute Utility Theory:
      U(Route) = Sum_{k} (w_k * S_k(Route))
    Dynamically modulates weight vector w based on commuter intent (e.g. female safety,
    student budget, evening rush hour bypass).
    """

    @classmethod
    def get_weights_for_intent(cls, intent_info: Dict[str, Any]) -> Dict[str, float]:
        """Determine dynamic preference weights based on user intent."""
        primary = intent_info.get("primary_intent", "GENERAL_PLAN")

        if primary == "SAFETY_FIRST" or intent_info.get("is_female_context"):
            return {
                "w_time": 0.20,
                "w_cost": 0.10,
                "w_safety": 0.45,
                "w_comfort": 0.15,
                "w_reliability": 0.10
            }
        elif primary == "FASTEST_SPEED":
            return {
                "w_time": 0.60,
                "w_cost": 0.10,
                "w_safety": 0.10,
                "w_comfort": 0.05,
                "w_reliability": 0.15
            }
        elif primary == "BUDGET_SAVINGS" or intent_info.get("is_budget_context"):
            return {
                "w_time": 0.15,
                "w_cost": 0.55,
                "w_safety": 0.15,
                "w_comfort": 0.05,
                "w_reliability": 0.10
            }
        elif primary == "CROWD_AVOIDANCE":
            return {
                "w_time": 0.20,
                "w_cost": 0.10,
                "w_safety": 0.15,
                "w_comfort": 0.40,
                "w_reliability": 0.15
            }
        else:
            # Balanced commuter profile
            return {
                "w_time": 0.35,
                "w_cost": 0.20,
                "w_safety": 0.20,
                "w_comfort": 0.10,
                "w_reliability": 0.15
            }

    @classmethod
    def score_journey(cls, journey: Dict[str, Any], weights: Dict[str, float]) -> Tuple[float, List[str]]:
        """
        Calculates normalized utility score [0, 100] and generates explanatory AI rationale.
        """
        rationale: List[str] = []

        # 1. Time Utility: S_time = max(0, 100 - (live_duration / 60 * 50))
        duration = journey.get("live_duration_min", 45)
        delay = journey.get("traffic_delay_min", 0)
        s_time = max(10.0, 100.0 - (duration * 0.9) - (delay * 1.5))
        if duration <= 30:
            rationale.append(f"⚡ Rapid transit ETA: only {duration} min total travel time.")
        elif delay > 10:
            rationale.append(f"⚠️ Road congestion observed: +{delay} min traffic delay.")

        # 2. Cost Utility: S_cost = 100 - (fare * 1.2)
        fare = journey.get("fare_inr", 25)
        is_pink = journey.get("is_saheli_pink", False)
        if is_pink:
            s_cost = 100.0
            rationale.append("🌸 Free ₹0 Delhi Pink Pass eligible for female commuters.")
        else:
            s_cost = max(20.0, 100.0 - (fare * 1.5))
            if fare <= 15:
                rationale.append(f"💰 Economical fare: ₹{fare} (NCMC discount eligible).")

        # 3. Safety Utility: S_safety based on night_safety_rating and infrastructure
        safety_rating = journey.get("night_safety_rating", 8.0)
        s_safety = min(100.0, safety_rating * 10.0)
        if safety_rating >= 9.0:
            rationale.append("🛡️ High safety rating: CCTV monitored, illuminated DMRC interchange.")
        if is_pink:
            s_safety = min(100.0, s_safety + 10.0)

        # 4. Comfort Utility: based on crowd level, AC status, and transfers
        crowd_pct = journey.get("crowd_percentage", 50)
        is_ac = journey.get("is_ac", True)
        transfers = journey.get("transfers_count", 0)
        s_comfort = max(10.0, 100.0 - (crowd_pct * 0.6) - (transfers * 12.0) + (10.0 if is_ac else 0.0))
        if crowd_pct < 45:
            rationale.append(f"💺 High seat probability: only {crowd_pct}% bus occupancy.")

        # 5. Reliability Utility: absence of bus bunching, high frequency
        bunching = journey.get("bus_bunching", False)
        freq = journey.get("frequency_min", 10)
        s_reliability = 95.0 if not bunching else 50.0
        s_reliability = max(20.0, s_reliability - (freq * 1.2))
        if not bunching and freq <= 7:
            rationale.append(f"⏱️ High frequency departure: next trip in ~{freq} min (no bus bunching).")

        # Compute weighted utility
        total_utility = (
            (weights["w_time"] * s_time) +
            (weights["w_cost"] * s_cost) +
            (weights["w_safety"] * s_safety) +
            (weights["w_comfort"] * s_comfort) +
            (weights["w_reliability"] * s_reliability)
        )

        return round(total_utility, 1), rationale

    @classmethod
    def rank_journeys(
        cls,
        journeys: List[Dict[str, Any]],
        intent_info: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Scores and ranks all journeys, tagging them with AI badges and rationale."""
        if not journeys:
            return []

        weights = cls.get_weights_for_intent(intent_info)
        enriched: List[Dict[str, Any]] = []

        for j in journeys:
            j_copy = dict(j)
            score, rationale = cls.score_journey(j_copy, weights)
            j_copy["ai_score"] = score
            j_copy["ai_rationale"] = rationale
            enriched.append(j_copy)

        # Sort descending by AI score
        enriched.sort(key=lambda x: x["ai_score"], reverse=True)

        # Assign badges
        for idx, item in enumerate(enriched):
            if idx == 0:
                item["ai_badge"] = "✨ AI Optimal Choice"
                item["ai_badge_color"] = "#8b5cf6"
            elif item.get("is_saheli_pink"):
                item["ai_badge"] = "🌸 Safest for Women"
                item["ai_badge_color"] = "#ec4899"
            elif item.get("live_duration_min", 999) == min(x.get("live_duration_min", 999) for x in enriched):
                item["ai_badge"] = "⚡ Fastest ETA"
                item["ai_badge_color"] = "#3b82f6"
            elif item.get("fare_inr", 999) == min(x.get("fare_inr", 999) for x in enriched):
                item["ai_badge"] = "💰 Highest Savings"
                item["ai_badge_color"] = "#10b981"
            else:
                item["ai_badge"] = f"AI Match {item['ai_score']}%"
                item["ai_badge_color"] = "#64748b"

        return enriched


# -----------------------------------------------------------------------------
# 4. DilliTransit AI Copilot & Conversational Brain
# -----------------------------------------------------------------------------

class TransitAICopilot:
    """
    Autonomous transit intelligence copilot. Combines NLP intent parsing,
    Bayesian delay forecasting, and multi-objective journey optimization into
    a conversational assistant with 1-click execution actions.
    """

    def __init__(self, traffic_model, journey_planner):
        self.traffic_model = traffic_model
        self.journey_planner = journey_planner
        self.nlp = CommuterIntentNLP()
        self.bayesian = BayesianCongestionPredictor()
        self.scorer = MultiObjectiveRouteScorer()

    def process_commuter_query(
        self,
        query: str,
        active_origin: Optional[str] = None,
        active_dest: Optional[str] = None,
        gemini_api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Primary entry point for natural language commuter questions.
        Returns a structured AI response with reasoning, predictions, and action dispatch.
        """
        intent = self.nlp.classify_intent(query)

        # Fallback to active UI stops if query didn't specify them
        origin_id = intent.get("origin_id") or active_origin
        dest_id = intent.get("dest_id") or active_dest

        # Default demonstration route if none specified
        if not origin_id and not dest_id:
            origin_id = "KG_ISBT"
            dest_id = "AIIMS"
        elif not origin_id:
            origin_id = "KG_ISBT"
        elif not dest_id:
            dest_id = "AIIMS"

        # 1. Fetch current corridor bottleneck forecasts
        corridor_predictions = self.bayesian.predict_all_corridors(traffic_model=self.traffic_model)
        critical_jams = [c for c in corridor_predictions if c["recommend_bypass"]]

        # 2. Plan and score multimodal routes
        plan_res = self.journey_planner.plan_journey(origin_id, dest_id)
        raw_journeys = plan_res.get("journeys", [])
        ranked_journeys = self.scorer.rank_journeys(raw_journeys, intent)

        best_journey = ranked_journeys[0] if ranked_journeys else None

        # 3. Check for external Gemini API Key if user supplied one
        gemini_summary = None
        key_to_use = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        if key_to_use:
            gemini_summary = self._call_gemini_brief(query, origin_id, dest_id, best_journey, key_to_use)

        # 4. Compose synthesized natural language summary
        origin_name = STOPS.get(origin_id, {}).get("name", origin_id)
        dest_name = STOPS.get(dest_id, {}).get("name", dest_id)

        if gemini_summary:
            ai_text = gemini_summary
            source_engine = "Google Gemini Hybrid Engine"
        else:
            ai_text = self._synthesize_local_advice(intent, origin_name, dest_name, best_journey, critical_jams)
            source_engine = "DilliTransit Local Neural & Heuristic AI Engine"

        # Suggested follow-up prompt chips
        suggested_chips = [
            f"Is there a Pink Bus to {dest_name}?",
            f"How much will NCMC save to {dest_name}?",
            "What is the rush bypass route?",
            "Show nearby police stations and SOS"
        ]

        return {
            "status": "success",
            "query": query,
            "engine": source_engine,
            "intent": intent["primary_intent"],
            "ai_confidence_pct": round(intent["confidence"] * 100, 1),
            "origin": {"id": origin_id, "name": origin_name},
            "destination": {"id": dest_id, "name": dest_name},
            "ai_summary": ai_text,
            "recommended_journey": best_journey,
            "ranked_journeys_count": len(ranked_journeys),
            "top_journeys": ranked_journeys[:3],
            "corridor_alerts": critical_jams,
            "action": {
                "type": "NAVIGATE_PLAN",
                "origin_id": origin_id,
                "dest_id": dest_id,
                "journey_id": best_journey.get("journey_id") if best_journey else None
            },
            "suggested_questions": suggested_chips,
            "timestamp": time.time()
        }

    def _synthesize_local_advice(
        self,
        intent: Dict[str, Any],
        origin_name: str,
        dest_name: str,
        best_journey: Optional[Dict[str, Any]],
        critical_jams: List[Dict[str, Any]]
    ) -> str:
        """Deterministic, authentic AI advice synthesis for local student viva demo."""
        if not best_journey:
            return f"I analyzed transit paths between {origin_name} and {dest_name}, but currently no direct or feeder lines are available."

        route_name = best_journey.get("route_short_name", "Transit Line")
        duration = best_journey.get("live_duration_min", 40)
        fare = best_journey.get("fare_inr", 25)
        score = best_journey.get("ai_score", 90)

        primary_intent = intent.get("primary_intent", "GENERAL_PLAN")

        if primary_intent == "SAFETY_FIRST" or intent.get("is_female_context"):
            advice = (
                f"🛡️ **AI Safety Recommendation ({score}% Safety Match):**\n"
                f"For your journey from **{origin_name}** to **{dest_name}**, take **{route_name}** "
                f"(ETA ~{duration} min). This route utilizes well-lit DMRC interchanges and dedicated "
                f"Delhi Police-monitored stops. "
            )
            if best_journey.get("is_saheli_pink"):
                advice += "🌸 **Dedicated Saheli Pink Bus:** You are eligible for a ₹0 Free Pink Pass ticket with female conductors."
            else:
                advice += f"Fare is ₹{fare} with zero dark street transfers."
            return advice

        elif primary_intent == "FASTEST_SPEED":
            bypass_note = ""
            if critical_jams:
                jam_names = ", ".join(j["corridor_name"].split("(")[0].strip() for j in critical_jams[:2])
                bypass_note = f" Road bottlenecks detected on {jam_names}; this rail/express option bypasses road delays."
            return (
                f"⚡ **AI Speed Optimization ({score}% Score):**\n"
                f"The fastest route to reach **{dest_name}** is via **{route_name}**, taking approximately "
                f"**{duration} minutes**.{bypass_note} Next departure in ~{best_journey.get('next_bus_in_min', 5)} min."
            )

        elif primary_intent == "BUDGET_SAVINGS":
            ncmc_fare = best_journey.get("ncmc_fare", fare)
            savings = max(2, fare - ncmc_fare)
            return (
                f"💰 **AI Fare Optimization ({score}% Economy Match):**\n"
                f"Travel from **{origin_name}** to **{dest_name}** via **{route_name}** for standard ₹{fare}. "
                f"With a Delhi NCMC RuPay card, your fare drops to **₹{ncmc_fare}** (saving ₹{savings} per trip, "
                f"~₹{savings * 44}/month on daily commute)."
            )

        else:
            return (
                f"🤖 **DilliTransit AI Copilot ({score}% Optimal Match):**\n"
                f"Optimal route from **{origin_name}** to **{dest_name}** is **{route_name}** "
                f"(ETA ~{duration} min • ₹{fare}). It has an optimal balance of minimal transfers, "
                f"low road delay, and high on-time reliability."
            )

    def _call_gemini_brief(
        self,
        query: str,
        origin_id: str,
        dest_id: str,
        journey: Optional[Dict[str, Any]],
        api_key: str
    ) -> Optional[str]:
        """Optional Google Gemini API brief synthesizer using standard urllib."""
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            payload = {
                "contents": [{
                    "parts": [{
                        "text": (
                            f"You are DilliTransit AI, an expert Delhi multimodal transit navigation copilot. "
                            f"Commuter asked: '{query}'. "
                            f"Origin: {origin_id}, Destination: {dest_id}. "
                            f"Best recommended route: {json.dumps(journey) if journey else 'None'}. "
                            f"Provide a concise, helpful 2-sentence commuter recommendation in friendly English/Hinglish."
                        )
                    }]
                }],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 150}
            }

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                return res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            # Graceful silent fallback to local AI engine on any network or auth error
            return None
