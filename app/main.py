from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.core.config import get_cors_headers, get_cors_methods, get_cors_origins, settings


app = FastAPI(
    title=settings.api_title,
    description="Real-time fraud detection with behavioral analysis, alerts, payment checks, and blockchain evidence.",
    version=settings.api_version,
    openapi_tags=[
        {"name": "default", "description": "Root and service health"},
        {"name": "Statistics", "description": "Dashboard statistics and daily metrics"},
        {"name": "Fraud Detection", "description": "Single and batch fraud prediction"},
        {"name": "Keystroke Bot", "description": "Keystroke behavior analysis"},
        {"name": "Mouse Bot", "description": "Mouse movement behavior analysis"},
        {"name": "Alerts", "description": "Fraud alert creation, listing, and resolution"},
        {"name": "Payment Gateway", "description": "Checkout and payment risk screening"},
        {"name": "Blockchain Evidence", "description": "Evidence anchoring and verification"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=settings.cors_credentials,
    allow_methods=get_cors_methods(),
    allow_headers=get_cors_headers(),
)

@app.get("/", tags=["default"])
async def root():
    return {
        "message": "Fraud Detection API",
        "version": settings.api_version,
        "sequence": [
            "GET /health",
            "GET /v1/health",
            "GET /v1/stats/health",
            "GET /v1/stats/overview",
            "GET /v1/stats/daily",
            "POST /v1/fraud/predict",
            "POST /v1/fraud/predict_batch",
            "GET /v1/fraud/transaction/{transaction_id}",
            "GET /v1/fraud/health",
            "POST /v1/keystroke/analyze",
            "GET /v1/keystroke/health",
            "POST /v1/mouse/analyze",
            "GET /v1/mouse/health",
            "POST /v1/alerts/create",
            "GET /v1/alerts/list",
            "PUT /v1/alerts/resolve/{alert_id}",
            "GET /v1/alerts/health",
            "GET /v1/payment/",
            "POST /v1/payment/process",
            "GET /v1/payment/health",
            "POST /v1/evidence/anchor",
            "GET /v1/evidence/verify/{evidence_hash}",
        ],
        "docs": "/docs",
    }


@app.get("/health", tags=["default"])
async def health():
    return {"status": "healthy", "service": "fraud-detection-api"}


# Primary API namespace, registered after default routes for clean docs ordering.
app.include_router(v1_router, prefix="/v1")
