import { OgunGlyph } from './Glyph';
import './sections.css';

export default function Ogun() {
  return (
    <div className="section">
      <header className="section-head">
        <div className="section-glyph-row">
          <OgunGlyph />
          <span className="section-eyebrow">Welcome to the Shrine</span>
        </div>
        <h1>Ogun 3D</h1>
        <p className="section-dek">
          Procedural modeling, fabrication, and the material sciences — split between Dead Matter
          (mechanical, electronic, built things) and Living Matter (biological systems).
        </p>
      </header>

      <div className="tool-groups">
        <div className="tool-group">
          <h3>Dead Matter — modeling &amp; fabrication</h3>
          <ul>
            <li><strong>Blender (bpy)</strong> — headless procedural mesh generation from a description</li>
            <li><strong>FreeCAD</strong> — parametric CAD for mechanical/electronic parts</li>
            <li><strong>KiCad + ngspice</strong> — circuit design and simulation</li>
            <li><strong>PyBullet</strong> — physical-lab simulation before anything is printed</li>
            <li><strong>OctoPrint/Klipper, grblHAL</strong> — 3D printer, CNC and laser cutter control</li>
          </ul>
        </div>
        <div className="tool-group">
          <h3>Chemistry &amp; safety</h3>
          <ul>
            <li><strong>RDKit</strong> — reaction and mixture-safety checks</li>
            <li><strong>PubChem</strong> — hazard/reactivity reference data</li>
          </ul>
        </div>
        <div className="tool-group">
          <h3>Living Matter (Obatala)</h3>
          <ul>
            <li><strong>Biopython, ESMFold</strong> — biological structure and system study</li>
            <li><strong>GBIF / iNaturalist</strong> — species and taxonomy reference data</li>
          </ul>
        </div>
      </div>

      <p className="status-note">
        Not wired up yet — this is the planned tool set. The next slice after the shell and Orunmila's
        chat loop is the Blender scripting round-trip: describe a part, get a mesh back.
      </p>
    </div>
  );
}
