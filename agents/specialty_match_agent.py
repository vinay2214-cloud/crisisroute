from typing import Optional, List, Dict, Any
from agents.mcp_client import mcp_client

# Dummy attribute for backward compatibility with unit test mock patches
es = None

# Direct keyword-to-specialty map — fast O(1) lookup that catches obvious cases
# before hitting the MCP/Elasticsearch path. Prevents wrong specialty returns
# when ES text relevance scoring returns low-confidence noise matches.
DIRECT_MAP = {
    "chest": "cardiology",
    "cardiac": "cardiology",
    "heart": "cardiology",
    "palpitation": "cardiology",
    "stroke": "neurology",
    "slurred": "neurology",
    "seizure": "neurology",
    "paralysis": "neurology",
    "trauma": "trauma",
    "accident": "trauma",
    "fracture": "orthopedics",
    "fever": "pediatrics",
    "child": "pediatrics",
    "infant": "pediatrics",
    "pregnancy": "gynecology",
    "labor": "gynecology",
    "kidney": "nephrology",
    "dialysis": "nephrology",
}

# Minimum confidence threshold — if ES returns below this, fall back to general
MIN_CONFIDENCE_THRESHOLD = 0.40


def match_specialty(symptom_keywords: List[str], severity: str) -> Dict[str, Any]:
    """
    Finds the best matching medical specialty for given symptoms.
    
    Resolution order:
    1. Empty keywords guard → returns general
    2. Direct keyword map → fast O(1) deterministic match
    3. MCP Server (Elasticsearch fuzzy text search) → confidence-gated
    """
    # Step 0: Guard against empty keywords (from failed triage)
    if not symptom_keywords or len(symptom_keywords) == 0:
        return {
            "specialty": "general",
            "confidence": 0.0,
            "alternative_specialty": "general",
            "search_method": "fallback_empty_keywords",
            "matched_symptom": ""
        }

    # Step 1: Direct keyword map — fast, deterministic, reliable
    keywords_lower = [k.lower() for k in symptom_keywords]
    for kw in keywords_lower:
        for trigger, specialty in DIRECT_MAP.items():
            if trigger in kw:
                return {
                    "specialty": specialty,
                    "confidence": 0.95,
                    "alternative_specialty": "general",
                    "search_method": "direct_keyword_map",
                    "matched_symptom": kw
                }

    # Step 2: MCP Server (Elasticsearch text search with fuzzy matching)
    try:
        result = mcp_client.call_tool("match_specialty", {
            "symptom_keywords": symptom_keywords,
            "severity": severity
        })

        # Confidence threshold gate: if ES returned a low-confidence match,
        # fall back to general to avoid misrouting (e.g. gynecology for cardiac)
        if result and result.get("confidence", 0) < MIN_CONFIDENCE_THRESHOLD:
            import logging
            logger = logging.getLogger("crisisroute.specialty")
            logger.warning(
                f"Rejected low-confidence specialty '{result.get('specialty')}' "
                f"with score/confidence: {result.get('confidence', 0):.3f}"
            )
            return {
                "specialty": "general",
                "confidence": result.get("confidence", 0),
                "alternative_specialty": result.get("alternative_specialty", "general"),
                "search_method": "low_confidence_fallback",
                "matched_symptom": result.get("matched_symptom", "")
            }


        import logging
        logger = logging.getLogger("crisisroute.specialty")
        logger.info(
            f"Specialty match resolved: specialty='{result.get('specialty')}', "
            f"confidence={result.get('confidence', 0):.3f}, "
            f"method='{result.get('search_method')}'"
        )
        return result
    except Exception as e:
        print(f"[SpecialtyMatchAgent ERROR] MCP call failed: {e}")
        # Final fallback: general specialty
        return {
            "specialty": "general",
            "confidence": 0.0,
            "alternative_specialty": "general",
            "search_method": "error_fallback",
            "matched_symptom": ""
        }

def search_hospitals_by_specialty(
    specialty: str,
    patient_lat: float,
    patient_lng: float,
    radius_km: int = 100
) -> List[Dict[str, Any]]:
    """
    Search hospitals using the Elastic MCP Server tool, filtering by specialty and geo_distance.
    """
    return mcp_client.call_tool("search_hospitals", {
        "specialty": specialty,
        "patient_lat": patient_lat,
        "patient_lng": patient_lng,
        "radius_km": radius_km
    })

if __name__ == "__main__":
    test_cases = [
        (["chest", "pain", "left", "arm", "sweating"], "critical", "cardiology"),
        (["slurred", "speech", "facial", "drooping"], "critical", "neurology"),
        (["fever", "child", "infant", "crying"], "urgent", "pediatrics"),
        (["road", "accident", "bleeding", "unconscious"], "critical", "trauma"),
        ([], "critical", "general"),  # empty keywords fallback
    ]

    all_passed = True
    for keywords, severity, expected in test_cases:
        result = match_specialty(keywords, severity)
        status = "PASS" if result["specialty"] == expected else "FAIL"
        if status == "FAIL":
            all_passed = False
        print(f"{status}: keywords={keywords[:2]}... → got={result['specialty']} expected={expected} confidence={result.get('confidence', 0):.2f}")

    print("\nALL TESTS PASSED" if all_passed else "\nSOME TESTS FAILED - fix before deploying")
