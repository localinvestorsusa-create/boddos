"""Spoken replies for Ori, via Piper — a real neural TTS engine that
synthesizes in real time on CPU, not the browser's flat default voice.

Same split as every other Ogun tool: the local chat model only decides
*what* to say; this module is the external, specialized "muscle" that
makes it actually sound like something you'd want to listen to. Swapping
`tts_voice` in config never touches the model — it's a completely
separate, swappable piece, same as picking a different OpenSCAD render
or Cantera mechanism.

Needs a voice model on disk (not bundled — pick one and fetch it once):
`python -m piper.download_voices <name> --download-dir <voices_dir>`
Browse free voices at https://github.com/OHF-voice/piper1-gpl.
"""
from __future__ import annotations

import io
import wave
from pathlib import Path

from ..config import VoiceCfg

_VOICE_CACHE: dict[str, object] = {}


def _piper_voice_cls():
    """Imported lazily, not at module load — piper-tts pulls in onnxruntime,
    which is slow to import and only worth the cost on a node that actually
    speaks replies aloud."""
    try:
        from piper.voice import PiperVoice
        return PiperVoice
    except ImportError:  # pragma: no cover - exercised via the ok=False path
        return None


class SpeakResult:
    def __init__(self, ok: bool, error: str = "", audio_wav: bytes = b""):
        self.ok = ok
        self.error = error
        self.audio_wav = audio_wav

    def to_dict(self) -> dict:
        return {"ok": self.ok, "error": self.error}


class TTSEngine:
    def __init__(self, cfg: VoiceCfg):
        self.cfg = cfg

    def _voices_dir(self) -> Path:
        return Path(self.cfg.voices_dir).expanduser()

    def _load(self, voice_name: str):
        cached = _VOICE_CACHE.get(voice_name)
        if cached is not None:
            return cached
        piper_voice_cls = _piper_voice_cls()
        if piper_voice_cls is None:
            raise RuntimeError("piper-tts not installed (pip install 'boddos[voice]')")
        model_path = self._voices_dir() / f"{voice_name}.onnx"
        if not model_path.exists():
            raise FileNotFoundError(
                f"voice model not found: {model_path} — fetch it with "
                f"`python -m piper.download_voices {voice_name} "
                f"--download-dir {self._voices_dir()}`"
            )
        voice = piper_voice_cls.load(str(model_path))
        _VOICE_CACHE[voice_name] = voice
        return voice

    def speak(self, text: str, voice_name: str | None = None) -> SpeakResult:
        if not self.cfg.enabled:
            return SpeakResult(ok=False, error="voice disabled on this node (set voice.enabled: true)")
        text = text.strip()
        if not text:
            return SpeakResult(ok=False, error="no text to speak")

        name = voice_name or self.cfg.tts_voice
        try:
            voice = self._load(name)
        except Exception as e:
            return SpeakResult(ok=False, error=str(e))

        buf = io.BytesIO()
        wrote_any = False
        with wave.open(buf, "wb") as wav_file:
            for chunk in voice.synthesize(text):
                if not wrote_any:
                    wav_file.setframerate(chunk.sample_rate)
                    wav_file.setsampwidth(chunk.sample_width)
                    wav_file.setnchannels(chunk.sample_channels)
                    wrote_any = True
                wav_file.writeframes(chunk.audio_int16_bytes)

        if not wrote_any:
            return SpeakResult(ok=False, error="synthesis produced no audio")
        return SpeakResult(ok=True, audio_wav=buf.getvalue())
