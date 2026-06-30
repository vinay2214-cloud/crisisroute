from typing import List, Dict, Any
from agents.mcp_client import mcp_client

# Dummy attribute for backward compatibility with unit test mock patches
es = None

def check_capacity(hospital_ids: List[str]) -> Dict[str, Any]:
    """
    Check current capacity statistics for a list of hospitals in a single request via MCP.
    """
    res = mcp_client.call_tool("get_capacity", {"hospital_ids": hospital_ids})
    return res if res is not None else {}

def reserve_bed(hospital_id: str) -> Dict[str, Any]:
    """
    Atomically reserve a bed at a hospital using optimistic locking via MCP.
    """
    res = mcp_client.call_tool("reserve_bed", {"hospital_id": hospital_id})
    return res if res is not None else {"success": False, "new_count": 0, "conflict": False}

def get_system_stats() -> Dict[str, Any]:
    """
    Returns aggregated stats across all AP hospitals using Elasticsearch aggregations via MCP.
    """
    res = mcp_client.call_tool("get_dashboard_stats", {})
    return res if res is not None else {
        "total_hospitals": 0,
        "total_beds": 0,
        "available_beds": 0,
        "available_icu": 0,
        "occupancy_rate": 1.0,
        "status_breakdown": {"available": 0, "limited": 0, "full": 0},
        "by_district": []
    }
