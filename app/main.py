import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database import engine, Base
from app.api.v1.router import api_router

# Configure structured logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bristlecone.api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(
    title="Bristlecone Logic API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None
)

# Restrict CORS to internal proxy and UI network
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Internal Nginx handles external SSL/boundary
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Security Header Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

# Standardized Global Error Envelope
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Please contact system support.",
                "path": request.url.path
            }
        }
    )

app.include_router(api_router, prefix="/api/v1")

@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "service": "bristlecone-api"}

@app.get("/", tags=["system"])
async def root():
    return {
        "system": "Bristlecone Logic API",
        "status": "online",
        "version": "1.0.0",
        "endpoints": ["/health", "/docs"]
    }
