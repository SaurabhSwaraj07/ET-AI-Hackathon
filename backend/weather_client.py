"""
weather_client.py — Fetches current weather for Bengaluru via OpenWeather API.

- Falls back to ERA5 constants when OPENWEATHER_API_KEY is absent or on any error.
- Caches live data for CACHE_TTL_SECONDS to avoid quota burn.
- Returns a dict whose keys match _build_feature_row() exactly.
"""
import math
import time
import logging

import requests

from config import OPENWEATHER_API_KEY, OPENWEATHER_ENABLED, OPENWEATHER_LAT, OPENWEATHER_LON

logger = logging.getLogger("airiq.weather")

CACHE_TTL_SECONDS = 1800  # 30 minutes

# ERA5 constants — same values previously hardcoded in _build_feature_row()
_ERA5_FALLBACK: dict = {
    "temperature_2m":         28.0,
    "relative_humidity_2m":   60.0,
    "wind_speed_10m":          5.0,
    "wind_direction_10m":    180.0,
    "surface_pressure":      912.0,
    "precipitation":           0.0,
    "u_component_of_wind":     0.0,
    "v_component_of_wind":     0.0,
    "boundary_layer_height": 500.0,
}

# Module-level cache
_cache: dict = {"data": None, "ts": 0.0}


def _fetch_from_api() -> dict:
    """
    Call OpenWeather Current Weather API (v2.5) and return a normalised dict.
    Raises requests.RequestException on HTTP/network failure.
    """
    url = "https://api.openweathermap.org/data/2.5/weather"  # FIX: was data/4.0/onecall

    params = {
        "lat":   OPENWEATHER_LAT,
        "lon":   OPENWEATHER_LON,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    wind     = data.get("wind", {})
    main     = data.get("main", {})
    rain     = data.get("rain", {})
    wind_deg = float(wind.get("deg", 180.0))
    wind_spd = float(wind.get("speed", 5.0))

    # Decompose wind speed into u/v components (meteorological convention)
    wind_rad = math.radians(wind_deg)
    u = -wind_spd * math.sin(wind_rad)
    v = -wind_spd * math.cos(wind_rad)

    return {
        "temperature_2m":        float(main.get("temp",     28.0)),
        "relative_humidity_2m":  float(main.get("humidity", 60.0)),
        "wind_speed_10m":        wind_spd,
        "wind_direction_10m":    wind_deg,
        "surface_pressure":      float(main.get("pressure", 912.0)),
        "precipitation":         float(rain.get("1h", 0.0)),
        "u_component_of_wind":   round(u, 4),
        "v_component_of_wind":   round(v, 4),
        "boundary_layer_height": 500.0,   # Not provided by OWM; keep ERA5 constant
    }


def get_current_weather() -> dict:
    """
    Public interface. Returns weather dict compatible with _build_feature_row().

    - If OPENWEATHER_ENABLED is False → ERA5 fallback (no network call).
    - If cached data is fresh → return cache.
    - Otherwise → fetch from API, update cache, return data.
    - On any error → log warning, return ERA5 fallback.
    """
    if not OPENWEATHER_ENABLED:
        return dict(_ERA5_FALLBACK)

    now = time.time()
    if _cache["data"] is not None and (now - _cache["ts"]) < CACHE_TTL_SECONDS:
        logger.debug("Weather cache HIT (age=%.0f s)", now - _cache["ts"])
        return dict(_cache["data"])

    try:
        wx = _fetch_from_api()
        _cache["data"] = wx
        _cache["ts"]   = now
        logger.info(
            "Weather fetched from OpenWeather: temp=%.1f°C  humidity=%.0f%%  wind=%.1f m/s",
            wx["temperature_2m"], wx["relative_humidity_2m"], wx["wind_speed_10m"],
        )
        return dict(wx)
    except Exception as exc:
        logger.warning("OpenWeather fetch failed (%s) — using ERA5 fallback.", exc)
        return dict(_ERA5_FALLBACK)