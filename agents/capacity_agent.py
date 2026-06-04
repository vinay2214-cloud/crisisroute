from typing import List, Dict, Any
from agents.mcp_client import mcp_client

# Dummy attribute for backward compatibility with unit test mock patches
es = None

def check_capacity(hospital_ids: List[str]) -> Dict[str, Any]:
    """
    Check current capacity statistics for a list of hospitals in a single request via MCP.
    """
    return mcp_client.call_tool("get_capacity", {"hospital_ids": hospital_ids})

def reserve_bed(hospital_id: str) -> Dict[str, Any]:
    """
    Atomically reserve a bed at a hospital using optimistic locking via MCP.
    """
    return mcp_client.call_tool("reserve_bed", {"hospital_id": hospital_id})

def get_system_stats() -> Dict[str, Any]:
    """
    Returns aggregated stats across all AP hospitals using Elasticsearch aggregations via MCP.
    """
    return mcp_client.call_tool("get_dashboard_stats", {})
