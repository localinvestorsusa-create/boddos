import { useEffect, useState } from 'react';
import { fetchHardware, fetchMeshNodes, type HardwareReport, type MeshNode } from '../api';
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
          <li className="empty">
            No peers yet — add one by pointing another machine's <code>mesh.peers</code> at this one (or vice versa)
            with a shared <code>mesh.psk</code>.
          </li>
        )}
      </ul>
    </div>
  );
}
