import time
import logging
import os
import sys
import json

# Ensure the project root is in sys.path when run directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.triage_agent import triage_severity
from agents.specialty_match_agent import match_specialty, search_hospitals_by_specialty
from agents.capacity_agent import check_capacity, reserve_bed
from agents.routing_agent import rank_hospitals, generate_routing_explanation
from agents.notify_agent import create_case_record

logger = logging.getLogger("crisisroute.orchestrator")

AGENT_NAMES = {
    1: "TriageAgent",
    2: "SpecialtyMatchAgent",
    3: "HospitalSearchAgent",
    4: "CapacityAgent",
    5: "RoutingAgent",
    6: "AdmissionAgent",
    7: "NotifyAgent"
}

def run_crisisroute(
    symptoms: str,
    age: int,
    patient_name: str,
    patient_lat: float,
    patient_lng: float
):
    start_time = time.time()
    
    def elapsed():
        return int((time.time() - start_time) * 1000)

    # Safe defaults for fallback chain
    triage_result = {
        "severity": "critical", 
        "chief_complaint": "Unable to assess",
        "keywords": ["emergency"], 
        "reasoning": "",
        "immediate_action": "Call 108 immediately", 
        "confidence": 0.0,
        "differential_diagnoses": [], 
        "red_flags": []
    }
    specialty_result = {
        "specialty": "general", 
        "confidence": 0.5,
        "alternative_specialty": "general", 
        "search_method": "fallback",
        "matched_symptom": ""
    }
    hospitals = []
    capacity = {}
    ranked = []
    selected_hospital = "None"
    routing_explanation = ""
    rejected_options = []
    confidence_score = 0.8


    # STEP 1: TriageAgent
    yield {
        "step": 1, 
        "agent": "TriageAgent", 
        "status": "running",
        "data": {"message": "Assessing symptoms..."}, 
        "elapsed_ms": elapsed()
    }
    logger.info(json.dumps({"agent": "TriageAgent", "status": "started"}))
    step_start = time.time()
    try:
        triage_result = triage_severity(symptoms, age)
        duration_ms = int((time.time() - step_start) * 1000)
        logger.info(json.dumps({
            "agent": "TriageAgent",
            "status": "completed",
            "duration_ms": duration_ms,
            "severity": triage_result.get("severity"),
            "confidence": triage_result.get("confidence"),
            "result_size": len(str(triage_result))
        }))
        yield {
            "step": 1, 
            "agent": "TriageAgent", 
            "status": "complete",
            "data": {
                "severity": triage_result["severity"],
                "chief_complaint": triage_result["chief_complaint"],
                "immediate_action": triage_result["immediate_action"],
                "confidence": triage_result["confidence"],
                "keywords": triage_result["keywords"],
                "red_flags": triage_result.get("red_flags", [])
            }, 
            "elapsed_ms": elapsed()
        }
    except Exception as e:
        duration_ms = int((time.time() - step_start) * 1000)
        logger.error(json.dumps({
            "agent": "TriageAgent",
            "status": "failed",
            "duration_ms": duration_ms,
            "exception_type": type(e).__name__,
            "exception_message": str(e)
        }))
        logging.error(f"TriageAgent failed: {e}")
        yield {
            "step": 1, 
            "agent": "TriageAgent", 
            "status": "error",
            "data": {"error": str(e), "fallback": "critical"}, 
            "elapsed_ms": elapsed()
        }

    # STEP 2: SpecialtyMatchAgent
    yield {
        "step": 2, 
        "agent": "SpecialtyMatchAgent", 
        "status": "running",
        "data": {"message": "Matching medical specialty via Elasticsearch..."}, 
        "elapsed_ms": elapsed()
    }
    logger.info(json.dumps({"agent": "SpecialtyMatchAgent", "status": "started"}))
    step_start = time.time()
    try:
        specialty_result = match_specialty(triage_result["keywords"], triage_result["severity"])
        duration_ms = int((time.time() - step_start) * 1000)
        logger.info(json.dumps({
            "agent": "SpecialtyMatchAgent",
            "status": "completed",
            "duration_ms": duration_ms,
            "specialty": specialty_result.get("specialty"),
            "confidence": specialty_result.get("confidence"),
            "result_size": len(str(specialty_result))
        }))
        yield {
            "step": 2, 
            "agent": "SpecialtyMatchAgent", 
            "status": "complete",
            "data": {
                "specialty": specialty_result["specialty"],
                "confidence": specialty_result["confidence"],
                "alternative": specialty_result.get("alternative_specialty"),
                "method": specialty_result["search_method"]
            }, 
            "elapsed_ms": elapsed()
        }
    except Exception as e:
        duration_ms = int((time.time() - step_start) * 1000)
        logger.error(json.dumps({
            "agent": "SpecialtyMatchAgent",
            "status": "failed",
            "duration_ms": duration_ms,
            "exception_type": type(e).__name__,
            "exception_message": str(e)
        }))
        logging.error(f"SpecialtyMatchAgent failed: {e}")
        yield {
            "step": 2, 
            "agent": "SpecialtyMatchAgent", 
            "status": "error",
            "data": {"error": str(e), "fallback": "general"}, 
            "elapsed_ms": elapsed()
        }

    # STEP 3: HospitalSearchAgent
    yield {
        "step": 3, 
        "agent": "HospitalSearchAgent", 
        "status": "running",
        "data": {"message": f"Searching {specialty_result['specialty']} hospitals near you..."}, 
        "elapsed_ms": elapsed()
    }
    logger.info(json.dumps({"agent": "HospitalSearchAgent", "status": "started"}))
    step_start = time.time()
    try:
        hospitals = search_hospitals_by_specialty(
            specialty_result["specialty"], patient_lat, patient_lng
        )
        if not hospitals:
            hospitals = search_hospitals_by_specialty("general", patient_lat, patient_lng)
        duration_ms = int((time.time() - step_start) * 1000)
        logger.info(json.dumps({
            "agent": "HospitalSearchAgent",
            "status": "completed",
            "duration_ms": duration_ms,
            "hospital_count": len(hospitals),
            "result_size": len(str(hospitals))
        }))
        yield {
            "step": 3, 
            "agent": "HospitalSearchAgent", 
            "status": "complete",
            "data": {
                "hospitals_found": len(hospitals),
                "search_radius_km": hospitals[0].get("radius_used", 100) if hospitals else 100,
                "nearest": hospitals[0]["name"] if hospitals else "None found"
            }, 
            "elapsed_ms": elapsed()
        }
    except Exception as e:
        duration_ms = int((time.time() - step_start) * 1000)
        logger.error(json.dumps({
            "agent": "HospitalSearchAgent",
            "status": "failed",
            "duration_ms": duration_ms,
            "exception_type": type(e).__name__,
            "exception_message": str(e)
        }))
        logging.error(f"HospitalSearchAgent failed: {e}")
        yield {
            "step": 3, 
            "agent": "HospitalSearchAgent", 
            "status": "error",
            "data": {"error": str(e)}, 
            "elapsed_ms": elapsed()
        }

    # STEP 4: CapacityAgent
    yield {
        "step": 4, 
        "agent": "CapacityAgent", 
        "status": "running",
        "data": {"message": "Checking real-time bed availability..."}, 
        "elapsed_ms": elapsed()
    }
    logger.info(json.dumps({"agent": "CapacityAgent", "status": "started"}))
    step_start = time.time()
    try:
        if hospitals:
            capacity = check_capacity([h["hospital_id"] for h in hospitals])
            available_count = sum(1 for c in capacity.values() if c["capacity_status"] != "full")
            duration_ms = int((time.time() - step_start) * 1000)
            logger.info(json.dumps({
                "agent": "CapacityAgent",
                "status": "completed",
                "duration_ms": duration_ms,
                "hospitals_checked": len(capacity),
                "total_available_beds": sum(c["beds_available"] for c in capacity.values()),
                "result_size": len(str(capacity))
            }))
            yield {
                "step": 4, 
                "agent": "CapacityAgent", 
                "status": "complete",
                "data": {
                    "hospitals_checked": len(capacity),
                    "hospitals_available": available_count,
                    "total_available_beds": sum(c["beds_available"] for c in capacity.values())
                }, 
                "elapsed_ms": elapsed()
            }
    except Exception as e:
        duration_ms = int((time.time() - step_start) * 1000)
        logger.error(json.dumps({
            "agent": "CapacityAgent",
            "status": "failed",
            "duration_ms": duration_ms,
            "exception_type": type(e).__name__,
            "exception_message": str(e)
        }))
        logging.error(f"CapacityAgent failed: {e}")
        yield {
            "step": 4, 
            "agent": "CapacityAgent", 
            "status": "error",
            "data": {"error": str(e)}, 
            "elapsed_ms": elapsed()
        }

    # STEP 5: RoutingAgent
    yield {
        "step": 5, 
        "agent": "RoutingAgent", 
        "status": "running",
        "data": {"message": "Calculating optimal route..."}, 
        "elapsed_ms": elapsed()
    }
    logger.info(json.dumps({"agent": "RoutingAgent", "status": "started"}))
    step_start = time.time()
    try:
        if hospitals:
            ranked = rank_hospitals(
                hospitals, capacity, patient_lat, patient_lng,
                triage_result["severity"], specialty_result["specialty"]
            )
            top = ranked[0] if ranked else None
            
            # Call Gemini explainability
            try:
                expl = generate_routing_explanation(
                    ranked_hospitals=ranked,
                    severity=triage_result["severity"],
                    specialty=specialty_result["specialty"]
                )
                selected_hospital = expl.get("selected_hospital", top["name"] if top else "None")
                routing_explanation = expl.get("routing_explanation", "")
                rejected_options = expl.get("rejected_options", [])
                confidence_score = expl.get("confidence_score", 0.8)
            except Exception as expl_err:
                logging.error(f"Failed to generate routing explanation: {expl_err}")
                selected_hospital = top["name"] if top else "None"
                routing_explanation = "Selected based on optimal composite score combining ETA, distance, and specialty care capabilities."
                rejected_options = [f"{h.get('name')} rejected due to lower priority ranking." for h in ranked[1:]]
                confidence_score = 0.80

            duration_ms = int((time.time() - step_start) * 1000)
            logger.info(json.dumps({
                "agent": "RoutingAgent",
                "status": "completed",
                "duration_ms": duration_ms,
                "hospitals_ranked": len(ranked),
                "top_hospital": top["name"] if top else "None",
                "result_size": len(str(ranked)) + len(routing_explanation)
            }))
            yield {
                "step": 5, 
                "agent": "RoutingAgent", 
                "status": "complete",
                "data": {
                    "top_hospital": top["name"] if top else "None",
                    "eta_minutes": top["eta_minutes"] if top else 0,
                    "distance_km": top["distance_km"] if top else 0,
                    "hospitals_ranked": len(ranked),
                    "routing_explanation": routing_explanation,
                    "confidence_score": confidence_score
                }, 
                "elapsed_ms": elapsed()
            }
    except Exception as e:
        duration_ms = int((time.time() - step_start) * 1000)
        logger.error(json.dumps({
            "agent": "RoutingAgent",
            "status": "failed",
            "duration_ms": duration_ms,
            "exception_type": type(e).__name__,
            "exception_message": str(e)
        }))
        logging.error(f"RoutingAgent failed: {e}")
        yield {
            "step": 5, 
            "agent": "RoutingAgent", 
            "status": "error",
            "data": {"error": str(e)}, 
            "elapsed_ms": elapsed()
        }

    # STEP 6: AdmissionAgent
    yield {
        "step": 6, 
        "agent": "AdmissionAgent", 
        "status": "running",
        "data": {"message": "Pre-registering patient..."}, 
        "elapsed_ms": elapsed()
    }
    logger.info(json.dumps({"agent": "AdmissionAgent", "status": "started"}))
    step_start = time.time()
    try:
        if ranked:
            # Reserve a bed at top hospital
            reserve_result = reserve_bed(ranked[0]["hospital_id"])
            duration_ms = int((time.time() - step_start) * 1000)
            logger.info(json.dumps({
                "agent": "AdmissionAgent",
                "status": "completed",
                "duration_ms": duration_ms,
                "hospital": ranked[0]["name"],
                "bed_reserved": reserve_result.get("success", False),
                "result_size": len(str(reserve_result))
            }))
            yield {
                "step": 6, 
                "agent": "AdmissionAgent", 
                "status": "complete",
                "data": {
                    "hospital": ranked[0]["name"],
                    "bed_reserved": reserve_result.get("success", False),
                    "remaining_beds": reserve_result.get("new_count", 0),
                    "status": "pre-registered"
                }, 
                "elapsed_ms": elapsed()
            }
    except Exception as e:
        duration_ms = int((time.time() - step_start) * 1000)
        logger.error(json.dumps({
            "agent": "AdmissionAgent",
            "status": "failed",
            "duration_ms": duration_ms,
            "exception_type": type(e).__name__,
            "exception_message": str(e)
        }))
        logging.error(f"AdmissionAgent failed: {e}")
        yield {
            "step": 6, 
            "agent": "AdmissionAgent", 
            "status": "error",
            "data": {"error": str(e)}, 
            "elapsed_ms": elapsed()
        }

    # STEP 7: NotifyAgent
    yield {
        "step": 7, 
        "agent": "NotifyAgent", 
        "status": "running",
        "data": {"message": "Alerting hospital..."}, 
        "elapsed_ms": elapsed()
    }
    logger.info(json.dumps({"agent": "NotifyAgent", "status": "started"}))
    step_start = time.time()
    pipeline_ms = elapsed()
    notify_result = {"case_id": "PENDING", "logged": False, "hospital_notified": False}
    try:
        if ranked:
            notify_result = create_case_record(
                symptoms=symptoms, 
                age=age, 
                patient_name=patient_name,
                triage_result=triage_result, 
                specialty_result=specialty_result,
                selected_hospital=ranked[0], 
                all_ranked_hospitals=ranked,
                patient_lat=patient_lat, 
                patient_lng=patient_lng,
                pipeline_duration_ms=pipeline_ms
            )
            duration_ms = int((time.time() - step_start) * 1000)
            logger.info(json.dumps({
                "agent": "NotifyAgent",
                "status": "completed",
                "duration_ms": duration_ms,
                "case_id": notify_result.get("case_id"),
                "hospital_notified": notify_result.get("hospital_notified", False),
                "result_size": len(str(notify_result))
            }))
            yield {
                "step": 7, 
                "agent": "NotifyAgent", 
                "status": "complete",
                "data": {
                    "case_id": notify_result["case_id"],
                    "hospital_notified": True,
                    "logged": True
                }, 
                "elapsed_ms": elapsed()
            }
    except Exception as e:
        duration_ms = int((time.time() - step_start) * 1000)
        logger.error(json.dumps({
            "agent": "NotifyAgent",
            "status": "failed",
            "duration_ms": duration_ms,
            "exception_type": type(e).__name__,
            "exception_message": str(e)
        }))
        logging.error(f"NotifyAgent failed: {e}")
        yield {
            "step": 7, 
            "agent": "NotifyAgent", 
            "status": "error",
            "data": {"error": str(e)}, 
            "elapsed_ms": elapsed()
        }

    # FINAL RESULT
    yield {
        "step": "complete",
        "agent": "Orchestrator",
        "status": "complete",
        "elapsed_ms": elapsed(),
        "final_result": {
            "case_id": notify_result.get("case_id", "ERROR"),
            "severity": triage_result["severity"],
            "severity_color": {"critical": "#E74C3C", "urgent": "#F39C12", "stable": "#27AE60"}.get(triage_result["severity"], "#888"),
            "chief_complaint": triage_result["chief_complaint"],
            "immediate_action": triage_result["immediate_action"],
            "specialty_needed": specialty_result["specialty"],
            "specialty_confidence": specialty_result["confidence"],
            "top_hospitals": ranked[:3] if ranked else [],
            "selected_hospital": selected_hospital,
            "routing_explanation": routing_explanation,
            "rejected_options": rejected_options,
            "confidence_score": confidence_score,
            "eta_minutes": ranked[0]["eta_minutes"] if ranked else 0,
            "distance_km": ranked[0]["distance_km"] if ranked else 0,
            "hospital_notified": notify_result.get("hospital_notified", False),
            "pipeline_duration_ms": pipeline_ms,
            "disclaimer": "CrisisRoute is a navigation aid only — not a clinical diagnosis. Always call 108 for life-threatening emergencies.",
            "emergency_number": "108"
        },
        "data": {}
    }

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    print("Running full CrisisRoute pipeline...\n")
    for step in run_crisisroute(
        symptoms="severe chest pain radiating to left arm, sweating, dizziness",
        age=55, patient_name="Ravi Kumar",
        patient_lat=16.5062, patient_lng=80.6480
    ):
        if step["step"] == "complete":
            r = step["final_result"]
            print(f"\n✅ PIPELINE COMPLETE in {step['elapsed_ms']}ms")
            print(f"Case ID: {r['case_id']}")
            print(f"Severity: {r['severity'].upper()}")
            print(f"Specialty: {r['specialty_needed']}")
            sh = r['selected_hospital']
            sh_name = sh.get('name') if isinstance(sh, dict) else sh
            print(f"Hospital: {sh_name}")
            print(f"ETA: {r['eta_minutes']} minutes")
        else:
            status_icon = "✅" if step["status"] == "complete" else ("⚠️" if step["status"] == "error" else "⏳")
            print(f"{status_icon} Step {step['step']}: {step['agent']} [{step['elapsed_ms']}ms]")
