const COLORS = ['#d9a441', '#5fc3b8', '#e06a5c', '#9aa1c2'];

interface TraceChartProps {
  timeS: number[];
  traces: Record<string, number[]>;
  height?: number;
}

export default function TraceChart({ timeS, traces, height = 200 }: TraceChartProps) {
  const width = 640;
  const pad = 32;
  const names = Object.keys(traces);
  const allValues = names.flatMap((n) => traces[n] ?? []);
  if (!timeS.length || !allValues.length) return null;

  const tMin = timeS[0];
  const tMax = timeS[timeS.length - 1];
  const vMin = Math.min(0, ...allValues);
  const vMax = Math.max(...allValues) || 1;

  const x = (t: number) => pad + ((t - tMin) / (tMax - tMin || 1)) * (width - pad * 2);
  const y = (v: number) => height - pad - ((v - vMin) / (vMax - vMin || 1)) * (height - pad * 2);

  const paths = names.map((name, i) => {
    const values = traces[name] ?? [];
    const d = values.map((v, idx) => `${idx === 0 ? 'M' : 'L'} ${x(timeS[idx]).toFixed(2)} ${y(v).toFixed(2)}`).join(' ');
    return { name, d, color: COLORS[i % COLORS.length] };
  });

  return (
    <svg className="trace-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Simulation trace">
      <line x1={pad} y1={y(0)} x2={width - pad} y2={y(0)} className="trace-axis" />
      <line x1={pad} y1={pad} x2={pad} y2={height - pad} className="trace-axis" />
      {paths.map((p) => (
        <path key={p.name} d={p.d} fill="none" stroke={p.color} strokeWidth={2} />
      ))}
      <g className="trace-legend">
        {paths.map((p, i) => (
          <g key={p.name} transform={`translate(${pad + i * 90}, 14)`}>
            <rect width={10} height={10} fill={p.color} rx={2} />
            <text x={16} y={9} className="trace-legend-label">{p.name}</text>
          </g>
        ))}
      </g>
    </svg>
  );
}
