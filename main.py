from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as api_router

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

# Include all API routes
app.include_router(api_router)

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Fraud Detection API Running",
        "docs": "/docs",
        "health": "/health"
    }

# Health endpoint
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "fraud-detection-api"
    }
