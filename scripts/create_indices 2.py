import os
from dotenv import load_dotenv
from elasticsearch import Elasticsearch

def main():
    # Load environment variables from .env file
    load_dotenv()

    # Read credentials
    elastic_endpoint = os.getenv("ELASTIC_ENDPOINT")
    elastic_api_key = os.getenv("ELASTIC_API_KEY")

    if not elastic_endpoint or not elastic_api_key:
        print("Error: ELASTIC_ENDPOINT and ELASTIC_API_KEY must be set in the .env file.")
        return

    # Initialize Elasticsearch client
    es = Elasticsearch(
        elastic_endpoint,
        api_key=elastic_api_key
    )

    # Define indices and their mappings
    indices_to_create = {
        "hospitals": {
            "properties": {
                "hospital_id": {"type": "keyword"},
                "name": {
                    "type": "text",
                    "fields": {
                        "keyword": {"type": "keyword"}
                    }
                },
                "district": {"type": "keyword"},
                "state": {"type": "keyword"},
                "location": {"type": "geo_point"},
                "specialties": {"type": "keyword"},
                "beds_total": {"type": "integer"},
                "beds_available": {"type": "integer"},
                "icu_total": {"type": "integer"},
                "icu_available": {"type": "integer"},
                "contact_phone": {"type": "keyword"},
                "is_government": {"type": "boolean"},
                "updated_at": {"type": "date"}
            }
        },
        "symptom_specialty_map": {
            "properties": {
                "symptom_text": {"type": "text"},
                "specialty": {"type": "keyword"},
                "severity_hint": {"type": "keyword"},
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
                "symptoms_raw": {"type": "text"},
                "patient_age": {"type": "integer"},
                "triage_severity": {"type": "keyword"},
                "specialty_matched": {"type": "keyword"},
                "hospital_selected_id": {"type": "keyword"},
                "hospital_selected_name": {"type": "keyword"},
                "eta_minutes": {"type": "integer"},
                "hospital_notified": {"type": "boolean"},
                "timestamp": {"type": "date"},
                "session_id": {"type": "keyword"}
            }
        }
    }

    # Iterate, delete if exists, and create
    for index_name, mappings in indices_to_create.items():
        if es.indices.exists(index=index_name):
            es.indices.delete(index=index_name)
            
        es.indices.create(index=index_name, mappings=mappings)
        print(f"Index '{index_name}' created successfully.")

    print("All 3 indices created successfully")

if __name__ == "__main__":
    main()
