import os
import math
from dotenv import load_dotenv
from elasticsearch import Elasticsearch

# Load environment variables
load_dotenv()

ELASTIC_ENDPOINT = os.getenv("ELASTIC_ENDPOINT")
ELASTIC_API_KEY = os.getenv("ELASTIC_API_KEY")

es = Elasticsearch(
    ELASTIC_ENDPOINT,
    api_key=ELASTIC_API_KEY
)

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

def match_specialty(symptom_keywords: list, severity: str) -> dict:
    """
    Finds the best matching medical specialty for given symptoms using Elasticsearch
    with red-flags boosting and keyword-based fallbacks.
    """
    # 3. FALLBACK: Keyword rule-based matching
    def keyword_fallback(keywords):
        kw_str = " ".join(keywords).lower()
        if any(x in kw_str for x in ["chest", "heart", "cardiac"]):
            return "cardiology", 0.5, "general", "matched_symptom"
        elif any(x in kw_str for x in ["head", "brain", "stroke", "seizure"]):
            return "neurology", 0.5, "general", "matched_symptom"
        elif any(x in kw_str for x in ["accident", "trauma", "bleeding", "wound"]):
            return "trauma", 0.5, "general", "matched_symptom"
        elif any(x in kw_str for x in ["child", "infant", "baby", "pediatric"]):
            return "pediatrics", 0.5, "general", "matched_symptom"
        elif any(x in kw_str for x in ["pregnancy", "labor", "obstetric"]):
            return "gynecology", 0.5, "general", "matched_symptom"
        else:
            return "general", 0.5, "general", "matched_symptom"

    fallback_spec, fallback_conf, fallback_alt, fallback_match = keyword_fallback(symptom_keywords)
    
    if not es or not symptom_keywords:
        return {
            "specialty": fallback_spec,
            "confidence": fallback_conf,
            "alternative_specialty": fallback_alt,
            "search_method": "keyword_fallback",
            "matched_symptom": ""
        }

    query_str = " ".join(symptom_keywords)
    
    # 1. PRIMARY: Multi-match query on symptom_specialty_map index
    query = {
        "multi_match": {
            "query": query_str,
            "fields": ["symptom_text"],
            "type": "best_fields",
            "fuzziness": "AUTO"
        }
    }
    
    try:
        res = es.search(index="symptom_specialty_map", query=query, size=5)
        hits = res.get("hits", {}).get("hits", [])
        
        if not hits:
            # No results -> use fallback
            return {
                "specialty": fallback_spec,
                "confidence": fallback_conf,
                "alternative_specialty": fallback_alt,
                "search_method": "keyword_fallback",
                "matched_symptom": ""
            }
            
        top_match = hits[0]
        top_spec = top_match["_source"]["specialty"]
        top_score = top_match.get("_score", 1.0)
        top_text = top_match["_source"]["symptom_text"]
        
        confidence = min(1.0, top_score / 10.0)
        
        alt_spec = "general"
        if len(hits) > 1:
            for hit in hits[1:]:
                cand_spec = hit["_source"]["specialty"]
                if cand_spec != top_spec:
                    alt_spec = cand_spec
                    break
        
        # 2. BOOST LOGIC: If severity == "critical"
        if severity.lower() == "critical":
            if top_spec not in ("cardiology", "neurology", "trauma") and top_score < 8.0:
                red_flags = ["chest", "heart", "stroke", "seizure", "unconscious", 
                             "bleed", "trauma", "accident", "breathing", "oxygen"]
                
                kw_str = query_str.lower()
                found_flags = [f for f in red_flags if f in kw_str]
                
                if len(found_flags) >= 2:
                    # Override with best matching critical specialty based on red flags
                    red_flag_counts = {"cardiology": 0, "neurology": 0, "trauma": 0}
                    for f in found_flags:
                        if f in ("chest", "heart", "breathing", "oxygen"):
                            red_flag_counts["cardiology"] += 1
                        elif f in ("stroke", "seizure", "unconscious"):
                            red_flag_counts["neurology"] += 1
                        elif f in ("bleed", "trauma", "accident"):
                            red_flag_counts["trauma"] += 1
                            
                    best_critical = max(red_flag_counts, key=red_flag_counts.get)
                    if red_flag_counts[best_critical] > 0:
                        top_spec = best_critical
                        confidence = 0.9  # Set high confidence for clinical safety override
        
        return {
            "specialty": top_spec,
            "confidence": confidence,
            "alternative_specialty": alt_spec,
            "search_method": "elasticsearch",
            "matched_symptom": top_text
        }
        
    except Exception as e:
        print(f"Error in match_specialty: {e}")
        return {
            "specialty": fallback_spec,
            "confidence": fallback_conf,
            "alternative_specialty": fallback_alt,
            "search_method": "keyword_fallback",
            "matched_symptom": ""
        }

def search_hospitals_by_specialty(
    specialty: str,
    patient_lat: float,
    patient_lng: float,
    radius_km: int = 100
) -> list:
    """
    Search hospitals in Elasticsearch, filtering by specialty and geo_distance.
    Supports radius expansion, specialty removal, and capacity requirement removal fallbacks.
    """
    if not es:
        return []

    def perform_query(spec, rad, req_capacity=True):
        filters = [
            {"geo_distance": {"distance": f"{rad}km", "location": {"lat": patient_lat, "lon": patient_lng}}}
        ]
        if spec:
            filters.append({"term": {"specialties": spec}})
            
        musts = []
        if req_capacity:
            musts.append({"range": {"beds_available": {"gt": 0}}})
            
        query = {
            "bool": {
                "filter": filters,
                "must": musts
            }
        }
        
        sort = [
            {"beds_available": {"order": "desc"}},
            {
                "_geo_distance": {
                    "location": {"lat": patient_lat, "lon": patient_lng},
                    "order": "asc",
                    "unit": "km"
                }
            }
        ]
        
        try:
            res = es.search(index="hospitals", query=query, sort=sort, size=15)
            return res.get("hits", {}).get("hits", [])
        except Exception as e:
            print(f"Elastic search hospitals query error: {e}")
            return []

    # Step 1: Query with specialty, radius, and beds_available > 0
    hits = perform_query(specialty, radius_km, req_capacity=True)
    radius_used = radius_km

    # Fallback 1: Double the radius if results < 3
    if len(hits) < 3 and radius_km < 200:
        hits = perform_query(specialty, radius_km * 2, req_capacity=True)
        radius_used = radius_km * 2

    # Fallback 2: Remove specialty filter and look for nearest with beds_available > 0
    if len(hits) < 3:
        hits = perform_query(None, radius_used, req_capacity=True)

    # Fallback 3: If still < 3, remove beds_available filter (include full hospitals)
    if len(hits) < 3:
        hits = perform_query(None, radius_used, req_capacity=False)

    results = []
    for hit in hits:
        source = hit["_source"]
        h_lat = source["location"]["lat"]
        h_lon = source["location"]["lon"]
        dist = haversine(patient_lat, patient_lng, h_lat, h_lon)
        
        results.append({
            "hospital_id": source.get("hospital_id"),
            "name": source.get("name"),
            "district": source.get("district"),
            "state": source.get("state"),
            "lat": h_lat,
            "lng": h_lon,
            "specialties": source.get("specialties", []),
            "beds_available": source.get("beds_available", 0),
            "icu_available": source.get("icu_available", 0),
            "ventilators_available": source.get("ventilators_available", 0),
            "capacity_status": source.get("capacity_status"),
            "contact_phone": source.get("contact_phone"),
            "emergency_phone": source.get("emergency_phone", "108"),
            "is_government": source.get("is_government", False),
            "accreditation": source.get("accreditation"),
            "rating": source.get("rating", 0.0),
            "distance_km": round(dist, 2),
            "radius_used": radius_used
        })
        
    return results[:15]

if __name__ == "__main__":
    # Test 1: Specialty matching
    keywords = ["chest", "pain", "left", "arm", "sweating", "heart"]
    result = match_specialty(keywords, "critical")
    print(f"Specialty: {result['specialty']} ({result['confidence']:.2f}) via {result['search_method']}")
    
    # Test 2: Hospital search from Vijayawada
    hospitals = search_hospitals_by_specialty("cardiology", 16.5062, 80.6480)
    print(f"Found {len(hospitals)} cardiology hospitals near Vijayawada")
    for h in hospitals[:3]:
        print(f"  {h['name']} — {h['distance_km']:.1f}km — {h['beds_available']} beds")
    
    # Test 3: Rare specialty fallback
    hospitals2 = search_hospitals_by_specialty("oncology", 16.5062, 80.6480)
    print(f"Found {len(hospitals2)} oncology hospitals (with fallback if needed)")
