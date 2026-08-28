import { useState } from 'react';
import './sections.css';

interface ScreenEl {
  label: string;
  kind: string;
  x: number;
  y: number;
}

interface LookResponse {
  ok: boolean;
  error?: string;
  image_b64?: string;
  elements?: ScreenEl[];
}

interface ActionResponse {
  ok: boolean;
  error?: string;
  raw?: string;
}

export default function ScreenControl() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [image, setImage] = useState<string | null>(null);
  const [elements, setElements] = useState<ScreenEl[]>([]);
  const [note, setNote] = useState<string | null>(null);

  async function look() {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const res = await fetch('/api/agent/screen/look', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const data: LookResponse = await res.json();
      if (!data.ok) {
        setError(data.error || 'screen agent unavailable');
        setElements([]);
        setImage(null);
        return;
      }
      setImage(data.image_b64 ?? null);
      setElements(data.elements ?? []);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function clickElement(el: ScreenEl) {
    setNote(null);
    try {
      const res = await fetch('/api/agent/screen/click', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ x: el.x, y: el.y, confirm: true }),
      });
      const data: ActionResponse = await res.json();
      setNote(data.ok ? `Clicked "${el.label}".` : `Couldn't click: ${data.error}`);
    } catch (e) {
      setNote(`Couldn't click: ${e}`);
    }
  }

  return (
    <div className="screen-control">
      <div className="screen-control-head">
        <h3>Screen control</h3>
        <button onClick={look} disabled={busy}>
          {busy ? 'Looking…' : 'Look at my screen'}
        </button>
      </div>
      {error && <p className="section-warn">{error}</p>}
      {note && <p className="screen-note">{note}</p>}
      {image && (
        <div className="screen-preview">
          <img src={`data:image/png;base64,${image}`} alt="Current screen" />
          <ul>
            {elements.map((el, i) => (
              <li key={i}>
                <span>
                  <em>{el.kind}</em> {el.label}
                </span>
                <button onClick={() => clickElement(el)}>Click</button>
              </li>
            ))}
            {elements.length === 0 && (
              <li className="empty">No elements parsed from the model's reply.</li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
