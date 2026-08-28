import { useState } from 'react';
import { simulateBeam, type BeamResult } from '../api';

const MATERIALS = ['aluminum', 'steel', 'titanium', 'wood_pine', 'abs_plastic'];

export default function StructuresPanel() {
  const [length, setLength] = useState('1.0');
  const [width, setWidth] = useState('0.05');
  const [height, setHeight] = useState('0.05');
  const [force, setForce] = useState('-100');
  const [material, setMaterial] = useState('aluminum');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BeamResult | null>(null);

  async function solve(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setResult(null);
    try {
      setResult(await simulateBeam(
        parseFloat(length) || 1, parseFloat(width) || 0.05, parseFloat(height) || 0.05,
        parseFloat(force) || -100, material,
      ));
    } catch (e) {
      setResult({ ok: false, error: String(e), tip_deflection_m: 0, analytical_deflection_m: 0, agreement_pct: 0, nodes: 0, elements: 0 });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ogun-panel">
      <div className="ogun-panel-head">
        <h3>Physical lab — cantilever beam (FEA)</h3>
      </div>
      <form className="ogun-inline-form beam-form" onSubmit={solve}>
        <label>Length (m)<input value={length} onChange={(e) => setLength(e.target.value)} inputMode="decimal" /></label>
        <label>Width (m)<input value={width} onChange={(e) => setWidth(e.target.value)} inputMode="decimal" /></label>
        <label>Height (m)<input value={height} onChange={(e) => setHeight(e.target.value)} inputMode="decimal" /></label>
        <label>Tip force (N)<input value={force} onChange={(e) => setForce(e.target.value)} inputMode="decimal" /></label>
        <label>
          Material
          <select value={material} onChange={(e) => setMaterial(e.target.value)}>
            {MATERIALS.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
        <button type="submit" disabled={busy}>{busy ? 'Solving…' : 'Solve'}</button>
      </form>

      {result && !result.ok && <p className="section-warn">{result.error}</p>}
      {result?.ok && (
        <div className="beam-result">
          <div className="beam-stat">
            <strong>{(result.tip_deflection_m * 1000).toFixed(3)} mm</strong>
            <span>FEA tip deflection</span>
          </div>
          <div className="beam-stat">
            <strong>{(result.analytical_deflection_m * 1000).toFixed(3)} mm</strong>
            <span>beam-theory deflection</span>
          </div>
          <div className="beam-stat">
            <strong>{result.agreement_pct.toFixed(1)}%</strong>
            <span>agreement · {result.nodes} nodes, {result.elements} elements</span>
          </div>
          {result.max_stress_note && <p className="screen-note">{result.max_stress_note}</p>}
        </div>
      )}
    </div>
  );
}
