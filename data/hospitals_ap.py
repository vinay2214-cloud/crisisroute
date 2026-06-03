import os
import random
from dotenv import load_dotenv
from elasticsearch import Elasticsearch, helpers

# Load environment variables
load_dotenv()

ELASTIC_ENDPOINT = os.getenv("ELASTIC_ENDPOINT")
ELASTIC_API_KEY = os.getenv("ELASTIC_API_KEY")

es = Elasticsearch(
    ELASTIC_ENDPOINT,
    api_key=ELASTIC_API_KEY
)

CITIES = {
    "Vijayawada": {"district": "Krishna", "code": "KRS", "lat": 16.5062, "lon": 80.6480, "count": 12, "phone_prefix": "866"},
    "Visakhapatnam": {"district": "Visakhapatnam", "code": "VZG", "lat": 17.6868, "lon": 83.2185, "count": 10, "phone_prefix": "891"},
    "Guntur": {"district": "Guntur", "code": "GNT", "lat": 16.3067, "lon": 80.4365, "count": 8, "phone_prefix": "863"},
    "Tirupati": {"district": "Chittoor", "code": "TPT", "lat": 13.6288, "lon": 79.4192, "count": 8, "phone_prefix": "877"},
    "Kurnool": {"district": "Kurnool", "code": "KNL", "lat": 15.8281, "lon": 78.0373, "count": 6, "phone_prefix": "8518"},
    "Nellore": {"district": "Nellore", "code": "NLR", "lat": 14.4426, "lon": 79.9865, "count": 6, "phone_prefix": "861"}
}

SPECIALTIES_LIST = [
    "cardiology", "trauma", "neurology", "pediatrics", "orthopedics",
    "general", "oncology", "gynecology", "nephrology", "gastroenterology",
    "pulmonology", "urology", "psychiatry", "dermatology", "ophthalmology"
]

GOVT_NAMES = [
    "Government General Hospital {City}",
    "Government District Hospital {City}",
    "Area Hospital {City}",
    "Community Health Centre {City}"
]

PRIVATE_NAMES = [
    "Apollo Hospitals {City}", "KIMS Hospital {City}", "Care Hospitals {City}",
    "Narayana Health {City}", "NRI Medical College & Hospital",
    "Seven Hills Hospital", "Manipal Hospital {City}", "Omega Hospital",
    "Ramesh Hospitals {City}", "Aayush Hospitals", "Sunrise Hospital",
    "City Care Hospital", "Life Hospital {City}", "Medicover Hospitals {City}"
]

def generate_hospitals():
    docs = []
    
    for city_name, data in CITIES.items():
        city_count = data["count"]
        
        # Ensure at least 1-2 Govt hospitals per city
        govt_count = max(1, int(city_count * 0.25))
        
        private_pool = PRIVATE_NAMES.copy()
        random.shuffle(private_pool)
        
        for i in range(1, city_count + 1):
            hid = f"AP-{data['code']}-{i:03d}"
            
            is_government = i <= govt_count
            
            if is_government:
                # First govt hospital is usually GGH
                name_template = GOVT_NAMES[0] if i == 1 else random.choice(GOVT_NAMES[1:])
                name = name_template.replace("{City}", city_name).replace("{Area}", city_name)
                accreditation = "Govt"
                
                # Size
                if "General" in name:
                    beds_total = random.randint(300, 600)
                    spec_count = random.randint(6, 8)
                else:
                    beds_total = random.randint(100, 300)
                    spec_count = random.randint(4, 6)
            else:
                name_template = private_pool.pop() if private_pool else "Private Hospital {City}"
                name = name_template.replace("{City}", city_name)
                accreditation = random.choice(["NABH", "JCI"])
                
                # Determine multispecialty or small based on name and randomness
                is_multi = any(x in name for x in ["Apollo", "KIMS", "Care", "Narayana", "Manipal", "Medicover", "College"])
                if is_multi or random.random() > 0.5:
                    beds_total = random.randint(100, 400)
                    spec_count = random.randint(4, 6)
                else:
                    beds_total = random.randint(50, 100)
                    spec_count = random.randint(2, 3)

            # Capacity constraints
            beds_available = int(beds_total * random.uniform(0.20, 0.50))
            icu_total = int(beds_total * 0.08)
            icu_available = random.randint(0, icu_total)
            ventilators_available = random.randint(0, 5)
            
            if beds_available > 10:
                capacity_status = "available"
            elif beds_available > 0:
                capacity_status = "limited"
            else:
                capacity_status = "full"
                
            # Randomize location slightly around city center
            lat = data["lat"] + random.uniform(-0.08, 0.08)
            lon = data["lon"] + random.uniform(-0.08, 0.08)
            
            # Select specialties
            # Always include general & trauma for big hospitals
            selected_specialties = []
            if beds_total > 150:
                selected_specialties.extend(["general", "trauma", "cardiology"])
            
            remaining_specs = [s for s in SPECIALTIES_LIST if s not in selected_specialties]
            needed = max(1, spec_count - len(selected_specialties))
            selected_specialties.extend(random.sample(remaining_specs, needed))
            
            phone = f"+91-{data['phone_prefix']}-{random.randint(2000000, 9999999)}"
            rating = round(random.uniform(3.2, 4.8), 1)

            doc = {
                "hospital_id": hid,
                "name": name,
                "district": data["district"],
                "state": "Andhra Pradesh",
                "location": {"lat": lat, "lon": lon},
                "specialties": selected_specialties,
                "beds_total": beds_total,
                "beds_available": beds_available,
                "icu_total": icu_total,
                "icu_available": icu_available,
                "ventilators_available": ventilators_available,
                "contact_phone": phone,
                "emergency_phone": "108",
                "is_government": is_government,
                "accreditation": accreditation,
                "rating": rating,
                "capacity_status": capacity_status,
                "last_updated": "2026-06-03T00:00:00Z",
                "version": 1
            }
            
            docs.append({
                "_index": "hospitals",
                "_id": hid,
                "_source": doc
            })
            
    return docs

def seed_data():
    docs = generate_hospitals()
    
    # Bulk insert
    success, _ = helpers.bulk(es, docs)
    # Refresh to ensure available for count
    es.indices.refresh(index="hospitals")
    
    # Print count
    count = es.count(index="hospitals")["count"]
    print(f"✅ Seeded 50 hospitals | Total: {count}")
    
    # Print sample AP-KRS-001
    sample = es.get(index="hospitals", id="AP-KRS-001")["_source"]
    print("\nSample Hospital (AP-KRS-001):")
    print(f"Name: {sample['name']}")
    print(f"Specialties: {', '.join(sample['specialties'])}")

if __name__ == "__main__":
    seed_data()
