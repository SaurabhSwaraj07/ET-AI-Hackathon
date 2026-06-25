"""
forecast.py — GET /api/forecast/{station_name}
Runs XGBoost inference and returns a 24-hour PM2.5 forecast array.
"""
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import xgboost as xgb
from fastapi import APIRouter, HTTPException

from database import get_recent_readings, get_latest_forecast, upsert_forecast
from ml_loader import get_model, get_feature_cols

router = APIRouter(tags=["forecast"])


def _build_feature_row(readings: list[dict], feature_cols: list[str]) -> pd.DataFrame:
    """
    Build a single-row feature DataFrame from the last 48 readings.
    Matches the exact column order from feature_cols.json.
    Column engineering must mirror 02_feature_engineering.ipynb.
    """
    if not readings:
        raise ValueError("No readings available for feature engineering.")

    # Use the most recent reading as the base row
    latest = readings[-1]

    # --- Lag features ---
    pm25_values = [r.get("pm25") or 0.0 for r in readings]

    lag_1h   = pm25_values[-2] if len(pm25_values) >= 2  else 0.0
    lag_24h  = pm25_values[-25] if len(pm25_values) >= 25 else pm25_values[0]
    roll_6   = pm25_values[-6:] if len(pm25_values) >= 6  else pm25_values
    roll_mean_6h = float(np.mean(roll_6))
    roll_std_6h  = float(np.std(roll_6)) if len(roll_6) > 1 else 0.0

    # --- Time features ---
    try:
        ts = pd.to_datetime(latest["timestamp"])
    except Exception:
        ts = pd.Timestamp.now()

    # --- Assemble base dict with all possible column names ---
    row = {
        # Pollutant readings
        "pm25":                   latest.get("pm25")  or 0.0,
        "pm10":                   latest.get("pm10")  or 0.0,
        "no2":                    latest.get("no2")   or 0.0,
        "so2":                    latest.get("so2")   or 0.0,
        "co":                     latest.get("co")    or 0.0,

        # Lag features
        "pm25_lag_1h":            lag_1h,
        "pm25_lag_24h":           lag_24h,
        "pm25_rolling_mean_6h":   roll_mean_6h,
        "pm25_rolling_std_6h":    roll_std_6h,

        # Time features
        "hour":                   ts.hour,
        "dayofweek":              ts.dayofweek,
        "month":                  ts.month,
        "is_weekend":             int(ts.dayofweek >= 5),

        # Weather placeholders (ERA5 columns from feature matrix)
        # These will be replaced by real OpenWeather data on Day 9
        "temperature_2m":         28.0,
        "relative_humidity_2m":   60.0,
        "wind_speed_10m":         5.0,
        "wind_direction_10m":     180.0,
        "surface_pressure":       912.0,
        "precipitation":          0.0,
        "u_component_of_wind":    0.0,
        "v_component_of_wind":    0.0,
        "boundary_layer_height":  500.0,
    }

    # Build DataFrame with exactly the columns in feature_cols, in order
    df = pd.DataFrame([row])
    for col in feature_cols:
        if col not in df.columns:
            df[col] = 0.0

    return df[feature_cols]


@router.get("/forecast/{station_name}")
def get_forecast(station_name: str):
    """
    Run XGBoost inference for the given station.
    Returns a 24-element array of predicted PM2.5 values (µg/m³).

    MVP approach: predict next hour from current features, then
    use that prediction as pm25_lag_1h for hour+1 (iterative rollout).
    """
    # --- Load ML artifacts (cached after first call) ---
    try:
        model = get_model()
        feature_cols = get_feature_cols()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"ML model not found. Run model training first. ({e})"
        )

    # --- Get recent readings ---
    readings = get_recent_readings(station_name, n=48)
    if not readings:
        raise HTTPException(
            status_code=404,
            detail=f"No readings found for station '{station_name}'. Check station name."
        )

    # --- Generate 24-hour iterative forecast ---
    forecast_values = []
    current_readings = list(readings)  # copy so we can append predictions

    try:
        for hour_offset in range(24):
            feature_df = _build_feature_row(current_readings, feature_cols)
            dmatrix = xgb.DMatrix(feature_df, feature_names=feature_cols)
            prediction = float(model.predict(dmatrix)[0])
            # Clamp to valid PM2.5 range
            prediction = max(0.0, min(prediction, 999.0))
            forecast_values.append(round(prediction, 2))

            # Append synthetic reading for next iteration (rolling lag window)
            last = dict(current_readings[-1])
            last["pm25"] = prediction
            current_readings.append(last)
            if len(current_readings) > 48:
                current_readings = current_readings[-48:]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")

    # --- Persist to DB ---
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    forecast_payload = json.dumps({
        "generated_at":  generated_at,
        "horizon_hours": 24,
        "values":        forecast_values,
        "note":          "XGBoost iterative 24h rollout",
    })
    upsert_forecast(station_name, generated_at, forecast_payload)

    return {
        "station":        station_name,
        "generated_at":   generated_at,
        "forecast_hours": forecast_values,
        "horizon":        24,
        "unit":           "µg/m³",
    }