// Pure helpers of the live prospects map: grid clustering by zoom, filters and facets. No DOM, no network.
export const CELL_PX = 64;
export const POLL_MS = 20000; // Render's free plan has no WebSocket worker: the map polls, visibly, while the tab is shown

const worldPx = (lat, lon, zoom) => {
  const scale = 256 * 2 ** zoom;
  const s = Math.sin((Math.max(-85, Math.min(85, lat)) * Math.PI) / 180);
  return { x: ((lon + 180) / 360) * scale, y: (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * scale };
};

// Points close on screen at this zoom form one cluster; its position is the mean of its members.
export function clusterPoints(points, zoom) {
  const cells = new Map();
  for (const p of points) {
    const { x, y } = worldPx(p.lat, p.lon, zoom);
    const key = `${Math.floor(x / CELL_PX)}:${Math.floor(y / CELL_PX)}`;
    if (!cells.has(key)) cells.set(key, []);
    cells.get(key).push(p);
  }
  return [...cells.entries()].map(([key, members]) => {
    const lat = members.reduce((a, m) => a + m.lat, 0) / members.length;
    const lon = members.reduce((a, m) => a + m.lon, 0) / members.length;
    return { key, lat, lon, count: members.length, members };
  });
}

export const hasFilter = (f) => Boolean(f.vertical || f.status || f.minScore !== "" || f.signal);

export const EMPTY_FILTER = { vertical: "", status: "", minScore: "", signal: "" };

// A prospect without a score never passes a score threshold: "not scored" is not 0 and not a pass.
export function applyFilter(points, f) {
  const min = f.minScore === "" || f.minScore === null || f.minScore === undefined ? null : Number(f.minScore);
  return points.filter(
    (p) =>
      (!f.vertical || p.vertical === f.vertical) &&
      (!f.status || p.review_status === f.status) &&
      (min === null || (p.score !== null && p.score !== undefined && p.score >= min)) &&
      (!f.signal || (p.signals || []).includes(f.signal)),
  );
}

const countBy = (points, pick) => {
  const m = new Map();
  points.forEach((p) => pick(p).forEach((v) => m.set(v, (m.get(v) || 0) + 1)));
  return [...m.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]))).map(([value, count]) => ({ value, count }));
};

// Choices offered by the filters come from the data itself, never from a fixed list.
export const facets = (points) => ({
  verticals: countBy(points, (p) => (p.vertical ? [p.vertical] : [])),
  signals: countBy(points, (p) => p.signals || []),
});

export const filterSummary = (shown, all) =>
  all === 0
    ? "No prospect with a position yet."
    : shown === all
      ? `${all} prospect${all === 1 ? "" : "s"} on the map.`
      : `${shown} of ${all} prospects match the filters.`;

// Ids that appeared since the previous poll: the map flags them as new instead of hiding the change.
export const newIds = (previous, current) => {
  if (!previous) return new Set();
  const seen = new Set(previous.map((p) => p.id));
  return new Set(current.filter((p) => !seen.has(p.id)).map((p) => p.id));
};

export const clusterSize = (n) => (n >= 100 ? 52 : n >= 10 ? 44 : 36);

export const signalLabel = (key) => String(key).replace(/_/g, " ");

// Only approved prospects can join a campaign (the API enforces it too): say how many are left out instead of failing silently.
export function campaignPick(points, selectedIds) {
  const chosen = points.filter((p) => selectedIds.has(p.id));
  const ok = chosen.filter((p) => p.review_status === "approved");
  return { ids: ok.map((p) => p.id), excluded: chosen.length - ok.length };
}
