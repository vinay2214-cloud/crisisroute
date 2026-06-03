import os
import math
import json
import urllib.request
import urllib.parse
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

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
    
    # Calculate distance for all first to establish max_dist
    candidate_dists = []
    filtered_candidates = []
    
    for h in hospitals:
        hid = h.get("hospital_id")
        cap = capacity.get(hid, {})
        cap_status = cap.get("capacity_status", h.get("capacity_status", "full"))
        
        # Step 1: Filter
        if cap_status == "full" and severity.lower() != "critical":
            continue
            
        h_lat = h.get("lat") or h.get("location", {}).get("lat") or 0.0
        h_lng = h.get("lng") or h.get("location", {}).get("lon") or 0.0
        dist = haversine(patient_lat, patient_lng, h_lat, h_lng)
        
        candidate_dists.append(dist)
        filtered_candidates.append((h, cap, dist, h_lat, h_lng, cap_status))
        
    if not filtered_candidates:
        return []
        
    max_dist = max(candidate_dists) if candidate_dists else 1.0

    # Step 2: Score each hospital
    for h, cap, dist_km, h_lat, h_lng, cap_status in filtered_candidates:
        # Distance score (closer = higher score)
        dist_score = 1.0 - (dist_km / max_dist) if max_dist > 0 else 1.0
        
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
        icu_score = min(icu_avail / 4, 1.0)
        
        # Specialty match score
        h_specs = h.get("specialties", [])
        specialty_match = specialty in h_specs
        specialty_score = 1.0 if specialty_match else 0.3
        
        # Government bonus
        is_govt = h.get("is_government", False)
        gov_bonus = 0.05 if is_govt else 0.0
        
        # Severity-adjusted weights:
        sev = severity.lower()
        if sev == "critical":
            weights = {"distance": 0.35, "capacity": 0.20, "icu": 0.25, "specialty": 0.20}
        elif sev == "urgent":
            weights = {"distance": 0.40, "capacity": 0.25, "icu": 0.10, "specialty": 0.25}
        else:  # stable
            weights = {"distance": 0.50, "capacity": 0.30, "icu": 0.05, "specialty": 0.15}
            
        composite_score = (
            dist_score * weights["distance"] +
            capacity_score * weights["capacity"] +
            icu_score * weights["icu"] +
            specialty_score * weights["specialty"] +
            gov_bonus
        )
        
        # Penalty if capacity is full and patient is critical
        if cap_status == "full":
            composite_score -= 0.20

        # Step 3: Calculate ETA
        eta_minutes = get_google_maps_eta(patient_lat, patient_lng, h_lat, h_lng)
        if eta_minutes is None:
            if sev == "critical":
                eta_minutes = max(1, int(dist_km / 0.7))  # 42 km/h
            elif sev == "urgent":
                eta_minutes = max(1, int(dist_km / 0.5))  # 30 km/h
            else:
                eta_minutes = max(1, int(dist_km / 0.4))  # 24 km/h

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
