import { useState } from 'react';
import {
  streamChat, fetchRepo, scanSkillScript, saveSkill,
  type FetchRepoResult, type ScanResult, type SkillInputSpec,
} from '../api';

const SYSTEM_PROMPT =
  "You are Ori's Skill Portal. Given a compressed repository (or just a plain " +
  'description if none was fetched) and what the user wants built, reply with ' +
  'ONLY one fenced ```json code block, no prose before or after, containing:\n' +
  '{"manifest": {"skill_id": string, "label": string, "description": string, ' +
  '"inputs": [{"name": string, "label": string, "type": "text"|"number"}]}, ' +
  '"script": "<python source, as a string>"}\n' +
  'The script must read its inputs as one JSON object from sys.argv[1], print a ' +
  'JSON result to stdout, and use only the standard library or a simple HTTP call — ' +
  'never eval, exec, os.system, or shutil.rmtree.';

function extractJson(text: string): unknown | null {
  const match = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  const body = match ? match[1] : text;
  try {
    return JSON.parse(body);
  } catch {
    return null;
  }
}

interface DraftShape {
  manifest?: { skill_id?: string; label?: string; description?: string; inputs?: SkillInputSpec[] };
  script?: string;
}

interface SkillPortalProps {
  onSaved: () => void;
}

export default function SkillPortal({ onSaved }: SkillPortalProps) {
  const [source, setSource] = useState('');
  const [fetching, setFetching] = useState(false);
  const [fetchResult, setFetchResult] = useState<FetchRepoResult | null>(null);

  const [request, setRequest] = useState('');
  const [drafting, setDrafting] = useState(false);

  const [label, setLabel] = useState('');
  const [description, setDescription] = useState('');
  const [script, setScript] = useState('');
  const [inputs, setInputs] = useState<SkillInputSpec[]>([]);

  const [scan, setScan] = useState<ScanResult | null>(null);
  const [scanning, setScanning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  async function doFetch(e: React.FormEvent) {
    e.preventDefault();
    if (!source.trim() || fetching) return;
    setFetching(true);
    setFetchResult(null);
    try {
      setFetchResult(await fetchRepo(source.trim()));
    } catch (err) {
      setFetchResult({ ok: false, error: String(err), source, files_packed: 0, compressed: '', compressed_chars: 0 });
    } finally {
      setFetching(false);
    }
  }

  async function draft(e: React.FormEvent) {
    e.preventDefault();
    if (!request.trim() || drafting) return;
    setDrafting(true);
    setScan(null);
    let acc = '';
    const context = fetchResult?.ok
      ? `Compressed repo (${fetchResult.files_packed} files):\n${fetchResult.compressed}\n\n`
      : '';
    try {
      await streamChat(
        [
          { role: 'system', content: SYSTEM_PROMPT },
          { role: 'user', content: `${context}Build: ${request.trim()}` },
        ],
        (chunk) => { acc += chunk; },
      );
      const parsed = extractJson(acc) as DraftShape | null;
      if (parsed?.manifest && parsed.script) {
        setLabel(parsed.manifest.label || '');
        setDescription(parsed.manifest.description || '');
        setScript(parsed.script);
        setInputs(parsed.manifest.inputs || []);
      } else {
        setScript(`# couldn't parse a draft from the model's reply — edit by hand:\n# ${acc.slice(0, 300)}`);
      }
    } catch (err) {
      setScript(`# couldn't reach the model: ${err}`);
    } finally {
      setDrafting(false);
    }
  }

  async function runScan() {
    if (!script.trim() || scanning) return;
    setScanning(true);
    setSaveMsg(null);
    try {
      setScan(await scanSkillScript(script));
    } finally {
      setScanning(false);
    }
  }

  async function save() {
    if (!label.trim() || !script.trim() || saving) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const cleanInputs = inputs.filter((inp) => inp.name.trim());
      const res = await saveSkill(script, { label: label.trim(), description, inputs: cleanInputs });
      setSaveMsg(res.ok ? `Saved "${res.skill?.label}" as a muscle-memory tool below.` : res.error || 'save failed');
      if (res.ok) {
        onSaved();
        setLabel('');
        setDescription('');
        setScript('');
        setInputs([]);
        setScan(null);
      }
    } catch (err) {
      setSaveMsg(String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="ogun-panel">
      <div className="ogun-panel-head">
        <h3>New wishes — the skill portal</h3>
      </div>

      <form className="ogun-inline-form" onSubmit={doFetch}>
        <input
          value={source}
          onChange={(e) => setSource(e.target.value)}
          placeholder="A GitHub repo URL (optional) — Ori compresses it with RepoMix"
        />
        <button type="submit" disabled={fetching || !source.trim()}>
          {fetching ? 'Fetching…' : 'Fetch & compress'}
        </button>
      </form>
      {fetchResult && !fetchResult.ok && <p className="section-warn">{fetchResult.error}</p>}
      {fetchResult?.ok && (
        <p className="screen-note">
          Packed {fetchResult.files_packed} files, {fetchResult.compressed_chars.toLocaleString()} characters.
        </p>
      )}

      <form className="ogun-inline-form" onSubmit={draft} style={{ marginTop: '0.9rem' }}>
        <input
          value={request}
          onChange={(e) => setRequest(e.target.value)}
          placeholder="What should this skill do?"
        />
        <button type="submit" disabled={drafting || !request.trim()}>
          {drafting ? 'Drafting…' : 'Ask Ori to draft it'}
        </button>
      </form>

      <div className="skill-fields">
        <input className="skill-label-input" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Skill name" />
        <input className="skill-label-input" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="One-line description" />
      </div>

      <div className="skill-inputs-editor">
        {inputs.map((inp, i) => (
          <div className="skill-input-row" key={i}>
            <input
              value={inp.name}
              placeholder="arg name (e.g. n)"
              onChange={(e) => setInputs((prev) => prev.map((p, j) => (j === i ? { ...p, name: e.target.value } : p)))}
            />
            <input
              value={inp.label}
              placeholder="field label shown on the card"
              onChange={(e) => setInputs((prev) => prev.map((p, j) => (j === i ? { ...p, label: e.target.value } : p)))}
            />
            <select
              value={inp.type}
              onChange={(e) =>
                setInputs((prev) =>
                  prev.map((p, j) => (j === i ? { ...p, type: e.target.value as SkillInputSpec['type'] } : p)),
                )
              }
            >
              <option value="text">text</option>
              <option value="number">number</option>
            </select>
            <button
              type="button"
              className="row-remove"
              aria-label="Remove input"
              onClick={() => setInputs((prev) => prev.filter((_, j) => j !== i))}
            >
              ×
            </button>
          </div>
        ))}
        <button
          type="button"
          className="skill-add-input-btn"
          onClick={() => setInputs((prev) => [...prev, { name: '', label: '', type: 'text' }])}
        >
          + add input field
        </button>
      </div>

      <textarea
        className="scad-editor"
        value={script}
        onChange={(e) => setScript(e.target.value)}
        placeholder="Python source appears here — reads inputs as JSON from argv[1], prints a JSON result"
        rows={9}
        spellCheck={false}
      />

      <div className="ogun-panel-actions" style={{ display: 'flex', gap: '0.6rem' }}>
        <button onClick={runScan} disabled={!script.trim() || scanning}>
          {scanning ? 'Scanning…' : 'Run security check'}
        </button>
        <button onClick={save} disabled={!label.trim() || !script.trim() || saving || (scan ? !scan.ok : false)}>
          {saving ? 'Saving…' : 'Save as muscle-memory skill'}
        </button>
      </div>

      {scan && (
        <div className={scan.ok ? 'scan-pass' : 'scan-fail'}>
          {scan.ok ? (
            <p className="screen-note">Passed — no banned patterns, no high-severity Bandit findings.</p>
          ) : (
            <ul className="combustion-warnings">
              {scan.ast_findings.map((f, i) => <li key={`a${i}`}>{f}</li>)}
              {scan.bandit_findings.map((f, i) => (
                <li key={`b${i}`}>line {f.line}: {f.text} ({f.test}, {f.severity}/{f.confidence})</li>
              ))}
            </ul>
          )}
          {scan.error && <p className="section-warn">{scan.error}</p>}
        </div>
      )}
      {saveMsg && <p className="screen-note">{saveMsg}</p>}
    </div>
  );
}
