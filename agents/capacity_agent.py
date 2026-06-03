import os
from dotenv import load_dotenv
from elasticsearch import Elasticsearch, ConflictError

# Load environment variables
load_dotenv()

ELASTIC_ENDPOINT = os.getenv("ELASTIC_ENDPOINT")
ELASTIC_API_KEY = os.getenv("ELASTIC_API_KEY")

es = Elasticsearch(
    ELASTIC_ENDPOINT,
    api_key=ELASTIC_API_KEY
)

def check_capacity(hospital_ids: list) -> dict:
    """
    Check current capacity statistics for a list of hospitals in a single request.
    """
    if not es or not hospital_ids:
        return {}

    try:
        response = es.mget(index="hospitals", ids=hospital_ids)
        docs = response.get("docs", [])
    except Exception as e:
        print(f"Error checking capacity via mget: {e}")
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
            
            # Determine capacity_status
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
            
    # Add any missing IDs with default full status
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

def reserve_bed(hospital_id: str) -> dict:
    """
    Atomically reserve a bed at a hospital using optimistic locking.
    Retries up to 3 times on conflict.
    """
    if not es:
        return {"success": False, "new_count": 0, "conflict": False}

    for attempt in range(3):
        try:
            # Step 1: GET hospital doc and sequence number/primary term
            doc = es.get(index="hospitals", id=hospital_id)
            seq_no = doc["_seq_no"]
            primary_term = doc["_primary_term"]
            source = doc["_source"]
            
            beds_avail = source.get("beds_available", 0)
            if beds_avail <= 0:
                # No beds available to reserve
                return {"success": False, "new_count": 0, "conflict": False}

            # Step 2: UPDATE with painless script and optimistic parameters
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
                
            # Get updated doc to check count and update status
            updated_doc = es.get(index="hospitals", id=hospital_id)
            updated_source = updated_doc["_source"]
            new_beds_avail = updated_source.get("beds_available", 0)
            
            # Update capacity_status accordingly
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
            # Optimistic lock conflict
            if attempt == 2:
                return {"success": False, "new_count": 0, "conflict": True}
            # Wait briefly and retry
            import time
            time.sleep(0.1)
        except Exception as e:
            print(f"Exception during reserve_bed: {e}")
            return {"success": False, "new_count": 0, "conflict": False}
            
    return {"success": False, "new_count": 0, "conflict": True}

def get_system_stats() -> dict:
    """
    Returns aggregated stats across all AP hospitals using Elasticsearch aggregations.
    """
    if not es:
        return {
            "total_hospitals": 0, "total_beds": 0, "available_beds": 0, "available_icu": 0,
            "occupancy_rate": 1.0, "status_breakdown": {"available": 0, "limited": 0, "full": 0},
            "by_district": []
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
        print(f"Error compiling system stats: {e}")
        return {
            "total_hospitals": 0, "total_beds": 0, "available_beds": 0, "available_icu": 0,
            "occupancy_rate": 1.0, "status_breakdown": {"available": 0, "limited": 0, "full": 0},
            "by_district": []
        }

if __name__ == "__main__":
    test_ids = ["AP-KRS-001", "AP-KRS-002", "AP-VZG-001", "NONEXISTENT"]
    capacity = check_capacity(test_ids)
    print("Capacity check:")
    for hid, data in capacity.items():
        print(f"  {hid}: {data['beds_available']} beds — {data['capacity_status']}")
    
    stats = get_system_stats()
    print(f"\nSystem stats:")
    print(f"  Total beds: {stats['total_beds']}")
    print(f"  Available: {stats['available_beds']}")
    print(f"  Occupancy: {stats['occupancy_rate']:.1%}")
