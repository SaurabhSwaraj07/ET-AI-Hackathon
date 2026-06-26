"""
main.py — AirIQ FastAPI application entry point.

Usage:
    cd backend
    uvicorn main:app --reload --port 8000
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler

from database import init_db
from routers import stations, forecast, attribution, advisory
from routers.health import router as health_router
from routers.forecast import _run_forecast_for_station

logger = logging.getLogger("airiq")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ---------------------------------------------------------------------------
# Station list — must match DB. Adjust after confirming /api/stations.
# ---------------------------------------------------------------------------
STATION_NAMES = [
    "Peenya",
    "BTM Layout",
    "Jayanagar",
    "Yeshwanthpur",
    "Silk Board",
    "City Railway Station",
]


def _refresh_all_forecasts() -> None:
    """Background job: regenerate forecasts for all stations."""
    logger.info("⏰ Scheduled forecast refresh started.")
    ok, fail = 0, 0
    for name in STATION_NAMES:
        try:
            values = _run_forecast_for_station(name)
            logger.info("  ✅ %s — %d hours generated (first=%.1f µg/m³)", name, len(values), values[0])
            ok += 1
        except Exception as exc:
            logger.warning("  ⚠️  %s — skipped: %s", name, exc)
            fail += 1
    logger.info("⏰ Refresh complete. OK=%d  FAIL=%d", ok, fail)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, warm forecasts, start scheduler. Teardown: stop scheduler."""
    init_db()
    logger.info("✅ DB initialised.")

    # Warm all forecasts immediately so the first API call is never cold
    _refresh_all_forecasts()

    # Start hourly background scheduler
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        _refresh_all_forecasts,
        trigger="interval",
        hours=1,
        id="forecast_refresh",
        replace_existing=True,
    )
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("✅ APScheduler started — forecast refresh every 1 h.")

    yield

    # Teardown
    scheduler.shutdown(wait=False)
    logger.info("AirIQ API shutting down.")


app = FastAPI(
    title="AirIQ — Bengaluru Air Quality API",
    version="0.2.0",
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
app.include_router(health_router,      prefix="/api")


# ---------------------------------------------------------------------------
# Root health check
# ---------------------------------------------------------------------------
@app.get("/")
def root():
    return {
        "status":  "ok",
        "service": "AirIQ API",
        "version": "0.2.0",
        "docs":    "/docs",
    }