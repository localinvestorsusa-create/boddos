import { OgunGlyph } from './Glyph';
import CadStudio from './CadStudio';
import ChemLabPanel from './ChemLabPanel';
import CircuitLabPanel from './CircuitLabPanel';
import './sections.css';
import './ogun.css';

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
          Describe a part and Ogun writes the OpenSCAD to build it. Describe a mixture and Cantera
          checks how it burns. Sketch a circuit and ngspice tells you how it behaves.
        </p>
      </header>

      <CadStudio />
      <ChemLabPanel />
      <CircuitLabPanel />

      <div className="tool-groups">
        <div className="tool-group">
          <h3>Still on the roadmap</h3>
          <ul>
            <li><strong>FreeCAD</strong> — parametric CAD with real tolerances, for parts OpenSCAD's CSG language can't express cleanly</li>
            <li><strong>CalculiX / OpenFOAM</strong> — structural FEA and CFD, once basic modeling is solid</li>
            <li><strong>Aerospace stack</strong> — OpenVSP, XFLR5, PX4/ArduPilot SITL, RocketPy for the airplane/drone/rocket cases</li>
            <li><strong>Material sourcing</strong> — Materials Project data, plus a search agent for real supplier listings</li>
            <li><strong>Living Matter (Obatala)</strong> — Biopython, OpenMM, OpenSim for human/animal/plant systems</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
