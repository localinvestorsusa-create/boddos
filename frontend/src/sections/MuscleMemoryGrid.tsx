import { useEffect, useState } from 'react';
import { listSkills, runSkill, deleteSkill, type SkillRecord, type SkillRunResult } from '../api';

interface CardProps {
  skill: SkillRecord;
  onDeleted: () => void;
}

function SkillCard({ skill, onDeleted }: CardProps) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SkillRunResult | null>(null);

  async function run() {
    setBusy(true);
    setResult(null);
    try {
      setResult(await runSkill(skill.slug, values));
    } catch (e) {
      setResult({ ok: false, error: String(e), stdout: '', stderr: '', exit_code: null });
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    await deleteSkill(skill.slug);
    onDeleted();
  }

  return (
    <li className="skill-card">
      <div className="skill-card-head">
        <div>
          <strong>{skill.label}</strong>
          {skill.description && <span className="skill-card-desc">{skill.description}</span>}
        </div>
        <button className="row-remove" onClick={remove} aria-label={`Delete ${skill.label}`}>×</button>
      </div>
      {skill.inputs.length > 0 && (
        <div className="skill-card-inputs">
          {skill.inputs.map((inp) => (
            <input
              key={inp.name}
              placeholder={inp.label}
              inputMode={inp.type === 'number' ? 'decimal' : 'text'}
              value={values[inp.name] ?? ''}
              onChange={(e) => setValues((v) => ({ ...v, [inp.name]: e.target.value }))}
            />
          ))}
        </div>
      )}
      <button className="finder-scan-btn skill-run-btn" onClick={run} disabled={busy}>
        {busy ? 'Running…' : 'Run'}
      </button>
      {result && (
        <p className={result.ok ? 'screen-note' : 'section-warn'}>
          {result.ok ? result.stdout || '(no output)' : result.error || result.stderr}
        </p>
      )}
    </li>
  );
}

export default function MuscleMemoryGrid({ refreshKey }: { refreshKey: number }) {
  const [skills, setSkills] = useState<SkillRecord[] | null>(null);

  async function load() {
    setSkills(await listSkills());
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  return (
    <div className="ogun-panel">
      <div className="ogun-panel-head">
        <h3>Muscle memory</h3>
      </div>
      <ul className="skill-grid">
        {(skills ?? []).map((s) => (
          <SkillCard key={s.slug} skill={s} onDeleted={load} />
        ))}
        {skills && skills.length === 0 && (
          <li className="empty">No skills saved yet — build one above.</li>
        )}
      </ul>
    </div>
  );
}
