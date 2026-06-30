import os
import math
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import uuid4
from dotenv import load_dotenv
from fastmcp import FastMCP
from elasticsearch import Elasticsearch, ConflictError

# Load environment variables
load_dotenv()

# Initialize FastMCP Server
mcp = FastMCP("Elasticsearch MCP Server")

ELASTIC_ENDPOINT = os.getenv("ELASTIC_ENDPOINT")
ELASTIC_API_KEY = os.getenv("ELASTIC_API_KEY")

es = None
if ELASTIC_ENDPOINT:
    try:
        es = Elasticsearch(
            ELASTIC_ENDPOINT,
            api_key=ELASTIC_API_KEY
        )
        # Verify connection viability
        if not es.ping():
            print("Warning: Elasticsearch cloud ping failed. Elasticsearch disabled, running in local fallback mode.")
            es = None
    except Exception as e:
        print(f"Error initializing Elasticsearch client in MCP Server: {e}. Running in local fallback mode.")
        es = None
else:
    print("Warning: ELASTIC_ENDPOINT not configured in MCP Server. Elasticsearch disabled.")
    es = None

# Fallback Local In-Memory Datastores
LOCAL_HOSPITALS = []
LOCAL_CASES = []

try:
    from data.hospitals_ap import generate_hospitals
    LOCAL_HOSPITALS = [doc["_source"] for doc in generate_hospitals()]
    print(f"Loaded {len(LOCAL_HOSPITALS)} local fallback hospitals successfully.")
except Exception as e:
    print(f"Failed to load local fallback hospitals: {e}")

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

@mcp.tool()
def match_specialty(symptom_keywords: List[str], severity: str) -> Dict[str, Any]:
    """
    Finds the best matching medical specialty for given symptoms using Elasticsearch
    with red-flags boosting and keyword-based fallbacks.
    """
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
        
        if severity.lower() == "critical":
            if top_spec not in ("cardiology", "neurology", "trauma") and top_score < 8.0:
                red_flags = ["chest", "heart", "stroke", "seizure", "unconscious", 
                             "bleed", "trauma", "accident", "breathing", "oxygen"]
                
                kw_str = query_str.lower()
                found_flags = [f for f in red_flags if f in kw_str]
                
                if len(found_flags) >= 2:
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
                        confidence = 0.9
        
        return {
            "specialty": top_spec,
            "confidence": confidence,
            "alternative_specialty": alt_spec,
            "search_method": "elasticsearch",
            "matched_symptom": top_text
        }
        
    except Exception as e:
        print(f"Error in match_specialty tool: {e}")
        return {
            "specialty": fallback_spec,
            "confidence": fallback_conf,
            "alternative_specialty": fallback_alt,
            "search_method": "keyword_fallback",
            "matched_symptom": ""
        }

@mcp.tool()
def search_hospitals(
    specialty: Optional[str],
    patient_lat: float,
    patient_lng: float,
    radius_km: int = 100
) -> List[Dict[str, Any]]:
    """
    Search hospitals in Elasticsearch, filtering by specialty and geo_distance.
    Supports radius expansion, specialty removal, and capacity requirement removal fallbacks.
    """
    if not es:
        # Fall back to local search query processing over local fallback hospitals
        def perform_local_filter(spec, rad, req_capacity=True):
            filtered = []
            for h in LOCAL_HOSPITALS:
                h_lat = h["location"]["lat"]
                h_lon = h["location"]["lon"]
                dist = haversine(patient_lat, patient_lng, h_lat, h_lon)
                
                if dist > rad:
                    continue
                if spec and spec not in h.get("specialties", []):
                    continue
                if req_capacity and h.get("beds_available", 0) <= 0:
                    continue
                
                filtered.append((h, dist))
            
            # Sort by beds_available descending, distance ascending
            filtered.sort(key=lambda x: (-x[0].get("beds_available", 0), x[1]))
            return filtered

        hits = perform_local_filter(specialty, radius_km, req_capacity=True)
        radius_used = radius_km

        if len(hits) < 3 and radius_km < 200:
            hits = perform_local_filter(specialty, radius_km * 2, req_capacity=True)
            radius_used = radius_km * 2

        if len(hits) < 3:
            hits = perform_local_filter(None, radius_used, req_capacity=True)

        if len(hits) < 3:
            hits = perform_local_filter(None, radius_used, req_capacity=False)

        results = []
        for h, dist in hits:
            results.append({
                "hospital_id": h.get("hospital_id"),
                "name": h.get("name"),
                "district": h.get("district"),
                "state": h.get("state"),
                "lat": h["location"]["lat"],
                "lng": h["location"]["lon"],
                "specialties": h.get("specialties", []),
                "beds_available": h.get("beds_available", 0),
                "icu_available": h.get("icu_available", 0),
                "ventilators_available": h.get("ventilators_available", 0),
                "capacity_status": h.get("capacity_status"),
                "contact_phone": h.get("contact_phone"),
                "emergency_phone": h.get("emergency_phone", "108"),
                "is_government": h.get("is_government", False),
                "accreditation": h.get("accreditation"),
                "rating": h.get("rating", 0.0),
                "hospital_tier": h.get("hospital_tier"),
                "has_cardiology": h.get("has_cardiology", False),
                "has_trauma": h.get("has_trauma", False),
                "has_neurology": h.get("has_neurology", False),
                "has_oncology": h.get("has_oncology", False),
                "distance_km": round(dist, 2),
                "radius_used": radius_used
            })
        return results[:15]

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
            print(f"Elastic search hospitals query error in tool: {e}")
            return []

    hits = perform_query(specialty, radius_km, req_capacity=True)
    radius_used = radius_km

    if len(hits) < 3 and radius_km < 200:
        hits = perform_query(specialty, radius_km * 2, req_capacity=True)
        radius_used = radius_km * 2

    if len(hits) < 3:
        hits = perform_query(None, radius_used, req_capacity=True)

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
            "hospital_tier": source.get("hospital_tier"),
            "has_cardiology": source.get("has_cardiology", False),
            "has_trauma": source.get("has_trauma", False),
            "has_neurology": source.get("has_neurology", False),
            "has_oncology": source.get("has_oncology", False),
            "distance_km": round(dist, 2),
            "radius_used": radius_used
        })
        
    return results[:15]

@mcp.tool()
def get_capacity(hospital_ids: List[str]) -> Dict[str, Any]:
    """
    Check current capacity statistics for a list of hospitals in a single request.
    """
    if not hospital_ids:
        return {}
    if not es:
        capacity_map = {}
        for hid in hospital_ids:
            found_h = None
            for h in LOCAL_HOSPITALS:
                if h.get("hospital_id") == hid:
                    found_h = h
                    break
            if found_h:
                beds_avail = found_h.get("beds_available", 0)
                beds_total = found_h.get("beds_total", 0)
                capacity_map[hid] = {
                    "beds_available": beds_avail,
                    "icu_available": found_h.get("icu_available", 0),
                    "ventilators_available": found_h.get("ventilators_available", 0),
                    "capacity_status": found_h.get("capacity_status"),
                    "beds_total": beds_total,
                    "occupancy_rate": round((beds_total - beds_avail) / beds_total if beds_total > 0 else 1.0, 3),
                    "version": found_h.get("version", 1),
                    "found": True
                }
            else:
                capacity_map[hid] = {
                    "beds_available": 0,
                    "icu_available": 0,
                    "ventilators_available": 0,
                    "capacity_status": "full",
                    "beds_total": 0,
                    "occupancy_rate": 1.0,
                    "version": 0,
                    "found": False
                }
        return capacity_map

    try:
        response = es.mget(index="hospitals", ids=hospital_ids)
        docs = response.get("docs", [])
    except Exception as e:
        print(f"Error checking capacity via mget in tool: {e}")
        docs = []

    capacity_map = {}
    for doc in docs:
        hid = doc.get("_id")
        if not hid:
            continue
            
        if doc.get("found"):
            source = doc["_source"]
            beds_total = source.get("beds_total", 0)
            beds_avail = source.get("beds_available", 0)
            icu_avail = source.get("icu_available", 0)
            vent_avail = source.get("ventilators_available", 0)
            
            if beds_avail > 10:
                status = "available"
            elif beds_avail >= 1:
                status = "limited"
            else:
                status = "full"
                
            occupancy_rate = 1.0
            if beds_total > 0:
                occupancy_rate = (beds_total - beds_avail) / beds_total
                
            capacity_map[hid] = {
                "beds_available": beds_avail,
                "icu_available": icu_avail,
                "ventilators_available": vent_avail,
                "capacity_status": status,
                "beds_total": beds_total,
                "occupancy_rate": round(occupancy_rate, 3),
                "version": source.get("version", doc.get("_version", 1)),
                "found": True
            }
        else:
            capacity_map[hid] = {
                "beds_available": 0,
                "icu_available": 0,
                "ventilators_available": 0,
                "capacity_status": "full",
                "beds_total": 0,
                "occupancy_rate": 1.0,
                "version": 0,
                "found": False
            }
            
    for hid in hospital_ids:
        if hid not in capacity_map:
            capacity_map[hid] = {
                "beds_available": 0,
                "icu_available": 0,
                "ventilators_available": 0,
                "capacity_status": "full",
                "beds_total": 0,
                "occupancy_rate": 1.0,
                "version": 0,
                "found": False
            }
            
    return capacity_map

@mcp.tool()
def reserve_bed(hospital_id: str) -> Dict[str, Any]:
    """
    Atomically reserve a bed at a hospital using optimistic locking.
    Retries up to 3 times on conflict.
    """
    if not es:
        for h in LOCAL_HOSPITALS:
            if h.get("hospital_id") == hospital_id:
                if h.get("beds_available", 0) > 0:
                    h["beds_available"] -= 1
                    h["version"] = h.get("version", 1) + 1
                    if h["beds_available"] > 10:
                        h["capacity_status"] = "available"
                    elif h["beds_available"] > 0:
                        h["capacity_status"] = "limited"
                    else:
                        h["capacity_status"] = "full"
                    return {"success": True, "new_count": h["beds_available"], "conflict": False}
        return {"success": False, "new_count": 0, "conflict": False}

    for attempt in range(3):
        try:
            doc = es.get(index="hospitals", id=hospital_id)
            seq_no = doc["_seq_no"]
            primary_term = doc["_primary_term"]
            source = doc["_source"]
            
            beds_avail = source.get("beds_available", 0)
            if beds_avail <= 0:
                return {"success": False, "new_count": 0, "conflict": False}

            script = {
                "source": "if (ctx._source.beds_available > 0) { ctx._source.beds_available -= 1; ctx._source.version += 1; } else { ctx.op = 'noop'; }",
                "lang": "painless"
            }
            
            res = es.update(
                index="hospitals",
                id=hospital_id,
                script=script,
                if_seq_no=seq_no,
                if_primary_term=primary_term
            )
            
            if res.get("result") == "noop":
                return {"success": False, "new_count": 0, "conflict": False}
                
            updated_doc = es.get(index="hospitals", id=hospital_id)
            updated_source = updated_doc["_source"]
            new_beds_avail = updated_source.get("beds_available", 0)
            
            if new_beds_avail > 10:
                new_status = "available"
            elif new_beds_avail >= 1:
                new_status = "limited"
            else:
                new_status = "full"
                
            es.update(
                index="hospitals",
                id=hospital_id,
                doc={"capacity_status": new_status}
            )
            
            return {"success": True, "new_count": new_beds_avail, "conflict": False}
            
        except ConflictError:
            if attempt == 2:
                return {"success": False, "new_count": 0, "conflict": True}
            import time
            time.sleep(0.1)
        except Exception as e:
            print(f"Exception during reserve_bed in tool: {e}")
            return {"success": False, "new_count": 0, "conflict": False}
            
    return {"success": False, "new_count": 0, "conflict": True}

@mcp.tool()
def create_case_record(
    symptoms: str,
    age: int,
    patient_name: str,
    triage_result: Dict[str, Any],
    specialty_result: Dict[str, Any],
    selected_hospital: Dict[str, Any],
    all_ranked_hospitals: List[Dict[str, Any]],
    patient_lat: float,
    patient_lng: float,
    pipeline_duration_ms: int
) -> Dict[str, Any]:
    """
    Creates a triage case record, indexes it in Elasticsearch, formats and logs a simulated dispatch alert.
    """
    case_id = f"CR-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"
    timestamp = datetime.now(timezone.utc).isoformat()
    
    severity = triage_result.get("severity", "critical")
    chief_complaint = triage_result.get("chief_complaint", "Unknown Emergency")
    specialty = specialty_result.get("specialty", "general")
    eta_minutes = selected_hospital.get("eta_minutes", 0)
    
    notification_message = f"""
═══════ CRISISROUTE MCP ALERT ═══════
CASE ID: {case_id}
TIME: {datetime.now().strftime('%H:%M:%S')} IST
SEVERITY: {severity.upper()}

PATIENT ARRIVING IN {eta_minutes} MINUTES
Chief complaint: {chief_complaint}
Required specialty: {specialty.upper()} TEAM

Immediate action: Prepare {specialty} team in emergency bay
Contact patient family: {selected_hospital.get('contact_phone', '108')}
════════════════════════════════════
""".strip()

    print(notification_message)
    
    doc = {
        "case_id": case_id,
        "session_id": str(uuid4()),
        "symptoms_raw": symptoms,
        "patient_age": age,
        "patient_name": patient_name,
        "triage_severity": severity,
        "chief_complaint": chief_complaint,
        "specialty_matched": specialty,
        "specialty_confidence": specialty_result.get("confidence", 0.0),
        "hospital_selected_id": selected_hospital.get("hospital_id"),
        "hospital_selected_name": selected_hospital.get("name"),
        "hospitals_considered": len(all_ranked_hospitals),
        "eta_minutes": eta_minutes,
        "distance_km": selected_hospital.get("distance_km", 0.0),
        "hospital_notified": True,
        "patient_location": {"lat": patient_lat, "lon": patient_lng},
        "pipeline_duration_ms": pipeline_duration_ms,
        "timestamp": timestamp,
        "outcome_status": "dispatched"
    }

    logged = False
    if es:
        try:
            es.index(index="triage_cases", id=case_id, document=doc)
            logged = True
        except Exception as e:
            print(f"Error logging case to Elasticsearch in tool: {e}")
    else:
        LOCAL_CASES.append(doc)
        logged = True
            
    return {
        "case_id": case_id,
        "logged": logged,
        "hospital_notified": True,
        "notification_message": notification_message,
        "timestamp": timestamp
    }

@mcp.tool()
def get_case(case_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves a case record from Elasticsearch by its case_id using a term query.
    """
    if not es:
        for c in LOCAL_CASES:
            if c.get("case_id") == case_id:
                return c
        return None
        
    try:
        query = {"term": {"case_id": case_id}}
        res = es.search(index="triage_cases", query=query, size=1)
        hits = res.get("hits", {}).get("hits", [])
        if hits:
            return hits[0]["_source"]
    except Exception as e:
        print(f"Error in get_case tool for ID {case_id}: {e}")
        
    return None

@mcp.tool()
def get_recent_cases(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Retrieves recent cases from Elasticsearch sorted by timestamp descending.
    """
    if not es:
        sorted_cases = sorted(LOCAL_CASES, key=lambda x: x.get("timestamp", ""), reverse=True)
        return sorted_cases[:limit]
        
    try:
        sort_config = [{"timestamp": {"order": "desc"}}]
        res = es.search(index="triage_cases", query={"match_all": {}}, sort=sort_config, size=limit)
        hits = res.get("hits", {}).get("hits", [])
        return [hit["_source"] for hit in hits]
    except Exception as e:
        print(f"Error in get_recent_cases tool: {e}")
        return []

@mcp.tool()
def get_dashboard_stats() -> Dict[str, Any]:
    """
    Returns aggregated stats across all AP hospitals using Elasticsearch aggregations.
    """
    if not es:
        t_beds = sum(h.get("beds_total", 0) for h in LOCAL_HOSPITALS)
        a_beds = sum(h.get("beds_available", 0) for h in LOCAL_HOSPITALS)
        a_icu = sum(h.get("icu_available", 0) for h in LOCAL_HOSPITALS)
        
        status_bd = {"available": 0, "limited": 0, "full": 0}
        for h in LOCAL_HOSPITALS:
            k = h.get("capacity_status", "full").lower()
            if k in status_bd:
                status_bd[k] += 1
                
        districts = {}
        for h in LOCAL_HOSPITALS:
            d = h.get("district", "Unknown")
            districts[d] = districts.get(d, 0) + h.get("beds_available", 0)
            
        by_district = [{"district": k, "available_beds": v} for k, v in districts.items()]
        
        return {
            "total_hospitals": len(LOCAL_HOSPITALS),
            "total_beds": t_beds,
            "available_beds": a_beds,
            "available_icu": a_icu,
            "occupancy_rate": round((t_beds - a_beds) / t_beds if t_beds > 0 else 1.0, 3),
            "status_breakdown": status_bd,
            "by_district": by_district
        }

    aggs = {
        "total_beds": {"sum": {"field": "beds_total"}},
        "available_beds": {"sum": {"field": "beds_available"}},
        "available_icu": {"sum": {"field": "icu_available"}},
        "by_status": {"terms": {"field": "capacity_status"}},
        "by_district": {
            "terms": {"field": "district", "size": 10},
            "aggs": {
                "avail": {"sum": {"field": "beds_available"}}
            }
        }
    }
    
    try:
        res = es.search(index="hospitals", aggs=aggs, size=0)
        total_docs = res.get("hits", {}).get("total", {}).get("value", 0)
        agg_results = res.get("aggregations", {})
        
        t_beds = int(agg_results.get("total_beds", {}).get("value", 0))
        a_beds = int(agg_results.get("available_beds", {}).get("value", 0))
        a_icu = int(agg_results.get("available_icu", {}).get("value", 0))
        
        occ_rate = 1.0
        if t_beds > 0:
            occ_rate = (t_beds - a_beds) / t_beds
            
        status_buckets = agg_results.get("by_status", {}).get("buckets", [])
        status_bd = {"available": 0, "limited": 0, "full": 0}
        for b in status_buckets:
            k = b["key"].lower()
            if k in status_bd:
                status_bd[k] = b["doc_count"]
                
        dist_buckets = agg_results.get("by_district", {}).get("buckets", [])
        by_district = []
        for b in dist_buckets:
            by_district.append({
                "district": b["key"],
                "available_beds": int(b["avail"]["value"])
            })
            
        return {
            "total_hospitals": total_docs,
            "total_beds": t_beds,
            "available_beds": a_beds,
            "available_icu": a_icu,
            "occupancy_rate": round(occ_rate, 3),
            "status_breakdown": status_bd,
            "by_district": by_district
        }
    except Exception as e:
        print(f"Error compiling system stats in tool: {e}")
        return {
            "total_hospitals": 0, "total_beds": 0, "available_beds": 0, "available_icu": 0,
            "occupancy_rate": 1.0, "status_breakdown": {"available": 0, "limited": 0, "full": 0},
            "by_district": []
        }

if __name__ == "__main__":
    # Start the FastMCP server (standard stdio protocol)
    mcp.run()
