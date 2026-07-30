from fastapi import FastAPI
from app.api.v1.router import api_router
from app.api.v1 import admin

app = FastAPI(title="Bristlecone v2.0 API")

app.include_router(api_router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
