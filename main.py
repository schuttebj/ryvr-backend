from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
import uvicorn

from database import engine, Base
from routers import auth, clients, integrations, workflows, analytics, seo, ai, data_processing, businesses, admin, simple_api, flows, files, embeddings
from config import settings

# DEPLOYMENT MARKER: 2025-10-03 - Fixed SQL parameter binding in embeddings v2.0.0

# Create database tables
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # Install pgvector extension before creating tables
    try:
        from sqlalchemy import text
        with engine.connect() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            connection.commit()
    except Exception as e:
        # Extension may already exist or user doesn't have permissions
        # If it fails, tables with vector columns will fail to create
        print(f"Note: Could not install pgvector extension: {e}")
    
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown
    pass

app = FastAPI(
    title="RYVR API",
    description="AI-powered marketing automation platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend
# Temporary permissive CORS for testing - TODO: Make more restrictive
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins temporarily
    allow_credentials=False,  # Must be False when allow_origins=["*"]
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include routers (preserve existing + add new multi-tenant)
app.include_router(auth.router, prefix="/api/v1/auth", tags=["authentication"])
app.include_router(clients.router)  # Legacy client router (kept for backward compatibility)
app.include_router(integrations.router, prefix="/api/v1/integrations", tags=["integrations"])
app.include_router(workflows.router, prefix="/api/v1/workflows", tags=["workflows"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(seo.router, prefix="/api/v1/seo", tags=["seo"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["ai"])
app.include_router(data_processing.router, prefix="/api/v1/data", tags=["data_processing"])

# New multi-tenant routers
# app.include_router(agencies.router, tags=["agencies"])  # Removed in simplified structure
app.include_router(businesses.router, tags=["businesses"])
app.include_router(admin.router, tags=["admin"])
app.include_router(flows.router, prefix="/api/v1", tags=["flows"])

# Simple API router (legacy support)
app.include_router(simple_api.router, tags=["simple"])

# File management router
app.include_router(files.router, tags=["files"])

# Vector embeddings & semantic search router
app.include_router(embeddings.router, tags=["embeddings"])

@app.get("/")
async def root():
    return {"message": "RYVR API - Streamlining marketing automation flows", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ryvr-api"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 