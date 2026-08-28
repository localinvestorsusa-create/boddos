import { EsuGlyph } from './Glyph';
import './sections.css';

export default function Esu() {
  return (
    <div className="section">
      <header className="section-head">
        <div className="section-glyph-row">
          <EsuGlyph />
          <span className="section-eyebrow">Pathfinder</span>
        </div>
        <h1>Esu Pathways</h1>
        <p className="section-dek">
          Where do you want to go, what do you want to do, or who do you want to reach? Esu proposes
          the tools and, once you confirm, drives them.
        </p>
      </header>

      <div className="tool-groups">
        <div className="tool-group">
          <h3>Navigation &amp; live context</h3>
          <ul>
            <li><strong>OSRM / Valhalla</strong> on OpenStreetMap — open-source turn-by-turn routing</li>
            <li><strong>RTAB-Map / ORB-SLAM3</strong> — builds a live map as you move</li>
            <li><strong>YOLOv11</strong> — object detection along the way</li>
            <li><strong>OpenSky, GTFS feeds</strong> — flights and transit where published openly</li>
          </ul>
        </div>
        <div className="tool-group">
          <h3>Your own communication, automated</h3>
          <ul>
            <li><strong>Playwright</strong> — paced, human-timed sending through your own accounts</li>
            <li>Rate-limited by design: a 1,000-message ask becomes a sequenced plan, not a burst</li>
          </ul>
        </div>
      </div>

      <p className="status-note">
        Scoped deliberately: outreach tools work on lists you already own, and location tooling maps
        your own path — not a lookup service aimed at other people. Not wired up yet; navigation is the
        planned next slice.
      </p>
    </div>
  );
}
