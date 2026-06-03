import os
import random
import uuid
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

symptoms_raw_data = [
    # CARDIOLOGY — severity: critical
    ("severe chest pain radiating to left arm jaw sweating cold clammy", "cardiology", "critical", ["I21.9", "I21.0"]),
    ("crushing substernal chest pressure dyspnea diaphoresis", "cardiology", "critical", ["I21.9", "I21.1"]),
    ("heart palpitations rapid irregular pulse dizziness pre-syncope", "cardiology", "critical", ["R00.2", "I48.91"]),
    ("sudden sharp tearing chest pain radiating to back aortic", "cardiology", "critical", ["I71.01", "I71.00"]),
    ("shortness of breath orthopnea paroxysmal nocturnal dyspnea edema", "cardiology", "critical", ["I50.9", "R06.02"]),

    # NEUROLOGY — severity: critical
    ("sudden slurred speech facial drooping arm weakness unilateral stroke", "neurology", "critical", ["I63.9", "R47.81"]),
    ("thunderclap headache worst of life sudden onset subarachnoid", "neurology", "critical", ["I60.9", "R51.9"]),
    ("loss of consciousness seizure convulsion postictal confusion", "neurology", "critical", ["G40.909", "R56.9"]),
    ("sudden vision loss one eye amaurosis fugax transient", "neurology", "critical", ["G45.3", "H54.41"]),
    ("hemiparesis hemisensory loss gait ataxia acute neurological deficit", "neurology", "critical", ["G81.90", "R26.0"]),
    ("altered mental status confusion agitation acute onset elderly", "neurology", "critical", ["R41.82", "F05"]),

    # TRAUMA — severity: critical
    ("major road traffic accident unconscious polytrauma", "trauma", "critical", ["T14.90", "V89.2"]),
    ("fall from height multiple long bone fractures spinal injury", "trauma", "critical", ["T08", "W17.9"]),
    ("penetrating stab wound gunshot wound internal bleeding", "trauma", "critical", ["T14.1", "T14.8"]),
    ("severe traumatic brain injury head injury skull fracture", "trauma", "critical", ["S06.9X9A", "S02.91"]),
    ("crush injury entrapment rhabdomyolysis", "trauma", "critical", ["T79.6XXA", "M62.82"]),
    ("drowning near-drowning hypoxia resuscitation", "trauma", "critical", ["T75.1XXA", "R09.02"]),

    # PEDIATRICS — severity: critical/urgent
    ("infant high fever 104F febrile seizure crying inconsolable", "pediatrics", "critical", ["R56.01", "R50.9"]),
    ("child respiratory distress stridor barking cough croup", "pediatrics", "critical", ["J38.5", "J05.0"]),
    ("newborn jaundice phototherapy hyperbilirubinemia", "pediatrics", "urgent", ["P59.9", "Z48.816"]),
    ("toddler foreign body aspiration choking cyanosis", "pediatrics", "critical", ["T17.908A", "R06.82"]),
    ("child acute abdomen intussusception bilious vomiting", "pediatrics", "critical", ["K56.1", "R11.10"]),
    ("pediatric anaphylaxis allergic reaction urticaria angioedema", "pediatrics", "critical", ["T78.2XXA", "L50.0"]),
    ("neonatal sepsis poor feeding lethargy temperature instability", "pediatrics", "critical", ["P36.9", "R53.83"]),

    # ORTHOPEDICS — severity: urgent
    ("closed fracture long bone deformity neurovascular compromise", "orthopedics", "urgent", ["S72.90XA", "M21.9"]),
    ("open fracture wound contamination bone exposed", "orthopedics", "urgent", ["T14.2", "M86.9"]),
    ("acute joint dislocation shoulder hip knee locked", "orthopedics", "urgent", ["S43.006A", "M24.50"]),
    ("spinal cord injury paralysis paresthesia bladder bowel dysfunction", "orthopedics", "urgent", ["S14.109A", "R15.9"]),
    ("acute compartment syndrome severe pain passive stretch tense compartment", "orthopedics", "urgent", ["M79.A19", "R52"]),

    # GYNECOLOGY — severity: critical/urgent
    ("third trimester bleeding placenta previa abruption", "gynecology", "critical", ["O46.93", "O44.13"]),
    ("shoulder dystocia cord prolapse obstetric emergency", "gynecology", "critical", ["O66.0", "O69.0"]),
    ("postpartum hemorrhage uterine atony retained placenta", "gynecology", "critical", ["O72.1", "O73.0"]),
    ("ectopic pregnancy ruptured hemoperitoneum acute abdomen", "gynecology", "critical", ["O00.90", "R10.0"]),
    ("severe preeclampsia hypertension proteinuria headache visual", "gynecology", "critical", ["O14.13", "I10"]),
    ("hyperemesis gravidarum severe dehydration", "gynecology", "urgent", ["O21.1", "E86.0"]),

    # NEPHROLOGY — severity: urgent
    ("acute kidney injury oliguria anuria elevated creatinine uremia", "nephrology", "urgent", ["N17.9", "R34"]),
    ("severe renal colic ureteral stone obstruction", "nephrology", "urgent", ["N20.1", "N13.2"]),
    ("dialysis access failure graft thrombosis fistula problem", "nephrology", "urgent", ["T82.868A", "I82.90"]),

    # GASTROENTEROLOGY — severity: urgent
    ("hematemesis melena upper GI bleed coffee ground vomiting", "gastroenterology", "urgent", ["K92.0", "K92.1"]),
    ("acute abdomen peritonitis rebound tenderness guarding rigidity", "gastroenterology", "urgent", ["R10.0", "K65.9"]),
    ("acute pancreatitis epigastric pain radiating to back amylase", "gastroenterology", "urgent", ["K85.90", "R10.13"]),
    ("appendicitis right lower quadrant pain McBurney rebound", "gastroenterology", "urgent", ["K35.80", "R10.31"]),
    ("intestinal obstruction volvulus distension no flatus", "gastroenterology", "urgent", ["K56.69", "K56.2"]),

    # PULMONOLOGY — severity: critical/urgent
    ("acute severe asthma status asthmaticus SpO2 dropping", "pulmonology", "critical", ["J46", "R09.02"]),
    ("tension pneumothorax tracheal deviation absent breath sounds", "pulmonology", "critical", ["J93.0", "R06.02"]),
    ("pulmonary embolism acute dyspnea pleuritic chest pain hemoptysis", "pulmonology", "critical", ["I26.99", "R04.2"]),
    ("COPD exacerbation hypercapnia respiratory failure", "pulmonology", "urgent", ["J44.1", "J96.01"]),

    # ONCOLOGY — severity: urgent
    ("febrile neutropenia cancer chemotherapy fever immunocompromised", "oncology", "urgent", ["D70.1", "R50.81"]),
    ("spinal cord compression malignancy back pain weakness urinary", "oncology", "urgent", ["G95.20", "M54.9"]),

    # GENERAL — severity: stable
    ("mild fever cough cold upper respiratory tract infection", "general", "stable", ["J06.9", "R50.9"])
]

def generate_embeddings_and_seed():
    docs = []
    
    for symptom_text, specialty, severity_hint, icd10_codes in symptoms_raw_data:
        # Generate random normalized 768-dim vector
        vec = [random.gauss(0, 1) for _ in range(768)]
        mag = sum(x**2 for x in vec)**0.5
        symptom_embedding = [x/mag for x in vec]
        
        doc = {
            "symptom_text": symptom_text,
            "specialty": specialty,
            "severity_hint": severity_hint,
            "icd10_codes": icd10_codes,
            "symptom_embedding": symptom_embedding
        }
        
        doc_id = str(uuid.uuid4())
        
        docs.append({
            "_index": "symptom_specialty_map",
            "_id": doc_id,
            "_source": doc
        })
        
    # Bulk insert
    helpers.bulk(es, docs)
    # Refresh to ensure available for count
    es.indices.refresh(index="symptom_specialty_map")
    
    # Print count
    count = es.count(index="symptom_specialty_map")["count"]
    print(f"✅ Seeded 50 symptom mappings | Total: {count}")

if __name__ == "__main__":
    generate_embeddings_and_seed()
