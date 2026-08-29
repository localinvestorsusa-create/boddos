import pytest
from fastapi.testclient import TestClient

from boddos.api import build_app
from boddos.config import Config, NodeCfg, VoiceCfg
from boddos.voice.tts import TTSEngine


def test_disabled_reports_disabled():
    engine = TTSEngine(VoiceCfg(tts_enabled=False))
    res = engine.speak("hello there")
    assert not res.ok
    assert "disabled" in res.error


def test_empty_text_rejected():
    engine = TTSEngine(VoiceCfg())
    res = engine.speak("   ")
    assert not res.ok
    assert "no text" in res.error


def test_missing_voice_model_fails_cleanly(tmp_path):
    # No voice model has been downloaded into this empty dir. Whether or not
    # piper-tts itself is installed in this environment, speak() must return
    # a clean ok=False with a real explanation — never raise.
    engine = TTSEngine(VoiceCfg(voices_dir=str(tmp_path)))
    res = engine.speak("hello there", voice_name="en_US-amy-medium")
    assert not res.ok
    assert res.error
    assert res.audio_wav == b""


@pytest.fixture
def client(tmp_path):
    cfg = Config(node=NodeCfg(id="test", role="host"))
    cfg.security.audit_log = str(tmp_path / "audit.log")
    cfg.voice.voices_dir = str(tmp_path / "voices")
    with TestClient(build_app(cfg)) as c:
        yield c


def test_speak_endpoint_fails_cleanly_without_a_model(client):
    r = client.post("/api/voice/speak", json={"text": "hello there"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"]


def test_speak_endpoint_rejects_empty_text(client):
    r = client.post("/api/voice/speak", json={"text": ""})
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_ui_config_reports_voice_settings(client):
    r = client.get("/api/ui-config")
    body = r.json()
    assert body["tts_enabled"] is True
    assert body["tts_voice"] == "en_US-amy-medium"
