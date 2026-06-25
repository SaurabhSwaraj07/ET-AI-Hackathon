"""
db_seed.py — Seed airiq.db with station metadata + last 48h of AQ readings.
Run once after Day 5 setup, and re-run any time you want fresh data.

Usage:
    cd backend
    python db_seed.py
"""
import os
import glob
import json
import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from database import init_db, get_db, DB_PATH

# ---------------------------------------------------------------------------
# Station metadata — 7 confirmed stations from feature matrix
# Hebbal excluded (dropped during AQ + ERA5 merge in Day 3)
# Coordinates from master plan (confirmed Bengaluru locations)
# ---------------------------------------------------------------------------
STATION_MAP = {
    "BTM Layout": {
        "csv_fragment": "site_162_BTM_Layout",
        "lat": 12.9166, "lon": 77.6101,
        "zone": "residential_traffic", "agency": "CPCB",
    },
    "Peenya": {
        "csv_fragment": "site_163_Peenya",
        "lat": 13.0297, "lon": 77.5182,
        "zone": "industrial", "agency": "CPCB",
    },
    "Hombegowda Nagar": {
        "csv_fragment": "site_1555_Hombegowda_Nagar",
        "lat": 12.9343, "lon": 77.5971,
        "zone": "residential", "agency": "KSPCB",
    },
    "Jayanagar 5th Block": {
        "csv_fragment": "site_1556_Jayanagar_5th_Block",
        "lat": 12.9308, "lon": 77.5834,
        "zone": "residential", "agency": "KSPCB",
    },
    "Silk Board": {
        "csv_fragment": "site_1558_Silk_Board",
        "lat": 12.9174, "lon": 77.6228,
        "zone": "traffic_corridor", "agency": "KSPCB",
    },
    "Kasturi Nagar": {
        "csv_fragment": "site_5681_Kasturi_Nagar",
        "lat": 13.0218, "lon": 77.6560,
        "zone": "residential", "agency": "KSPCB",
    },
    "Jigani": {
        "csv_fragment": "site_5729_Jigani",
        "lat": 12.7985, "lon": 77.6396,
        "zone": "industrial", "agency": "KSPCB",
    },
}

# Number of hourly readings to seed per station
# 48 = 2 days of history, covers pm25_lag_24h + buffer for rolling features
READINGS_PER_STATION = 48

# Where to find raw CSVs — relative to this file (backend/)
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


# ---------------------------------------------------------------------------
# Column name mapping — raw CSV column names → our DB column names
# Some CSVs use slightly different spellings; we try all variants.
# ---------------------------------------------------------------------------
PM25_VARIANTS  = ["PM2.5 (µg/m³)", "PM2.5(µg/m³)", "PM2.5 (ug/m3)", "PM2.5"]
PM10_VARIANTS  = ["PM10 (µg/m³)",  "PM10(µg/m³)",  "PM10 (ug/m3)",  "PM10"]
NO2_VARIANTS   = ["NO2 (µg/m³)",   "NO2(µg/m³)",   "NO2 (ug/m3)",   "NO2"]
SO2_VARIANTS   = ["SO2 (µg/m³)",   "SO2(µg/m³)",   "SO2 (ug/m3)",   "SO2"]
CO_VARIANTS    = ["CO (mg/m³)",    "CO(mg/m³)",    "CO (mg/m3)",    "CO"]
BP_VARIANTS    = ["BP (mmHg)",     "BP(mmHg)",     "BP"]
TS_VARIANTS    = ["Timestamp", "Date Time", "DateTime", "Time", "date_time"]


def _find_col(df: pd.DataFrame, variants: list[str]) -> str | None:
    """Return the first column name from variants that exists in df."""
    for v in variants:
        if v in df.columns:
            return v
    return None


def _safe_float(val) -> float | None:
    """Convert to float, return None on error or negative sentinel values."""
    try:
        f = float(val)
        # Many AQ datasets use -999 or 0 as missing sentinels
        return None if (f < 0 or f > 9999) else f
    except (TypeError, ValueError):
        return None


def find_csv(csv_fragment: str) -> str | None:
    """Glob-search DATA_DIR for a CSV matching the station fragment."""
    pattern = os.path.join(DATA_DIR, f"*{csv_fragment}*.csv")
    matches = glob.glob(pattern)
    if not matches:
        # Also try the raw/ subdirectory
        pattern2 = os.path.join(DATA_DIR, "raw", f"*{csv_fragment}*.csv")
        matches = glob.glob(pattern2)
    return matches[0] if matches else None


def read_station_readings(station_name: str, meta: dict) -> list[dict]:
    """
    Read last READINGS_PER_STATION rows from the station's CSV.
    Returns a list of dicts ready for INSERT into readings table.
    """
    csv_path = find_csv(meta["csv_fragment"])
    if not csv_path:
        print(f"  ⚠️  CSV not found for {station_name} (fragment: {meta['csv_fragment']})")
        return []

    df = pd.read_csv(csv_path, low_memory=False)

    # Find timestamp column
    ts_col = _find_col(df, TS_VARIANTS)
    if ts_col is None:
        print(f"  ⚠️  No timestamp column found in {os.path.basename(csv_path)}")
        print(f"      Available columns: {list(df.columns[:10])}")
        return []

    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
    df = df.dropna(subset=[ts_col])
    df = df.sort_values(ts_col, ascending=False)
    df = df.head(READINGS_PER_STATION)

    pm25_col = _find_col(df, PM25_VARIANTS)
    pm10_col = _find_col(df, PM10_VARIANTS)
    no2_col  = _find_col(df, NO2_VARIANTS)
    so2_col  = _find_col(df, SO2_VARIANTS)
    co_col   = _find_col(df, CO_VARIANTS)
    bp_col   = _find_col(df, BP_VARIANTS)

    rows = []
    for _, row in df.iterrows():
        rows.append({
            "station_name": station_name,
            "timestamp":    row[ts_col].strftime("%Y-%m-%d %H:%M:%S"),
            "pm25":         _safe_float(row[pm25_col])  if pm25_col else None,
            "pm10":         _safe_float(row[pm10_col])  if pm10_col else None,
            "no2":          _safe_float(row[no2_col])   if no2_col  else None,
            "so2":          _safe_float(row[so2_col])   if so2_col  else None,
            "co":           _safe_float(row[co_col])    if co_col   else None,
            "bp":           _safe_float(row[bp_col])    if bp_col   else None,
        })

    return rows


def seed_stations(db: sqlite3.Connection):
    """Insert or replace all 7 station rows."""
    print("\n📍 Seeding stations...")
    for name, meta in STATION_MAP.items():
        db.execute(
            """
            INSERT OR REPLACE INTO stations (name, lat, lon, zone, agency)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, meta["lat"], meta["lon"], meta["zone"], meta["agency"]),
        )
        print(f"  ✅ {name} ({meta['zone']})")
    print(f"  → {len(STATION_MAP)} stations seeded.")


def seed_readings(db: sqlite3.Connection):
    """Seed last 48h readings for all stations."""
    print("\n📊 Seeding readings...")

    # Clear existing readings to avoid duplicates on re-run
    db.execute("DELETE FROM readings")

    total_rows = 0
    for station_name, meta in STATION_MAP.items():
        rows = read_station_readings(station_name, meta)
        if rows:
            db.executemany(
                """
                INSERT INTO readings
                    (station_name, timestamp, pm25, pm10, no2, so2, co, bp)
                VALUES
                    (:station_name, :timestamp, :pm25, :pm10, :no2, :so2, :co, :bp)
                """,
                rows,
            )
            # Get non-null PM2.5 count for reporting
            pm25_valid = sum(1 for r in rows if r["pm25"] is not None)
            latest_ts  = rows[0]["timestamp"]   # rows are desc order
            print(f"  ✅ {station_name:<25} {len(rows):>3} rows | "
                  f"PM2.5 valid: {pm25_valid:>3} | latest: {latest_ts}")
            total_rows += len(rows)
        else:
            print(f"  ❌ {station_name:<25} 0 rows (CSV missing or unreadable)")

    print(f"  → {total_rows} total reading rows seeded.")


def seed_forecast_placeholders(db: sqlite3.Connection):
    """
    Seed one placeholder forecast row per station.
    This ensures /api/forecast never returns 404 before Day 7 runs.
    Forecast is a flat array of 24 zeros — FastAPI replaces this with real predictions.
    """
    print("\n🔮 Seeding forecast placeholders...")
    db.execute("DELETE FROM forecasts")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    placeholder = json.dumps({
        "generated_at": now,
        "horizon_hours": 24,
        "values": [0.0] * 24,
        "note": "placeholder — real forecast generated by /api/forecast endpoint"
    })

    for station_name in STATION_MAP:
        db.execute(
            """
            INSERT INTO forecasts (station_name, generated_at, forecast_json)
            VALUES (?, ?, ?)
            """,
            (station_name, now, placeholder),
        )
        print(f"  ✅ {station_name}")
    print(f"  → {len(STATION_MAP)} placeholder forecasts seeded.")


def main():
    print("=" * 60)
    print("AirIQ — DB Seed Script")
    print(f"Target DB : {DB_PATH}")
    print("=" * 60)

    # 1. Initialise schema (creates tables if not exist)
    init_db()

    # 2. Seed all tables inside a single transaction
    with get_db() as db:
        seed_stations(db)
        seed_readings(db)
        seed_forecast_placeholders(db)

    print("\n" + "=" * 60)
    print("✅ Seeding complete. Run db_verify.py to confirm.")
    print("=" * 60)


if __name__ == "__main__":
    main()