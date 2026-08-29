"""Hardware capacity detection — "identify my laptop's capacity" from the
brief. Runs once at node startup (and on demand via /api/hardware) so a
model tier gets picked automatically instead of asking the user to guess,
both from the installer and from Orunmila at runtime.

Best-effort across platforms: every detector degrades to a safe default
instead of raising, since a node with no GPU (or on a platform this can't
fully introspect) still needs to start and pick *something*.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass
class HardwareReport:
    cpu_model: str
    cpu_cores: int
    ram_gb: float
    gpu_vendor: str | None
    gpu_name: str | None
    vram_gb: float
    has_gpu: bool
    os_name: str
    recommended_model: str
    recommended_vision_model: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _cpu_info() -> tuple[str, int]:
    try:
        import cpuinfo  # py-cpuinfo
        info = cpuinfo.get_cpu_info()
        brand = info.get("brand_raw") or platform.processor() or "unknown CPU"
        cores = info.get("count") or os.cpu_count() or 1
        return brand, int(cores)
    except Exception:
        return platform.processor() or platform.machine() or "unknown CPU", os.cpu_count() or 1


def _ram_gb() -> float:
    try:
        import psutil
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        pass
    system = platform.system()
    try:
        if system == "Linux":
            out = subprocess.run(["free", "-b"], capture_output=True, text=True, timeout=5).stdout
            for line in out.splitlines():
                if line.startswith("Mem:"):
                    return round(int(line.split()[1]) / (1024 ** 3), 1)
        elif system == "Darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5).stdout
            return round(int(out.strip()) / (1024 ** 3), 1)
    except Exception:
        pass
    return 0.0


def _gpu_info() -> tuple[str | None, str | None, float]:
    """Returns (vendor, name, vram_gb) — best-effort, never raises."""
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            if out:
                name, mem_mib = out.splitlines()[0].split(",")
                return "nvidia", name.strip(), round(float(mem_mib) / 1024, 1)
        except Exception:
            pass
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        # Apple Silicon: unified memory — no separate VRAM figure, the GPU
        # draws from system RAM within limits macOS manages itself.
        try:
            name = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, timeout=5,
            ).stdout.strip() or "Apple Silicon"
        except Exception:
            name = "Apple Silicon"
        return "apple", name, 0.0
    return None, None, 0.0


# (minimum usable GB, ollama model tag, vision model tag, human note)
# Tuned around Ollama's published quantized sizes — a Q4/Q8 model needs
# roughly its parameter count in GB of VRAM/RAM headroom to run comfortably.
_TIERS: list[tuple[float, str, str, str]] = [
    (24.0, "qwen2.5-coder:14b-instruct-q8_0", "llava:13b", "plenty of headroom — a 14B model fits comfortably"),
    (12.0, "qwen2.5-coder:7b-instruct-q8_0", "llava:7b", "the sweet spot this whole stack is tuned for"),
    (8.0, "qwen2.5-coder:7b-instruct-q4_K_M", "llava:7b", "7B fits at a lower quant — a bit less sharp, still solid"),
    (4.0, "qwen2.5-coder:3b-instruct-q4_K_M", "moondream", "tight — a 3B model and a small vision model"),
    (0.0, "qwen3:1.7b", "moondream",
     "very tight — expect a slow, small model; consider adding a mesh peer"),
]


def _recommend(budget_gb: float) -> tuple[str, str, str]:
    for min_gb, model, vision, note in _TIERS:
        if budget_gb >= min_gb:
            return model, vision, note
    return _TIERS[-1][1], _TIERS[-1][2], _TIERS[-1][3]


def detect() -> HardwareReport:
    cpu_model, cpu_cores = _cpu_info()
    ram_gb = _ram_gb()
    gpu_vendor, gpu_name, vram_gb = _gpu_info()
    has_gpu = gpu_vendor is not None

    # What a model actually gets to use: real VRAM on a dedicated GPU, a
    # generous slice of unified memory on Apple Silicon, otherwise a
    # conservative slice of system RAM (leaving room for the OS and
    # everything else running on a CPU-only box).
    if gpu_vendor == "nvidia" and vram_gb > 0:
        budget_gb = vram_gb
    elif gpu_vendor == "apple":
        budget_gb = max(0.0, ram_gb * 0.6)
    else:
        budget_gb = max(0.0, ram_gb * 0.4)

    model, vision_model, note = _recommend(budget_gb)
    notes = [note]
    if not has_gpu:
        notes.append("no dedicated GPU detected — running on CPU will be noticeably slower")
    if ram_gb == 0.0:
        notes.append("couldn't detect RAM on this platform — defaulting conservatively")

    return HardwareReport(
        cpu_model=cpu_model, cpu_cores=cpu_cores, ram_gb=ram_gb,
        gpu_vendor=gpu_vendor, gpu_name=gpu_name, vram_gb=vram_gb, has_gpu=has_gpu,
        os_name=f"{platform.system()} {platform.release()}",
        recommended_model=model, recommended_vision_model=vision_model, notes=notes,
    )
