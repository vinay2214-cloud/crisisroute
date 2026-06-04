from typing import Optional, List, Dict, Any
from agents.mcp_client import mcp_client

# Dummy attribute for backward compatibility with unit test mock patches
es = None

def match_specialty(symptom_keywords: List[str], severity: str) -> Dict[str, Any]:
    """
    Finds the best matching medical specialty for given symptoms using the Elastic MCP Server.
    """
    return mcp_client.call_tool("match_specialty", {
        "symptom_keywords": symptom_keywords,
        "severity": severity
    })

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
