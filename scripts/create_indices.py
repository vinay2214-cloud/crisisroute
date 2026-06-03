import os
from dotenv import load_dotenv
from elasticsearch import Elasticsearch

# Load environment variables
load_dotenv()

# Initialize Elasticsearch client
ELASTIC_ENDPOINT = os.getenv("ELASTIC_ENDPOINT")
ELASTIC_API_KEY = os.getenv("ELASTIC_API_KEY")

es = Elasticsearch(
    ELASTIC_ENDPOINT,
    api_key=ELASTIC_API_KEY
)

# Common index settings
settings = {
    "number_of_shards": 1,
    "number_of_replicas": 0
}

# Define indices and their mappings
indices = {
    "hospitals": {
        "properties": {
            "hospital_id": {"type": "keyword"},
            "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "district": {"type": "keyword"},
            "state": {"type": "keyword"},
            "location": {"type": "geo_point"},
            "specialties": {"type": "keyword"},
            "beds_total": {"type": "integer"},
            "beds_available": {"type": "integer"},
            "icu_total": {"type": "integer"},
            "icu_available": {"type": "integer"},
            "ventilators_available": {"type": "integer"},
            "contact_phone": {"type": "keyword"},
            "emergency_phone": {"type": "keyword"},
            "is_government": {"type": "boolean"},
            "accreditation": {"type": "keyword"},
            "rating": {"type": "float"},
            "capacity_status": {"type": "keyword"},
            "last_updated": {"type": "date"},
            "version": {"type": "integer"}
        }
    },
    "symptom_specialty_map": {
        "properties": {
            "symptom_text": {"type": "text", "analyzer": "english"},
            "specialty": {"type": "keyword"},
            "severity_hint": {"type": "keyword"},
            "icd10_codes": {"type": "keyword"},
            "symptom_embedding": {
                "type": "dense_vector",
                "dims": 768,
                "index": True,
                "similarity": "cosine"
            }
        }
    },
    "triage_cases": {
        "properties": {
            "case_id": {"type": "keyword"},
            "session_id": {"type": "keyword"},
            "symptoms_raw": {"type": "text"},
            "patient_age": {"type": "integer"},
            "patient_name": {"type": "keyword"},
            "triage_severity": {"type": "keyword"},
            "chief_complaint": {"type": "text"},
            "specialty_matched": {"type": "keyword"},
            "specialty_confidence": {"type": "float"},
            "hospital_selected_id": {"type": "keyword"},
            "hospital_selected_name": {"type": "keyword"},
            "hospitals_considered": {"type": "integer"},
            "eta_minutes": {"type": "integer"},
            "distance_km": {"type": "float"},
            "hospital_notified": {"type": "boolean"},
            "patient_location": {"type": "geo_point"},
            "pipeline_duration_ms": {"type": "integer"},
            "timestamp": {"type": "date"},
            "outcome_status": {"type": "keyword"}
        }
    }
}

def create_indices():
    for index_name, mapping in indices.items():
        # Delete if exists
        if es.indices.exists(index=index_name):
            es.indices.delete(index=index_name)
        
        # Create index
        try:
            es.indices.create(
                index=index_name,
                body={
                    "settings": settings,
                    "mappings": mapping
                }
            )
        except Exception as e:
            # If serverless doesn't accept settings, retry without them
            if "serverless" in str(e).lower() or "illegal_argument_exception" in str(e).lower() or "bad_request" in str(e).lower():
                es.indices.create(
                    index=index_name,
                    body={
                        "mappings": mapping
                    }
                )
            else:
                raise e
        print(f"✓ Created: {index_name}")
    
    print("✅ All 3 indices ready")

if __name__ == "__main__":
    create_indices()
