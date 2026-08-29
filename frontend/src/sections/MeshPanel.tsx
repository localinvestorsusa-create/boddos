import { useEffect, useState } from 'react';
import {
  fetchHardware, fetchMeshNodes, startPairing, redeemPairing,
  type HardwareReport, type MeshNode, type PairStartResult,
} from '../api';
import './sections.css';
import './ogun.css';

function timeAgo(unixSeconds: number): string {
  const s = Math.max(0, Date.now() / 1000 - unixSeconds);
  if (s < 5) return 'just now';
  if (s < 90) return `${Math.round(s)}s ago`;
  return `${Math.round(s / 60)}m ago`;
}

export default function MeshPanel() {
  const [hardware, setHardware] = useState<HardwareReport | null>(null);
  const [nodes, setNodes] = useState<MeshNode[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [myCode, setMyCode] = useState<PairStartResult | null>(null);
  const [codeBusy, setCodeBusy] = useState(false);

  const [hostUrl, setHostUrl] = useState('');
  const [joinCode, setJoinCode] = useState('');
  const [joinBusy, setJoinBusy] = useState(false);
  const [joinMsg, setJoinMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function refresh() {
    try {
      const [hw, mesh] = await Promise.all([fetchHardware(), fetchMeshNodes()]);
      setHardware(hw);
      setNodes(mesh);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 8000);
    return () => clearInterval(id);
  }, []);

  async function getCode() {
    setCodeBusy(true);
    try {
      setMyCode(await startPairing());
    } catch (e) {
      setError(String(e));
    } finally {
      setCodeBusy(false);
    }
  }

  async function connect(e: React.FormEvent) {
    e.preventDefault();
    if (!hostUrl.trim() || joinCode.trim().length !== 6 || joinBusy) return;
    setJoinBusy(true);
    setJoinMsg(null);
    try {
      const res = await redeemPairing(hostUrl.trim(), joinCode.trim());
      setJoinMsg(res.ok
        ? { ok: true, text: `Connected to ${res.connected_to}.` }
        : { ok: false, text: res.error || 'connect failed' });
      if (res.ok) {
        setJoinCode('');
        refresh();
      }
    } catch (err) {
      setJoinMsg({ ok: false, text: String(err) });
    } finally {
      setJoinBusy(false);
    }
  }

  return (
    <div className="ogun-panel">
      <div className="ogun-panel-head">
        <h3>This machine &amp; the mesh</h3>
      </div>
      {error && <p className="section-warn">{error}</p>}

      {hardware && (
        <div className="hw-summary">
          <div className="beam-stat">
            <strong>{hardware.cpu_cores} cores</strong>
            <span>{hardware.cpu_model}</span>
          </div>
          <div className="beam-stat">
            <strong>{hardware.ram_gb} GB RAM</strong>
            <span>{hardware.has_gpu ? `${hardware.gpu_name} · ${hardware.vram_gb} GB VRAM` : 'no dedicated GPU'}</span>
          </div>
          <div className="beam-stat">
            <strong>{hardware.recommended_model}</strong>
            <span>recommended model for this machine</span>
          </div>
        </div>
      )}
      {hardware?.notes.map((n, i) => <p key={i} className="screen-note">{n}</p>)}

      <ul className="mesh-node-list">
        {(nodes ?? []).map((n, i) => (
          <li key={n.id} className="mesh-node-row">
            <div>
              <strong>{n.name || n.id}</strong>{i === 0 && <span className="mesh-self-tag">this machine</span>}
              <span className="mesh-node-url">{n.url}</span>
            </div>
            <div className="mesh-node-specs">
              <span>{n.ram_gb} GB{n.has_gpu ? ` · ${n.gpu_name || 'GPU'}` : ''}</span>
              <span>{n.models.length ? n.models.join(', ') : 'no models pulled'}</span>
              <span>{timeAgo(n.last_seen)}</span>
            </div>
          </li>
        ))}
        {nodes && nodes.length <= 1 && (
          <li className="empty">No peers yet — connect one below.</li>
        )}
      </ul>

      <div className="pair-section">
        <div className="pair-col">
          <h4>On this machine, give a code to another</h4>
          {!myCode ? (
            <button onClick={getCode} disabled={codeBusy}>
              {codeBusy ? 'Generating…' : 'Get a code for this machine'}
            </button>
          ) : (
            <div className="pair-code-display">
              <span className="pair-code">{myCode.code}</span>
              <span className="pair-code-addr">at <code className="mono">{myCode.my_url}</code></span>
              <span className="pair-code-hint">
                Enter both on the other machine's Mesh tab. Valid {Math.round(myCode.expires_in_s / 60)} minutes,
                one-time use.
              </span>
              <button className="pair-code-refresh" onClick={getCode} disabled={codeBusy}>
                {codeBusy ? 'Generating…' : 'New code'}
              </button>
            </div>
          )}
        </div>

        <div className="pair-col">
          <h4>On this machine, connect to another</h4>
          <form className="pair-connect-form" onSubmit={connect}>
            <input
              value={hostUrl}
              onChange={(e) => setHostUrl(e.target.value)}
              placeholder="its address, e.g. http://192.168.1.42:8787"
            />
            <input
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="6-digit code"
              inputMode="numeric"
              maxLength={6}
            />
            <button type="submit" disabled={joinBusy || !hostUrl.trim() || joinCode.length !== 6}>
              {joinBusy ? 'Connecting…' : 'Connect'}
            </button>
          </form>
          {joinMsg && <p className={joinMsg.ok ? 'screen-note' : 'section-warn'}>{joinMsg.text}</p>}
        </div>
      </div>
    </div>
  );
}
