"""
attribution.py — GET /api/attribution/{station_name}
Returns top-10 SHAP feature attribution values for the station's latest reading.
"""
import numpy as np
import pandas as pd
import xgboost as xgb
import shap
from fastapi import APIRouter, HTTPException

from database import get_recent_readings
from ml_loader import get_model, get_feature_cols
# Reuse the feature-building helper from forecast router
from routers.forecast import _build_feature_row

router = APIRouter(tags=["attribution"])

# Cache the SHAP explainer (expensive to build)
_explainer = None


def _get_explainer(model: xgb.Booster) -> shap.TreeExplainer:
    global _explainer
    if _explainer is None:
        _explainer = shap.TreeExplainer(model)
    return _explainer


@router.get("/attribution/{station_name}")
def get_attribution(station_name: str, top_n: int = 10):
    """
    Return SHAP feature attribution for the station's most recent reading.
    Used by the attribution table in the frontend (Day 12).
    """
    try:
        model = get_model()
        feature_cols = get_feature_cols()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"ML model not found. ({e})")

    readings = get_recent_readings(station_name, n=48)
    if not readings:
        raise HTTPException(
            status_code=404,
            detail=f"No readings found for station '{station_name}'."
        )

    try:
        feature_df = _build_feature_row(readings, feature_cols)
        explainer = _get_explainer(model)
        shap_values = explainer.shap_values(feature_df)  # shape (1, n_features)
        shap_row = shap_values[0]  # 1D array

        # Zip and sort by absolute SHAP value
        attribution = sorted(
            [
                {"feature": col, "shap_value": round(float(val), 4)}
                for col, val in zip(feature_cols, shap_row)
            ],
            key=lambda x: abs(x["shap_value"]),
            reverse=True,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SHAP error: {str(e)}")

    return {
        "station":     station_name,
        "attribution": attribution[:top_n],
        "total_features": len(feature_cols),
    }