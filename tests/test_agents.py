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
    assert res["search_method"] in ("elasticsearch", "keyword_fallback", "direct_keyword_map")
    
    res2 = match_specialty(["facial", "droop", "stroke", "slurred"], "critical")
    assert res2["specialty"] == "neurology"
    
    res3 = match_specialty(["cough", "fever", "cold"], "stable")
    assert res3["specialty"] in ("general", "pediatrics")  # "fever" triggers pediatrics in direct map
    
    # Empty keywords must return general — prevents misrouting from failed triage
    res4 = match_specialty([], "critical")
    assert res4["specialty"] == "general"
    assert res4["confidence"] == 0.0
    assert res4["search_method"] == "fallback_empty_keywords"

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
    
    with patch('agents.notify_agent.publish_notification') as mock_publish, \
         patch('agents.notify_agent.generate_hospital_briefing') as mock_briefing:
         
        mock_publish.return_value = True
        mock_briefing.return_value = {
            "Emergency Summary": "Severe chest pain radiating to left arm",
            "Recommended Preparation": "Prepare emergency bay for CARDIOLOGY intake",
            "Required Team": "Emergency department physicians and CARDIOLOGY team on standby",
            "Risk Assessment": "Standard transit risks apply. Monitor vitals",
            "emergency_summary": "Severe chest pain radiating to left arm",
            "recommended_preparation": "Prepare emergency bay for CARDIOLOGY intake",
            "required_team": "Emergency department physicians and CARDIOLOGY team on standby",
            "risk_assessment": "Standard transit risks apply. Monitor vitals"
        }
        
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
        assert res["hospital_notified"] is True
        
        # Verify briefing keys exist
        assert "Emergency Summary" in res["briefing"]
        assert "Recommended Preparation" in res["briefing"]
        assert "Required Team" in res["briefing"]
        assert "Risk Assessment" in res["briefing"]
        assert res["briefing"]["Emergency Summary"] == "Severe chest pain radiating to left arm"
        
        # Verify publish parameters
        mock_publish.assert_called_once()
        _, kwargs = mock_publish.call_args
        assert kwargs["case_id"] == res["case_id"]
        assert kwargs["hospital_id"] == "AP-KRS-001"
        assert kwargs["severity"] == "critical"
        assert kwargs["specialty"] == "cardiology"
        assert kwargs["eta_minutes"] == 10
        assert kwargs["briefing"] == mock_briefing.return_value


def test_triage_agent_error_graceful_fallback():
    # If client initialization throws an exception, verify triage_severity recovers and returns FALLBACK_RESPONSE
    with patch('google.genai.Client') as mock_client:
        mock_client.side_effect = Exception("API Key Error")
        res = triage_severity("severe pain", 55)
        assert res == FALLBACK_RESPONSE


def test_routing_ranking_algorithm_eta_influence():
    # Verify that a closer ETA hospital outranks a farther hospital when other factors are identical
    hospitals = [
        {
            "hospital_id": "AP-KRS-003",
            "name": "Farther Hospital but faster ETA",
            "lat": 16.5300,
            "lng": 80.6200,
            "specialties": ["cardiology"],
            "is_government": False,
            "accreditation": "NABH",
            "rating": 4.0
        },
        {
            "hospital_id": "AP-KRS-004",
            "name": "Closer Hospital but slower ETA",
            "lat": 16.5100,
            "lng": 80.6400,
            "specialties": ["cardiology"],
            "is_government": False,
            "accreditation": "NABH",
            "rating": 4.0
        }
    ]
    capacity = {
        "AP-KRS-003": {"beds_available": 10, "icu_available": 2, "capacity_status": "available"},
        "AP-KRS-004": {"beds_available": 10, "icu_available": 2, "capacity_status": "available"}
    }
    
    from unittest.mock import patch
    
    def side_effect(origin_lat, origin_lng, dest_lat, dest_lng):
        if abs(dest_lat - 16.5300) < 0.001:
            return 5  # 5 minutes ETA
        else:
            return 45  # 45 minutes ETA

    with patch('agents.routing_agent.get_google_maps_eta', side_effect=side_effect):
        ranked = rank_hospitals(hospitals, capacity, 16.5062, 80.6480, "critical", "cardiology")
        # AP-KRS-003 (Farther, 5 min ETA) should outrank AP-KRS-004 (Closer, 45 min ETA)
        assert len(ranked) == 2
        assert ranked[0]["hospital_id"] == "AP-KRS-003"
        assert ranked[0]["rank"] == 1
        assert ranked[0]["eta_minutes"] == 5
        assert ranked[1]["hospital_id"] == "AP-KRS-004"
        assert ranked[1]["eta_minutes"] == 45


def test_routing_cardiac_scenario():
    # Verify critical cardiac scenario returns cardiology specialty matching hospitals at top
    hospitals = [
        {
            "hospital_id": "H-CARDIAC",
            "name": "Heart Care Hospital",
            "lat": 16.5100,
            "lng": 80.6400,
            "specialties": ["cardiology"],
            "is_government": False,
            "rating": 4.0
        },
        {
            "hospital_id": "H-GENERAL",
            "name": "General Health Hospital",
            "lat": 16.5100,
            "lng": 80.6400,
            "specialties": ["pediatrics", "general"],
            "is_government": False,
            "rating": 4.0
        }
    ]
    capacity = {
        "H-CARDIAC": {"beds_available": 10, "icu_available": 2, "capacity_status": "available"},
        "H-GENERAL": {"beds_available": 10, "icu_available": 2, "capacity_status": "available"}
    }
    
    ranked = rank_hospitals(hospitals, capacity, 16.5062, 80.6480, "critical", "cardiology")
    # Heart Care Hospital (cardiology) should rank first because of specialty match score (1.0 vs 0.3)
    assert len(ranked) == 2
    assert ranked[0]["hospital_id"] == "H-CARDIAC"
    assert ranked[0]["specialty_match"] is True

def test_icu_scaling():
    import math
    # Test formula directly
    def get_icu_score(icu_avail):
        return math.log1p(icu_avail) / math.log1p(50)
        
    s1 = get_icu_score(1)
    s5 = get_icu_score(5)
    s14 = get_icu_score(14)
    s50 = get_icu_score(50)
    
    assert s1 < s5 < s14 < s50
    assert abs(s50 - 1.0) < 1e-9

    # Test via ranking function
    hospitals = [
        {"hospital_id": f"H-{i}", "name": f"H{i}", "lat": 16.51, "lng": 80.64, "specialties": ["cardiology"]}
        for i in [1, 5, 14, 50]
    ]
    capacity = {
        "H-1": {"beds_available": 25, "icu_available": 1, "capacity_status": "available"},
        "H-5": {"beds_available": 25, "icu_available": 5, "capacity_status": "available"},
        "H-14": {"beds_available": 25, "icu_available": 14, "capacity_status": "available"},
        "H-50": {"beds_available": 25, "icu_available": 50, "capacity_status": "available"},
    }
    ranked = rank_hospitals(hospitals, capacity, 16.5062, 80.6480, "critical", "cardiology")
    assert ranked[0]["hospital_id"] == "H-50"
    assert ranked[1]["hospital_id"] == "H-14"
    assert ranked[2]["hospital_id"] == "H-5"
    assert ranked[3]["hospital_id"] == "H-1"

def test_score_breakdown_exists():
    hospitals = [
        {"hospital_id": "H-1", "name": "H1", "lat": 16.51, "lng": 80.64, "specialties": ["cardiology"]}
    ]
    capacity = {
        "H-1": {"beds_available": 25, "icu_available": 5, "capacity_status": "available"}
    }
    ranked = rank_hospitals(hospitals, capacity, 16.5062, 80.6480, "critical", "cardiology")
    assert len(ranked) == 1
    h = ranked[0]
    assert "score_breakdown" in h
    sb = h["score_breakdown"]
    
    # Raw values
    assert "raw_eta_minutes" in sb
    assert "raw_distance_km" in sb
    assert "beds_available" in sb
    assert "icu_available" in sb
    
    # Score metrics
    assert "eta_score" in sb
    assert "distance_score" in sb
    assert "capacity_score" in sb
    assert "icu_score" in sb
    assert "specialty_score" in sb
    
    # Modifier & aggregate
    assert "government_bonus" in sb
    assert "final_score" in sb

def test_cardiology_routing():
    hospitals = [
        {
            "hospital_id": "H-CARD",
            "name": "Cardio Clinic",
            "lat": 16.5100,
            "lng": 80.6400,
            "specialties": ["cardiology"],
            "is_government": False
        },
        {
            "hospital_id": "H-ORTHO",
            "name": "Ortho Clinic",
            "lat": 16.5100,
            "lng": 80.6400,
            "specialties": ["orthopedics"],
            "is_government": False
        }
    ]
    capacity = {
        "H-CARD": {"beds_available": 15, "icu_available": 2, "capacity_status": "available"},
        "H-ORTHO": {"beds_available": 15, "icu_available": 2, "capacity_status": "available"}
    }
    ranked = rank_hospitals(hospitals, capacity, 16.5062, 80.6480, "critical", "cardiology")
    assert ranked[0]["hospital_id"] == "H-CARD"

def test_score_bounds():
    import math
    hospitals = [
        {"hospital_id": "H-MIN", "name": "H-min", "lat": 16.51, "lng": 80.64, "specialties": ["cardiology"]},
        {"hospital_id": "H-MAX", "name": "H-max", "lat": 16.51, "lng": 80.64, "specialties": ["cardiology"]}
    ]
    capacity = {
        "H-MIN": {"beds_available": 0, "icu_available": 0, "capacity_status": "full"},
        "H-MAX": {"beds_available": 50, "icu_available": 50, "capacity_status": "available"}
    }
    
    ranked = rank_hospitals(hospitals, capacity, 16.5062, 80.6480, "critical", "cardiology")
    
    for h in ranked:
        sb = h["score_breakdown"]
        assert 0 <= sb["icu_score"] <= 1.0
        assert 0 <= sb["final_score"]
        
        # Verify no NaN values occur
        for k, v in sb.items():
            if isinstance(v, (int, float)):
                assert not math.isnan(v), f"Value for key '{k}' is NaN"

def test_cardiac_emergency_scenario():
    hospitals = [
        {
            "hospital_id": "AP-TIER3-001",
            "name": "Community Health Centre Vijayawada",
            "lat": 16.53, "lng": 80.59,
            "specialties": ["general", "trauma"],  # Tier 3 can't have cardiology
            "is_government": True,
            "hospital_tier": "tier3"
        },
        {
            "hospital_id": "AP-TIER1-001",
            "name": "GGH Vijayawada",
            "lat": 16.51, "lng": 80.64,
            "specialties": ["general", "trauma", "cardiology", "neurology", "oncology"],
            "is_government": True,
            "hospital_tier": "tier1"
        }
    ]
    capacity = {
        "AP-TIER3-001": {"beds_available": 30, "icu_available": 1, "capacity_status": "available"},
        "AP-TIER1-001": {"beds_available": 30, "icu_available": 15, "capacity_status": "available"}
    }
    ranked = rank_hospitals(hospitals, capacity, 16.5062, 80.6480, "critical", "cardiology")
    assert ranked[0]["hospital_id"] == "AP-TIER1-001"
    assert ranked[0]["hospital_tier"] == "tier1"

def test_trauma_emergency_scenario():
    hospitals = [
        {
            "hospital_id": "AP-NOTRAUMA-001",
            "name": "Specialty Eye Clinic",
            "lat": 16.51, "lng": 80.64,
            "specialties": ["general", "ophthalmology"],
            "is_government": False
        },
        {
            "hospital_id": "AP-TRAUMA-001",
            "name": "Area Hospital Trauma Centre",
            "lat": 16.51, "lng": 80.64,
            "specialties": ["general", "trauma"],
            "is_government": True
        }
    ]
    capacity = {
        "AP-NOTRAUMA-001": {"beds_available": 30, "icu_available": 10, "capacity_status": "available"},
        "AP-TRAUMA-001": {"beds_available": 30, "icu_available": 10, "capacity_status": "available"}
    }
    ranked = rank_hospitals(hospitals, capacity, 16.5062, 80.6480, "critical", "trauma")
    assert ranked[0]["hospital_id"] == "AP-TRAUMA-001"

def test_neurology_emergency_scenario():
    hospitals = [
        {
            "hospital_id": "AP-NONEURO-001",
            "name": "Community Health Centre",
            "lat": 16.51, "lng": 80.64,
            "specialties": ["general", "trauma"],
            "is_government": True
        },
        {
            "hospital_id": "AP-NEURO-001",
            "name": "Manipal Hospital Neurology",
            "lat": 16.51, "lng": 80.64,
            "specialties": ["general", "trauma", "neurology"],
            "is_government": False
        }
    ]
    capacity = {
        "AP-NONEURO-001": {"beds_available": 30, "icu_available": 5, "capacity_status": "available"},
        "AP-NEURO-001": {"beds_available": 30, "icu_available": 15, "capacity_status": "available"}
    }
    ranked = rank_hospitals(hospitals, capacity, 16.5062, 80.6480, "critical", "neurology")
    assert ranked[0]["hospital_id"] == "AP-NEURO-001"

def test_routing_explanation():
    from agents.routing_agent import generate_routing_explanation
    ranked = [
        {
            "rank": 1,
            "name": "GGH Vijayawada",
            "distance_km": 1.2,
            "eta_minutes": 5,
            "beds_available": 20,
            "icu_available": 10,
            "hospital_tier": "tier1",
            "is_government": True,
            "specialties": ["cardiology"],
            "score_breakdown": {"final_score": 0.95}
        },
        {
            "rank": 2,
            "name": "Area Hospital",
            "distance_km": 5.4,
            "eta_minutes": 15,
            "beds_available": 5,
            "icu_available": 1,
            "hospital_tier": "tier2",
            "is_government": False,
            "specialties": ["cardiology"],
            "score_breakdown": {"final_score": 0.65}
        }
    ]
    
    # We patch the Gemini client call to verify explainability returns correctly without live network calls
    with patch('google.genai.Client') as mock_client:
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance
        
        # Setup mock response text
        mock_response = MagicMock()
        mock_response.text = '{"selected_hospital": "GGH Vijayawada", "routing_explanation": "Selected GGH due to extremely low ETA and high ICU beds availability.", "rejected_options": ["Area Hospital was rejected because of its 15 minutes ETA (10 minutes slower)."], "confidence_score": 0.95}'
        mock_instance.models.generate_content.return_value = mock_response
        
        res = generate_routing_explanation(ranked, "critical", "cardiology")
        
        assert res["selected_hospital"] == "GGH Vijayawada"
        assert "GGH due to extremely low ETA" in res["routing_explanation"]
        assert len(res["rejected_options"]) == 1
        assert "Area Hospital was rejected" in res["rejected_options"][0]
        assert res["confidence_score"] == 0.95

