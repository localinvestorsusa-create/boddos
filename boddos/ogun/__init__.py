"""Ogun 3D's building tools: parametric modeling, combustion/mixture
chemistry, and circuit simulation — the first three domains from the
Ogun brief, each backed by a real open-source engine rather than an LLM
guess."""
from .cad import CadStudio, ModelResult
from .chemistry import ChemLab, CombustionResult
from .circuits import CircuitLab, CircuitResult
from .structures import StructuresLab, BeamResult
from .aerospace import AerospaceLab, RocketFlightResult
from .biology import BioLab, SequenceResult, DynamicsResult
from .materials import MaterialsLab, MaterialResult

__all__ = [
    "CadStudio", "ModelResult",
    "ChemLab", "CombustionResult",
    "CircuitLab", "CircuitResult",
    "StructuresLab", "BeamResult",
    "AerospaceLab", "RocketFlightResult",
    "BioLab", "SequenceResult", "DynamicsResult",
    "MaterialsLab", "MaterialResult",
]
