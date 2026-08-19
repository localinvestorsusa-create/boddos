"""Weather-aware planning via Open-Meteo (no API key required).

Returns a compact same-day picture plus a plain-language advisory the advisor
model can fold into task planning ("bring a jacket", "storm window at 3pm").
"""
from __future__ import annotations

import httpx

_WMO = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "rime fog", 51: "light drizzle", 53: "drizzle",
    55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers",
    81: "rain showers", 82: "violent rain showers", 95: "thunderstorm",
    96: "thunderstorm w/ hail", 99: "severe thunderstorm w/ hail",
}


async def get_forecast(lat: float, lon: float) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
        "hourly": "temperature_2m,precipitation_probability,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        "forecast_days": 1,
        "timezone": "auto",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get("https://api.open-meteo.com/v1/forecast", params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return {"ok": False, "error": f"weather unavailable: {e}"}

    cur = data.get("current", {})
    daily = data.get("daily", {})
    code = int(cur.get("weather_code", 0))
    cond = _WMO.get(code, "unknown")
    pop = (daily.get("precipitation_probability_max") or [0])[0]

    advisory = []
    if pop >= 60:
        advisory.append("high chance of precipitation — plan cover/reschedule outdoor tasks")
    if code in (95, 96, 99):
        advisory.append("thunderstorms expected — avoid open/exposed areas")
    if cur.get("wind_speed_10m", 0) >= 35:
        advisory.append("strong winds — unsafe for drone flight")
    if (daily.get("temperature_2m_min") or [99])[0] <= 0:
        advisory.append("freezing temps — dress warm, watch for ice")

    return {
        "ok": True,
        "condition": cond,
        "temp_c": cur.get("temperature_2m"),
        "feels_c": cur.get("apparent_temperature"),
        "wind_kmh": cur.get("wind_speed_10m"),
        "precip_prob_max": pop,
        "high_c": (daily.get("temperature_2m_max") or [None])[0],
        "low_c": (daily.get("temperature_2m_min") or [None])[0],
        "advisory": advisory or ["conditions look fine for planned tasks"],
    }
