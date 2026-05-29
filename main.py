from fastapi import FastAPI
from app.api.v1 import router as api_router

app = FastAPI()

app.include_router(api_router)

@app.get("/")
async def root():
    return {"message": "working"}
