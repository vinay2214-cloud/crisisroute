import os, json, logging, uuid, time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Structured JSON logger
class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "time": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module
        })

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(handlers=[handler], level=logging.INFO, force=True)
logger = logging.getLogger("crisisroute")

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    from dotenv import load_dotenv
    load_dotenv()
    endpoint = os.getenv("ELASTIC_ENDPOINT")
    api_key_exists = bool(os.getenv("ELASTIC_API_KEY"))
    logger.info("CrisisRoute API starting")
    logger.info(f"Resolved Elasticsearch Endpoint: {endpoint or 'None'}")
    logger.info(f"Elasticsearch API Key configured: {api_key_exists}")
    
    # Startup Environment Checks
    gcp_project = os.getenv("GOOGLE_CLOUD_PROJECT")
    gcp_location = os.getenv("GOOGLE_CLOUD_LOCATION")
    gemini_key_exists = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    
    adc_detected = False
    adc_error = None
    try:
        import google.auth
        credentials, project_id = google.auth.default()
        adc_detected = True
    except Exception as e:
        adc_error = str(e)
        
    logger.info(f"GOOGLE_CLOUD_PROJECT: {gcp_project or 'None'}")
    logger.info(f"GOOGLE_CLOUD_LOCATION: {gcp_location or 'None'}")
    logger.info(f"GEMINI_API_KEY exists: {gemini_key_exists}")
    logger.info(f"ADC credentials detected: {adc_detected}" + (f" (Error: {adc_error})" if not adc_detected else ""))
    
    logger.info("Dashboard Query target indices: hospitals, triage_cases")
    yield
    logger.info("CrisisRoute API shutting down")

app = FastAPI(
    title="CrisisRoute API",
    description="Emergency Healthcare Navigation — Powered by Gemini + Elasticsearch",
    version="1.0.0",
    lifespan=lifespan
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start = time.time()
    response = await call_next(request)
    duration = int((time.time() - start) * 1000)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{duration}ms"
    return response

# Models
class TriageRequest(BaseModel):
    symptoms: str = Field(..., min_length=5, max_length=1000)
    age: int = Field(default=35, ge=0, le=120)
    name: str = Field(default="Patient", max_length=100)
    lat: float = Field(default=16.5062, ge=8.0, le=37.0)
    lng: float = Field(default=80.6480, ge=68.0, le=97.0)

class FeedbackRequest(BaseModel):
    case_id: str
    outcome: str  # "arrived", "redirected", "cancelled"
    notes: str = ""

# Import agents (lazy import to avoid startup failures)
def get_orchestrator():
    from agents.orchestrator import run_crisisroute
    return run_crisisroute

def get_notify_agent():
    from agents.notify_agent import get_recent_cases, get_case
    return get_recent_cases, get_case

def get_capacity_agent():
    from agents.capacity_agent import get_system_stats
    return get_system_stats

# Endpoints

@app.get("/")
async def root():
    return {"service": "CrisisRoute", "status": "operational", "version": "1.0.0",
            "disclaimer": "Navigation aid only. Always call 108 for emergencies."}

@app.get("/health")
async def health():
    services = {"api": "ok"}
    # Test Elasticsearch
    try:
        from elasticsearch import Elasticsearch
        from dotenv import load_dotenv
        load_dotenv()
        es = Elasticsearch(os.getenv("ELASTIC_ENDPOINT"), api_key=os.getenv("ELASTIC_API_KEY"))
        info = es.info()
        services["elasticsearch"] = "ok"
    except Exception as e:
        services["elasticsearch"] = f"error: {str(e)[:50]}"
    # Test Gemini
    try:
        from agents.vertex_client import get_vertex_client
        client = get_vertex_client()
        services["gemini"] = "ok"
    except Exception as e:
        services["gemini"] = f"error: {str(e)[:50]}"
    
    all_ok = all(v == "ok" for v in services.values())
    return JSONResponse(
        content={"status": "healthy" if all_ok else "degraded", "services": services},
        status_code=200 if all_ok else 207
    )

@app.get("/debug/gemini")
async def debug_gemini():
    """Diagnostic endpoint to perform a single Gemini call and return details."""
    try:
        from agents.vertex_client import get_vertex_client
        import time
        
        start_time = time.time()
        client = get_vertex_client()
            
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Say hello"
        )
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Log details
        logger.info(
            f"Gemini Debug Call: SUCCESS | Model: gemini-2.5-flash | "
            f"Auth Mode: vertex_ai | Duration: {duration_ms}ms"
        )
        
        return {
            "success": True,
            "model": "gemini-2.5-flash",
            "response": response.text.strip(),
            "auth_mode": "vertex_ai"
        }
    except Exception as e:
        logger.error(
            f"Gemini Debug Call: FAILURE | Model: gemini-2.5-flash | "
            f"Error Type: {type(e).__name__} | Error Message: {str(e)}"
        )
        return JSONResponse(
            content={
                "success": False,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "auth_mode": "vertex_ai"
            },
            status_code=500
        )

@app.post("/api/triage")
@limiter.limit("20/minute")
async def triage_stream(request: Request, body: TriageRequest):
    """Stream the 7-agent CrisisRoute pipeline as Server-Sent Events."""
    run_crisisroute = get_orchestrator()
    
    logger.info(f"Triage request: age={body.age}, symptoms_len={len(body.symptoms)}")
    
    def generate():
        try:
            for step in run_crisisroute(
                symptoms=body.symptoms,
                age=body.age,
                patient_name=body.name,
                patient_lat=body.lat,
                patient_lng=body.lng
            ):
                yield f"data: {json.dumps(step)}\n\n"
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            error_event = {
                "step": "error", "agent": "Orchestrator",
                "status": "error",
                "data": {"error": "Pipeline failed. Please call 108."},
                "elapsed_ms": 0
            }
            yield f"data: {json.dumps(error_event)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"}
    )

@app.get("/api/dashboard/stats")
async def dashboard_stats():
    """System-wide capacity stats for admin dashboard."""
    try:
        get_system_stats = get_capacity_agent()
        stats = get_system_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {e}")
        return {
            "total_hospitals": 0,
            "total_beds": 0,
            "available_beds": 0,
            "available_icu": 0,
            "occupancy_rate": 1.0,
            "status_breakdown": {"available": 0, "limited": 0, "full": 0},
            "by_district": []
        }

@app.get("/api/dashboard/cases")
async def recent_cases(limit: int = 20):
    """Recent triage cases for admin dashboard."""
    try:
        get_recent_cases, _ = get_notify_agent()
        cases = get_recent_cases(limit=limit)
        return {"cases": cases, "total": len(cases)}
    except Exception as e:
        logger.error(f"Error getting recent cases: {e}")
        return {"cases": [], "total": 0}

@app.get("/api/case/{case_id}")
async def get_case_status(case_id: str):
    """Get status of a specific case."""
    try:
        _, get_case = get_notify_agent()
        case = get_case(case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        return case
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/feedback")
async def submit_feedback(feedback: FeedbackRequest):
    """Record outcome feedback for a case (improves future routing)."""
    try:
        from elasticsearch import Elasticsearch
        from dotenv import load_dotenv
        load_dotenv()
        endpoint = os.getenv("ELASTIC_ENDPOINT")
        if not endpoint:
            return {"success": False, "error": "Elasticsearch endpoint not configured"}
        es = Elasticsearch(endpoint, api_key=os.getenv("ELASTIC_API_KEY"))
        es.update(
            index="triage_cases",
            id=feedback.case_id,
            body={"doc": {"outcome_status": feedback.outcome, "feedback_notes": feedback.notes}}
        )
        return {"success": True, "case_id": feedback.case_id}
    except Exception as e:
        logger.error(f"Error in submit_feedback: {e}")
        return {"success": False, "error": str(e)}
