# api/index.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Create a new app instance (not importing from main.py)
app = FastAPI(title="Fraud Detection API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Fraud Detection API v2.0", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/predict")
async def predict(amount: float, user_id: str, merchant_id: str):
    risk_score = min(amount / 1200.0, 0.99)
    is_fraud = risk_score > 0.8
    return {
        "risk_score": round(risk_score, 4),
        "is_fraud": is_fraud,
        "decision": "BLOCK" if is_fraud else "APPROVE"
    }

# Vercel handler
handler = app
