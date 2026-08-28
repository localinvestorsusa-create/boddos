import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from boddos.api import build_app
from boddos.config import Config, NodeCfg
from boddos.services.routing import DEFAULT_NOMINATIM, DEFAULT_OSRM, directions, geocode, route


@pytest.fixture
def client(tmp_path):
    cfg = Config(node=NodeCfg(id="x", role="host"))
    cfg.security.audit_log = str(tmp_path / "a.log")
    with TestClient(build_app(cfg)) as c:
        yield c


NOMINATIM_HIT = [{
    "display_name": "Empire State Building, 350, 5th Avenue, Manhattan, New York, NY, USA",
    "lat": "40.7484405",
    "lon": "-73.9856644",
}]

OSRM_ROUTE = {
    "code": "Ok",
    "routes": [{
        "distance": 1532.4,
        "duration": 1104.9,
        "geometry": {"type": "LineString", "coordinates": [[-73.98, 40.75], [-73.986, 40.748]]},
        "legs": [{
            "steps": [
                {"distance": 12.3, "duration": 9.1, "name": "5th Avenue",
                 "maneuver": {"type": "depart", "modifier": ""}},
                {"distance": 900.0, "duration": 600.0, "name": "5th Avenue",
                 "maneuver": {"type": "turn", "modifier": "left"}},
                {"distance": 0.0, "duration": 0.0, "name": "",
                 "maneuver": {"type": "arrive", "modifier": ""}},
            ],
        }],
    }],
}


@respx.mock
async def test_geocode_success():
    respx.get(f"{DEFAULT_NOMINATIM}/search").mock(
        return_value=httpx.Response(200, json=NOMINATIM_HIT)
    )
    result = await geocode("Empire State Building")
    assert result["ok"] is True
    assert result["lat"] == pytest.approx(40.7484405)
    assert "Empire State" in result["display_name"]


@respx.mock
async def test_geocode_no_results():
    respx.get(f"{DEFAULT_NOMINATIM}/search").mock(return_value=httpx.Response(200, json=[]))
    result = await geocode("a place that does not exist anywhere")
    assert result["ok"] is False
    assert "couldn't find" in result["error"]


async def test_geocode_empty_query():
    result = await geocode("   ")
    assert result["ok"] is False


@respx.mock
async def test_geocode_network_failure_reported_not_raised():
    respx.get(f"{DEFAULT_NOMINATIM}/search").mock(side_effect=httpx.ConnectError("boom"))
    result = await geocode("anywhere")
    assert result["ok"] is False
    assert "geocoding unavailable" in result["error"]


@respx.mock
async def test_route_success_produces_readable_steps():
    respx.get(url__startswith=f"{DEFAULT_OSRM}/route/v1/").mock(
        return_value=httpx.Response(200, json=OSRM_ROUTE)
    )
    result = await route(40.75, -73.98, 40.748, -73.986, profile="walking")
    assert result["ok"] is True
    assert result["distance_m"] == 1532
    assert len(result["steps"]) == 3
    assert result["steps"][0]["instruction"] == "Head out onto 5th Avenue"
    assert result["steps"][1]["instruction"] == "Turn left onto 5th Avenue"
    assert result["steps"][2]["instruction"] == "Arrive at your destination"


@respx.mock
async def test_route_no_route_found():
    respx.get(url__startswith=f"{DEFAULT_OSRM}/route/v1/").mock(
        return_value=httpx.Response(200, json={"code": "NoRoute", "message": "no route"})
    )
    result = await route(0, 0, 1, 1)
    assert result["ok"] is False


@respx.mock
async def test_directions_chains_geocode_and_route():
    respx.get(f"{DEFAULT_NOMINATIM}/search").mock(
        return_value=httpx.Response(200, json=NOMINATIM_HIT)
    )
    respx.get(url__startswith=f"{DEFAULT_OSRM}/route/v1/").mock(
        return_value=httpx.Response(200, json=OSRM_ROUTE)
    )
    result = await directions(40.75, -73.98, "Empire State Building")
    assert result["ok"] is True
    assert "Empire State" in result["destination"]
    assert result["steps"]


@respx.mock
async def test_directions_stops_early_when_geocode_fails():
    respx.get(f"{DEFAULT_NOMINATIM}/search").mock(return_value=httpx.Response(200, json=[]))
    result = await directions(40.75, -73.98, "nowhere in particular")
    assert result["ok"] is False


def test_esu_directions_endpoint_requires_destination(client):
    r = client.post("/api/esu/directions", json={"from_lat": 40.7, "from_lon": -73.9})
    assert r.json()["ok"] is False


def test_esu_directions_endpoint_requires_location(client):
    r = client.post("/api/esu/directions", json={"destination": "somewhere"})
    assert r.json()["ok"] is False


@respx.mock
def test_esu_directions_endpoint_success(client):
    respx.get(f"{DEFAULT_NOMINATIM}/search").mock(
        return_value=httpx.Response(200, json=NOMINATIM_HIT)
    )
    respx.get(url__startswith=f"{DEFAULT_OSRM}/route/v1/").mock(
        return_value=httpx.Response(200, json=OSRM_ROUTE)
    )
    r = client.post("/api/esu/directions", json={
        "destination": "Empire State Building", "from_lat": 40.75, "from_lon": -73.98,
    })
    body = r.json()
    assert body["ok"] is True
    assert body["steps"]
