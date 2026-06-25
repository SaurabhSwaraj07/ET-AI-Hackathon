"""
ml_loader.py — Singleton loader for XGBoost model + feature columns.
Import this in forecast.py and attribution.py to avoid loading twice.
"""
import os
import json
import joblib
import xgboost as xgb

ML_DIR = os.path.join(os.path.dirname(__file__), "ml")

_model = None
_feature_cols = None


def get_model() -> xgb.Booster:
    global _model
    if _model is None:
        model_path = os.path.join(ML_DIR, "model.joblib")
        _model = joblib.load(model_path)
    return _model


def get_feature_cols() -> list[str]:
    global _feature_cols
    if _feature_cols is None:
        fc_path = os.path.join(ML_DIR, "feature_cols.json")
        with open(fc_path) as f:
            _feature_cols = json.load(f)
    return _feature_cols


def get_ml_dir() -> str:
    return ML_DIR