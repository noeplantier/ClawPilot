// The map's head-up display: where the view is centred, at what zoom, and whether this area can be searched. Decorative frame
// and vignette are aria-hidden; the readout is real map state (lib/mapHud.js), never a made-up figure.
import { formatCoord, formatZoom, searchState } from "@/lib/mapHud";

export default function MapHud({ center, zoom, busy, tooLarge }) {
  const state = searchState({ busy, tooLarge });
  return (
    <div className="map-hud hidden lg:flex" data-testid="map-hud" aria-label="Map position and search area">
      <span className="map-hud-dot" data-state={state.key} aria-hidden="true" />
      <span data-testid="map-hud-coords">{formatCoord(center[0], center[1])}</span>
      <span className="map-hud-sep" aria-hidden="true">·</span>
      <span data-testid="map-hud-zoom">{formatZoom(zoom)}</span>
      <span className="map-hud-sep" aria-hidden="true">·</span>
      <span data-testid="map-hud-state" data-state={state.key}>{state.label}</span>
    </div>
  );
}
