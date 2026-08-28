import { useState } from 'react';
import { lookupMaterial, type MaterialResult } from '../api';

export default function MaterialsPanel() {
  const [formula, setFormula] = useState('Fe2O3');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<MaterialResult | null>(null);

  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (!formula.trim() || busy) return;
    setBusy(true);
    setResult(null);
    try {
      setResult(await lookupMaterial(formula.trim()));
    } catch (e) {
      setResult({ ok: false, error: String(e), matches: [] });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ogun-panel">
      <div className="ogun-panel-head">
        <h3>Material properties — Materials Project</h3>
      </div>
      <form className="ogun-inline-form" onSubmit={search}>
        <input value={formula} onChange={(e) => setFormula(e.target.value)} placeholder="Chemical formula, e.g. Fe2O3" />
        <button type="submit" disabled={busy || !formula.trim()}>{busy ? 'Looking up…' : 'Look up'}</button>
      </form>
      {result && !result.ok && <p className="section-warn">{result.error}</p>}
      {result?.ok && (
        <ul className="component-list">
          {result.matches.map((m) => (
            <li key={m.material_id} className="material-row">
              <strong>{m.formula}</strong>
              <span>{m.material_id}</span>
              <span>{m.density_g_cm3 != null ? `${m.density_g_cm3.toFixed(2)} g/cm³` : '—'}</span>
              <span>{m.crystal_system ?? '—'}</span>
            </li>
          ))}
          {result.matches.length === 0 && <li className="empty">No matches.</li>}
        </ul>
      )}
    </div>
  );
}
