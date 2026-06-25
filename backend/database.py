"""
database.py — AirIQ SQLite connection factory + schema + query helpers
All FastAPI routers import from here. No ORM — raw sqlite3 only.
"""
import sqlite3
import os
from contextlib import contextmanager
from typing import Optional

# Path to DB file — relative to this file's location (backend/)
DB_PATH = os.path.join(os.path.dirname(__file__), "airiq.db")


@contextmanager
def get_db():
    """
    Context-managed SQLite connection.
    Usage:
        with get_db() as db:
            rows = db.execute("SELECT * FROM stations").fetchall()
    Returns sqlite3.Row objects (accessible as dicts or by column name).
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safe for concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """
    Create all tables if they don't exist.
    Idempotent — safe to call on every FastAPI startup.
    """
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS stations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    UNIQUE NOT NULL,
                lat         REAL    NOT NULL,
                lon         REAL    NOT NULL,
                zone        TEXT    NOT NULL,
                agency      TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS readings (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                station_name  TEXT    NOT NULL,
                timestamp     TEXT    NOT NULL,
                pm25          REAL,
                pm10          REAL,
                no2           REAL,
                so2           REAL,
                co            REAL,
                bp            REAL,
                FOREIGN KEY (station_name) REFERENCES stations(name)
            );

            CREATE INDEX IF NOT EXISTS idx_readings_station_ts
                ON readings (station_name, timestamp DESC);

            CREATE TABLE IF NOT EXISTS forecasts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                station_name  TEXT    NOT NULL,
                generated_at  TEXT    NOT NULL,
                forecast_json TEXT    NOT NULL,
                FOREIGN KEY (station_name) REFERENCES stations(name)
            );

            CREATE INDEX IF NOT EXISTS idx_forecasts_station
                ON forecasts (station_name, generated_at DESC);
        """)
    print(f"✅ Database initialised at: {DB_PATH}")


# ---------------------------------------------------------------------------
# Query helpers — used by FastAPI routers (Days 6–9)
# ---------------------------------------------------------------------------

def get_all_stations() -> list[dict]:
    """Return all station rows as list of dicts."""
    with get_db() as db:
        rows = db.execute(
            "SELECT id, name, lat, lon, zone, agency FROM stations ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


def get_latest_reading(station_name: str) -> Optional[dict]:
    """
    Return the single most recent reading for a station.
    Used by /api/stations to attach current AQ values.
    """
    with get_db() as db:
        row = db.execute(
            """
            SELECT * FROM readings
            WHERE station_name = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (station_name,),
        ).fetchone()
    return dict(row) if row else None


def get_recent_readings(station_name: str, n: int = 48) -> list[dict]:
    """
    Return last N readings for a station, oldest-first.
    Used by /api/forecast to build lag feature vectors.
    n=48 gives 48 hours — covers pm25_lag_24h + buffer.
    """
    with get_db() as db:
        rows = db.execute(
            """
            SELECT * FROM readings
            WHERE station_name = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (station_name, n),
        ).fetchall()
    # Reverse so oldest first (chronological order for lag calculation)
    return [dict(r) for r in reversed(rows)]


def get_latest_forecast(station_name: str) -> Optional[dict]:
    """Return the most recently generated forecast for a station."""
    with get_db() as db:
        row = db.execute(
            """
            SELECT * FROM forecasts
            WHERE station_name = ?
            ORDER BY generated_at DESC
            LIMIT 1
            """,
            (station_name,),
        ).fetchone()
    return dict(row) if row else None


def upsert_forecast(station_name: str, generated_at: str, forecast_json: str):
    """
    Insert a new forecast row.
    Old forecasts are kept (useful for debugging); only latest is served.
    """
    with get_db() as db:
        db.execute(
            """
            INSERT INTO forecasts (station_name, generated_at, forecast_json)
            VALUES (?, ?, ?)
            """,
            (station_name, generated_at, forecast_json),
        )


def refresh_readings(station_name: str, rows: list[dict]):
    """
    Replace all readings for a station with a fresh batch.
    Called by APScheduler on Day 9 every 15 minutes.
    """
    with get_db() as db:
        db.execute("DELETE FROM readings WHERE station_name = ?", (station_name,))
        db.executemany(
            """
            INSERT INTO readings
                (station_name, timestamp, pm25, pm10, no2, so2, co, bp)
            VALUES
                (:station_name, :timestamp, :pm25, :pm10, :no2, :so2, :co, :bp)
            """,
            rows,
        )


if __name__ == "__main__":
    init_db()