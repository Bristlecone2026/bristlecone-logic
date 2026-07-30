from fastapi import APIRouter
from app.api.v1.endpoints import agent, billing, keys

api_router = APIRouter()
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])
api_router.include_router(keys.router, prefix="/keys", tags=["keys"])
