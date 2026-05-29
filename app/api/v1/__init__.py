from fastapi import APIRouter
from .endpoints import fraud

router = APIRouter()

router.include_router(
    fraud.router,
    prefix="/fraud",
    tags=["Fraud Detection"]
)
