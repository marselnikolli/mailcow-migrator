from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from contextlib import asynccontextmanager

# Import routers
from app.routes import auth, jobs, domains, logs
from app.config import settings

# Database initialization
from app.db import init_db, migrate_schema, backfill_encrypted_secrets
from app.core.metrics import render_metrics

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    migrate_schema()
    backfill_encrypted_secrets()
    yield
    # Shutdown
    pass

app = FastAPI(title="mailcow-migrator", lifespan=lifespan)

# Add CORS middleware - explicit origin allowlist (see CORS_ORIGINS env var)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tenant scoping is derived exclusively from the verified JWT (see
# app/deps/roles.py:get_current_user), never from client-supplied headers.

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Prometheus metrics endpoint (exposition text format)
@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    return render_metrics()

# Register routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(domains.router, prefix="/api/v1/domains", tags=["domains"])
app.include_router(logs.router, prefix="/api/v1/logs", tags=["logs"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
