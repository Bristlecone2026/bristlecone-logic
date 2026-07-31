from fastapi import APIRouter
from app.api.v1.endpoints import keys, billing

api_router = APIRouter()
api_router.include_router(keys.router, prefix="/keys", tags=["Keys"])
api_router.include_router(billing.router, prefix="/billing", tags=["Billing"])
