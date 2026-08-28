"""Material property lookup for Ogun 3D, via the Materials Project — DFT-
computed properties for 150,000+ materials, the closest thing to
"expert material sourcing" that's genuinely open data rather than a
guess.

Needs a free API key from materialsproject.org (`ogun.materials_api_key`
in config, or the MP_API_KEY environment variable) — unlike every other
Ogun tool, this one depends on an external account and network access,
so it fails cleanly with a clear "not configured" message rather than
attempting a call when no key is present.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from ..config import OgunCfg

try:
    from mp_api.client import MPRester
except ImportError:  # pragma: no cover - exercised via the ok=False path
    MPRester = None


@dataclass
class MaterialResult:
    ok: bool
    error: str = ""
    matches: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class MaterialsLab:
    def __init__(self, cfg: OgunCfg):
        self.cfg = cfg

    def _api_key(self) -> str:
        return self.cfg.materials_api_key or os.environ.get("MP_API_KEY", "")

    def search_by_formula(self, formula: str, limit: int = 5) -> MaterialResult:
        if not self.cfg.enabled:
            return MaterialResult(ok=False, error="Ogun 3D disabled on this node (set ogun.enabled: true)")
        if MPRester is None:
            return MaterialResult(ok=False, error="mp-api not installed (pip install 'boddos[ogun]')")
        if not formula.strip():
            return MaterialResult(ok=False, error="empty formula")
        api_key = self._api_key()
        if not api_key:
            return MaterialResult(ok=False, error=(
                "no Materials Project API key configured — get a free key at "
                "materialsproject.org/api and set ogun.materials_api_key or $MP_API_KEY"
            ))

        try:
            with MPRester(api_key=api_key) as mpr:
                docs = mpr.materials.summary.search(
                    formula=formula.strip(), num_chunks=1, chunk_size=limit,
                    fields=["material_id", "formula_pretty", "density", "band_gap",
                           "energy_above_hull", "symmetry"],
                )
        except Exception as e:
            return MaterialResult(ok=False, error=f"Materials Project lookup failed: {e}")

        matches = [{
            "material_id": str(d.material_id),
            "formula": d.formula_pretty,
            "density_g_cm3": d.density,
            "band_gap_ev": d.band_gap,
            "energy_above_hull_ev": d.energy_above_hull,
            "crystal_system": str(d.symmetry.crystal_system) if d.symmetry else None,
        } for d in docs[:limit]]

        return MaterialResult(ok=True, matches=matches)
