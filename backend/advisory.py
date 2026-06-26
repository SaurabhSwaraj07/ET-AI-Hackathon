"""
advisory.py — GET /api/advisory/{station_name}

Day 8: refactored with generate_advisory() as the single callable.
Day 9: real Gemini gemini-1.5-flash call wired; falls back to rule-based on any error.
"""
import logging

from fastapi import APIRouter, HTTPException

from database import get_recent_readings
from config import GEMINI_ENABLED, GEMINI_API_KEY

logger = logging.getLogger("airiq.advisory")
router = APIRouter(tags=["advisory"])


# ---------------------------------------------------------------------------
# AQI breakpoints (CPCB India, PM2.5 µg/m³ 24-hour average)
# ---------------------------------------------------------------------------
_AQI_LEVELS = [
    (30,          "Good",          "Air quality is satisfactory. Outdoor activities are safe."),
    (60,          "Satisfactory",  "Minor discomfort for very sensitive individuals. Most people unaffected."),
    (90,          "Moderate",      "Sensitive groups (children, elderly, respiratory patients) should limit prolonged outdoor exertion."),
    (120,         "Poor",          "Everyone may experience health effects. Sensitive groups should avoid outdoor activities."),
    (250,         "Very Poor",     "Health alert: everyone should avoid prolonged outdoor exertion. Wear N95 indoors if needed."),
    (float("inf"),"Severe",        "Health emergency: avoid all outdoor activity. Wear N95/FFP2 masks indoors."),
]


def _get_aqi_category(pm25: float) -> str:
    """Return CPCB AQI category string for a given PM2.5 value."""
    for threshold, category, _ in _AQI_LEVELS:
        if pm25 <= threshold:
            return category
    return "Severe"


def _rule_based_advisory(pm25: float) -> dict:
    """Return AQI category + advisory text from CPCB PM2.5 breakpoints."""
    for threshold, category, message in _AQI_LEVELS:
        if pm25 <= threshold:
            return {
                "category": category,
                "message":  message,
                "pm25":     round(pm25, 2),
                "source":   "rule-based",
            }
    # Fallback (should not reach here)
    return {
        "category": "Severe",
        "message":  _AQI_LEVELS[-1][2],
        "pm25":     round(pm25, 2),
        "source":   "rule-based",
    }


def _gemini_advisory(station_name: str, pm25: float) -> dict:
    """
    Day 9: real Gemini gemini-1.5-flash advisory.
    Raises Exception on any failure so generate_advisory() falls back to rule-based.
    """
    import google.generativeai as genai

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-3.1-flash-lite")

    category = _get_aqi_category(pm25)

    prompt = (
        f"You are an air quality health advisor for Bengaluru, India.\n"
        f"Station: {station_name}\n"
        f"Current PM2.5: {pm25:.1f} µg/m³ (CPCB category: {category})\n"
        f"Write a 2-sentence health advisory for the general public. "
        f"Be specific and actionable. Do not use markdown or bullet points."
    )

    generation_config = genai.GenerationConfig(
        max_output_tokens=150,
        temperature=0.4,
    )

    response = model.generate_content(prompt, generation_config=generation_config)
    message  = response.text.strip()

    if not message:
        raise ValueError("Empty response from Gemini.")

    return {
        "category": category,
        "message":  message,
        "pm25":     round(pm25, 2),
        "source":   "gemini",
    }


def generate_advisory(station_name: str, pm25: float) -> dict:
    """
    Single callable for advisory generation.
    Uses Gemini when GEMINI_ENABLED, falls back to rule-based on any error.
    """
    if GEMINI_ENABLED:
        try:
            return _gemini_advisory(station_name, pm25)
        except Exception as exc:
            logger.warning("Gemini advisory failed for %s: %s — using rule-based.", station_name, exc)

    return _rule_based_advisory(pm25)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

@router.get("/advisory/{station_name}")
def get_advisory(station_name: str):
    """
    Return an AQ advisory for the station based on the latest PM2.5 reading.
    Response includes a 'source' field: 'rule-based' or 'gemini'.
    """
    readings = get_recent_readings(station_name, n=1)
    if not readings:
        raise HTTPException(
            status_code=404,
            detail=f"No readings found for station '{station_name}'.",
        )

    pm25     = float(readings[-1].get("pm25") or 0.0)
    advisory = generate_advisory(station_name, pm25)

    return {
        "station":  station_name,
        "advisory": advisory,
    }