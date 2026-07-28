from fastapi import APIRouter
from app.api.v1.endpoints import health, logs, auth, organizations, projects, users, agent
from app.api.v1 import dag

router = APIRouter()
router.include_router(health.router)
router.include_router(logs.router)
router.include_router(auth.router)
router.include_router(organizations.router)
router.include_router(projects.router)
router.include_router(users.router)
router.include_router(agent.router)
router.include_router(dag.router)

api_router = router
