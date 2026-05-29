from fastapi import APIRouter
from .endpoints import evidence

router = APIRouter()

router.include_router(
    evidence.router,
    prefix="/v1/evidence",
    tags=["Blockchain Evidence"]
)
