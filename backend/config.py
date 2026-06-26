"""
config.py — Centralised environment variable loading for AirIQ.

Day 9: populate .env with real keys and set OPENWEATHER_ENABLED / GEMINI_ENABLED to True.
"""
import os
from dotenv import load_dotenv

# Load .env from the backend/ directory (same dir as this file)
_ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(_ENV_PATH, override=False)

# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------
OPENWEATHER_API_KEY: str = os.getenv("OPENWEATHER_API_KEY", "")
GEMINI_API_KEY:      str = os.getenv("GEMINI_API_KEY",      "")

# ---------------------------------------------------------------------------
# OpenWeather target coordinates — central Bengaluru
# ---------------------------------------------------------------------------
OPENWEATHER_LAT: float = float(os.getenv("OPENWEATHER_LAT", "12.9716"))
OPENWEATHER_LON: float = float(os.getenv("OPENWEATHER_LON", "77.5946"))

# ---------------------------------------------------------------------------
# Feature flags (derived — do not set manually in .env)
# ---------------------------------------------------------------------------
OPENWEATHER_ENABLED: bool = bool(OPENWEATHER_API_KEY.strip())
GEMINI_ENABLED:      bool = bool(GEMINI_API_KEY.strip())