import pytest
from fastapi.testclient import TestClient

from boddos.api import build_app
from boddos.config import Config, NodeCfg, VoiceCfg
from boddos.voice.stt import STTEngine, partial_text, final_text


def test_disabled_reports_disabled():
    engine = STTEngine(VoiceCfg(stt_enabled=False))
    with pytest.raises(RuntimeError, match="disabled"):
        engine.load_model()


def test_missing_model_fails_cleanly(tmp_path):
    # Whether or not vosk itself is installed in this environment,
    # load_model() must raise a clean, specific error — never crash the
    # process (vosk's own name-based auto-download can call sys.exit()).
    engine = STTEngine(VoiceCfg(stt_model_dir=str(tmp_path / "nope")))
    with pytest.raises(Exception, match="not found|not installed"):
        engine.load_model()


def test_new_recognizer_fails_cleanly_without_a_model(tmp_path):
    engine = STTEngine(VoiceCfg(stt_model_dir=str(tmp_path / "nope")))
    with pytest.raises(Exception, match="not found|not installed"):
        engine.new_recognizer(16000)


def test_partial_and_final_text_handle_malformed_input():
    class _NotARecognizer:
        def PartialResult(self):
            return "not json"

        def Result(self):
            raise AttributeError("boom")

    assert partial_text(_NotARecognizer()) == ""
    assert final_text(_NotARecognizer()) == ""


@pytest.fixture
def client(tmp_path):
    cfg = Config(node=NodeCfg(id="test", role="host"))
    cfg.security.audit_log = str(tmp_path / "audit.log")
    cfg.voice.stt_model_dir = str(tmp_path / "nope")
    with TestClient(build_app(cfg)) as c:
        yield c


def test_ws_reports_error_without_a_model(client):
    with client.websocket_connect("/ws/voice/stt?rate=16000") as ws:
        msg = ws.receive_json()
        assert "error" in msg


def test_ui_config_reports_stt_enabled(client):
    r = client.get("/api/ui-config")
    assert r.json()["stt_enabled"] is True
