import time

import pytest

from boddos.security.auth import MeshAuth, ClientAuth, constant_time_eq
from boddos.security.audit import AuditLog
from boddos.security.ratelimit import RateLimiter
from boddos.security.vault import SecretVault
from boddos.safety.surveillance import evil_twin_candidates, fingerprint_devices
from boddos.safety.geofence import GeoFence, Zone, haversine_m
from boddos.safety.deadman import DeadMansSwitch


def test_mesh_sign_verify_roundtrip():
    a = MeshAuth("psk")
    body = b'{"x":1}'
    ok, _ = a.verify(a.sign(body), body)
    assert ok


def test_mesh_rejects_tampered_body():
    a = MeshAuth("psk")
    headers = a.sign(b'{"x":1}')
    ok, reason = a.verify(headers, b'{"x":2}')
    assert not ok and reason == "bad signature"


def test_mesh_rejects_stale():
    a = MeshAuth("psk", max_skew_s=0)
    headers = a.sign(b"body")
    time.sleep(1.1)
    ok, reason = a.verify(headers, b"body")
    assert not ok and reason == "stale timestamp"


def test_mesh_rejects_replay():
    a = MeshAuth("psk")
    body = b"body"
    headers = a.sign(body)
    assert a.verify(headers, body)[0]
    assert not a.verify(headers, body)[0]


def test_client_auth_optional_and_required():
    assert ClientAuth(None, require=False).check(None) is True
    ca = ClientAuth("tok", require=True)
    assert ca.check("Bearer tok") is True
    assert ca.check("Bearer nope") is False
    assert ca.check(None, query_token="tok") is True


def test_constant_time_eq():
    assert constant_time_eq("a", "a")
    assert not constant_time_eq("a", "b")


def test_audit_hash_chain_detects_tampering(tmp_path):
    log = AuditLog(tmp_path / "audit.log")
    log.record("a", {"n": 1})
    log.record("b", {"n": 2})
    intact, n = log.verify_chain()
    assert intact and n == 2
    # Corrupt a line.
    p = tmp_path / "audit.log"
    lines = p.read_text().splitlines()
    lines[0] = lines[0].replace('"n":1', '"n":9')
    p.write_text("\n".join(lines) + "\n")
    intact, _ = log.verify_chain()
    assert not intact


def test_rate_limiter_and_lockout():
    rl = RateLimiter(rate_per_sec=0, capacity=2, lockout_threshold=2, lockout_seconds=100)
    assert rl.allow("ip") and rl.allow("ip")
    assert not rl.allow("ip")           # bucket empty
    rl.record_failure("ip"); rl.record_failure("ip")
    assert rl.is_locked("ip")


def test_vault_encrypt_decrypt(tmp_path):
    v = SecretVault(tmp_path / "vault.bin", passphrase="hunter2")
    v.set("api_key", "s3cr3t")
    assert v.get("api_key") == "s3cr3t"
    # Wrong passphrase cannot read.
    with pytest.raises(Exception):
        SecretVault(tmp_path / "vault.bin", passphrase="wrong").load()


def test_vault_locked_without_passphrase(tmp_path):
    v = SecretVault(tmp_path / "vault.bin", passphrase="")
    assert not v.unlocked
    with pytest.raises(RuntimeError):
        v.save({"x": 1})


def test_evil_twin_detection():
    wifi = [
        {"bssid": "AA:00:00:00:00:01", "ssid": "Net", "rssi": -40},
        {"bssid": "BB:00:00:00:00:02", "ssid": "Net", "rssi": -60},
    ]
    twins = evil_twin_candidates(wifi)
    assert twins and twins[0]["ssid"] == "Net" and twins[0]["bssid_count"] == 2


def test_device_fingerprint_by_oui():
    ble = [{"mac": "2C:AA:8E:11:22:33", "name": "cam"}]
    hits = fingerprint_devices([], ble)
    assert hits and "camera" in hits[0]["vendor_guess"].lower()


def test_geofence_leaving_safe_zone():
    gf = GeoFence([Zone("home", 40.0, -74.0, 100, "safe")])
    assert gf.evaluate(40.0, -74.0)["in_safe_zone"] is True
    out = gf.evaluate(41.0, -75.0)
    assert "outside all safe zones" in out["alerts"]


def test_haversine_reasonable():
    # ~111 km per degree of latitude.
    d = haversine_m(40.0, -74.0, 41.0, -74.0)
    assert 110000 < d < 112000


def test_deadman_fires_when_overdue():
    dm = DeadMansSwitch()
    dm.arm("t", minutes=0)  # deadline == now
    time.sleep(0.01)
    due = dm.due()
    assert len(due) == 1 and due[0].label == "t"
    # Doesn't double-fire.
    assert dm.due() == []
