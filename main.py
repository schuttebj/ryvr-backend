from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
import uvicorn

from database import engine, Base
from routers import auth, clients, integrations, workflows, analytics, seo, ai, data_processing
from config import settings

# Create database tables
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
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

# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["authentication"])
app.include_router(clients.router, prefix="/api/v1/clients", tags=["clients"])
app.include_router(integrations.router, prefix="/api/v1/integrations", tags=["integrations"])
app.include_router(workflows.router, prefix="/api/v1/workflows", tags=["workflows"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(seo.router, prefix="/api/v1/seo", tags=["seo"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["ai"])
app.include_router(data_processing.router, prefix="/api/v1/data", tags=["data_processing"])

@app.get("/")
async def root():
    return {"message": "RYVR API - Streamlining marketing automation flows", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ryvr-api"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 