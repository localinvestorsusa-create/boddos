import { useEffect, useRef, useState } from 'react';
import {
  scanForDevices, trackDevice, stopTrackingDevice, fetchFinderStatus,
  type FoundDevice, type FinderStatus,
} from '../api';
import './sections.css';
import './ogun.css';

const PROXIMITY_METER: Record<string, number> = {
  'very close': 4, nearby: 3, far: 2, 'very far': 1, '': 0,
};

export default function FinderPanel() {
  const [scanning, setScanning] = useState(false);
  const [devices, setDevices] = useState<FoundDevice[] | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [status, setStatus] = useState<FinderStatus | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    fetchFinderStatus().then((s) => { if (s.tracking) startPolling(); setStatus(s); });
    return () => stopPolling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startPolling() {
    stopPolling();
    pollRef.current = setInterval(async () => {
      const s = await fetchFinderStatus();
      setStatus(s);
    }, 1500);
  }

  function stopPolling() {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = null;
  }

  async function scan() {
    setScanning(true);
    setScanError(null);
    setDevices(null);
    try {
      const res = await scanForDevices();
      if (!res.ok) {
        setScanError(res.error || 'scan failed');
      } else {
        setDevices(res.devices);
      }
    } catch (e) {
      setScanError(String(e));
    } finally {
      setScanning(false);
    }
  }

  async function track(d: FoundDevice) {
    const s = await trackDevice(d.address, d.name);
    setStatus(s);
    if (s.tracking) startPolling();
  }

  async function stop() {
    stopPolling();
    const s = await stopTrackingDevice();
    setStatus(s);
  }

  const meter = status ? PROXIMITY_METER[status.proximity] ?? 0 : 0;

  return (
    <div className="ogun-panel">
      <div className="ogun-panel-head">
        <h3>Find a device</h3>
        {!status?.tracking && (
          <button className="finder-scan-btn" onClick={scan} disabled={scanning}>
            {scanning ? 'Scanning…' : 'Scan for nearby devices'}
          </button>
        )}
      </div>

      {scanError && <p className="section-warn">{scanError}</p>}

      {status?.tracking ? (
        <div className="finder-tracking">
          <div className="finder-target">
            <strong>{status.name || status.address}</strong>
            <span>{status.address}</span>
          </div>
          <div className="finder-meter" aria-hidden="true">
            {[1, 2, 3, 4].map((i) => (
              <span key={i} className={i <= meter ? 'lit' : ''} />
            ))}
          </div>
          <p className="finder-readout">
            {status.proximity || 'reading…'} · {status.trend}
            {status.rssi != null && <span className="mono-text"> · {status.rssi} dBm</span>}
          </p>
          {status.last_seen_s_ago != null && (
            <p className="screen-note">last heard from {status.last_seen_s_ago.toFixed(0)}s ago</p>
          )}
          <button className="finder-stop-btn" onClick={stop}>Stop</button>
        </div>
      ) : (
        <ul className="mesh-node-list">
          {(devices ?? []).map((d) => (
            <li key={d.address} className="mesh-node-row">
              <div>
                <strong>{d.name}</strong>
                <span className="mesh-node-url">{d.address}</span>
              </div>
              <div className="mesh-node-specs">
                <span>{d.rssi} dBm</span>
                <button className="finder-track-btn" onClick={() => track(d)}>Track this</button>
              </div>
            </li>
          ))}
          {devices && devices.length === 0 && (
            <li className="empty">No BLE devices heard in that scan.</li>
          )}
        </ul>
      )}
    </div>
  );
}
