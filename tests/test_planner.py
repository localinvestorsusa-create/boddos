import pytest
from fastapi.testclient import TestClient

from boddos.api import build_app
from boddos.config import Config, NodeCfg, PlannerCfg
from boddos.services.planner import PlannerStore


@pytest.fixture
def store(tmp_path):
    return PlannerStore(PlannerCfg(db_path=str(tmp_path / "planner.db")))


# ------------------------------- events -------------------------------

def test_add_and_list_event(store):
    event = store.add_event("Standup", "2026-01-05 09:00:00", "2026-01-05 09:15:00")
    events = store.list_events("2026-01-05")
    assert len(events) == 1
    assert events[0].id == event.id
    assert events[0].title == "Standup"


def test_list_events_filters_by_date(store):
    store.add_event("Standup", "2026-01-05 09:00:00", "2026-01-05 09:15:00")
    store.add_event("Dentist", "2026-01-06 14:00:00", "2026-01-06 15:00:00")
    assert len(store.list_events("2026-01-05")) == 1
    assert len(store.list_events("2026-01-06")) == 1
    assert len(store.list_events()) == 2


def test_delete_event(store):
    event = store.add_event("Standup", "2026-01-05 09:00:00", "2026-01-05 09:15:00")
    assert store.delete_event(event.id) is True
    assert store.list_events("2026-01-05") == []
    assert store.delete_event(event.id) is False


# ------------------------------- alarms -------------------------------

def test_add_list_delete_alarm(store):
    alarm = store.add_alarm("07:00", "Wake up")
    alarms = store.list_alarms()
    assert len(alarms) == 1
    assert alarms[0].label == "Wake up"
    assert store.delete_alarm(alarm.id) is True
    assert store.list_alarms() == []


# ------------------------------- tasks -------------------------------

def test_add_toggle_delete_task(store):
    task = store.add_task("Buy groceries")
    assert store.list_tasks()[0].completed is False
    assert store.toggle_task(task.id, True) is True
    assert store.list_tasks()[0].completed is True
    assert store.delete_task(task.id) is True
    assert store.list_tasks() == []


def test_disabled_store_skips_db_init(tmp_path):
    db_path = tmp_path / "should-not-exist.db"
    PlannerStore(PlannerCfg(enabled=False, db_path=str(db_path)))
    assert not db_path.exists()


# ------------------------------- endpoints -------------------------------

@pytest.fixture
def client(tmp_path):
    cfg = Config(node=NodeCfg(id="test", role="host"))
    cfg.security.audit_log = str(tmp_path / "audit.log")
    cfg.services.planner.db_path = str(tmp_path / "planner.db")
    with TestClient(build_app(cfg)) as c:
        yield c


def test_event_endpoints_round_trip(client):
    r = client.post("/api/planner/events", json={
        "title": "Standup", "start_time": "2026-01-05 09:00:00", "end_time": "2026-01-05 09:15:00",
    })
    assert r.status_code == 200
    event_id = r.json()["id"]

    r = client.get("/api/planner/events", params={"date": "2026-01-05"})
    assert len(r.json()["events"]) == 1

    r = client.delete(f"/api/planner/events/{event_id}")
    assert r.json()["ok"] is True


def test_event_endpoint_rejects_missing_fields(client):
    r = client.post("/api/planner/events", json={"title": "Standup"})
    assert r.status_code == 400


def test_task_endpoints_round_trip(client):
    r = client.post("/api/planner/tasks", json={"text": "Buy groceries"})
    assert r.status_code == 200
    task_id = r.json()["id"]

    r = client.get("/api/planner/tasks")
    assert len(r.json()["tasks"]) == 1

    r = client.post(f"/api/planner/tasks/{task_id}/toggle", json={"completed": True})
    assert r.json()["ok"] is True

    r = client.delete(f"/api/planner/tasks/{task_id}")
    assert r.json()["ok"] is True


def test_task_endpoint_rejects_empty_text(client):
    r = client.post("/api/planner/tasks", json={"text": "   "})
    assert r.status_code == 400


def test_alarm_endpoints_round_trip(client):
    r = client.post("/api/planner/alarms", json={"time": "07:00", "label": "Wake up"})
    assert r.status_code == 200
    alarm_id = r.json()["id"]

    r = client.get("/api/planner/alarms")
    assert len(r.json()["alarms"]) == 1

    r = client.delete(f"/api/planner/alarms/{alarm_id}")
    assert r.json()["ok"] is True
