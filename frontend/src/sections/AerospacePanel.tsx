import { useState } from 'react';
import { simulateRocket, type RocketResult } from '../api';

export default function AerospacePanel() {
  const [impulse, setImpulse] = useState('2000');
  const [burnTime, setBurnTime] = useState('1.5');
  const [propMass, setPropMass] = useState('0.5');
  const [dryMass, setDryMass] = useState('5');
  const [radius, setRadius] = useState('0.04');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<RocketResult | null>(null);

  async function fly(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setResult(null);
    try {
      setResult(await simulateRocket({
        total_impulse_ns: parseFloat(impulse) || 2000,
        burn_time_s: parseFloat(burnTime) || 1.5,
        propellant_mass_kg: parseFloat(propMass) || 0.5,
        rocket_dry_mass_kg: parseFloat(dryMass) || 5,
        rocket_radius_m: parseFloat(radius) || 0.04,
      }));
    } catch (e) {
      setResult({ ok: false, error: String(e), apogee_m: 0, max_speed_ms: 0, max_acceleration_ms2: 0, time_to_apogee_s: 0, warnings: [] });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ogun-panel">
      <div className="ogun-panel-head">
        <h3>Aerospace — rocket flight</h3>
      </div>
      <form className="ogun-inline-form beam-form" onSubmit={fly}>
        <label>Total impulse (N·s)<input value={impulse} onChange={(e) => setImpulse(e.target.value)} inputMode="decimal" /></label>
        <label>Burn time (s)<input value={burnTime} onChange={(e) => setBurnTime(e.target.value)} inputMode="decimal" /></label>
        <label>Propellant mass (kg)<input value={propMass} onChange={(e) => setPropMass(e.target.value)} inputMode="decimal" /></label>
        <label>Dry mass (kg)<input value={dryMass} onChange={(e) => setDryMass(e.target.value)} inputMode="decimal" /></label>
        <label>Body radius (m)<input value={radius} onChange={(e) => setRadius(e.target.value)} inputMode="decimal" /></label>
        <button type="submit" disabled={busy}>{busy ? 'Flying…' : 'Simulate flight'}</button>
      </form>

      {result && !result.ok && <p className="section-warn">{result.error}</p>}
      {result?.ok && (
        <div className="beam-result">
          <div className="beam-stat">
            <strong>{result.apogee_m.toFixed(0)} m</strong>
            <span>apogee, {result.time_to_apogee_s.toFixed(1)}s</span>
          </div>
          <div className="beam-stat">
            <strong>{result.max_speed_ms.toFixed(0)} m/s</strong>
            <span>max speed</span>
          </div>
          <div className="beam-stat">
            <strong>{result.max_acceleration_ms2.toFixed(0)} m/s²</strong>
            <span>max acceleration</span>
          </div>
          {result.warnings.map((w, i) => (
            <p key={i} className="screen-note">{w}</p>
          ))}
        </div>
      )}
    </div>
  );
}
