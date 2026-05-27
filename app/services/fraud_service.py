# fraud_detection_api/app/services/fraud_service.py
import hashlib
import json
import os
import time
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

# ============================================================
# REQUEST/RESPONSE MODELS
# ============================================================
class TransactionRequest(BaseModel):
    amount: float
    user_id: str
    merchant_id: str
    transaction_id: Optional[str] = None

class FraudResponse(BaseModel):
    risk_score: float
    is_fraud: bool
    decision: str
    blockchain_tx: Optional[str] = None
    evidence_cid: Optional[str] = None
    evidence_hash: Optional[str] = None
    verified: bool = False

# ============================================================
# EVIDENCE MANAGER
# ============================================================
class EvidenceManager:
    def __init__(self):
        self.evidence_dir = "evidence_store"
        os.makedirs(self.evidence_dir, exist_ok=True)
        print(f"[OK] Evidence Manager ready (storage: {self.evidence_dir}/)")
    
    def _hash_evidence(self, data: dict) -> str:
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    
    def store_evidence(self, transaction: dict, risk_score: float, decision: str) -> dict:
        evidence = {
            "transaction_id": transaction.get("transaction_id", "unknown"),
            "amount": transaction["amount"],
            "merchant": transaction["merchant_id"],
            "user_id": transaction["user_id"],
            "risk_score": int(risk_score * 100),
            "decision": decision,
            "timestamp": datetime.now().isoformat()
        }
        
        evidence_hash = self._hash_evidence(evidence)
        
        # Save to local file
        with open(f"{self.evidence_dir}/{evidence_hash}.json", "w") as f:
            json.dump(evidence, f, indent=2)
        
        return {
            "stored": True,
            "cid": evidence_hash[:20],
            "hash": evidence_hash,
            "tx": f"local_{evidence_hash[:10]}",
            "verified": True
        }
    
    def verify_evidence(self, evidence_hash: str) -> dict:
        file_path = f"{self.evidence_dir}/{evidence_hash}.json"
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                return {"exists": True, "evidence": json.load(f)}
        return {"exists": False}

# ============================================================
# FRAUD DETECTOR
# ============================================================
class FraudDetector:
    def __init__(self):
        self.model_loaded = False
        self.evidence_mgr = EvidenceManager()
    
    def load_models(self):
        """Load ML model (placeholder for now)"""
        self.model_loaded = True
    
    def is_ready(self) -> bool:
        return self.model_loaded
    
    def detect_fraud(self, amount: float) -> dict:
        """Simple fraud detection based on amount"""
        risk_score = min(amount / 1200.0, 0.99)
        is_fraud = risk_score > 0.8
        return {
            "risk_score": round(risk_score, 4),
            "is_fraud": is_fraud,
            "decision": "BLOCK" if is_fraud else "APPROVE"
        }

# Global instance
fraud_detector = FraudDetector()