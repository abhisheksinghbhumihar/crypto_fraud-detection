from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import hashlib
import json
import os
import time
from datetime import datetime

router = APIRouter()

# ============================================================
# REQUEST MODELS
# ============================================================
class TransactionRequest(BaseModel):
    amount: float
    user_id: str
    merchant_id: str
    transaction_id: Optional[str] = None

class BatchTransactionRequest(BaseModel):
    transactions: List[TransactionRequest]

class FraudResponse(BaseModel):
    risk_score: float
    is_fraud: bool
    decision: str
    blockchain_tx: Optional[str] = None
    evidence_cid: Optional[str] = None
    evidence_hash: Optional[str] = None
    verified: bool = False

# ============================================================
# EVIDENCE STORAGE
# ============================================================
EVIDENCE_DIR = "evidence_store"
os.makedirs(EVIDENCE_DIR, exist_ok=True)

def detect_fraud(amount: float) -> dict:
    risk_score = min(amount / 1200.0, 0.99)
    is_fraud = risk_score > 0.8
    return {
        "risk_score": round(risk_score, 4),
        "is_fraud": is_fraud,
        "decision": "BLOCK" if is_fraud else "APPROVE"
    }

# ============================================================
# FRAUD ENDPOINTS
# ============================================================

@router.post("/predict", response_model=FraudResponse)
async def predict_fraud(tx: TransactionRequest):
    """Predict fraud for a single transaction"""
    if not tx.transaction_id:
        tx.transaction_id = f"TXN_{int(time.time())}"
    
    fraud_result = detect_fraud(tx.amount)
    
    response = FraudResponse(**fraud_result)
    
    if fraud_result["is_fraud"]:
        evidence = {
            "transaction_id": tx.transaction_id,
            "amount": tx.amount,
            "merchant": tx.merchant_id,
            "user_id": tx.user_id,
            "risk_score": int(fraud_result["risk_score"] * 100),
            "decision": fraud_result["decision"],
            "timestamp": datetime.now().isoformat()
        }
        evidence_hash = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
        
        with open(f"{EVIDENCE_DIR}/{evidence_hash}.json", "w") as f:
            json.dump(evidence, f, indent=2)
        
        response.blockchain_tx = f"local_{evidence_hash[:10]}"
        response.evidence_cid = evidence_hash[:20]
        response.evidence_hash = evidence_hash
        response.verified = True
    
    return response

@router.post("/predict_batch")
async def predict_batch(batch: BatchTransactionRequest):
    """Predict fraud for multiple transactions"""
    results = []
    for tx in batch.transactions:
        risk = min(tx.amount / 1200.0, 0.99)
        results.append({
            "amount": tx.amount,
            "risk_score": round(risk, 4),
            "is_fraud": risk > 0.8,
            "user_id": tx.user_id,
            "merchant_id": tx.merchant_id
        })
    return {"total": len(results), "results": results}

@router.get("/transaction/{transaction_id}")
async def get_transaction(transaction_id: str):
    """Get transaction by ID from evidence store"""
    for file in os.listdir(EVIDENCE_DIR):
        if file.endswith(".json"):
            with open(f"{EVIDENCE_DIR}/{file}", "r") as f:
                evidence = json.load(f)
                if evidence.get("transaction_id") == transaction_id:
                    return evidence
    raise HTTPException(status_code=404, detail="Transaction not found")

@router.get("/health")
async def fraud_health():
    """Fraud detection health check"""
    return {"status": "healthy", "service": "fraud-detection"}