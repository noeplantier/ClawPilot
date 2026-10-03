/* global ResizeObserver, AbortController */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { ArrowsOut, ArrowsIn, CaretDoubleRight, CaretDoubleLeft, MagnifyingGlass, MapPin } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, importsApi, mapApi, prospectsApi, useAsync } from "@/lib/outreach";
import { describeApiError } from "@/lib/outreachFormat";
import {
  CATEGORY_LABELS, IMPORT_ORIGIN, MAX_SITES_CHECKED, STATUS_COLOR, STATUS_LABEL, areaTooLarge, importRows, knownIds, markerColor,
  mineSummary, summaryText,
} from "@/lib/mapSearch";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";

const START = { center: [45.764, 4.8357], zoom: 14 }; // Lyon; move the map anywhere in the world
const BASEMAPS = {
  light: { label: "Light", url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", credit: "© OpenStreetMap contributors © CARTO" },
  dark: { label: "Dark", url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", credit: "© OpenStreetMap contributors © CARTO" },
  osm: { label: "Standard", url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png", credit: "© OpenStreetMap contributors" },
};
const GLASS = "bg-white/85 backdrop-blur-md border border-white/60 shadow-xl rounded-2xl";

const minePin = (p) =>
  L.divIcon({
    className: "map-pin",
    html: `<span style="--c:${STATUS_COLOR[p.review_status]}" class="map-pin-square"></span>`,
    iconSize: [22, 22], iconAnchor: [11, 11], popupAnchor: [0, -10],
  });

function minePopup(p) {
  const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  return `<strong>${esc(p.name)}</strong><div>${p.city ? esc(p.city) : "<i>city not set</i>"}</div><div><b>status</b> ${STATUS_LABEL[p.review_status]} · <b>e-mail</b> ${p.has_email ? "known" : "<i>not known</i>"}</div>` +
    `<div><a href="/app/prospects/${esc(p.id)}">Open the prospect</a></div>`;
}

const pin = (p, active) =>
  L.divIcon({
    className: "map-pin",
    html: `<span style="--c:${markerColor(p)}" class="map-pin-dot${active ? " is-active" : ""}"></span>`,
    iconSize: [22, 22], iconAnchor: [11, 11], popupAnchor: [0, -10],
  });

const bounds = (map) => {
  const b = map.getBounds();
  return { south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast() };
};

function popupHtml(p) {
  const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const line = (label, value) => `<div><b>${label}</b> ${value ? esc(value) : "<i>not published</i>"}</div>`;
  const place = [p.address, p.postcode, p.city].filter(Boolean).join(", ");
  const site = p.website ? `<a href="${esc(p.website)}" target="_blank" rel="noopener noreferrer">${esc(p.website)}</a>` : "";
  return `<strong>${esc(p.name)}</strong>${line("address", place)}${line("phone", p.phone)}${line("e-mail", p.email)}<div><b>site</b> ${site || "<i>not published</i>"}</div>` +
    `<div><a href="${esc(p.source_url)}" target="_blank" rel="noopener noreferrer">source on OpenStreetMap</a></div>`;
}

function ImportPanel({ selected, onDone }) {
  const [attest, setAttest] = useState(false);
  const [checkSites, setCheckSites] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await importsApi.submit({
        format: "json", content: JSON.stringify(importRows(selected)), filename: "map-selection.json",
        origin: IMPORT_ORIGIN, legal_basis: "legitimate_interest_b2b", country: "FR", language: "fr", vertical: "local business",
        preview: false, attestation: attest, check_websites: checkSites,
      });
      toast.success(`Imported: ${out.created} new, ${out.updated} updated${checkSites ? ` · ${out.sites_checked} website(s) checked` : ""}. All wait for your review.`);
      onDone();
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="surface p-4 space-y-3" data-testid="map-import">
      <h2 className="font-display text-lg font-bold">Import {selected.length} selected place{selected.length === 1 ? "" : "s"}</h2>
      <p className="text-xs text-[#5F5F5A]">
        They become prospects waiting for your review, with their OpenStreetMap page as provenance. Nothing is sent.
      </p>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" checked={checkSites} onChange={(e) => setCheckSites(e.target.checked)} className="mt-1" data-testid="map-check-sites" />
        <span>Look for a public contact e-mail on each business&apos;s own website (robots.txt respected, {MAX_SITES_CHECKED} sites max per import). Needs FEATURE_EXTERNAL_SOURCES.</span>
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" checked={attest} onChange={(e) => setAttest(e.target.checked)} className="mt-1" data-testid="map-attest" />
        <span>I confirm that I may use these professional contact details for B2B prospecting (legitimate interest), and that I will honour opt-outs.</span>
      </label>
      {error && <div role="alert" className="text-sm text-[#991B1B]" data-testid="map-import-error">{error}</div>}
      <button className="btn-ink" disabled={busy || !attest || selected.length === 0} onClick={send} data-testid="map-import-run">
        {busy ? "IMPORTING…" : `IMPORT ${selected.length}`}
      </button>
    </div>
  );
}

function MapView({ canImport }) {
  const root = useRef(null);
  const el = useRef(null);
  const map = useRef(null);
  const layer = useRef(null);
  const tiles = useRef(null);
  const [base, setBase] = useState("light");
  const [category, setCategory] = useState("restaurants");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [tooLarge, setTooLarge] = useState(false);
  const [panelOpen, setPanelOpen] = useState(() => window.innerWidth >= 768);
  const [full, setFull] = useState(false);
  const [query, setQuery] = useState("");
  const [cities, setCities] = useState([]);
  const [mine, setMine] = useState([]);
  const [showMine, setShowMine] = useState(true);
  const mineLayer = useRef(null);

  useEffect(() => {
    const m = L.map(el.current, { center: START.center, zoom: START.zoom, zoomControl: false });
    L.control.zoom({ position: "bottomleft" }).addTo(m);
    mineLayer.current = L.layerGroup().addTo(m);
    layer.current = L.layerGroup().addTo(m);
    const check = () => setTooLarge(areaTooLarge(bounds(m)));
    m.on("moveend", check);
    check();
    map.current = m;
    const watch = new ResizeObserver(() => m.invalidateSize());
    watch.observe(el.current);
    return () => { watch.disconnect(); m.remove(); };
  }, []);

  useEffect(() => {
    if (!map.current) return;
    if (tiles.current) tiles.current.remove();
    const b = BASEMAPS[base];
    tiles.current = L.tileLayer(b.url, { maxZoom: 19, subdomains: "abcd", attribution: `${b.credit}` }).addTo(map.current);
  }, [base]);

  useEffect(() => {
    const onChange = () => setFull(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const toggleFull = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (root.current && root.current.requestFullscreen) root.current.requestFullscreen();
  };

  // Jump to a town: French national address API (free, no key); only the typed town name leaves the browser.
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) { setCities([]); return undefined; }
    const ctl = new AbortController();
    const t = setTimeout(() => {
      fetch(`https://api-adresse.data.gouv.fr/search/?q=${encodeURIComponent(q)}&type=municipality&limit=5`, { signal: ctl.signal })
        .then((r) => r.json())
        .then((d) => setCities((d.features || []).map((f) => ({ label: `${f.properties.city} (${f.properties.postcode})`, lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0] }))))
        .catch(() => setCities([]));
    }, 300);
    return () => { clearTimeout(t); ctl.abort(); };
  }, [query]);

  useEffect(() => {
    mapApi.prospects().then(setMine).catch(() => setMine([]));
  }, []);

  useEffect(() => {
    if (!mineLayer.current) return;
    mineLayer.current.clearLayers();
    if (!showMine) return;
    mine.forEach((p) => L.marker([p.lat, p.lon], { icon: minePin(p), title: p.name }).bindPopup(minePopup(p), { className: "map-popup" }).addTo(mineLayer.current));
  }, [mine, showMine]);

  const known = useMemo(() => knownIds(mine), [mine]);
  // A place already in the prospects is shown by its prospect pin, not offered again.
  const places = useMemo(() => (result ? result.places.filter((p) => !known.has(p.external_id)) : []), [result, known]);
  const toggle = useCallback((id) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; }), []);

  useEffect(() => {
    if (!layer.current) return;
    layer.current.clearLayers();
    places.forEach((p) => {
      const marker = L.marker([p.lat, p.lon], { icon: pin(p, selected.has(p.external_id)), title: p.name }).bindPopup(popupHtml(p), { className: "map-popup" });
      marker.on("dblclick", () => toggle(p.external_id));
      marker.addTo(layer.current);
    });
  }, [places, selected, toggle]);

  const search = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await mapApi.search({ ...bounds(map.current), category });
      setResult(out);
      setSelected(new Set());
      setPanelOpen(true);
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy(false);
    }
  }, [category]);

  const chosen = places.filter((p) => selected.has(p.external_id));

  return (
    <div ref={root} className="relative w-full h-[calc(100svh-9.5rem)] md:h-[calc(100vh-4.25rem)] min-h-[28rem] overflow-hidden bg-[#EDEBE0]" data-testid="map-page">
      <div ref={el} className="absolute inset-0 z-0" data-testid="map" aria-label="Interactive map" />

      {/* search card */}
      <div className={`absolute z-[500] top-3 left-3 right-3 md:right-auto md:w-[26rem] p-4 space-y-3 ${GLASS}`}>
        <div className="flex items-center justify-between gap-2">
          <div>
            <div className="mono-accent">// live.map</div>
            <h1 className="text-2xl font-black tracking-tighter leading-none">Map search</h1>
          </div>
          <button className="btn-ghost !px-2" onClick={toggleFull} aria-label={full ? "Leave full screen" : "Full screen"} data-testid="map-fullscreen">
            {full ? <ArrowsIn size={16} /> : <ArrowsOut size={16} />}
          </button>
        </div>
        <div className="relative">
          <input className="neo-input w-full" placeholder="Go to a town… (e.g. Lyon)" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Go to a town" data-testid="map-goto" />
          {cities.length > 0 && (
            <ul className={`absolute left-0 right-0 mt-1 z-10 max-h-56 overflow-auto ${GLASS} !rounded-lg`} data-testid="map-cities">
              {cities.map((c) => (
                <li key={c.label}>
                  <button className="w-full text-left px-3 py-2 text-sm hover:bg-[#F4F2E7] flex gap-2 items-center"
                    onClick={() => { map.current.setView([c.lat, c.lon], 14); setQuery(""); setCities([]); }}>
                    <MapPin size={14} /> {c.label}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="flex gap-1.5 flex-wrap" role="group" aria-label="Business category">
          {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
            <button key={k} onClick={() => setCategory(k)} aria-pressed={category === k} data-testid={`map-cat-${k}`}
              className={`px-3 py-1 rounded-full text-xs border transition-colors ${category === k ? "bg-[#0F172A] text-white border-[#0F172A]" : "bg-white/70 border-[#D6D3C8] hover:bg-white"}`}>
              {v.split(",")[0].split(" (")[0]}
            </button>
          ))}
        </div>
        <div className="flex md:hidden gap-1" role="group" aria-label="Map style (mobile)">
          {Object.entries(BASEMAPS).map(([k, v]) => (
            <button key={k} onClick={() => setBase(k)} aria-pressed={base === k}
              className={`px-3 py-1 rounded-full text-xs border ${base === k ? "bg-[#0F172A] text-white border-[#0F172A]" : "bg-white/70 border-[#D6D3C8]"}`}>{v.label}</button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-xs" data-testid="map-mine-toggle">
          <input type="checkbox" checked={showMine} onChange={(e) => setShowMine(e.target.checked)} />
          <span><b>My prospects</b> (squares) — {mineSummary(mine)}</span>
        </label>
        <button className="btn-ink w-full justify-center" onClick={search} disabled={busy || tooLarge} data-testid="map-search">
          <MagnifyingGlass size={14} /> {busy ? "SEARCHING…" : "SEARCH THIS AREA"}
        </button>
        {tooLarge && <p className="text-xs text-[#92400E]" data-testid="map-zoom-hint">Zoom in on a town or a neighbourhood to search.</p>}
        {error && <div role="alert" className="text-sm text-[#991B1B]" data-testid="map-error">{error}</div>}
      </div>

      {/* basemap switch */}
      <div className={`hidden md:flex absolute z-[500] top-3 right-3 gap-1 p-1 ${GLASS} !rounded-full ${panelOpen ? "md:right-[25rem]" : ""}`} role="group" aria-label="Map style">
        {Object.entries(BASEMAPS).map(([k, v]) => (
          <button key={k} onClick={() => setBase(k)} aria-pressed={base === k} data-testid={`map-base-${k}`}
            className={`px-3 py-1 rounded-full text-xs ${base === k ? "bg-[#0F172A] text-white" : "hover:bg-white"}`}>{v.label}</button>
        ))}
      </div>

      {/* results drawer */}
      <aside className={`absolute z-[500] bottom-8 left-3 right-3 md:left-auto md:top-3 md:bottom-8 md:w-[24rem] flex flex-col ${panelOpen ? "" : "md:translate-x-[calc(100%+1rem)] translate-y-[calc(100%+1rem)] md:translate-y-0"} transition-transform duration-300 max-h-[45%] md:max-h-none`} aria-label="Results">
        <div className={`${GLASS} flex-1 min-h-0 flex flex-col overflow-hidden`}>
          {!result ? (
            <div className="p-4" data-testid="map-empty">
              <h2 className="font-display text-lg font-bold">Nothing searched yet</h2>
              <p className="text-sm text-[#5F5F5A] mt-1">Move the map to a town, choose a category and press “Search this area”.</p>
            </div>
          ) : (
            <section className="flex-1 min-h-0 flex flex-col" data-testid="map-results">
              <div className="p-4 pb-2 space-y-2">
                <p className="text-sm" data-testid="map-summary">{summaryText(places, result.truncated)}</p>
                {places.length > 0 && (
                  <div className="flex gap-2 flex-wrap">
                    <button className="btn-ghost" onClick={() => setSelected(new Set(places.map((p) => p.external_id)))} data-testid="map-select-all">SELECT ALL</button>
                    <button className="btn-ghost" onClick={() => setSelected(new Set(places.filter((p) => p.email).map((p) => p.external_id)))} data-testid="map-select-email">ONLY WITH E-MAIL</button>
                    <button className="btn-ghost" onClick={() => setSelected(new Set())}>NONE</button>
                  </div>
                )}
              </div>
              <ul className="flex-1 min-h-0 overflow-y-auto divide-y divide-[#EDEBE0] px-4">
                {places.map((p) => (
                  <li key={p.external_id} className="py-2 flex gap-2 items-start text-sm">
                    <input type="checkbox" checked={selected.has(p.external_id)} onChange={() => toggle(p.external_id)} aria-label={`Select ${p.name}`} className="mt-1" />
                    <button className="text-left min-w-0" onClick={() => map.current.setView([p.lat, p.lon], 18)}>
                      <span className="font-medium block truncate">{p.name}</span>
                      <span className="block text-xs text-[#5F5F5A] truncate">{p.email || p.phone || "no contact published"}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {canImport && chosen.length > 0 && <div className="border-t border-[#D6D3C8] p-3 overflow-y-auto max-h-[50%]"><ImportPanel selected={chosen} onDone={() => setSelected(new Set())} /></div>}
          {!canImport && result && <p className="p-3 text-xs text-[#92400E] border-t border-[#D6D3C8]" data-testid="map-import-off">Importing is off: set FEATURE_PROSPECT_IMPORT=true to import the selection.</p>}
        </div>
      </aside>
      <button className={`hidden md:flex absolute z-[501] top-1/2 ${GLASS} !rounded-full p-2 transition-all ${panelOpen ? "right-[24.6rem]" : "right-3"}`}
        onClick={() => setPanelOpen((o) => !o)} aria-label={panelOpen ? "Hide results" : "Show results"} aria-expanded={panelOpen} data-testid="map-panel-toggle">
        {panelOpen ? <CaretDoubleRight size={14} /> : <CaretDoubleLeft size={14} />}
      </button>

      <button className={`md:hidden absolute z-[501] bottom-1 left-1/2 -translate-x-1/2 ${GLASS} !rounded-full px-4 py-1.5 text-xs font-medium`}
        onClick={() => setPanelOpen((o) => !o)} aria-expanded={panelOpen} data-testid="map-panel-toggle-mobile">
        {panelOpen ? "Hide results" : result ? `Results (${places.length})` : "Results"}
      </button>
      <p className="absolute z-[400] bottom-1 left-24 text-[10px] text-[#0F172A]/70 bg-white/70 px-2 rounded-full pointer-events-none hidden lg:block">
        Round: search results (green e-mail, amber phone/site, grey name) · square: my prospects (blue to review, green approved) · double-click a pin to select
      </p>
    </div>
  );
}

export default function MapSearch() {
  const { user } = useAuth();
  const page = useAsync(() => prospectsApi.settings(), []);
  const flags = page.data ? page.data.flags : {};
  const ready = page.data && flags.external_sources && canDecide(user);
  if (ready) return <MapView canImport={Boolean(flags.prospect_import)} />;
  return (
    <div className="p-6 md:p-10 space-y-6 max-w-6xl" data-testid="map-page">
      <div>
        <div className="mono-accent">// live.map</div>
        <h1 className="text-4xl font-black tracking-tighter">Map search</h1>
        <p className="text-[#5F5F5A] mt-1 max-w-3xl">
          Find real local businesses on the map, with the phone, e-mail and website their OpenStreetMap contributors published.
          Free, no key. <Link to="/app/prospects/import" className="underline">Import a list instead</Link>
        </p>
      </div>
      {page.loading && !page.data && <LoadingBlock label="Loading…" />}
      {page.error && <ErrorBlock message={page.error} onRetry={page.reload} />}
      {page.data && !flags.external_sources && (
        <EmptyBlock title="Map search is switched off" testId="map-disabled">
          <p>Set <code>FEATURE_EXTERNAL_SOURCES=true</code> on the server to allow reading OpenStreetMap, then redeploy.</p>
        </EmptyBlock>
      )}
      {page.data && flags.external_sources && !canDecide(user) && (
        <EmptyBlock title="Owners and admins only" testId="map-forbidden"><p>Ask an owner or admin to search the map.</p></EmptyBlock>
      )}
    </div>
  );
}
