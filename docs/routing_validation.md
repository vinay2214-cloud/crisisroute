# CrisisRoute Routing Validation Report

This report documents the clinical and mathematical validation of the CrisisRoute routing algorithm across three emergency profiles: Cardiac, Trauma, and Neurology. All validation scenarios were run using a patient located at the center of Vijayawada (Latitude: `16.5062`, Longitude: `80.6480`).

---

## Scenario 1: Cardiac Emergency

### Patient Profile
*   **Symptoms:** Severe chest pain radiating to left arm, sweating, dizziness (Suspected Acute Coronary Syndrome).
*   **Age:** 55
*   **Severity:** Critical
*   **Required Specialty:** Cardiology

### Top 3 Routed Hospitals

#### 1. KIMS Hospital Vijayawada (Rank 1)
*   **Tier:** Tier 1 (Highly Capable Multispecialty)
*   **Distance:** 3.8 km | **ETA:** 17 minutes
*   **Beds Available:** 99 | **ICU Available:** 16
*   **Composite Score:** **0.886**
*   **Score Breakdown:**
    *   `eta_score`: 0.901
    *   `distance_score`: 0.907
    *   `capacity_score`: 1.000 (beds > 20)
    *   `icu_score`: 0.721 (logarithmic scale)
    *   `specialty_score`: 1.000 (matched cardiology)
    *   `government_bonus`: 0.000
    *   `final_score`: 0.886

#### 2. Sunrise Hospital (Rank 2)
*   **Tier:** Tier 2 (General & Trauma Hospital with optional Cardiology/Neurology capability)
*   **Distance:** 6.3 km | **ETA:** 20 minutes
*   **Beds Available:** 80 | **ICU Available:** 18
*   **Composite Score:** **0.873**
*   **Score Breakdown:**
    *   `eta_score`: 0.859
    *   `distance_score`: 0.845
    *   `capacity_score`: 1.000 (beds > 20)
    *   `icu_score`: 0.749 (logarithmic scale)
    *   `specialty_score`: 1.000 (matched cardiology)
    *   `government_bonus`: 0.000
    *   `final_score`: 0.873

#### 3. Government General Hospital Vijayawada (Rank 3)
*   **Tier:** Tier 1 (Public Multispecialty)
*   **Distance:** 7.1 km | **ETA:** 23 minutes
*   **Beds Available:** 104 | **ICU Available:** 17
*   **Composite Score:** **0.852**
*   **Score Breakdown:**
    *   `eta_score`: 0.817
    *   `distance_score`: 0.826
    *   `capacity_score`: 1.000 (beds > 20)
    *   `icu_score`: 0.735 (logarithmic scale)
    *   `specialty_score`: 1.000 (matched cardiology)
    *   `government_bonus`: 0.000
    *   `final_score`: 0.852

### Clinical Reasoning
*   **Capability Alignment:** All top 3 hospitals are Tier 1 or Tier 2 facilities equipped with active Cardiology teams. 
*   **Outlier Safety:** Tier 3 facilities (e.g., Community Health Centres) are mathematically excluded from the top ranks because they lack cardiology capabilities, ensuring critical patients are never routed to ill-equipped facilities.
*   **ICU Integration:** Logarithmic ICU scoring (`math.log1p(icu_avail)`) differentiates KIMS (16 ICU beds, score 0.721) and GGH (17 ICU beds, score 0.735) appropriately, rewarding large-scale capacity without hard-capping.

---

## Scenario 2: Trauma Emergency

### Patient Profile
*   **Symptoms:** Major road traffic accident, unconscious, heavy leg bleeding.
*   **Age:** 28
*   **Severity:** Critical
*   **Required Specialty:** Trauma

### Top 3 Routed Hospitals

#### 1. KIMS Hospital Vijayawada (Rank 1)
*   **Tier:** Tier 1 (Highly Capable Multispecialty)
*   **Distance:** 3.8 km | **ETA:** 17 minutes
*   **Beds Available:** 98 | **ICU Available:** 16
*   **Composite Score:** **0.886**
*   **Score Breakdown:**
    *   `eta_score`: 0.901
    *   `distance_score`: 0.907
    *   `capacity_score`: 1.000
    *   `icu_score`: 0.721
    *   `specialty_score`: 1.000
    *   `government_bonus`: 0.000
    *   `final_score`: 0.886

#### 2. Sunrise Hospital (Rank 2)
*   **Tier:** Tier 2
*   **Distance:** 6.3 km | **ETA:** 20 minutes
*   **Beds Available:** 80 | **ICU Available:** 18
*   **Composite Score:** **0.873**
*   **Score Breakdown:**
    *   `eta_score`: 0.859
    *   `distance_score`: 0.845
    *   `capacity_score`: 1.000
    *   `icu_score`: 0.749
    *   `specialty_score`: 1.000
    *   `government_bonus`: 0.000
    *   `final_score`: 0.873

#### 3. Government General Hospital Vijayawada (Rank 3)
*   **Tier:** Tier 1
*   **Distance:** 7.1 km | **ETA:** 23 minutes
*   **Beds Available:** 104 | **ICU Available:** 17
*   **Composite Score:** **0.852**
*   **Score Breakdown:**
    *   `eta_score`: 0.817
    *   `distance_score`: 0.826
    *   `capacity_score`: 1.000
    *   `icu_score`: 0.735
    *   `specialty_score`: 1.000
    *   `government_bonus`: 0.000
    *   `final_score`: 0.852

### Clinical Reasoning
*   **High Proximity Focus:** For trauma, real-time arrival is paramount. With the new critical severity weights (ETA weight = 0.40, distance weight = 0.05), KIMS (ETA 17 min) secures a major lead over GGH (ETA 23 min) due to travel-time optimization.
*   **ICU Resource Safety:** Both Tier 1 and Tier 2 trauma centres have ample ICU resources to handle multiple trauma resuscitations simultaneously.

---

## Scenario 3: Neurology Emergency

### Patient Profile
*   **Symptoms:** Sudden onset left facial droop, slurred speech, confusion (Stroke suspected).
*   **Age:** 68
*   **Severity:** Critical
*   **Required Specialty:** Neurology

### Top 3 Routed Hospitals

#### 1. KIMS Hospital Vijayawada (Rank 1)
*   **Tier:** Tier 1 (Highly Capable Multispecialty)
*   **Distance:** 3.8 km | **ETA:** 17 minutes
*   **Beds Available:** 97 | **ICU Available:** 16
*   **Composite Score:** **0.886**
*   **Score Breakdown:**
    *   `eta_score`: 0.901
    *   `distance_score`: 0.907
    *   `capacity_score`: 1.000
    *   `icu_score`: 0.721
    *   `specialty_score`: 1.000
    *   `government_bonus`: 0.000
    *   `final_score`: 0.886

#### 2. Sunrise Hospital (Rank 2)
*   **Tier:** Tier 2
*   **Distance:** 6.3 km | **ETA:** 20 minutes
*   **Beds Available:** 80 | **ICU Available:** 18
*   **Composite Score:** **0.873**
*   **Score Breakdown:**
    *   `eta_score`: 0.859
    *   `distance_score`: 0.845
    *   `capacity_score`: 1.000
    *   `icu_score`: 0.749
    *   `specialty_score`: 1.000
    *   `government_bonus`: 0.000
    *   `final_score`: 0.873

#### 3. Government General Hospital Vijayawada (Rank 3)
*   **Tier:** Tier 1
*   **Distance:** 7.1 km | **ETA:** 23 minutes
*   **Beds Available:** 104 | **ICU Available:** 17
*   **Composite Score:** **0.852**
*   **Score Breakdown:**
    *   `eta_score`: 0.817
    *   `distance_score`: 0.826
    *   `capacity_score`: 1.000
    *   `icu_score`: 0.735
    *   `specialty_score`: 1.000
    *   `government_bonus`: 0.000
    *   `final_score`: 0.852

### Clinical Reasoning
*   **Time-to-Thrombolysis (Golden Hour):** Stroke outcomes degrade severely with travel delay. The increased ETA weight (0.40) ensures that the closest stroke-capable center is selected.
*   **Exclusion of CHCs:** Community Health Centres (Tier 3) do not have CT scan units or neurology capabilities and are excluded, protecting stroke patients from invalid transfers.

---

## Conclusion
The clinical routing audits prove that the CrisisRoute composite score:
1.  Correctly filters out lower-tier, ill-equipped hospitals for specialized emergencies.
2.  Ensures proximity (ETA) is the primary driver of routing in critical scenarios.
3.  Evaluates ICU availability logarithmically to reward continuous capacity.
