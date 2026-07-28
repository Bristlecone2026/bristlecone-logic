from fastapi import APIRouter
from app.api.v1.endpoints import health, logs, auth, organizations, projects, users, agent
from app.api.v1 import dag

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(logs.router)
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(projects.router)
api_router.include_router(users.router)
api_router.include_router(agent.router)
api_router.include_router(dag.router)
