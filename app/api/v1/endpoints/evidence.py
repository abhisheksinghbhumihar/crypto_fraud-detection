from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.services.evidence_service import EvidenceService

router = APIRouter(tags=["Blockchain Evidence"])

evidence_service = EvidenceService()


class AnchorRequest(BaseModel):
    transaction_id: str
    amount: float
    merchant: Optional[str] = None
    merchant_id: Optional[str] = None
    user_id: str
    risk_score: float
    decision: str


class AnchorResponse(BaseModel):
    success: bool
    evidence_hash: str
    cid: str
    blockchain_tx: str
    timestamp: str
    verification_url: str


class VerifyResponse(BaseModel):
    exists: bool
    verified: bool
    evidence: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


@router.post("/anchor", response_model=AnchorResponse)
async def anchor_evidence(request: AnchorRequest):

    try:
        merchant = request.merchant or request.merchant_id or "Unknown"

        transaction_data = {
            "transaction_id": request.transaction_id,
            "amount": request.amount,
            "merchant_id": merchant,
            "user_id": request.user_id
        }

        result = await evidence_service.anchor_evidence(
            transaction_data=transaction_data,
            risk_score=request.risk_score,
            decision=request.decision
        )

        return AnchorResponse(**result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/verify/{evidence_hash}", response_model=VerifyResponse)
async def verify_evidence(evidence_hash: str):

    result = evidence_service.verify_evidence(evidence_hash)

    return VerifyResponse(**result)
