"""
forecast.py — GET /api/forecast/{station_name}
Runs XGBoost inference and returns a 24-hour PM2.5 forecast array.

Day 7 additions:
  - _run_forecast_for_station() extracted so APScheduler can call it directly.
  - Cache-hit path: returns DB forecast if generated < 60 min ago.
"""
import json
import logging
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import xgboost as xgb
from fastapi import APIRouter, HTTPException

from database import get_recent_readings, get_latest_forecast, upsert_forecast
from ml_loader import get_model, get_feature_cols

logger = logging.getLogger("airiq.forecast")
router = APIRouter(tags=["forecast"])

FORECAST_TTL_MINUTES = 60  # cache lifetime


# ---------------------------------------------------------------------------
# Feature engineering (shared with attribution.py)
# ---------------------------------------------------------------------------


from weather_client import get_current_weather   # ADD THIS IMPORT at the top of the file

def _build_feature_row(readings: list[dict], feature_cols: list[str]) -> pd.DataFrame:
    """
    Build a single-row feature DataFrame from the last 48 readings.
    Matches the exact column order from feature_cols.json.

    Day 8: weather fields sourced from weather_client (live or ERA5 fallback).
    Day 9: live values flow automatically once OPENWEATHER_API_KEY is set.
    """
    if not readings:
        raise ValueError("No readings available for feature engineering.")

    latest = readings[-1]

    pm25_values = [r.get("pm25") or 0.0 for r in readings]

    lag_1h        = pm25_values[-2]  if len(pm25_values) >= 2  else 0.0
    lag_24h       = pm25_values[-25] if len(pm25_values) >= 25 else pm25_values[0]
    roll_6        = pm25_values[-6:] if len(pm25_values) >= 6  else pm25_values
    roll_mean_6h  = float(np.mean(roll_6))
    roll_std_6h   = float(np.std(roll_6)) if len(roll_6) > 1 else 0.0

    try:
        ts = pd.to_datetime(latest["timestamp"])
    except Exception:
        ts = pd.Timestamp.now()

    # Fetch weather — returns live data or ERA5 fallback transparently
    wx = get_current_weather()

    row = {
        "pm25":                   latest.get("pm25")  or 0.0,
        "pm10":                   latest.get("pm10")  or 0.0,
        "no2":                    latest.get("no2")   or 0.0,
        "so2":                    latest.get("so2")   or 0.0,
        "co":                     latest.get("co")    or 0.0,
        "pm25_lag_1h":            lag_1h,
        "pm25_lag_24h":           lag_24h,
        "pm25_rolling_mean_6h":   roll_mean_6h,
        "pm25_rolling_std_6h":    roll_std_6h,
        "hour":                   ts.hour,
        "dayofweek":              ts.dayofweek,
        "month":                  ts.month,
        "is_weekend":             int(ts.dayofweek >= 5),
        # Weather — live via OpenWeather or ERA5 fallback
        "temperature_2m":         wx["temperature_2m"],
        "relative_humidity_2m":   wx["relative_humidity_2m"],
        "wind_speed_10m":         wx["wind_speed_10m"],
        "wind_direction_10m":     wx["wind_direction_10m"],
        "surface_pressure":       wx["surface_pressure"],
        "precipitation":          wx["precipitation"],
        "u_component_of_wind":    wx["u_component_of_wind"],
        "v_component_of_wind":    wx["v_component_of_wind"],
        "boundary_layer_height":  wx["boundary_layer_height"],
    }

    df = pd.DataFrame([row])
    for col in feature_cols:
        if col not in df.columns:
            df[col] = 0.0

    return df[feature_cols]


# ---------------------------------------------------------------------------
# Core inference — callable by both the router AND the scheduler
# ---------------------------------------------------------------------------

def _run_forecast_for_station(station_name: str) -> list[float]:
    """
    Run 24-hour XGBoost iterative rollout for a station.
    Persists result to DB. Returns list of 24 PM2.5 floats.
    Raises ValueError / FileNotFoundError on failure (caller handles logging).
    """
    model        = get_model()
    feature_cols = get_feature_cols()

    readings = get_recent_readings(station_name, n=48)
    if not readings:
        raise ValueError(f"No readings in DB for '{station_name}'.")

    forecast_values  = []
    current_readings = list(readings)

    for _ in range(24):
        feature_df = _build_feature_row(current_readings, feature_cols)
        dmatrix    = xgb.DMatrix(feature_df, feature_names=feature_cols)
        prediction = float(model.predict(dmatrix)[0])
        prediction = max(0.0, min(prediction, 999.0))
        forecast_values.append(round(prediction, 2))

        last         = dict(current_readings[-1])
        last["pm25"] = prediction
        current_readings.append(last)
        if len(current_readings) > 48:
            current_readings = current_readings[-48:]

    generated_at     = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    forecast_payload = json.dumps({
        "generated_at":  generated_at,
        "horizon_hours": 24,
        "values":        forecast_values,
        "note":          "XGBoost iterative 24h rollout",
    })
    upsert_forecast(station_name, generated_at, forecast_payload)
    return forecast_values


# ---------------------------------------------------------------------------
# Router endpoint
# ---------------------------------------------------------------------------

def _is_fresh(generated_at_str: str, ttl_minutes: int = FORECAST_TTL_MINUTES) -> bool:
    """Return True if generated_at is within ttl_minutes of now (UTC)."""
    try:
        generated_at = datetime.strptime(generated_at_str, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        age = datetime.now(timezone.utc) - generated_at
        return age < timedelta(minutes=ttl_minutes)
    except Exception:
        return False


@router.get("/forecast/{station_name}")
def get_forecast(station_name: str):
    """
    Return a 24-element PM2.5 forecast array for the given station.

    Cache-hit: if a DB forecast exists and is < 60 min old, return it
    immediately (no inference). Cache-miss: run XGBoost, persist, return.
    """
    # --- Check cache first ---
    cached = get_latest_forecast(station_name)
    if cached:
        try:
            payload = json.loads(cached["forecast_json"])
            generated_at = payload.get("generated_at") or cached.get("generated_at", "")
            if _is_fresh(generated_at):
                logger.info("Cache HIT for %s (age < %d min)", station_name, FORECAST_TTL_MINUTES)
                return {
                    "station":        station_name,
                    "generated_at":   generated_at,
                    "forecast_hours": payload["values"],
                    "horizon":        24,
                    "unit":           "µg/m³",
                    "cache":          "hit",
                }
        except Exception as exc:
            logger.warning("Cache parse error for %s: %s — running fresh inference.", station_name, exc)

    # --- Cache miss: run inference ---
    try:
        get_model()
        get_feature_cols()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"ML model not found. Run model training first. ({e})"
        )

    try:
        forecast_values = _run_forecast_for_station(station_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    logger.info("Cache MISS for %s — fresh inference complete.", station_name)

    return {
        "station":        station_name,
        "generated_at":   generated_at,
        "forecast_hours": forecast_values,
        "horizon":        24,
        "unit":           "µg/m³",
        "cache":          "miss",
    }