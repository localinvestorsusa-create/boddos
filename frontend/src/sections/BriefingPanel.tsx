import { useEffect, useState } from 'react';
import { fetchBriefing, type Headline } from '../api';
import './sections.css';
import './ogun.css';

export default function BriefingPanel() {
  const [headlines, setHeadlines] = useState<Headline[] | null>(null);
  const [curated, setCurated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetchBriefing();
      if (!res.ok) {
        setError(res.error || "couldn't load the briefing");
      } else {
        setHeadlines(res.headlines);
        setCurated(res.curated);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const grouped = (headlines ?? []).reduce<Record<string, Headline[]>>((acc, h) => {
    (acc[h.category || 'General'] ??= []).push(h);
    return acc;
  }, {});

  return (
    <div className="ogun-panel">
      <div className="ogun-panel-head">
        <h3>Daily briefing</h3>
        <button onClick={load} disabled={busy}>{busy ? 'Loading…' : 'Refresh'}</button>
      </div>
      {error && <p className="section-warn">{error}</p>}
      {headlines && !curated && !error && (
        <p className="screen-note">Showing raw headlines — the AI curation step didn't come back this time.</p>
      )}

      {Object.entries(grouped).map(([category, items]) => (
        <div key={category} className="briefing-group">
          <h4 className="briefing-category">{category}</h4>
          <ul className="component-list planner-list">
            {items.map((h, i) => (
              <li key={i} className="material-row planner-row briefing-row">
                <div>
                  {h.url ? (
                    <a href={h.url} target="_blank" rel="noreferrer"><strong>{h.title}</strong></a>
                  ) : (
                    <strong>{h.title}</strong>
                  )}
                  <span>{h.source}{h.date ? ` · ${h.date}` : ''}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {headlines && headlines.length === 0 && !error && (
        <p className="empty">No headlines available right now — try refreshing.</p>
      )}
    </div>
  );
}
