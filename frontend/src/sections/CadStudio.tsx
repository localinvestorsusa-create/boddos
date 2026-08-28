import { useState } from 'react';
import { streamChat, buildModel, type ModelResult } from '../api';

const SYSTEM_PROMPT =
  'You are Ogun, an OpenSCAD modeler. When asked to design a part, reply with ' +
  'ONLY a single ```scad fenced code block containing valid OpenSCAD source ' +
  '(cubes, cylinders, spheres, booleans, transforms, extrusions). No prose ' +
  'before or after the code block.';

function extractScad(text: string): string {
  const match = text.match(/```(?:scad)?\s*([\s\S]*?)```/);
  return (match ? match[1] : text).trim();
}

export default function CadStudio() {
  const [prompt, setPrompt] = useState('');
  const [scad, setScad] = useState('');
  const [thinking, setThinking] = useState(false);
  const [building, setBuilding] = useState(false);
  const [result, setResult] = useState<ModelResult | null>(null);

  async function design(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim() || thinking) return;
    setThinking(true);
    setResult(null);
    let acc = '';
    try {
      await streamChat(
        [
          { role: 'system', content: SYSTEM_PROMPT },
          { role: 'user', content: prompt.trim() },
        ],
        (chunk) => {
          acc += chunk;
          setScad(extractScad(acc));
        },
      );
    } catch (e) {
      setScad(`// couldn't reach the model: ${e}`);
    } finally {
      setThinking(false);
    }
  }

  async function build() {
    if (!scad.trim() || building) return;
    setBuilding(true);
    setResult(null);
    try {
      setResult(await buildModel(scad));
    } catch (e) {
      setResult({ ok: false, error: String(e), facets: 0 });
    } finally {
      setBuilding(false);
    }
  }

  return (
    <div className="ogun-panel">
      <div className="ogun-panel-head">
        <h3>Modeler</h3>
      </div>
      <form className="ogun-inline-form" onSubmit={design}>
        <input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Describe a part — e.g. a bracket with two mounting holes"
        />
        <button type="submit" disabled={thinking || !prompt.trim()}>
          {thinking ? 'Designing…' : 'Design it'}
        </button>
      </form>
      <textarea
        className="scad-editor"
        value={scad}
        onChange={(e) => setScad(e.target.value)}
        placeholder="OpenSCAD source appears here — edit freely before building"
        rows={8}
        spellCheck={false}
      />
      <div className="ogun-panel-actions">
        <button onClick={build} disabled={!scad.trim() || building}>
          {building ? 'Building…' : 'Build'}
        </button>
      </div>
      {result && !result.ok && (
        <p className="section-warn">
          {result.error}
          {result.log ? ` — ${result.log}` : ''}
        </p>
      )}
      {result?.ok && (
        <div className="model-result">
          {result.image_b64 && <img src={`data:image/png;base64,${result.image_b64}`} alt="Model preview" />}
          <p className="screen-note">
            {result.facets} facets{result.stl_b64 ? ' · STL rendered' : ''}
          </p>
        </div>
      )}
    </div>
  );
}
