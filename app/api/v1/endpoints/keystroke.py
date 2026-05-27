from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

class KeystrokeEvent(BaseModel):
    key_down: int
    key_up: int
    timestamp_ms: int
    is_paste: Optional[bool] = False

class KeystrokeSession(BaseModel):
    session_id: str
    user_id: str
    events: List[KeystrokeEvent]

@router.post("/analyze")
async def analyze_keystrokes(session: KeystrokeSession):
    # Simple bot detection based on keystroke timing
    if len(session.events) < 5:
        return {"session_id": session.session_id, "is_bot": False, "score": 0.1, "verdict": "INSUFFICIENT_DATA"}
    
    dwell_times = [e.key_up - e.key_down for e in session.events]
    
    # Calculate variance manually
    if len(dwell_times) > 0:
        mean = sum(dwell_times) / len(dwell_times)
        variance = sum((x - mean) ** 2 for x in dwell_times) / len(dwell_times)
    else:
        variance = 0
    
    # Low variance = bot-like (too consistent)
    is_bot = variance < 50
    score = min(0.9, 100 / (variance + 10)) if variance > 0 else 0.9
    
    return {
        "session_id": session.session_id,
        "is_bot": is_bot,
        "anomaly_score": round(score, 4),
        "verdict": "BOT" if is_bot else "HUMAN",
        "confidence": "HIGH" if variance < 30 else "MEDIUM"
    }

@router.get("/health")
async def keystroke_health():
    return {"status": "healthy", "service": "keystroke-detection"}