import { useState } from 'react';
import { analyzeSequence, runParticleDynamics, type SequenceResult, type DynamicsResult } from '../api';

export default function ObatalaPanel() {
  const [sequence, setSequence] = useState('ATGGCCATTGTAATGGGCCGCTGAAAGGGTGCCCGATAG');
  const [seqBusy, setSeqBusy] = useState(false);
  const [seqResult, setSeqResult] = useState<SequenceResult | null>(null);

  const [particles, setParticles] = useState('8');
  const [dynBusy, setDynBusy] = useState(false);
  const [dynResult, setDynResult] = useState<DynamicsResult | null>(null);

  async function checkSequence(e: React.FormEvent) {
    e.preventDefault();
    if (!sequence.trim() || seqBusy) return;
    setSeqBusy(true);
    setSeqResult(null);
    try {
      setSeqResult(await analyzeSequence(sequence.trim()));
    } catch (e) {
      setSeqResult({ ok: false, error: String(e), kind: '', length: 0 });
    } finally {
      setSeqBusy(false);
    }
  }

  async function runDynamics() {
    if (dynBusy) return;
    setDynBusy(true);
    setDynResult(null);
    try {
      setDynResult(await runParticleDynamics(parseInt(particles, 10) || 8));
    } catch (e) {
      setDynResult({ ok: false, error: String(e), platform: '', energy_kj_mol: [], max_energy_drift_pct: 0 });
    } finally {
      setDynBusy(false);
    }
  }

  return (
    <div className="ogun-panel">
      <div className="ogun-panel-head">
        <h3>Living Matter — Obatala</h3>
      </div>

      <form className="ogun-inline-form" onSubmit={checkSequence}>
        <input value={sequence} onChange={(e) => setSequence(e.target.value)} placeholder="DNA or protein sequence" />
        <button type="submit" disabled={seqBusy || !sequence.trim()}>{seqBusy ? 'Reading…' : 'Analyze sequence'}</button>
      </form>
      {seqResult && !seqResult.ok && <p className="section-warn">{seqResult.error}</p>}
      {seqResult?.ok && (
        <ul className="combustion-products" style={{ marginTop: '0.7rem' }}>
          <li><span>kind</span><em>{seqResult.kind}</em></li>
          {seqResult.gc_fraction != null && <li><span>GC content</span><em>{(seqResult.gc_fraction * 100).toFixed(1)}%</em></li>}
          {seqResult.molecular_weight_da != null && <li><span>molecular weight</span><em>{seqResult.molecular_weight_da.toFixed(0)} Da</em></li>}
          {seqResult.translated_protein && <li><span>translated</span><em>{seqResult.translated_protein}</em></li>}
          {seqResult.protein_molecular_weight_da != null && <li><span>protein MW</span><em>{seqResult.protein_molecular_weight_da.toFixed(1)} Da</em></li>}
          {seqResult.instability_index != null && <li><span>instability index</span><em>{seqResult.instability_index.toFixed(1)}</em></li>}
        </ul>
      )}

      <div className="ogun-panel-actions" style={{ marginTop: '1.3rem', display: 'flex', gap: '0.6rem', alignItems: 'center' }}>
        <input
          className="ogun-small-input"
          value={particles}
          onChange={(e) => setParticles(e.target.value)}
          placeholder="particles"
          inputMode="numeric"
        />
        <button onClick={runDynamics} disabled={dynBusy}>{dynBusy ? 'Simulating…' : 'Run particle-chain MD (OpenMM)'}</button>
      </div>
      {dynResult && !dynResult.ok && <p className="section-warn">{dynResult.error}</p>}
      {dynResult?.ok && (
        <p className="screen-note">
          Ran on {dynResult.platform} · max energy drift {dynResult.max_energy_drift_pct.toFixed(3)}% over{' '}
          {dynResult.energy_kj_mol.length} samples — a real, energy-conserving integrator, not a canned animation.
        </p>
      )}
    </div>
  );
}
