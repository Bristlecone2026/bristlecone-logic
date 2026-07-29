from fastapi import FastAPI
from app.api.v1 import dag, admin

app = FastAPI(title="Bristlecone v2.0 API")

app.include_router(dag.router, prefix="/api/v1")
app.include_router(admin.router)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
