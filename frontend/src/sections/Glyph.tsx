/** Small abstract geometric marks in the app's own line-and-node visual
 * language — not reproductions of specific orisha iconography. */
export function OgunGlyph({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <path d="M6 26 L16 6 L26 26" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" />
      <path d="M11 16 H21" stroke="var(--accent)" strokeWidth="2" />
      <circle cx="16" cy="6" r="2.4" fill="var(--accent)" />
    </svg>
  );
}

export function EsuGlyph({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <path d="M16 4 V28 M4 16 H28" stroke="var(--accent-2)" strokeWidth="2" />
      <circle cx="16" cy="16" r="4" stroke="var(--accent-2)" strokeWidth="2" />
    </svg>
  );
}

export function OriGlyph({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <rect x="7" y="7" width="18" height="18" rx="3" stroke="var(--ink)" strokeWidth="2" />
      <circle cx="16" cy="16" r="3.5" fill="var(--ink)" />
    </svg>
  );
}
