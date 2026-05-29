from fastapi import APIRouter

from .endpoints import (
    fraud,
    keystroke,
    mouse,
    stats,
    alerts,
    payment,
    evidence
)

router = APIRouter()

router.include_router(fraud.router, prefix="/fraud", tags=["Fraud Detection"])
router.include_router(keystroke.router, prefix="/keystroke", tags=["Keystroke Bot"])
router.include_router(mouse.router, prefix="/mouse", tags=["Mouse Bot"])
router.include_router(stats.router, prefix="/stats", tags=["Statistics"])
router.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
router.include_router(payment.router, prefix="/payment", tags=["Payment Gateway"])
router.include_router(evidence.router, prefix="/evidence", tags=["Blockchain Evidence"])
