// What the map's head-up display says. Pure: every figure is read from the map itself (its centre, its zoom) or from the state of
// the search (busy, area too large); nothing here is a measurement of anything else, and nothing is invented.
export const formatCoord = (lat, lon) =>
  `${Math.abs(lat).toFixed(4)}° ${lat >= 0 ? "N" : "S"}  ${Math.abs(lon).toFixed(4)}° ${lon >= 0 ? "E" : "W"}`;

export const formatZoom = (zoom) => `Z${Number.isInteger(zoom) ? zoom : zoom.toFixed(1)}`;

// The search state of the area on screen, as the HUD words it: scanning while a search runs, "zoom in" when the area is too
// large to be searched, ready otherwise.
export function searchState({ busy, tooLarge }) {
  if (busy) return { key: "scanning", label: "SCANNING" };
  if (tooLarge) return { key: "zoom", label: "ZOOM IN TO SEARCH" };
  return { key: "ready", label: "AREA READY" };
}
