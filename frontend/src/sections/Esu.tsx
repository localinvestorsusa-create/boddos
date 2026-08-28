import { useEffect, useState } from 'react';
import { fetchDirections, type DirectionsResult } from '../api';
import RouteMap from '../orun/RouteMap';
import LookoutCamera from './LookoutCamera';
import { EsuGlyph } from './Glyph';
import './sections.css';

type GeoStatus = 'locating' | 'ok' | 'denied' | 'manual';
type Profile = 'walking' | 'driving' | 'cycling';

function formatDistance(m: number): string {
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`;
}

function formatDuration(s: number): string {
  const mins = Math.round(s / 60);
  if (mins < 60) return `${mins} min`;
  return `${Math.floor(mins / 60)} h ${mins % 60} min`;
}

export default function Esu() {
  const [position, setPosition] = useState<{ lat: number; lon: number } | null>(null);
  const [geoStatus, setGeoStatus] = useState<GeoStatus>('locating');
  const [manualLat, setManualLat] = useState('');
  const [manualLon, setManualLon] = useState('');
  const [destination, setDestination] = useState('');
  const [profile, setProfile] = useState<Profile>('walking');
  const [result, setResult] = useState<DirectionsResult | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!navigator.geolocation) {
      setGeoStatus('denied');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setPosition({ lat: pos.coords.latitude, lon: pos.coords.longitude });
        setGeoStatus('ok');
      },
      () => setGeoStatus('denied'),
      { timeout: 8000 },
    );
  }, []);

  function useManualPosition() {
    const lat = parseFloat(manualLat);
    const lon = parseFloat(manualLon);
    if (Number.isNaN(lat) || Number.isNaN(lon)) return;
    setPosition({ lat, lon });
    setGeoStatus('ok');
  }

  async function getDirections(e: React.FormEvent) {
    e.preventDefault();
    if (!position || !destination.trim() || busy) return;
    setBusy(true);
    setResult(null);
    try {
      const res = await fetchDirections(position.lat, position.lon, destination.trim(), profile);
      setResult(res);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="section">
      <header className="section-head">
        <div className="section-glyph-row">
          <EsuGlyph />
          <span className="section-eyebrow">Pathfinder</span>
        </div>
        <h1>Esu Pathways</h1>
        <p className="section-dek">
          Where do you want to go? Esu draws the path on open map data and keeps a lookout with
          your camera along the way.
        </p>
      </header>

      <form className="esu-form" onSubmit={getDirections}>
        <input
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
          placeholder="Where do you want to go?"
        />
        <select value={profile} onChange={(e) => setProfile(e.target.value as Profile)}>
          <option value="walking">Walking</option>
          <option value="cycling">Cycling</option>
          <option value="driving">Driving</option>
        </select>
        <button type="submit" disabled={!position || busy || !destination.trim()}>
          {busy ? 'Finding path…' : 'Go'}
        </button>
      </form>

      {geoStatus === 'locating' && <p className="section-warn">Finding your location…</p>}
      {geoStatus === 'denied' && (
        <div className="geo-fallback">
          <p className="section-warn">
            Couldn't get your location automatically — enter coordinates to route from instead.
          </p>
          <div className="geo-fallback-row">
            <input
              value={manualLat}
              onChange={(e) => setManualLat(e.target.value)}
              placeholder="latitude"
              inputMode="decimal"
            />
            <input
              value={manualLon}
              onChange={(e) => setManualLon(e.target.value)}
              placeholder="longitude"
              inputMode="decimal"
            />
            <button type="button" onClick={useManualPosition}>
              Set
            </button>
          </div>
        </div>
      )}

      {result && !result.ok && <p className="section-warn">{result.error}</p>}

      {result?.ok && result.geometry && position && result.destination_lat != null && (
        <div className="route-result">
          <div className="route-summary">
            <strong>{result.destination}</strong>
            <span>
              {formatDistance(result.distance_m ?? 0)} · {formatDuration(result.duration_s ?? 0)} ·{' '}
              {profile}
            </span>
          </div>
          <RouteMap
            from={position}
            to={{ lat: result.destination_lat, lon: result.destination_lon! }}
            geometry={result.geometry}
          />
          <ol className="route-steps">
            {(result.steps ?? []).map((s, i) => (
              <li key={i}>
                <span>{s.instruction}</span>
                <em>{formatDistance(s.distance_m)}</em>
              </li>
            ))}
          </ol>
        </div>
      )}

      <LookoutCamera />

      <p className="status-note">
        Directions run on public OpenStreetMap services (Nominatim + OSRM) — point{' '}
        <code>services.routing</code> at a self-hosted instance in your config for real use. Lookout
        uses the same local vision model as camera analysis elsewhere in the app, describing the
        scene rather than running dedicated object detection.
      </p>
      <div className="tool-groups">
        <div className="tool-group">
          <h3>Still on the roadmap</h3>
          <ul>
            <li><strong>RTAB-Map / ORB-SLAM3</strong> — a live map built as you move, not just a route to a fixed destination</li>
            <li><strong>YOLOv11</strong> — dedicated real-time object detection, faster than a full vision-model description</li>
            <li><strong>Local sensing</strong> — nearby BLE/Wi-Fi discovery, transit and flight feeds</li>
            <li>Rate-limited outreach through your own accounts (see the scope note this section shipped with)</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
