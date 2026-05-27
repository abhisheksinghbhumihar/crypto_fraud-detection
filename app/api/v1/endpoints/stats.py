from fastapi import APIRouter
from datetime import datetime, timedelta

router = APIRouter()

@router.get("/overview")
async def stats_overview():
    return {
        "total_predictions": 0,
        "fraud_count": 0,
        "approve_count": 0,
        "block_count": 0,
        "avg_response_time_ms": 45.2,
        "timestamp": datetime.now().isoformat()
    }

@router.get("/daily")
async def daily_stats():
    return {
        "date": datetime.now().date().isoformat(),
        "predictions": 0,
        "frauds": 0,
        "fraud_rate": 0
    }

@router.get("/health")
async def stats_health():
    return {"status": "healthy", "service": "statistics"}