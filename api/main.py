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
    logger.info("CrisisRoute API starting")
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
        import google.genai as genai
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key:
            client = genai.Client(api_key=api_key)
        else:
            project = os.getenv("GOOGLE_CLOUD_PROJECT") or "crisisroute-2026-498212"
            location = os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1"
            client = genai.Client(vertexai=True, project=project, location=location)
        services["gemini"] = "ok"
    except Exception as e:
        services["gemini"] = f"error: {str(e)[:50]}"
    
    all_ok = all(v == "ok" for v in services.values())
    return JSONResponse(
        content={"status": "healthy" if all_ok else "degraded", "services": services},
        status_code=200 if all_ok else 207
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
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dashboard/cases")
async def recent_cases(limit: int = 20):
    """Recent triage cases for admin dashboard."""
    try:
        get_recent_cases, _ = get_notify_agent()
        cases = get_recent_cases(limit=limit)
        return {"cases": cases, "total": len(cases)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        es = Elasticsearch(os.getenv("ELASTIC_ENDPOINT"), api_key=os.getenv("ELASTIC_API_KEY"))
        es.update(
            index="triage_cases",
            id=feedback.case_id,
            body={"doc": {"outcome_status": feedback.outcome, "feedback_notes": feedback.notes}}
        )
        return {"success": True, "case_id": feedback.case_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
