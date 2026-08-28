import { useState } from 'react';
import { checkCombustion, type CombustionResult } from '../api';

export default function ChemLabPanel() {
  const [mixture, setMixture] = useState('CH4:1, O2:2, N2:7.52');
  const [tempK, setTempK] = useState('300');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CombustionResult | null>(null);

  async function check(e: React.FormEvent) {
    e.preventDefault();
    if (!mixture.trim() || busy) return;
    setBusy(true);
    setResult(null);
    try {
      setResult(await checkCombustion(mixture.trim(), parseFloat(tempK) || 300));
    } catch (e) {
      setResult({ ok: false, error: String(e), products: {}, warnings: [] });
    } finally {
      setBusy(false);
    }
  }

  const products = result?.ok ? Object.entries(result.products).sort((a, b) => b[1] - a[1]) : [];

  return (
    <div className="ogun-panel">
      <div className="ogun-panel-head">
        <h3>Chemical lab</h3>
      </div>
      <form className="ogun-inline-form" onSubmit={check}>
        <input
          value={mixture}
          onChange={(e) => setMixture(e.target.value)}
          placeholder="Mixture, e.g. CH4:1, O2:2, N2:7.52"
        />
        <input
          value={tempK}
          onChange={(e) => setTempK(e.target.value)}
          placeholder="Initial K"
          inputMode="decimal"
          className="ogun-small-input"
        />
        <button type="submit" disabled={busy || !mixture.trim()}>
          {busy ? 'Checking…' : 'Check combustion'}
        </button>
      </form>
      {result && !result.ok && <p className="section-warn">{result.error}</p>}
      {result?.ok && (
        <div className="combustion-result">
          <div className="combustion-temp">
            <strong>{result.flame_temperature_k?.toFixed(0)} K</strong>
            <span>adiabatic flame temperature</span>
          </div>
          {result.warnings.length > 0 && (
            <ul className="combustion-warnings">
              {result.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
          <ul className="combustion-products">
            {products.map(([name, frac]) => (
              <li key={name}>
                <span>{name}</span>
                <em>{(frac * 100).toFixed(1)}%</em>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
