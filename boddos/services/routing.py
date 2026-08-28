"""Wayfinding via public OpenStreetMap services (no API key required) —
geocoding through Nominatim, walking/driving/cycling directions through
OSRM. This is Esu Pathfinder's routing layer: point-to-point directions
for a destination the user names, not a tracking or lookup tool.

Both default to the public demo instances (best-effort, rate-limited —
see each project's usage policy). For real use, point
services.routing.nominatim_url / osrm_url at a self-hosted instance
instead; both are a couple of Docker containers on an OSM extract for
your region.
"""
from __future__ import annotations

import httpx

DEFAULT_NOMINATIM = "https://nominatim.openstreetmap.org"
DEFAULT_OSRM = "https://router.project-osrm.org"
_USER_AGENT = "boddos-esu-pathfinder/0.1 (self-hosted personal assistant; contact via project repo)"

_PROFILES = {
    "walking": "foot", "foot": "foot", "walk": "foot",
    "driving": "driving", "car": "driving", "drive": "driving",
    "cycling": "bike", "bike": "bike", "bicycle": "bike",
}


async def geocode(query: str, nominatim_url: str = DEFAULT_NOMINATIM) -> dict:
    """Resolve a place name / address to coordinates."""
    if not query.strip():
        return {"ok": False, "error": "empty query"}
    params = {"q": query, "format": "jsonv2", "limit": 1}
    try:
        async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": _USER_AGENT}) as c:
            r = await c.get(f"{nominatim_url.rstrip('/')}/search", params=params)
            r.raise_for_status()
            results = r.json()
    except Exception as e:
        return {"ok": False, "error": f"geocoding unavailable: {e}"}
    if not results:
        return {"ok": False, "error": f"couldn't find a location for '{query}'"}
    hit = results[0]
    try:
        return {
            "ok": True,
            "query": query,
            "display_name": hit.get("display_name", query),
            "lat": float(hit["lat"]),
            "lon": float(hit["lon"]),
        }
    except (KeyError, TypeError, ValueError) as e:
        return {"ok": False, "error": f"malformed geocoding response: {e}"}


def _describe_step(step: dict) -> str:
    maneuver = step.get("maneuver", {})
    m_type = maneuver.get("type", "")
    modifier = maneuver.get("modifier", "")
    name = step.get("name") or "the path"
    if m_type == "depart":
        return f"Head out onto {name}"
    if m_type == "arrive":
        return "Arrive at your destination"
    if m_type == "turn":
        return f"Turn {modifier} onto {name}".strip()
    if m_type in ("new name", "continue"):
        return f"Continue onto {name}"
    if m_type == "roundabout":
        return f"At the roundabout, take the exit onto {name}"
    if modifier:
        return f"{m_type.capitalize()} {modifier} onto {name}".strip()
    return f"{m_type.capitalize()} onto {name}".strip()


async def route(
    from_lat: float, from_lon: float, to_lat: float, to_lon: float,
    profile: str = "walking", osrm_url: str = DEFAULT_OSRM,
) -> dict:
    """Turn-by-turn directions between two points."""
    osrm_profile = _PROFILES.get(profile.lower(), "foot")
    coords = f"{from_lon},{from_lat};{to_lon},{to_lat}"
    params = {"overview": "full", "geometries": "geojson", "steps": "true"}
    try:
        async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": _USER_AGENT}) as c:
            r = await c.get(f"{osrm_url.rstrip('/')}/route/v1/{osrm_profile}/{coords}", params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return {"ok": False, "error": f"routing unavailable: {e}"}

    if data.get("code") != "Ok" or not data.get("routes"):
        return {"ok": False, "error": data.get("message") or "no route found"}

    leg = data["routes"][0]
    steps: list[dict] = []
    for l in leg.get("legs", []):
        for s in l.get("steps", []):
            steps.append({
                "instruction": _describe_step(s),
                "distance_m": round(s.get("distance", 0)),
                "duration_s": round(s.get("duration", 0)),
            })

    return {
        "ok": True,
        "profile": profile,
        "distance_m": round(leg.get("distance", 0)),
        "duration_s": round(leg.get("duration", 0)),
        "geometry": leg.get("geometry"),  # GeoJSON LineString: {type, coordinates: [[lon, lat], ...]}
        "steps": steps,
    }


async def directions(
    from_lat: float, from_lon: float, destination: str, profile: str = "walking",
    nominatim_url: str = DEFAULT_NOMINATIM, osrm_url: str = DEFAULT_OSRM,
) -> dict:
    """Geocode a named destination, then route to it from a live position."""
    geo = await geocode(destination, nominatim_url)
    if not geo.get("ok"):
        return geo
    result = await route(from_lat, from_lon, geo["lat"], geo["lon"], profile, osrm_url)
    if result.get("ok"):
        result["destination"] = geo["display_name"]
        result["destination_lat"] = geo["lat"]
        result["destination_lon"] = geo["lon"]
    return result
