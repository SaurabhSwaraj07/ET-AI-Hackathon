"""
advisory.py — GET /api/advisory/{station_name}
Returns a rule-based air quality advisory (Gemini LLM wired on Day 9).
"""
from fastapi import APIRouter, HTTPException
from database import get_latest_reading

router = APIRouter(tags=["advisory"])


def _pm25_to_category(pm25: float) -> tuple[str, str]:
    """
    Map PM2.5 (µg/m³) to AQI category + advisory text.
    Using WHO/CPCB breakpoints.
    Returns (category, advisory_text).
    """
    if pm25 < 12.0:
        return (
            "Good",
            "Air quality is satisfactory. Outdoor activities are safe for all groups.",
        )
    elif pm25 < 35.5:
        return (
            "Moderate",
            "Air quality is acceptable. Unusually sensitive individuals should consider "
            "reducing prolonged outdoor exertion.",
        )
    elif pm25 < 55.5:
        return (
            "Unhealthy for Sensitive Groups",
            "Members of sensitive groups (children, elderly, those with respiratory "
            "conditions) may experience health effects. Consider reducing outdoor activity.",
        )
    elif pm25 < 150.5:
        return (
            "Unhealthy",
            "Everyone may begin to experience health effects. Sensitive groups should "
            "avoid outdoor exertion. Wear an N95 mask if going outside.",
        )
    elif pm25 < 250.5:
        return (
            "Very Unhealthy",
            "Health alert: everyone should avoid outdoor exertion. Sensitive groups "
            "should remain indoors. Air purifiers recommended.",
        )
    else:
        return (
            "Hazardous",
            "Emergency health warning. Everyone should avoid all outdoor activity. "
            "Keep windows closed and use air purifiers.",
        )


@router.get("/advisory/{station_name}")
def get_advisory(station_name: str):
    """
    Return AQ advisory for the given station based on latest PM2.5.
    Rule-based stub — Gemini LLM integration added Day 9.
    """
    latest = get_latest_reading(station_name)
    if not latest:
        raise HTTPException(
            status_code=404,
            detail=f"No readings found for station '{station_name}'."
        )

    pm25 = latest.get("pm25")
    if pm25 is None:
        raise HTTPException(
            status_code=422,
            detail=f"Latest reading for '{station_name}' has null PM2.5."
        )

    category, advisory_text = _pm25_to_category(pm25)

    return {
        "station":   station_name,
        "pm25":      round(pm25, 2),
        "timestamp": latest.get("timestamp"),
        "category":  category,
        "advisory":  advisory_text,
        "source":    "rule-based",  # changes to "gemini-1.5-flash" on Day 9
    }