from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter()

class MouseEvent(BaseModel):
    type: str = "mousemove"
    x: int
    y: int
    timestamp: int

class MouseSession(BaseModel):
    session_id: str
    user_id: str
    events: List[MouseEvent]

@router.post("/analyze")
async def analyze_mouse(session: MouseSession):
    mouse_events = [e for e in session.events if e.type == "mousemove"]
    
    if len(mouse_events) < 10:
        return {"session_id": session.session_id, "is_bot": False, "score": 0.1, "verdict": "INSUFFICIENT_DATA"}
    
    # Calculate path linearity
    positions = [(e.x, e.y) for e in mouse_events]
    start, end = positions[0], positions[-1]
    straight = ((end[0]-start[0])**2 + (end[1]-start[1])**2)**0.5
    
    total = 0
    for i in range(1, len(positions)):
        total += ((positions[i][0]-positions[i-1][0])**2 + (positions[i][1]-positions[i-1][1])**2)**0.5
    
    linearity = straight / total if total > 0 else 1
    
    # High linearity = bot-like (perfect straight lines)
    is_bot = linearity > 0.95
    score = 1 - linearity
    
    return {
        "session_id": session.session_id,
        "is_bot": is_bot,
        "anomaly_score": round(score, 4),
        "verdict": "BOT" if is_bot else "HUMAN",
        "confidence": "HIGH" if linearity > 0.98 else "MEDIUM"
    }

@router.get("/health")
async def mouse_health():
    return {"status": "healthy", "service": "mouse-detection"}