import os
import logging
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional
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

logger = logging.getLogger("crisisroute.notify")

def create_case_record(
    symptoms: str,
    age: int,
    patient_name: str,
    triage_result: dict,
    specialty_result: dict,
    selected_hospital: dict,
    all_ranked_hospitals: list,
    patient_lat: float,
    patient_lng: float,
    pipeline_duration_ms: int
) -> dict:
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
═══════ CRISISROUTE ALERT ═══════
CASE ID: {case_id}
TIME: {datetime.now().strftime('%H:%M:%S')} IST
SEVERITY: {severity.upper()}

PATIENT ARRIVING IN {eta_minutes} MINUTES
Chief complaint: {chief_complaint}
Required specialty: {specialty.upper()} TEAM

Immediate action: Prepare {specialty} team in emergency bay
Contact patient family: {selected_hospital.get('contact_phone', '108')}
════════════════════════════════
""".strip()

    # Print notification message (simulates push to hospital)
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
            logger.info(f"Logged case {case_id} for hospital {selected_hospital.get('name')}")
        except Exception as e:
            logger.error(f"Error logging case to Elasticsearch: {e}")
            
    return {
        "case_id": case_id,
        "logged": logged,
        "hospital_notified": True,
        "notification_message": notification_message,
        "timestamp": timestamp
    }

def get_case(case_id: str) -> Optional[dict]:
    """
    Retrieves a case record from Elasticsearch by its case_id using a term query.
    """
    if not es:
        return None
        
    try:
        query = {"term": {"case_id": case_id}}
        res = es.search(index="triage_cases", query=query, size=1)
        hits = res.get("hits", {}).get("hits", [])
        if hits:
            return hits[0]["_source"]
    except Exception as e:
        logger.error(f"Error in get_case for ID {case_id}: {e}")
        
    return None

def get_recent_cases(limit: int = 20) -> list:
    """
    Retrieves recent cases from Elasticsearch sorted by timestamp descending.
    """
    if not es:
        return []
        
    try:
        sort_config = [{"timestamp": {"order": "desc"}}]
        res = es.search(index="triage_cases", query={"match_all": {}}, sort=sort_config, size=limit)
        hits = res.get("hits", {}).get("hits", [])
        return [hit["_source"] for hit in hits]
    except Exception as e:
        logger.error(f"Error in get_recent_cases: {e}")
        return []

if __name__ == "__main__":
    result = create_case_record(
        symptoms="severe chest pain left arm",
        age=55, patient_name="Test Patient",
        triage_result={"severity": "critical", "chief_complaint": "Acute MI suspected",
                       "immediate_action": "Call 108 immediately"},
        specialty_result={"specialty": "cardiology", "confidence": 0.95},
        selected_hospital={"hospital_id": "AP-KRS-001", "name": "GGH Vijayawada",
                           "eta_minutes": 12, "distance_km": 6.5,
                           "contact_phone": "+91-866-2577990"},
        all_ranked_hospitals=[],
        patient_lat=16.5062, patient_lng=80.6480,
        pipeline_duration_ms=2341
    )
    print(f"\nCase created: {result['case_id']}")
    
    fetched = get_case(result['case_id'])
    if fetched:
        print(f"Fetched case successfully: {fetched['chief_complaint']}")
    else:
        print("Failed to fetch case.")
        
    recents = get_recent_cases(5)
    print(f"Recent cases count: {len(recents)}")
