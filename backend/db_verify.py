"""
db_verify.py — Quick verification queries for airiq.db
Run after db_seed.py to confirm everything landed correctly.

Usage:
    cd backend
    python db_verify.py
"""
import os
import json
from database import get_db, DB_PATH


def verify():
    print("=" * 60)
    print("AirIQ — DB Verification")
    print(f"DB path : {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print("❌ airiq.db NOT FOUND. Run db_seed.py first.")
        return
    print(f"DB size : {os.path.getsize(DB_PATH):,} bytes")
    print("=" * 60)

    with get_db() as db:

        # --- V1: Station count ---
        station_count = db.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
        print(f"\n[V1] Stations in DB : {station_count}")
        if station_count == 7:
            print("     ✅ Expected 7 — correct.")
        else:
            print(f"     ⚠️  Expected 7, got {station_count}.")

        # --- V2: Station list ---
        print("\n[V2] Station list:")
        rows = db.execute(
            "SELECT name, lat, lon, zone, agency FROM stations ORDER BY name"
        ).fetchall()
        for r in rows:
            print(f"     • {r['name']:<25} {r['lat']}, {r['lon']}  [{r['zone']}] [{r['agency']}]")

        # --- V3: Reading count per station ---
        print("\n[V3] Readings per station:")
        rows = db.execute(
            """
            SELECT station_name,
                   COUNT(*)            AS total_rows,
                   SUM(pm25 IS NOT NULL) AS pm25_valid,
                   MAX(timestamp)      AS latest_ts,
                   MIN(timestamp)      AS earliest_ts
            FROM readings
            GROUP BY station_name
            ORDER BY station_name
            """
        ).fetchall()
        if not rows:
            print("     ❌ No readings found. db_seed.py may have failed.")
        else:
            for r in rows:
                flag = "✅" if r["total_rows"] >= 24 else "⚠️ "
                print(f"     {flag} {r['station_name']:<25} "
                      f"{r['total_rows']:>3} rows | "
                      f"PM2.5 valid: {r['pm25_valid']:>3} | "
                      f"latest: {r['latest_ts']}")

        # --- V4: Sample PM2.5 values (latest per station) ---
        print("\n[V4] Latest PM2.5 per station:")
        rows = db.execute(
            """
            SELECT station_name, timestamp, pm25, pm10, no2
            FROM readings
            WHERE (station_name, timestamp) IN (
                SELECT station_name, MAX(timestamp)
                FROM readings
                GROUP BY station_name
            )
            ORDER BY station_name
            """
        ).fetchall()
        for r in rows:
            pm25_str = f"{r['pm25']:.2f} µg/m³" if r["pm25"] is not None else "NULL"
            print(f"     • {r['station_name']:<25} PM2.5={pm25_str:<14} @ {r['timestamp']}")

        # --- V5: Forecast placeholder check ---
        forecast_count = db.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
        print(f"\n[V5] Forecast rows : {forecast_count}")
        if forecast_count == 7:
            print("     ✅ Placeholder forecasts present for all 7 stations.")
        else:
            print(f"     ⚠️  Expected 7 forecast rows, got {forecast_count}.")

        # --- V6: Inference readiness check ---
        # Confirm that get_recent_readings returns enough data for lag features
        print("\n[V6] Inference readiness (lag_24h requires ≥ 24 rows per station):")
        rows = db.execute(
            """
            SELECT station_name, COUNT(*) as cnt
            FROM readings
            GROUP BY station_name
            """
        ).fetchall()
        all_ready = True
        for r in rows:
            ready = r["cnt"] >= 24
            flag  = "✅" if ready else "❌"
            print(f"     {flag} {r['station_name']:<25} {r['cnt']} rows")
            if not ready:
                all_ready = False

        print()
        if all_ready:
            print("✅ All checks passed. DB is ready for Day 6 FastAPI integration.")
        else:
            print("⚠️  Some stations have fewer than 24 readings.")
            print("   This may affect lag feature quality in /api/forecast.")
            print("   Re-run db_seed.py — or check that raw CSVs are present in backend/data/")

    print("=" * 60)


if __name__ == "__main__":
    verify()