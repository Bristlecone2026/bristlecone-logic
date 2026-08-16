from fastapi import APIRouter
from app.api.v1.endpoints import keys, billing, tools

api_router = APIRouter()
api_router.include_router(keys.router, prefix="/keys", tags=["Keys"])
api_router.include_router(billing.router, prefix="/billing", tags=["Billing"])
api_router.include_router(tools.router, prefix="/tools", tags=["Microservice Tools"])
