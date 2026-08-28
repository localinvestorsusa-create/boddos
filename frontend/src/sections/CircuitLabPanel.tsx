import { useState } from 'react';
import { simulateCircuit, type CircuitComponent, type CircuitResult } from '../api';
import TraceChart from '../orun/TraceChart';

const PRESETS: Record<string, CircuitComponent[]> = {
  'RC low-pass': [
    { type: 'R', a: 'in', b: 'out', value: 1000 },
    { type: 'C', a: 'out', b: '0', value: 1e-6 },
  ],
  'RL circuit': [
    { type: 'R', a: 'in', b: 'mid', value: 100 },
    { type: 'L', a: 'mid', b: 'out', value: 0.1 },
  ],
  'RLC series': [
    { type: 'R', a: 'in', b: 'mid', value: 50 },
    { type: 'L', a: 'mid', b: 'mid2', value: 0.01 },
    { type: 'C', a: 'mid2', b: 'out', value: 1e-6 },
  ],
};

export default function CircuitLabPanel() {
  const [components, setComponents] = useState<CircuitComponent[]>(PRESETS['RC low-pass']);
  const [volts, setVolts] = useState('5');
  const [traceNodes, setTraceNodes] = useState('in,out');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CircuitResult | null>(null);

  function loadPreset(name: string) {
    setComponents(PRESETS[name]);
    setResult(null);
  }

  function updateComponent(i: number, patch: Partial<CircuitComponent>) {
    setComponents((prev) => prev.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));
  }

  function addComponent() {
    setComponents((prev) => [...prev, { type: 'R', a: 'a', b: 'b', value: 1000 }]);
  }

  function removeComponent(i: number) {
    setComponents((prev) => prev.filter((_, idx) => idx !== i));
  }

  async function simulate(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setResult(null);
    const nodes = traceNodes.split(',').map((n) => n.trim()).filter(Boolean);
    try {
      setResult(await simulateCircuit(components, parseFloat(volts) || 5, nodes));
    } catch (e) {
      setResult({ ok: false, error: String(e), time_s: [], traces: {} });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ogun-panel">
      <div className="ogun-panel-head">
        <h3>Physical lab — circuits</h3>
        <div className="preset-buttons">
          {Object.keys(PRESETS).map((name) => (
            <button key={name} type="button" onClick={() => loadPreset(name)}>
              {name}
            </button>
          ))}
        </div>
      </div>

      <table className="component-table">
        <thead>
          <tr>
            <th>Type</th><th>A</th><th>B</th><th>Value</th><th />
          </tr>
        </thead>
        <tbody>
          {components.map((c, i) => (
            <tr key={i}>
              <td>
                <select value={c.type} onChange={(e) => updateComponent(i, { type: e.target.value as CircuitComponent['type'] })}>
                  <option value="R">R (Ω)</option>
                  <option value="C">C (F)</option>
                  <option value="L">L (H)</option>
                </select>
              </td>
              <td><input value={c.a} onChange={(e) => updateComponent(i, { a: e.target.value })} /></td>
              <td><input value={c.b} onChange={(e) => updateComponent(i, { b: e.target.value })} /></td>
              <td>
                <input
                  value={c.value}
                  onChange={(e) => updateComponent(i, { value: parseFloat(e.target.value) || 0 })}
                  inputMode="decimal"
                />
              </td>
              <td>
                <button type="button" className="row-remove" onClick={() => removeComponent(i)} aria-label="Remove component">
                  ×
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button type="button" className="add-row" onClick={addComponent}>+ Add component</button>

      <form className="ogun-inline-form" onSubmit={simulate}>
        <input value={volts} onChange={(e) => setVolts(e.target.value)} placeholder="Source volts" inputMode="decimal" className="ogun-small-input" />
        <input value={traceNodes} onChange={(e) => setTraceNodes(e.target.value)} placeholder="Trace nodes, e.g. in,out" />
        <button type="submit" disabled={busy}>
          {busy ? 'Simulating…' : 'Simulate'}
        </button>
      </form>

      {result && !result.ok && <p className="section-warn">{result.error}</p>}
      {result?.ok && <TraceChart timeS={result.time_s} traces={result.traces} />}
    </div>
  );
}
