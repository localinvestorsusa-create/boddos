export interface TabDef {
  id: string;
  label: string;
}

interface TabNavProps {
  tabs: TabDef[];
  active: string;
  onChange: (id: string) => void;
}

export default function TabNav({ tabs, active, onChange }: TabNavProps) {
  return (
    <div className="tab-nav" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={active === t.id}
          className={`tab-btn ${active === t.id ? 'active' : ''}`}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
