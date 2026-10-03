import { linePoints, niceScale } from "@/lib/chartMath";

const AXIS = "#6B6B66";

// Horizontal bars with the exact value printed at the end of each bar (no hover needed to read a number).
export function HBarChart({ items, label }) {
  const { end } = niceScale(Math.max(...items.map((i) => i.value), 0));
  return (
    <ul className="space-y-3" aria-label={label}>
      {items.map((i) => (
        <li key={i.name} className="flex items-center gap-3">
          <span className="mono-accent w-24 shrink-0">{i.name}</span>
          <span className="flex-1 h-6 bg-[#F0F0EA] rounded-sm overflow-hidden relative">
            <span className="block h-full rounded-r" style={{ width: `${(i.value / end) * 100}%`, background: i.fill }} />
            <span className="absolute inset-0 flex items-center justify-end pr-2 font-mono text-xs text-[#0A0A0A]">{i.value}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

// Vertical bars with integer axis.
export function VBarChart({ rows, labelKey, valueKey, label, color = "#0F172A" }) {
  const W = 600, H = 240, left = 32, bottom = 22, top = 10;
  const { end, ticks } = niceScale(Math.max(...rows.map((r) => Number(r[valueKey]) || 0), 0));
  const y = (v) => top + (1 - v / end) * (H - top - bottom);
  const slot = (W - left - 8) / Math.max(rows.length, 1);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} className="w-full h-[260px]">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={left} x2={W - 8} y1={y(t)} y2={y(t)} stroke="#F0F0EA" />
          <text x={left - 6} y={y(t) + 4} textAnchor="end" fontSize="11" fill={AXIS}>{t}</text>
        </g>
      ))}
      {rows.map((r, i) => {
        const v = Number(r[valueKey]) || 0;
        const x = left + i * slot + slot * 0.2;
        return (
          <g key={r[labelKey]}>
            <rect x={x} y={y(v)} width={slot * 0.6} height={y(0) - y(v)} rx="3" fill={color}><title>{`${r[labelKey]}: ${v}`}</title></rect>
            <text x={x + slot * 0.3} y={H - 6} textAnchor="middle" fontSize="11" fill={AXIS}>{r[labelKey]}</text>
          </g>
        );
      })}
    </svg>
  );
}

// An area (first key) and a line (second key) over the days of the series.
export function AreaLineChart({ rows, areaKey, lineKey, label, areaColor = "#0F172A", lineColor = "#DC2626" }) {
  const W = 600, H = 240, left = 32, bottom = 22;
  const { end, ticks } = niceScale(Math.max(...rows.flatMap((r) => [Number(r[areaKey]) || 0, Number(r[lineKey]) || 0]), 0));
  const area = linePoints(rows, areaKey, end);
  const line = linePoints(rows, lineKey, end);
  const base = area.y(0);
  const step = Math.max(1, Math.ceil(rows.length / 6));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} className="w-full h-[260px]">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={left} x2={W - 8} y1={area.y(t)} y2={area.y(t)} stroke="#F0F0EA" />
          <text x={left - 6} y={area.y(t) + 4} textAnchor="end" fontSize="11" fill={AXIS}>{t}</text>
        </g>
      ))}
      {rows.length > 0 && <polygon points={`${area.x(0)},${base} ${area.points.join(" ")} ${area.x(rows.length - 1)},${base}`} fill={areaColor} fillOpacity="0.15" />}
      <polyline points={area.points.join(" ")} fill="none" stroke={areaColor} strokeWidth="2" />
      <polyline points={line.points.join(" ")} fill="none" stroke={lineColor} strokeWidth="2" />
      {rows.map((r, i) => (
        <g key={r.date || i}>
          <circle cx={area.x(i)} cy={area.y(r[areaKey])} r="3" fill={areaColor}><title>{`${r.date}: ${r[areaKey] || 0} / ${r[lineKey] || 0}`}</title></circle>
          {i % step === 0 && <text x={area.x(i)} y={H - 6 + (bottom - 22)} textAnchor="middle" fontSize="11" fill={AXIS}>{String(r.date).slice(5)}</text>}
        </g>
      ))}
    </svg>
  );
}
