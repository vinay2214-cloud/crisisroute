import os, json, time, logging
from typing import List
from pydantic import BaseModel, Field
import google.genai as genai

# Enable standard JSON logs
logging.basicConfig(level=logging.INFO)

class TriageResult(BaseModel):
    severity: str = Field(description="Triage severity classification. Must be exactly 'critical', 'urgent', or 'stable'")
    chief_complaint: str = Field(description="One-line clinical summary (max 80 chars)")
    keywords: List[str] = Field(description="List of 5 clinical keywords/symptoms")
    reasoning: str = Field(description="2-sentence clinical rationale for triage decision")
    immediate_action: str = Field(description="Specific instruction for patient/family right now")
    confidence: float = Field(description="Confidence score from 0.0 to 1.0")
    differential_diagnoses: List[str] = Field(description="List of differential diagnoses")
    red_flags: List[str] = Field(description="List of red flags")

SYSTEM_PROMPT = """
You are a medical triage AI trained on Emergency Severity Index (ESI) v4 guidelines.
You assess patient symptoms and classify severity for emergency triage.

Classification rules:
critical: Immediate life threat. Requires immediate physician intervention.
Examples: MI, stroke, major trauma, anaphylaxis, respiratory failure, septic shock.
Default to critical when uncertain about life threat.

urgent: Serious. High risk situation. Should be seen within 15-30 minutes.
Examples: Fracture, moderate pain, altered mental status, asthma (moderate).

stable: Low urgency. Can wait. Non-threatening.
Examples: Minor cuts, mild fever, cold, routine complaints.

Return ONLY a raw JSON object. No markdown. No backticks. No explanation before or after. Start your response with { and end with }. Nothing else.
""".strip()

USER_PROMPT_TEMPLATE = """
Patient: {age} years old.
Presenting symptoms: {symptoms}
"""

FALLBACK_RESPONSE = {
    "severity": "critical",
    "chief_complaint": "Assessment failed — treating as critical for safety",
    "keywords": ["emergency", "triage", "assessment", "required", "critical"],
    "reasoning": "AI triage system encountered an error. Patient is being treated as critical per safety protocol to prevent undertriage.",
    "immediate_action": "Call 108 emergency services immediately. Do not wait.",
    "confidence": 0.0,
    "differential_diagnoses": [],
    "red_flags": ["system error — auto-escalated to critical"]
}

def clean_json_response(text: str) -> str:
    """
    Strip markdown code fences (```json ... ```) that Gemini sometimes wraps
    around JSON responses, even when response_mime_type is set to application/json.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines).strip()
    return text

def triage_severity(symptoms: str, age: int) -> dict:
    """
    Classify patient severity using Gemini 2.5 Flash.
    Returns structured triage result. Never raises — returns fallback on any error.
    """
    for attempt in range(3):
        try:
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if api_key:
                client = genai.Client(api_key=api_key)
            else:
                project = os.getenv("GOOGLE_CLOUD_PROJECT") or "crisisroute-2026-498212"
                location = os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1"
                client = genai.Client(vertexai=True, project=project, location=location)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=USER_PROMPT_TEMPLATE.format(symptoms=symptoms, age=age),
                config=genai.types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.1,
                    max_output_tokens=2000,
                    response_mime_type="application/json",
                    response_schema=TriageResult,
                )
            )
            raw = response.text.strip()
            cleaned = clean_json_response(raw)
            try:
                result = json.loads(cleaned, strict=False)
            except Exception as parse_err:
                print(f"[TriageAgent ERROR] {type(parse_err).__name__}: {parse_err}")
                print(f"[TriageAgent] Raw response was: {raw}")
                logging.error(f"JSON parsing failed for raw: {raw}")
                raise parse_err
            # Ensure severity is lowercase and valid
            sev = result.get("severity", "").lower()
            if sev not in ("critical", "urgent", "stable"):
                result["severity"] = "critical"
            else:
                result["severity"] = sev
            return result
        except Exception as e:
            print(f"[TriageAgent ERROR] {type(e).__name__}: {e}")
            logging.warning(f"TriageAgent attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)
    logging.error("TriageAgent: all 3 attempts failed — returning fallback")
    return FALLBACK_RESPONSE

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    test_cases = [
        ("severe chest pain radiating to left arm, sweating, dizziness", 55),
        ("2 year old baby has fever 104F, crying, won't eat, rash on body", 2),
        ("sudden slurred speech, cannot lift left arm, facial drooping", 62),
        ("mild headache for 2 days, no other symptoms", 30),
        ("major road accident, unconscious, heavy bleeding from leg", 35),
    ]
    print("=" * 60)
    for symptoms, age in test_cases:
        result = triage_severity(symptoms, age)
        print(f"Age {age} | {symptoms[:50]}...")
        print(f"  → {result['severity'].upper()} | {result['chief_complaint']}")
        print(f"  → Action: {result['immediate_action']}")
        print(f"  → Confidence: {result['confidence']}")
        print()
