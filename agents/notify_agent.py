import os
import json
import time
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from google.cloud import pubsub_v1
from google.api_core.exceptions import GoogleAPICallError
import google.genai as genai
from agents.mcp_client import mcp_client

logger = logging.getLogger("crisisroute.notify")

def clean_json_response(text: str) -> str:
    """Strip markdown code fences from Gemini JSON responses."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines).strip()
    return text

# Dummy attribute for backward compatibility with unit test mock patches
es = None

# Initialize Publisher client
# Google Cloud SDK automatically honors PUBSUB_EMULATOR_HOST if set in environment.
publisher = None
try:
    publisher = pubsub_v1.PublisherClient()
except Exception as e:
    logger.error(f"Failed to initialize Google Cloud Pub/Sub PublisherClient: {e}")

class HospitalBriefing(BaseModel):
    emergency_summary: str = Field(..., description="Concise emergency summary of patient state")
    recommended_preparation: str = Field(..., description="Actionable recommended preparation instructions for the receiving emergency room")
    required_team: str = Field(..., description="Specific medical teams or specialties required to be present at arrival")
    risk_assessment: str = Field(..., description="Critical risk assessment during transit and immediate arrival")

def generate_hospital_briefing(
    symptoms: str,
    severity: str,
    specialty: str,
    eta_minutes: int
) -> Dict[str, str]:
    """
    Uses Gemini 2.5 Flash to generate a clinical hospital-ready briefing.
    """
    fallback_briefing = {
        "Emergency Summary": f"Patient presenting with symptoms: {symptoms}.",
        "Recommended Preparation": f"Prepare emergency bay for {specialty.upper()} intake.",
        "Required Team": f"Emergency department physicians and {specialty.upper()} team on standby.",
        "Risk Assessment": "Standard transit risks apply. Monitor vitals.",
        "emergency_summary": f"Patient presenting with symptoms: {symptoms}.",
        "recommended_preparation": f"Prepare emergency bay for {specialty.upper()} intake.",
        "required_team": f"Emergency department physicians and {specialty.upper()} team on standby.",
        "risk_assessment": "Standard transit risks apply. Monitor vitals."
    }

    system_prompt = """
You are an Emergency Medicine Dispatcher.
Your job is to generate a concise, hospital-ready clinical briefing for the receiving emergency department.
You will be given:
1. Patient's symptoms.
2. Triage severity level (critical, urgent, stable).
3. Matched medical specialty required.
4. Estimated Time of Arrival (ETA) in minutes.

You must output a JSON object containing:
- emergency_summary: A concise, medical-grade summary of the patient's presentation and chief complaints.
- recommended_preparation: Actionable, step-by-step instructions of how the ER bay should prepare (e.g. set up cath lab, prepare stroke protocol, draw baseline labs).
- required_team: The specific medical teams, specialists, nurses, or techs that must be activated and standby at the bay on arrival.
- risk_assessment: High-level risk evaluation (e.g. airway compromise risk, cardiac arrest risk during transit, hemorrhage control priority).

Keep the briefing extremely precise, professional, and clear. Every second counts.
"""

    user_prompt = f"""
Patient Symptoms: {symptoms}
Triage Severity: {severity.upper()}
Required Specialty: {specialty.upper()}
ETA: {eta_minutes} minutes
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
                    response_schema=HospitalBriefing,
                )
            )
            raw = response.text.strip()
            cleaned = clean_json_response(raw)
            result = json.loads(cleaned, strict=False)
            
            # Map keys to include both formats
            mapped_result = {
                "Emergency Summary": result.get("emergency_summary", ""),
                "Recommended Preparation": result.get("recommended_preparation", ""),
                "Required Team": result.get("required_team", ""),
                "Risk Assessment": result.get("risk_assessment", ""),
                "emergency_summary": result.get("emergency_summary", ""),
                "recommended_preparation": result.get("recommended_preparation", ""),
                "required_team": result.get("required_team", ""),
                "risk_assessment": result.get("risk_assessment", "")
            }
            return mapped_result
        except Exception as e:
            logger.warning(f"generate_hospital_briefing attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)

    logger.error("generate_hospital_briefing: all 3 attempts failed — returning fallback")
    return fallback_briefing

def publish_notification(
    case_id: str,
    hospital_id: str,
    severity: str,
    specialty: str,
    eta_minutes: int,
    timestamp: str,
    briefing: Dict[str, str]
) -> bool:
    """
    Publishes a structured notification payload to the GCP Pub/Sub topic 'hospital-alerts'.
    Implements retry logic with exponential backoff.
    """
    if not publisher:
        logger.error("Pub/Sub PublisherClient is not initialized. Cannot send notification.")
        return False

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or "crisisroute-2026-498212"
    topic_id = "hospital-alerts"
    topic_path = publisher.topic_path(project_id, topic_id)

    payload = {
        "case_id": case_id,
        "hospital_id": hospital_id,
        "severity": severity,
        "specialty": specialty,
        "eta_minutes": eta_minutes,
        "timestamp": timestamp,
        "briefing": briefing
    }
    
    data = json.dumps(payload).encode("utf-8")
    
    # Retry parameters
    max_retries = 3
    base_delay = 1.0  # 1 second
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Publishing notification to {topic_path} (Attempt {attempt+1}/{max_retries})")
            future = publisher.publish(topic_path, data)
            message_id = future.result(timeout=10.0)  # Wait for result
            logger.info(f"Published message ID: {message_id} to Pub/Sub topic {topic_id}")
            return True
        except (GoogleAPICallError, Exception) as e:
            delay = base_delay * (2 ** attempt)
            logger.error(f"Pub/Sub publish error on attempt {attempt+1}: {e}. Retrying in {delay:.1f}s...")
            if attempt < max_retries - 1:
                time.sleep(delay)
                
    logger.error("Failed to publish alert to Google Cloud Pub/Sub after maximum retries.")
    return False

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
    Creates a triage case record and indexes it via MCP, and dispatches a live Pub/Sub notification.
    """
    # 1. Create the case record in Elasticsearch via MCP Server
    res = mcp_client.call_tool("create_case_record", {
        "symptoms": symptoms,
        "age": age,
        "patient_name": patient_name,
        "triage_result": triage_result,
        "specialty_result": specialty_result,
        "selected_hospital": selected_hospital,
        "all_ranked_hospitals": all_ranked_hospitals,
        "patient_lat": patient_lat,
        "patient_lng": patient_lng,
        "pipeline_duration_ms": pipeline_duration_ms
    })
    
    case_id = res.get("case_id")
    hospital_id = selected_hospital.get("hospital_id")
    severity = triage_result.get("severity", "critical")
    specialty = specialty_result.get("specialty", "general")
    eta_minutes = selected_hospital.get("eta_minutes", 0)
    timestamp = res.get("timestamp") or datetime.now(timezone.utc).isoformat()
    
    # 2. Generate Hospital-ready briefing via Gemini 2.5 Flash
    briefing = generate_hospital_briefing(
        symptoms=symptoms,
        severity=severity,
        specialty=specialty,
        eta_minutes=eta_minutes
    )
    
    # 3. Dispatch real Pub/Sub notification to topic containing the briefing
    notified = publish_notification(
        case_id=case_id,
        hospital_id=hospital_id,
        severity=severity,
        specialty=specialty,
        eta_minutes=eta_minutes,
        timestamp=timestamp,
        briefing=briefing
    )
    
    # Update returned dictionary to reflect actual Pub/Sub status and briefing contents
    res["hospital_notified"] = notified
    res["briefing"] = briefing
    return res

def get_case(case_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves a case record via MCP.
    """
    return mcp_client.call_tool("get_case", {"case_id": case_id})

def get_recent_cases(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Retrieves recent cases via MCP.
    """
    return mcp_client.call_tool("get_recent_cases", {"limit": limit})
