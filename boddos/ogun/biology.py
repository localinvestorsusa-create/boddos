"""Living Matter (Obatala) tools: sequence analysis via Biopython, and a
minimal molecular dynamics demo via OpenMM.

The MD piece is deliberately a toy — a chain of particles connected by
harmonic bonds, not a real protein simulation. Simulating an actual
folded protein needs a structure (from ESMFold/AlphaFold) and a real
force field (Amber/CHARMM) as inputs neither of which this pass wires
up; what's here demonstrates the real, working OpenMM integration
(energy-conserving integrator, real physics) that a structure-driven
simulation would plug into later, without overclaiming biological
realism it doesn't have yet.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import OgunCfg

try:
    from Bio.Seq import Seq
    from Bio.SeqUtils import gc_fraction, molecular_weight
    from Bio.SeqUtils.ProtParam import ProteinAnalysis
except ImportError:  # pragma: no cover - exercised via the ok=False path
    Seq = None

try:
    import openmm as mm
    import openmm.unit as unit
except ImportError:  # pragma: no cover - exercised via the ok=False path
    mm = None

_VALID_BASES = set("ACGTUacgtu")


@dataclass
class SequenceResult:
    ok: bool
    error: str = ""
    kind: str = ""
    length: int = 0
    gc_fraction: float | None = None
    molecular_weight_da: float | None = None
    translated_protein: str | None = None
    protein_molecular_weight_da: float | None = None
    instability_index: float | None = None
    aromaticity: float | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class DynamicsResult:
    ok: bool
    error: str = ""
    platform: str = ""
    energy_kj_mol: list[float] = field(default_factory=list)
    max_energy_drift_pct: float = 0.0

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class BioLab:
    def __init__(self, cfg: OgunCfg):
        self.cfg = cfg

    def sequence_report(self, sequence: str) -> SequenceResult:
        if not self.cfg.enabled:
            return SequenceResult(ok=False, error="Ogun 3D disabled on this node (set ogun.enabled: true)")
        if Seq is None:
            return SequenceResult(ok=False, error="biopython not installed (pip install 'boddos[ogun]')")
        clean = sequence.strip().upper()
        if not clean:
            return SequenceResult(ok=False, error="empty sequence")

        is_nucleotide = set(clean) <= _VALID_BASES.union({"N"})
        if is_nucleotide:
            seq = Seq(clean.replace("U", "T"))
            try:
                protein = str(seq.translate(to_stop=True))
            except Exception:
                protein = ""
            result = SequenceResult(
                ok=True, kind="nucleotide", length=len(clean),
                gc_fraction=gc_fraction(seq), molecular_weight_da=molecular_weight(seq, seq_type="DNA"),
                translated_protein=protein or None,
            )
            if protein:
                pa = ProteinAnalysis(protein)
                result.protein_molecular_weight_da = pa.molecular_weight()
                result.instability_index = pa.instability_index()
                result.aromaticity = pa.aromaticity()
            return result

        try:
            pa = ProteinAnalysis(clean)
            return SequenceResult(
                ok=True, kind="protein", length=len(clean),
                protein_molecular_weight_da=pa.molecular_weight(),
                instability_index=pa.instability_index(),
                aromaticity=pa.aromaticity(),
            )
        except Exception as e:
            return SequenceResult(ok=False, error=f"couldn't parse as nucleotide or protein sequence: {e}")

    def particle_chain_dynamics(
        self, particle_count: int = 8, bond_length_nm: float = 0.15,
        bond_strength: float = 500.0, steps: int = 2000,
    ) -> DynamicsResult:
        if not self.cfg.enabled:
            return DynamicsResult(ok=False, error="Ogun 3D disabled on this node (set ogun.enabled: true)")
        if mm is None:
            return DynamicsResult(ok=False, error="openmm not installed (pip install 'boddos[ogun]')")
        if particle_count < 2:
            return DynamicsResult(ok=False, error="particle_count must be at least 2")

        try:
            system = mm.System()
            for _ in range(particle_count):
                system.addParticle(1.0)

            bonds = mm.HarmonicBondForce()
            for i in range(particle_count - 1):
                bonds.addBond(i, i + 1, bond_length_nm, bond_strength)
            system.addForce(bonds)

            integrator = mm.VerletIntegrator(0.001 * unit.picoseconds)
            context = mm.Context(system, integrator)
            # A slightly stretched chain so there's real dynamics to observe.
            positions = [[i * bond_length_nm * 1.3, 0, 0] for i in range(particle_count)]
            context.setPositions(positions)
            context.setVelocitiesToTemperature(300 * unit.kelvin)

            energies = []
            sample_every = max(1, steps // 200)
            for step in range(steps):
                if step % sample_every == 0:
                    state = context.getState(getEnergy=True)
                    total = state.getKineticEnergy() + state.getPotentialEnergy()
                    energies.append(total.value_in_unit(unit.kilojoules_per_mole))
                integrator.step(1)

            platform = context.getPlatform().getName()
        except Exception as e:
            return DynamicsResult(ok=False, error=f"simulation failed: {e}")

        e0 = energies[0] if energies else 0.0
        drift = max((abs(e - e0) / abs(e0) * 100 if e0 else 0.0) for e in energies) if energies else 0.0
        return DynamicsResult(ok=True, platform=platform, energy_kj_mol=energies, max_energy_drift_pct=drift)
