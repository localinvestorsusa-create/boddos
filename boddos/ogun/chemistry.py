"""Combustion / mixture chemistry checks for Ogun 3D's chemical lab,
backed by Cantera's real reaction mechanisms rather than an LLM guess.

Uses the bundled GRI-Mech 3.0 mechanism (hydrocarbon/air combustion, 53
species) by default — the right scope for "is this combustion mixture
sane and how hot does it get," not a general reaction-prediction engine
for arbitrary chemistry.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import OgunCfg

try:
    import cantera as ct
except ImportError:  # pragma: no cover - exercised via the ok=False path
    ct = None


@dataclass
class CombustionResult:
    ok: bool
    error: str = ""
    flame_temperature_k: float | None = None
    products: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class ChemLab:
    def __init__(self, cfg: OgunCfg):
        self.cfg = cfg

    def combustion(self, mixture: str, initial_temp_k: float = 300.0,
                   pressure_atm: float = 1.0) -> CombustionResult:
        """`mixture` is a Cantera mole-fraction string, e.g. 'CH4:1, O2:2, N2:7.52'."""
        if not self.cfg.enabled:
            return CombustionResult(ok=False, error="Ogun 3D disabled on this node (set ogun.enabled: true)")
        if ct is None:
            return CombustionResult(ok=False, error="cantera not installed (pip install 'boddos[ogun]')")
        if not mixture.strip():
            return CombustionResult(ok=False, error="empty mixture")

        try:
            gas = ct.Solution(self.cfg.chemistry_mechanism)
            gas.TPX = initial_temp_k, pressure_atm * ct.one_atm, mixture
        except Exception as e:
            return CombustionResult(ok=False, error=f"couldn't parse mixture: {e}")

        try:
            gas.equilibrate("HP")
        except Exception as e:
            return CombustionResult(ok=False, error=f"no stable equilibrium found — check the mixture: {e}")

        warnings: list[str] = []
        if gas.T > 3500:
            warnings.append("flame temperature is extreme (>3500K) — double-check the mixture ratio")
        if gas.T < initial_temp_k + 50:
            warnings.append("barely any temperature rise — this mixture may not actually combust")

        products = {sp: float(x) for sp, x in zip(gas.species_names, gas.X) if x > 0.01}
        return CombustionResult(ok=True, flame_temperature_k=float(gas.T), products=products, warnings=warnings)
