"""
main.py — AirIQ FastAPI application entry point.

Usage:
    cd backend
    uvicorn main:app --reload --port 8000
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import init_db
from routers import stations, forecast, attribution, advisory


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks before yielding; teardown after."""
    init_db()
    print("✅ AirIQ API started. DB initialised.")
    yield
    print("AirIQ API shutting down.")


app = FastAPI(
    title="AirIQ — Bengaluru Air Quality API",
    version="0.1.0",
    description="Real-time AQ monitoring + XGBoost 24h PM2.5 forecast for Bengaluru.",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow all origins for hackathon MVP
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static files — serves shap_chart.png at /static/shap_chart.png
# ---------------------------------------------------------------------------
ML_DIR = os.path.join(os.path.dirname(__file__), "ml")
if os.path.isdir(ML_DIR):
    app.mount("/static", StaticFiles(directory=ML_DIR), name="static")

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(stations.router,    prefix="/api")
app.include_router(forecast.router,    prefix="/api")
app.include_router(attribution.router, prefix="/api")
app.include_router(advisory.router,    prefix="/api")


# ---------------------------------------------------------------------------
# Root health check
# ---------------------------------------------------------------------------
@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "AirIQ API",
        "version": "0.1.0",
        "docs": "/docs",
    }