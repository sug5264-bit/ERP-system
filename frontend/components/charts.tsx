"use client";

export function BarChart({
  data,
  height = 200,
  format = (v: number) => v.toLocaleString(),
}: {
  data: { label: string; value: number }[];
  height?: number;
  format?: (v: number) => string;
}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  const width = Math.max(300, data.length * 60);
  const barW = (width - 40) / data.length - 10;

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
      {data.map((d, i) => {
        const x = 30 + i * ((width - 40) / data.length);
        const h = max === 0 ? 0 : ((height - 50) * d.value) / max;
        const y = height - 30 - h;
        return (
          <g key={i}>
            <rect x={x} y={y} width={barW} height={h} fill="#0f172a" rx="4" />
            <text
              x={x + barW / 2}
              y={y - 4}
              textAnchor="middle"
              className="fill-slate-700"
              fontSize="10"
            >
              {format(d.value)}
            </text>
            <text
              x={x + barW / 2}
              y={height - 10}
              textAnchor="middle"
              className="fill-slate-600"
              fontSize="10"
            >
              {d.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function PieChart({
  data,
  size = 200,
}: {
  data: { label: string; value: number }[];
  size?: number;
}) {
  const total = data.reduce((s, d) => s + d.value, 0);
  if (total === 0) return <div className="text-sm text-slate-500">데이터 없음</div>;

  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 10;
  const colors = ["#0f172a", "#475569", "#64748b", "#94a3b8", "#cbd5e1", "#1e293b"];

  let acc = 0;
  const slices = data.map((d, i) => {
    const start = (acc / total) * 2 * Math.PI;
    acc += d.value;
    const end = (acc / total) * 2 * Math.PI;
    const x1 = cx + r * Math.sin(start);
    const y1 = cy - r * Math.cos(start);
    const x2 = cx + r * Math.sin(end);
    const y2 = cy - r * Math.cos(end);
    const large = end - start > Math.PI ? 1 : 0;
    const path = `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`;
    return { path, color: colors[i % colors.length], label: d.label, value: d.value };
  });

  return (
    <div className="flex items-center gap-4">
      <svg width={size} height={size}>
        {slices.map((s, i) => (
          <path key={i} d={s.path} fill={s.color} />
        ))}
      </svg>
      <ul className="text-sm space-y-1">
        {slices.map((s, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className="w-3 h-3 inline-block" style={{ background: s.color }} />
            <span>
              {s.label} ({s.value})
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
