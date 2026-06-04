import os
import math
import json
import urllib.request
import urllib.parse
import time
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import google.genai as genai

# Load environment variables
load_dotenv()

logger = logging.getLogger("crisisroute.routing")


GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
DEBUG_ROUTING = os.getenv("DEBUG_ROUTING", "false").lower() == "true"


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance in kilometers between two points
    on the earth (specified in decimal degrees)
    """
    R = 6371.0  # Earth radius in kilometers

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

def get_google_maps_eta(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float
) -> Optional[int]:
    """
    Calls Google Maps Distance Matrix API for driving ETA in minutes.
    Returns None on any error or if key is missing.
    """
    if not GOOGLE_MAPS_API_KEY or "your_maps_key" in GOOGLE_MAPS_API_KEY or len(GOOGLE_MAPS_API_KEY) < 10:
        return None

    try:
        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            "origins": f"{origin_lat},{origin_lng}",
            "destinations": f"{dest_lat},{dest_lng}",
            "mode": "driving",
            "key": GOOGLE_MAPS_API_KEY
        }
        query_string = urllib.parse.urlencode(params)
        full_url = f"{url}?{query_string}"
        
        req = urllib.request.Request(full_url, headers={"User-Agent": "CrisisRoute/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            
        if data.get("status") == "OK":
            row = data.get("rows", [{}])[0]
            element = row.get("elements", [{}])[0]
            if element.get("status") == "OK":
                duration_sec = element.get("duration", {}).get("value", 0)
                return max(1, int(duration_sec / 60))
    except Exception as e:
        print(f"Error calling Google Maps API: {e}")
        
    return None

def rank_hospitals(
    hospitals: list,
    capacity: dict,
    patient_lat: float,
    patient_lng: float,
    severity: str,
    specialty: str
) -> list:
    """
    Ranks hospitals based on distance, capacity, specialties, and severity.
    Returns the top 5 sorted by composite score descending.
    """
    scored_hospitals = []
    
    # Calculate distance and ETA for all first to establish max_dist and max_eta
    candidate_dists = []
    candidate_etas = []
    filtered_candidates = []
    
    sev = severity.lower()
    
    for h in hospitals:
        hid = h.get("hospital_id")
        cap = capacity.get(hid, {})
        cap_status = cap.get("capacity_status", h.get("capacity_status", "full"))
        
        # Step 1: Filter
        if cap_status == "full" and sev != "critical":
            continue
            
        h_lat = h.get("lat") or h.get("location", {}).get("lat") or 0.0
        h_lng = h.get("lng") or h.get("location", {}).get("lon") or 0.0
        dist = haversine(patient_lat, patient_lng, h_lat, h_lng)
        
        # Calculate ETA
        eta_minutes = get_google_maps_eta(patient_lat, patient_lng, h_lat, h_lng)
        if eta_minutes is None:
            if sev == "critical":
                eta_minutes = max(1, int(dist / 0.7))  # 42 km/h
            elif sev == "urgent":
                eta_minutes = max(1, int(dist / 0.5))  # 30 km/h
            else:
                eta_minutes = max(1, int(dist / 0.4))  # 24 km/h
        
        candidate_dists.append(dist)
        candidate_etas.append(eta_minutes)
        filtered_candidates.append((h, cap, dist, h_lat, h_lng, cap_status, eta_minutes))
        
    if not filtered_candidates:
        return []
        
    max_dist = max(candidate_dists) if candidate_dists else 1.0
    max_eta = max(candidate_etas) if candidate_etas else 1.0
    min_eta = min(candidate_etas) if candidate_etas else 1.0

    # Step 2: Score each hospital
    for h, cap, dist_km, h_lat, h_lng, cap_status, eta_minutes in filtered_candidates:
        # Distance score (closer = higher score)
        dist_score = 1.0 - (dist_km / max_dist) if max_dist > 0 else 1.0
        
        # ETA score (closer = higher score) using bounded normalization
        if max_eta == min_eta:
            eta_score = 1.0
        else:
            eta_score = 1.0 - ((eta_minutes - min_eta) / (max_eta - min_eta))
        
        # Capacity score
        beds_avail = cap.get("beds_available", h.get("beds_available", 0))
        if beds_avail > 20:
            capacity_score = 1.0
        elif beds_avail > 10:
            capacity_score = 0.7
        elif beds_avail > 0:
            capacity_score = 0.4
        else:
            capacity_score = 0.0
            
        # ICU score
        icu_avail = cap.get("icu_available", h.get("icu_available", 0))
        icu_score = math.log1p(icu_avail) / math.log1p(50)
        
        # Specialty match score
        h_specs = h.get("specialties", [])
        specialty_match = specialty in h_specs
        specialty_score = 1.0 if specialty_match else 0.3
        
        # Government bonus
        is_govt = h.get("is_government", False)
        gov_bonus = 0.0

        
        # Severity-adjusted weights:
        if sev == "critical":
            weights = {
                "eta": 0.40,
                "distance": 0.05,
                "capacity": 0.15,
                "icu": 0.25,
                "specialty": 0.15
            }
        elif sev == "urgent":
            weights = {
                "eta": 0.15,
                "distance": 0.25,
                "capacity": 0.25,
                "icu": 0.10,
                "specialty": 0.25
            }
        else:  # stable
            weights = {
                "eta": 0.10,
                "distance": 0.40,
                "capacity": 0.30,
                "icu": 0.05,
                "specialty": 0.15
            }
            
        composite_score = (
            eta_score * weights["eta"] +
            dist_score * weights["distance"] +
            capacity_score * weights["capacity"] +
            icu_score * weights["icu"] +
            specialty_score * weights["specialty"] +
            gov_bonus
        )
        
        # Penalty if capacity is full and patient is critical
        if cap_status == "full":
            composite_score -= 0.20

        hospital_name = h.get("name")

        if DEBUG_ROUTING:
            print(
                f"{hospital_name} | "
                f"ETA={eta_score:.3f} "
                f"DIST={dist_score:.3f} "
                f"CAP={capacity_score:.3f} "
                f"ICU={icu_score:.3f} "
                f"SPEC={specialty_score:.3f} "
                f"FINAL={composite_score:.3f}"
            )

        scored_hospitals.append({
            "hospital_id": h.get("hospital_id"),
            "name": h.get("name"),
            "district": h.get("district"),
            "state": h.get("state", "Andhra Pradesh"),
            "lat": h_lat,
            "lng": h_lng,
            "distance_km": round(dist_km, 1),
            "eta_minutes": eta_minutes,
            "beds_available": beds_avail,
            "icu_available": icu_avail,
            "ventilators_available": cap.get("ventilators_available", h.get("ventilators_available", 0)),
            "capacity_status": cap_status,
            "specialty_match": specialty_match,
            "is_government": is_govt,
            "accreditation": h.get("accreditation"),
            "rating": h.get("rating", 0.0),
            "composite_score": round(composite_score, 3),
            "hospital_tier": h.get("hospital_tier"),
            "has_cardiology": h.get("has_cardiology", False),
            "has_trauma": h.get("has_trauma", False),
            "has_neurology": h.get("has_neurology", False),
            "has_oncology": h.get("has_oncology", False),
            "score_breakdown": {
                "raw_eta_minutes": eta_minutes,
                "raw_distance_km": round(dist_km, 1),
                "beds_available": beds_avail,
                "icu_available": icu_avail,
                "eta_score": round(eta_score, 3),
                "distance_score": round(dist_score, 3),
                "capacity_score": round(capacity_score, 3),
                "icu_score": round(icu_score, 3),
                "specialty_score": round(specialty_score, 3),
                "government_bonus": gov_bonus,
                "final_score": round(composite_score, 3)
            },
            "contact_phone": h.get("contact_phone"),
            "emergency_phone": "108",
            "maps_directions_url": f"https://www.google.com/maps/dir/?api=1&destination={h_lat},{h_lng}&travelmode=driving",
            "maps_embed_url": f"https://maps.google.com/maps?q={h_lat},{h_lng}&z=15&output=embed"
        })
        
    # Sort by composite_score descending
    scored_hospitals.sort(key=lambda x: x["composite_score"], reverse=True)
    
    # Assign ranks
    for idx, item in enumerate(scored_hospitals):
        item["rank"] = idx + 1
        
    return scored_hospitals[:5]

class RoutingExplanation(BaseModel):
    selected_hospital: str = Field(..., description="Name of the selected hospital (ranked #1)")
    routing_explanation: str = Field(..., description="Detailed clinical routing justification of why this hospital was selected, including risk factors considered")
    rejected_options: List[str] = Field(..., description="Explanations of why the nearby alternative hospitals (ranks #2, #3, etc.) were rejected for selection")
    confidence_score: float = Field(..., description="Confidence score between 0.0 and 1.0 representing the quality of the match")

def generate_routing_explanation(
    ranked_hospitals: List[Dict[str, Any]],
    severity: str,
    specialty: str
) -> Dict[str, Any]:
    """
    Generates a clinical explanation of why the top hospital was selected and why alternatives were rejected.
    Uses Gemini 2.5 Flash.
    """
    if not ranked_hospitals:
        return {
            "selected_hospital": "None",
            "routing_explanation": "No candidate hospitals available for explanation.",
            "rejected_options": [],
            "confidence_score": 0.0
        }

    fallback_explanation = {
        "selected_hospital": ranked_hospitals[0]["name"],
        "routing_explanation": "Selected based on optimal composite score combining ETA, distance, and specialty care capabilities.",
        "rejected_options": [f"{h.get('name')} was rejected due to lower priority ranking." for h in ranked_hospitals[1:]],
        "confidence_score": 0.80
    }

    # Format candidates list for Gemini context
    candidates_context = []
    for h in ranked_hospitals:
        sb = h.get("score_breakdown", {})
        candidates_context.append({
            "rank": h.get("rank"),
            "name": h.get("name"),
            "eta_minutes": h.get("eta_minutes"),
            "distance_km": h.get("distance_km"),
            "beds_available": h.get("beds_available"),
            "icu_available": h.get("icu_available"),
            "hospital_tier": h.get("hospital_tier"),
            "is_government": h.get("is_government"),
            "specialties": h.get("specialties"),
            "score_breakdown": sb
        })

    system_prompt = """
You are the Clinical Lead of the CrisisRoute Emergency Routing Engine.
Your job is to generate a clinical explainability layer for the hospital routing decision.
You will be given:
1. Patient's triage severity and clinical specialty required.
2. A list of candidate hospitals that were ranked. The list is sorted from rank 1 (top choice, selected) down to lower ranks (rejected options).
3. The capacity metrics and special properties for each hospital.

You must explain:
1. Why the selected hospital (rank #1) is the optimal choice based on its score breakdown, ETA, capacity, and capabilities.
2. Why nearby alternative hospitals (ranks 2+) were rejected in favor of the first option (e.g. slower ETA, lack of intensive care units, or different tier).
3. The clinical risk factors considered (e.g. golden hour timelines for critical cardiac/stroke patients, capacity saturation risk).
4. The overall clinical routing justification.

Maintain medical precision, clarity, and conciseness. Your explanation will be displayed directly to the dispatch team and the hospital emergency bay.
"""

    user_prompt = f"""
Patient Severity: {severity.upper()}
Required Specialty: {specialty.upper()}

Ranked Candidates:
{json.dumps(candidates_context, indent=2)}
"""

    for attempt in range(3):
        try:
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if api_key:
                client = genai.Client(api_key=api_key)
            else:
                project = os.getenv("GOOGLE_CLOUD_PROJECT") or "crisisroute-2026-498212"
                location = os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1"
                client = genai.Client(vertexai=True, project=project, location=location)
                
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=user_prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.1,
                    max_output_tokens=2000,
                    response_mime_type="application/json",
                    response_schema=RoutingExplanation,
                )
            )
            raw = response.text.strip()
            result = json.loads(raw, strict=False)
            return result
        except Exception as e:
            logger.warning(f"generate_routing_explanation attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)

    logger.error("generate_routing_explanation: all 3 attempts failed — returning fallback")
    return fallback_explanation

if __name__ == "__main__":
    mock_hospitals = [
        {"hospital_id": "AP-KRS-001", "name": "GGH Vijayawada", 
         "lat": 16.5062, "lng": 80.6480, "beds_available": 45, "icu_available": 3,
         "ventilators_available": 2, "specialties": ["cardiology", "trauma", "general"],
         "is_government": True, "accreditation": "Govt", "rating": 3.8,
         "contact_phone": "+91-866-2577990", "district": "Krishna"},
        {"hospital_id": "AP-KRS-002", "name": "Apollo Hospitals Vijayawada",
         "lat": 16.5180, "lng": 80.6350, "beds_available": 8, "icu_available": 4,
         "ventilators_available": 3, "specialties": ["cardiology", "neurology", "oncology"],
         "is_government": False, "accreditation": "JCI", "rating": 4.5,
         "contact_phone": "+91-866-6666666", "district": "Krishna"},
    ]
    mock_capacity = {
        "AP-KRS-001": {"beds_available": 45, "icu_available": 3, "capacity_status": "available"},
        "AP-KRS-002": {"beds_available": 8, "icu_available": 4, "capacity_status": "limited"},
    }
    ranked = rank_hospitals(mock_hospitals, mock_capacity, 16.5062, 80.6480, "critical", "cardiology")
    for h in ranked:
        print(f"Rank {h['rank']}: {h['name']} | {h['distance_km']}km | ETA {h['eta_minutes']}min | Score {h['composite_score']}")
    
    explanation = generate_routing_explanation(ranked, "critical", "cardiology")
    print(f"\nAI Explanation: {json.dumps(explanation, indent=2)}")

