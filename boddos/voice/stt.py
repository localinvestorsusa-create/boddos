"""Wake word + command recognition for Ori, via Vosk — a small, fast,
fully offline speech engine that runs comfortably on CPU, not the
browser's SpeechRecognition API (which on Chrome routes audio through
Google's own servers, and doesn't exist at all on Firefox).

Same split as every other voice/Ogun tool: recognition speed and
reliability never depend on the local chat model — Vosk's whole job is
done before the chat model is ever involved.

Needs a model on disk (not bundled — pick one and unzip it once): browse
https://alphacephei.com/vosk/models and unzip a model's folder to
voice.stt_model_dir. See README.md "Fast local speech recognition (Vosk)".
"""
from __future__ import annotations

import json
from pathlib import Path

from ..config import VoiceCfg

_MODEL_CACHE: dict[str, object] = {}


def _vosk():
    """Imported lazily, not at module load — vosk pulls in a compiled
    Kaldi recognizer library, and importing it eagerly for every node adds
    real seconds to server startup whether or not this feature is used."""
    try:
        import vosk
        vosk.SetLogLevel(-1)  # Kaldi's own C++ logging is extremely chatty by default
        return vosk
    except ImportError:  # pragma: no cover - exercised via the ok=False path
        return None


class STTEngine:
    def __init__(self, cfg: VoiceCfg):
        self.cfg = cfg

    def _model_dir(self) -> Path:
        return Path(self.cfg.stt_model_dir).expanduser()

    def load_model(self):
        """Returns a loaded vosk.Model, raising a clear, specific error
        (never vosk's own sys.exit-on-missing-model behavior) if it isn't
        available yet — always loaded from an explicit local path, never
        vosk's own name-based auto-download, so a typo or a renamed
        upstream model can't take down the whole server process."""
        if not self.cfg.stt_enabled:
            raise RuntimeError("speech recognition disabled on this node (set voice.stt_enabled: true)")
        key = str(self._model_dir())
        cached = _MODEL_CACHE.get(key)
        if cached is not None:
            return cached
        vosk = _vosk()
        if vosk is None:
            raise RuntimeError("vosk not installed (pip install 'boddos[voice]')")
        model_dir = self._model_dir()
        if not model_dir.exists():
            raise FileNotFoundError(
                f"speech model not found: {model_dir} — download a model from "
                f"https://alphacephei.com/vosk/models and unzip its folder there"
            )
        model = vosk.Model(model_path=str(model_dir))
        _MODEL_CACHE[key] = model
        return model

    def new_recognizer(self, sample_rate: int):
        """A fresh streaming recognizer for one listening session (one
        WebSocket connection), at whatever sample rate the browser's own
        AudioContext actually gave it — never assumed to be exactly 16kHz."""
        vosk = _vosk()
        if vosk is None:
            raise RuntimeError("vosk not installed (pip install 'boddos[voice]')")
        model = self.load_model()
        return vosk.KaldiRecognizer(model, sample_rate)


def partial_text(recognizer) -> str:
    try:
        return json.loads(recognizer.PartialResult()).get("partial", "")
    except (json.JSONDecodeError, AttributeError):
        return ""


def final_text(recognizer) -> str:
    try:
        return json.loads(recognizer.Result()).get("text", "")
    except (json.JSONDecodeError, AttributeError):
        return ""
