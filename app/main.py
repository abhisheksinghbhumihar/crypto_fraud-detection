cd C:\Users\anjal\OneDrive\Desktop\pubmed datttaaaa\crypto_fraud-detection

@'
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import router as api_router

app = FastAPI(
    title="Fraud Detection API",
    description="Real-time fraud detection with blockchain evidence",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
'@ | Out-File -FilePath app/main.py -Encoding utf8
