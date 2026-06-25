"""
stations.py — GET /api/stations
Returns all 7 stations with their latest PM2.5 reading attached.
"""
from fastapi import APIRouter, HTTPException
from database import get_all_stations, get_latest_reading

router = APIRouter(tags=["stations"])


@router.get("/stations")
def list_stations():
    """
    Return all monitoring stations with their latest PM2.5 reading.
    Used by the Leaflet map to render coloured markers.
    """
    stations = get_all_stations()
    if not stations:
        raise HTTPException(status_code=503, detail="No stations found in database.")

    result = []
    for station in stations:
        latest = get_latest_reading(station["name"])
        result.append({
            "id":        station["id"],
            "name":      station["name"],
            "lat":       station["lat"],
            "lon":       station["lon"],
            "zone":      station["zone"],
            "agency":    station["agency"],
            "pm25":      latest["pm25"]      if latest else None,
            "pm10":      latest["pm10"]      if latest else None,
            "no2":       latest["no2"]       if latest else None,
            "timestamp": latest["timestamp"] if latest else None,
        })

    return {"stations": result, "count": len(result)}