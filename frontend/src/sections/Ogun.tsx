import { useState } from 'react';
import { OgunGlyph } from './Glyph';
import TabNav from './TabNav';
import CadStudio from './CadStudio';
import ChemLabPanel from './ChemLabPanel';
import CircuitLabPanel from './CircuitLabPanel';
import StructuresPanel from './StructuresPanel';
import AerospacePanel from './AerospacePanel';
import ObatalaPanel from './ObatalaPanel';
import MaterialsPanel from './MaterialsPanel';
import './sections.css';
import './ogun.css';

const TABS = [
  { id: 'model', label: 'Model', Panel: CadStudio },
  { id: 'chem', label: 'Chemistry', Panel: ChemLabPanel },
  { id: 'circuits', label: 'Circuits', Panel: CircuitLabPanel },
  { id: 'structures', label: 'Structures', Panel: StructuresPanel },
  { id: 'aerospace', label: 'Aerospace', Panel: AerospacePanel },
  { id: 'obatala', label: 'Living Matter', Panel: ObatalaPanel },
  { id: 'materials', label: 'Materials', Panel: MaterialsPanel },
];

export default function Ogun() {
  const [tab, setTab] = useState('model');
  const Active = TABS.find((t) => t.id === tab)?.Panel ?? CadStudio;

  return (
    <div className="section">
      <header className="section-head">
        <div className="section-glyph-row">
          <OgunGlyph />
          <span className="section-eyebrow">Welcome to the Shrine</span>
        </div>
        <h1>Ogun 3D</h1>
        <p className="section-dek">
          Model it, burn it, wire it, bend it, fly it, grow it — each backed by a real
          open-source engine instead of a guess.
        </p>
      </header>

      <TabNav tabs={TABS} active={tab} onChange={setTab} />
      <Active />

      <div className="tool-groups">
        <div className="tool-group">
          <h3>Still on the roadmap</h3>
          <ul>
            <li><strong>FreeCAD</strong> — no clean apt package in this environment; parts OpenSCAD's CSG language can't express cleanly still need it</li>
            <li><strong>OpenFOAM</strong> — installed and real, but a working case needs mesh/boundary-condition setup that isn't yet reliably automatable from a text description</li>
            <li><strong>XFOIL / OpenVSP</strong> — the packaged xfoil binary crashes (SIGFPE) mid-solve in this environment, a real bug reproduced while evaluating it, not wired up until a working build is confirmed</li>
            <li><strong>PX4 / ArduPilot SITL</strong> — needs a dedicated build environment, too heavy to verify here</li>
            <li><strong>OpenSim</strong> — biomechanics/musculoskeletal simulation, layers in alongside the OpenMM dynamics above</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
