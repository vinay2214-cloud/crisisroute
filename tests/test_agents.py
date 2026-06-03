import pytest
from unittest.mock import MagicMock, patch

from agents.routing_agent import haversine, rank_hospitals
from agents.specialty_match_agent import match_specialty
from agents.capacity_agent import check_capacity
from agents.notify_agent import create_case_record
from agents.triage_agent import triage_severity, FALLBACK_RESPONSE

def test_haversine_distance():
    # Distance between Vijayawada (16.5062, 80.6480) and Guntur (16.3067, 80.4365)
    dist = haversine(16.5062, 80.6480, 16.3067, 80.4365)
    assert 30.0 <= dist <= 35.0

def test_specialty_match_keyword_fallback():
    # If elasticsearch is empty/None or doesn't return anything
    res = match_specialty(["chest", "pain", "sweating"], "critical")
    assert res["specialty"] == "cardiology"
    assert res["search_method"] in ("elasticsearch", "keyword_fallback")
    
    res2 = match_specialty(["facial", "droop", "stroke", "slurred"], "critical")
    assert res2["specialty"] == "neurology"
    
    res3 = match_specialty(["cough", "fever", "cold"], "stable")
    assert res3["specialty"] == "general"

def test_capacity_check_nonexistent_ids():
    # When list is empty, capacity should return empty dict
    res = check_capacity([])
    assert res == {}
    
    # Missing IDs should return safe default documents
    res2 = check_capacity(["NONEXISTENT-ID"])
    assert "NONEXISTENT-ID" in res2
    assert res2["NONEXISTENT-ID"]["beds_available"] == 0
    assert res2["NONEXISTENT-ID"]["capacity_status"] == "full"
    assert res2["NONEXISTENT-ID"]["found"] is False

def test_routing_ranking_algorithm():
    hospitals = [
        {
            "hospital_id": "AP-KRS-001",
            "name": "Hospital A",
            "lat": 16.5062,
            "lng": 80.6480,
            "specialties": ["cardiology", "trauma"],
            "is_government": True,
            "accreditation": "Govt",
            "rating": 4.0
        },
        {
            "hospital_id": "AP-KRS-002",
            "name": "Hospital B",
            "lat": 16.5200,
            "lng": 80.6350,
            "specialties": ["cardiology"],
            "is_government": False,
            "accreditation": "JCI",
            "rating": 4.5
        }
    ]
    capacity = {
        "AP-KRS-001": {"beds_available": 25, "icu_available": 5, "capacity_status": "available"},
        "AP-KRS-002": {"beds_available": 5, "icu_available": 1, "capacity_status": "limited"}
    }
    
    # Under critical cardiology triage, GGH Hospital A should rank first due to capacity + ICU + Gov bonus
    ranked = rank_hospitals(hospitals, capacity, 16.5062, 80.6480, "critical", "cardiology")
    assert len(ranked) == 2
    assert ranked[0]["hospital_id"] == "AP-KRS-001"
    assert ranked[0]["rank"] == 1
    assert ranked[0]["specialty_match"] is True

def test_notify_agent_case_creation():
    selected_h = {
        "hospital_id": "AP-KRS-001",
        "name": "GGH Vijayawada",
        "eta_minutes": 10,
        "distance_km": 5.0,
        "contact_phone": "+91-866-2577990"
    }
    
    # We patch es.index to prevent writing during unit test
    with patch('agents.notify_agent.es') as mock_es:
        res = create_case_record(
            symptoms="severe chest pain radiating to left arm",
            age=55,
            patient_name="Ravi Kumar",
            triage_result={"severity": "critical", "chief_complaint": "Acute MI suspected"},
            specialty_result={"specialty": "cardiology", "confidence": 0.9},
            selected_hospital=selected_h,
            all_ranked_hospitals=[selected_h],
            patient_lat=16.5062,
            patient_lng=80.6480,
            pipeline_duration_ms=1200
        )
        
        assert res["case_id"].startswith("CR-")
        assert "CARDIOLOGY TEAM" in res["notification_message"]
        assert selected_h["contact_phone"] in res["notification_message"]

def test_triage_agent_error_graceful_fallback():
    # If client initialization throws an exception, verify triage_severity recovers and returns FALLBACK_RESPONSE
    with patch('google.genai.Client') as mock_client:
        mock_client.side_effect = Exception("API Key Error")
        res = triage_severity("severe pain", 55)
        assert res == FALLBACK_RESPONSE
