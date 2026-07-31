from fastapi import APIRouter
from app.api.v1.endpoints import agent, auth, billing, keys, logs, organizations, projects, users

api_router = APIRouter()
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])
api_router.include_router(keys.router, prefix="/keys", tags=["keys"])
api_router.include_router(logs.router, tags=["logs"])
api_router.include_router(organizations.router, tags=["organizations"])
api_router.include_router(projects.router, tags=["projects"])
api_router.include_router(users.router, tags=["users"])
