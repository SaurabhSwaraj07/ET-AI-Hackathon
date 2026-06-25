"""
health.py — GET /api/health
Returns DB row counts and service uptime for monitoring.
"""
import time
import sqlite3
import os
from fastapi import APIRouter

router = APIRouter(tags=["health"])

_start_time = time.time()

# Resolve DB path the same way database.py does
_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "airiq.db")


def _query_counts() -> dict:
    try:
        conn = sqlite3.connect(_DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM readings")
        readings_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM forecasts")
        forecasts_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT station_name) FROM readings")
        stations_active = cursor.fetchone()[0]

        conn.close()
        return {
            "readings_count":  readings_count,
            "forecasts_count": forecasts_count,
            "stations_active": stations_active,
            "db_error":        None,
        }
    except Exception as exc:
        return {
            "readings_count":  None,
            "forecasts_count": None,
            "stations_active": None,
            "db_error":        str(exc),
        }


@router.get("/health")
def get_health():
    """
    Return service health: uptime + DB row counts.
    Useful for demo monitoring and verifying the scheduler ran.
    """
    counts = _query_counts()
    uptime = round(time.time() - _start_time, 1)

    return {
        "status":          "ok" if counts["db_error"] is None else "degraded",
        "uptime_seconds":  uptime,
        "version":         "0.2.0",
        **counts,
    }