from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

router = APIRouter()

class AlertCreate(BaseModel):
    symbol: str
    alert_type: str
    severity: int
    description: str

alerts_db = []

@router.post("/create")
async def create_alert(alert: AlertCreate):
    new_alert = {
        "id": len(alerts_db) + 1,
        "symbol": alert.symbol,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "description": alert.description,
        "is_investigated": False,
        "created_at": datetime.now().isoformat()
    }
    alerts_db.append(new_alert)
    return new_alert

@router.get("/list")
async def list_alerts(limit: int = 20):
    return {"alerts": alerts_db[-limit:], "total": len(alerts_db)}

@router.put("/resolve/{alert_id}")
async def resolve_alert(alert_id: int):
    for alert in alerts_db:
        if alert["id"] == alert_id:
            alert["is_investigated"] = True
            return {"success": True, "alert": alert}
    return {"success": False, "error": "Alert not found"}

@router.get("/health")
async def alerts_health():
    return {"status": "healthy", "service": "alerts"}