// Scale helpers for the small SVG charts: integer ticks from 0, so a count is never drawn as a fraction.
export function niceScale(max) {
  const top = Math.max(1, Math.ceil(max));
  const step = Math.max(1, Math.ceil(top / 4));
  const end = step * Math.ceil(top / step);
  const ticks = [];
  for (let v = 0; v <= end; v += step) ticks.push(v);
  return { end, ticks };
}

export const hasAnyValue = (rows, keys) => rows.some((r) => keys.some((k) => Number(r[k]) > 0));

// Points of a series in a width x height box (left/bottom margins for the axes).
export function linePoints(rows, key, end, { width = 600, height = 240, left = 32, right = 8, top = 10, bottom = 22 } = {}) {
  const x = (i) => left + (rows.length <= 1 ? 0 : (i * (width - left - right)) / (rows.length - 1));
  const y = (v) => top + (1 - Number(v || 0) / end) * (height - top - bottom);
  return { x, y, points: rows.map((r, i) => `${x(i).toFixed(1)},${y(r[key]).toFixed(1)}`) };
}
