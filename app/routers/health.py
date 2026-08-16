import logging
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

logger = logging.getLogger("api.health")
router = APIRouter(prefix="/api/v1", tags=["Health"])

@router.get("/health")
async def health_check(request: Request):
    checks = {"redis": False, "postgres": False}
    
    # 1. Check Redis
    try:
        redis_conn = request.app.state.redis
        await redis_conn.ping()
        checks["redis"] = True
    except Exception as e:
        logger.error(f"Healthcheck Redis failure: {e}")

    # 2. Check Postgres
    try:
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            checks["postgres"] = True
    except Exception as e:
        logger.error(f"Healthcheck Postgres failure: {e}")

    all_healthy = all(checks.values())
    status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={"status": "healthy" if all_healthy else "degraded", "checks": checks}
    )
