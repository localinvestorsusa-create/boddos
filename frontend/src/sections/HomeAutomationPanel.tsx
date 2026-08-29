import { useState } from 'react';
import { discoverSmartDevices, controlSmartDevice, type SmartDevice } from '../api';
import './sections.css';
import './ogun.css';

export default function HomeAutomationPanel() {
  const [devices, setDevices] = useState<SmartDevice[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function discover() {
    setBusy(true);
    setError(null);
    try {
      const res = await discoverSmartDevices();
      if (!res.ok) {
        setError(res.error || 'discovery failed');
      } else {
        setDevices(res.devices);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  function patchDevice(ip: string, patch: Partial<SmartDevice>) {
    setDevices((prev) => (prev ?? []).map((d) => (d.ip === ip ? { ...d, ...patch } : d)));
  }

  async function toggle(d: SmartDevice) {
    patchDevice(d.ip, { is_on: !d.is_on });
    const res = await controlSmartDevice(d.ip, d.is_on ? 'off' : 'on');
    if (!res.ok) {
      patchDevice(d.ip, { is_on: d.is_on });
      setError(res.error || `couldn't reach ${d.ip}`);
    }
  }

  async function brightness(d: SmartDevice, level: number) {
    patchDevice(d.ip, { brightness: level });
    const res = await controlSmartDevice(d.ip, 'brightness', { level });
    if (!res.ok) setError(res.error || `couldn't reach ${d.ip}`);
  }

  return (
    <div className="ogun-panel">
      <div className="ogun-panel-head">
        <h3>Smart home</h3>
        <button onClick={discover} disabled={busy}>
          {busy ? 'Scanning…' : 'Discover devices'}
        </button>
      </div>
      {error && <p className="section-warn">{error}</p>}

      <ul className="mesh-node-list">
        {(devices ?? []).map((d) => (
          <li key={d.ip} className="mesh-node-row home-device-row">
            <div>
              <strong>{d.alias || d.ip}</strong>
              <span className="mesh-node-url">{d.ip} · {d.model}</span>
            </div>
            <div className="home-device-controls">
              {d.is_dimmable && d.is_on && (
                <input
                  type="range"
                  min={1}
                  max={100}
                  value={d.brightness ?? 100}
                  onChange={(e) => brightness(d, Number(e.target.value))}
                  className="home-brightness"
                  aria-label={`${d.alias} brightness`}
                />
              )}
              <button
                className={`home-power-btn ${d.is_on ? 'on' : ''}`}
                onClick={() => toggle(d)}
                aria-pressed={d.is_on}
              >
                {d.is_on ? 'On' : 'Off'}
              </button>
            </div>
          </li>
        ))}
        {devices && devices.length === 0 && (
          <li className="empty">No Kasa devices found — make sure they're on the same network and powered on.</li>
        )}
        {devices === null && !busy && (
          <li className="empty">Click "Discover devices" to scan your network.</li>
        )}
      </ul>
    </div>
  );
}
