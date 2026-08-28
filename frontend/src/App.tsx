import { useRef, useState } from 'react';
import { Rnd } from 'react-rnd';
import './App.css';
import OrunGlobe from './orun/OrunGlobe';
import { MicLevel, PulseLevel } from './orun/audio';
import Orunmila from './sections/Orunmila';
import Esu from './sections/Esu';
import Ogun from './sections/Ogun';

type View = 'home' | 'orunmila' | 'esu' | 'ogun';

const SECTIONS: { id: View; label: string; blurb: string }[] = [
  { id: 'ogun', label: 'Ogun 3D', blurb: 'Modeling, labs & fabrication' },
  { id: 'orunmila', label: 'Orunmila Wishes', blurb: 'History, models & every tool' },
  { id: 'esu', label: 'Esu Pathfinder', blurb: 'Wayfinding & communication' },
];

export default function App() {
  const [view, setView] = useState<View>('home');
  const micLevel = useRef(new MicLevel()).current;
  const replyLevel = useRef(new PulseLevel()).current;

  return (
    <div className="app">
      <header className="topbar">
        <button className="wordmark" onClick={() => setView('home')}>
          O<span>run</span>
        </button>
        {view !== 'home' && (
          <nav className="topnav">
            {SECTIONS.map((s) => (
              <button key={s.id} className={view === s.id ? 'active' : ''} onClick={() => setView(s.id)}>
                {s.label}
              </button>
            ))}
          </nav>
        )}
      </header>

      <div className="stage">
        {view === 'home' && (
          <div className="home">
            <div className="hero-globe">
              <OrunGlobe micLevel={{ current: micLevel }} replyLevel={{ current: replyLevel }} />
            </div>
            <div className="home-title">
              <h1>Orun</h1>
              <p>Speak, and the line below moves. Reply, and the line above does.</p>
            </div>
            <div className="nav-cards">
              {SECTIONS.map((s) => (
                <button key={s.id} className="nav-card" onClick={() => setView(s.id)}>
                  <div>
                    <strong>{s.label}</strong>
                    <span>{s.blurb}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {view === 'orunmila' && <Orunmila micLevel={micLevel} replyLevel={replyLevel} />}
        {view === 'esu' && <Esu />}
        {view === 'ogun' && <Ogun />}

        {view !== 'home' && (
          <Rnd
            default={{ x: window.innerWidth - 180, y: window.innerHeight - 180, width: 140, height: 140 }}
            minWidth={90}
            minHeight={90}
            maxWidth={260}
            maxHeight={260}
            lockAspectRatio
            bounds="window"
            className="orun-widget"
            style={{ zIndex: 50 }}
          >
            <OrunGlobe
              micLevel={{ current: micLevel }}
              replyLevel={{ current: replyLevel }}
              compact
            />
          </Rnd>
        )}
      </div>
    </div>
  );
}
