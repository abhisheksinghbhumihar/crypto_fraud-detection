import sys
import os

# Add the fraud_detection_api directory to the sys.path so that we can import the 'app' package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import router as api_router
from app.core.config import settings

app = FastAPI(
    title="Fraud Detection API",
    description="Real-time fraud detection with blockchain evidence",
    version="2.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(api_router)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "fraud-detection"}

@app.get("/")
async def root():
    return {
        "message": "Fraud Detection API v2.0",
        "endpoints": {
            "POST /v1/fraud/predict": "Predict fraud",
            "POST /v1/evidence/anchor": "Store evidence on blockchain",
            "GET /v1/evidence/verify/{hash}": "Verify evidence",
            "GET /docs": "Swagger documentation"
        }
    }