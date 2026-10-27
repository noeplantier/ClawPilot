/* global ResizeObserver */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { ArrowsOut, ArrowsIn, CaretDoubleRight, CaretDoubleLeft, CaretDown, CaretUp, Eye, EyeSlash, MagnifyingGlass, X } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { campaignsApi, canDecide, importsApi, mapApi, prospectsApi, useAsync } from "@/lib/outreach";
import { describeApiError } from "@/lib/outreachFormat";
import { isTypingTarget, readPref, writePref } from "@/lib/uiPrefs";
import {
  CATEGORY_LABELS, IMPORT_ORIGIN, MAX_SITES_CHECKED, STATUS_COLOR, STATUS_LABEL, areaTooLarge, importRows, knownIds, markerColor,
  panelPadding, reachablePlace, readyOnly, readySummary, summaryText,
} from "@/lib/mapSearch";
import { fetchOverpass } from "@/lib/overpassBrowser";
import { canRetryInBrowser, jobLine, runSearch } from "@/lib/mapJobs";
import {
  EMPTY_FILTER, POLL_MS, applyFilter, campaignPick, clusterPoints, clusterSize, facets, filterSummary, hasFilter, newIds, signalLabel,
} from "@/lib/mapCluster";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";
import PlacePopup from "@/components/outreach/PlacePopup";
import AddedCard from "@/components/outreach/AddedCard";
import CityBox, { lookup } from "@/components/outreach/CityBox";
import { centroids, fold, zoomFor } from "@/lib/cityComplete";

const START = { center: [45.764, 4.8357], zoom: 14 }; // Lyon; move the map anywhere in the world
// One real map: the standard OpenStreetMap style (no light/dark variants).
const OSM_STANDARD = { url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png", credit: "© OpenStreetMap contributors" };
const GLASS = "glass rounded-2xl";

const clusterIcon = (n) => {
  const size = clusterSize(n);
  return L.divIcon({ className: "map-pin", html: `<span class="map-cluster" style="width:${size}px;height:${size}px">${n}</span>`, iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
};

const minePin = (p, fresh) =>
  L.divIcon({
    className: "map-pin",
    html: `<span style="--c:${STATUS_COLOR[p.review_status]}" class="map-pin-square${fresh ? " is-new" : ""}"></span>`,
    iconSize: [22, 22], iconAnchor: [11, 11], popupAnchor: [0, -10],
  });

function minePopup(p) {
  const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const site = p.website && /^https?:\/\//i.test(p.website)
    ? `<div><a href="${esc(p.website)}" target="_blank" rel="noopener noreferrer">${esc(p.website.replace(/^https?:\/\//i, ""))}</a></div>`
    : "";
  const heat = p.heat ? `<b>${p.heat.tier} ${p.heat.value}</b> · ` : "";
  return `<strong>${esc(p.name)}</strong><div>${p.city ? esc(p.city) : "<i>city not set</i>"}</div>` +
    `<div>${heat}${STATUS_LABEL[p.review_status]}</div>` +
    `<div><a href="tel:${esc(p.phone || "")}">${esc(p.phone || "")}</a></div><div><a href="mailto:${esc(p.email || "")}">${esc(p.email || "")}</a></div>${site}` +
    `<div><a href="/app/prospects/${esc(p.id)}">Open the prospect</a>${p.review_status === "approved" ? ` · <a href="/app/leads">in your CRM</a>` : ""}</div>`;
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

function ImportPanel({ selected, onDone, open, onToggle, onClose }) {
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
    <div className="rounded-xl border border-brand-violet/30 bg-white/[0.04] p-3 space-y-3" data-testid="map-import">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-bold">Import {selected.length} selected place{selected.length === 1 ? "" : "s"}</h2>
        <div className="flex gap-1">
          <button className="btn-ghost !px-2 !py-1" onClick={onToggle} aria-expanded={open} aria-label={open ? "Minimise the import form" : "Expand the import form"} data-testid="import-minimise">
            {open ? <CaretDown size={14} /> : <CaretUp size={14} />}
          </button>
          <button className="btn-ghost !px-2 !py-1" onClick={onClose} aria-label="Close the import form and clear the selection" data-testid="import-close"><X size={14} /></button>
        </div>
      </div>
      {open && (
        <>
      <p className="text-xs text-soft">
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
      {error && <div role="alert" className="text-sm text-red-300" data-testid="map-import-error">{error}</div>}
      <button className="btn-ink" disabled={busy || !attest || selected.length === 0} onClick={send} data-testid="map-import-run">
        {busy ? "IMPORTING…" : `IMPORT ${selected.length}`}
      </button>
        </>
      )}
    </div>
  );
}

function MapView({ canImport }) {
  const root = useRef(null);
  const el = useRef(null);
  const map = useRef(null);
  const layer = useRef(null);
  const [category, setCategory] = useState("restaurants");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [job, setJob] = useState(null); // the persisted search shown on the map (running, failed or done)
  const [retrying, setRetrying] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [tooLarge, setTooLarge] = useState(false);
  const [panelOpen, setPanelOpen] = useState(() => readPref("map.results", window.innerWidth >= 768));
  const [searchOpen, setSearchOpen] = useState(() => readPref("map.search", true)); // the "Map search" card, or a small pill
  const [overlaysHidden, setOverlaysHidden] = useState(false); // every panel hidden: just the map
  const [importOpen, setImportOpen] = useState(true); // the import form of the selection, expanded or minimised
  const [full, setFull] = useState(false);
  const [cityStats, setCityStats] = useState(null); // my leads per town, counted by the server (null until loaded)
  const [mine, setMine] = useState([]);
  const [showMine, setShowMine] = useState(true);
  // A search result is a place, not a lead yet (no score): it is drawn only with a published phone AND e-mail, unless asked.
  const [showAllFound, setShowAllFound] = useState(() => readPref("map.allfound", false));
  const mineLayer = useRef(null);
  const [filter, setFilter] = useState(EMPTY_FILTER);
  const [zoom, setZoom] = useState(START.zoom);
  const [group, setGroup] = useState(null); // the prospects of the cluster the user clicked
  const [picked, setPicked] = useState(new Set());
  const [fresh, setFresh] = useState(new Set());
  const [updatedAt, setUpdatedAt] = useState(null);
  const [stale, setStale] = useState(false);
  const [starting, setStarting] = useState(false);
  const previous = useRef(null);
  const pullRef = useRef(null);
  const hosts = useRef(new Map()); // one stable DOM node per place: the popup content is rendered into it
  const markers = useRef(new Map());
  const navigate = useNavigate();
  const hostFor = (id) => {
    let host = hosts.current.get(id);
    if (!host) { host = document.createElement("div"); hosts.current.set(id, host); }
    return host;
  };

  useEffect(() => {
    const m = L.map(el.current, {
      center: START.center, zoom: START.zoom, zoomControl: false, zoomSnap: 0.5, zoomDelta: 0.5, wheelPxPerZoomLevel: 100,
      attributionControl: false,
    });
    L.tileLayer(OSM_STANDARD.url, { maxZoom: 19, attribution: OSM_STANDARD.credit }).addTo(m);
    L.control.attribution({ position: "bottomright", prefix: false }).addTo(m);
    L.control.zoom({ position: "bottomleft" }).addTo(m);
    L.control.scale({ position: "bottomleft", imperial: false }).addTo(m);
    mineLayer.current = L.layerGroup().addTo(m);
    layer.current = L.layerGroup().addTo(m);
    const check = () => setTooLarge(areaTooLarge(bounds(m)));
    m.on("moveend", check);
    m.on("zoomend", () => setZoom(m.getZoom()));
    check();
    map.current = m;
    const watch = new ResizeObserver(() => m.invalidateSize());
    watch.observe(el.current);
    return () => { watch.disconnect(); m.remove(); };
  }, []);

  useEffect(() => {
    const onChange = () => setFull(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  useEffect(() => writePref("map.results", panelOpen), [panelOpen]);
  useEffect(() => writePref("map.search", searchOpen), [searchOpen]);
  useEffect(() => writePref("map.allfound", showAllFound), [showAllFound]);

  // "H" hides or shows every panel (never while typing in a field); Escape brings them back.
  useEffect(() => {
    const onKey = (e) => {
      if (isTypingTarget(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "h" || e.key === "H") setOverlaysHidden((v) => !v);
      if (e.key === "Escape") setOverlaysHidden(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const toggleFull = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (root.current && root.current.requestFullscreen) root.current.requestFullscreen();
  };

  const goTo = useCallback((town) => map.current.flyTo([town.lat, town.lon], zoomFor(town.population), { duration: 1.2 }), []);

  // Near real time without a WebSocket (none on the free plan): poll while the tab is visible, keep what is shown if a poll fails.
  useEffect(() => {
    let alive = true;
    const pull = () => {
      // the counts of the town search ride on the same poll; a failure keeps the last counts rather than showing zeros
      mapApi.cities().then((rows) => { if (alive) setCityStats(rows); }).catch(() => {});
      return mapApi.prospects().then((rows) => {
        if (!alive) return;
        setFresh(newIds(previous.current, rows));
        previous.current = rows;
        setMine(rows);
        setUpdatedAt(new Date());
        setStale(false);
      }).catch(() => { if (alive) setStale(true); });
    };
    pullRef.current = pull;
    pull();
    const id = setInterval(() => { if (!document.hidden) pull(); }, POLL_MS);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const ready = useMemo(() => readyOnly(mine), [mine]); // the only leads drawn on the map: hot, with a phone and an e-mail
  const shown = useMemo(() => applyFilter(ready, filter), [ready, filter]);
  const options = useMemo(() => facets(ready), [ready]);

  useEffect(() => {
    if (!mineLayer.current) return;
    mineLayer.current.clearLayers();
    if (!showMine) return;
    clusterPoints(shown, zoom).forEach((c) => {
      if (c.count === 1) {
        const p = c.members[0];
        L.marker([p.lat, p.lon], { icon: minePin(p, fresh.has(p.id)), title: p.name }).bindPopup(minePopup(p), { className: "map-popup" }).addTo(mineLayer.current);
        return;
      }
      const marker = L.marker([c.lat, c.lon], { icon: clusterIcon(c.count), title: `${c.count} hot leads` });
      marker.on("click", () => {
        setGroup(c.members);
        setPanelOpen(true);
        const lats = c.members.map((m) => m.lat);
        const lons = c.members.map((m) => m.lon);
        if (Math.min(...lats) !== Math.max(...lats) || Math.min(...lons) !== Math.max(...lons)) {
          map.current.fitBounds([[Math.min(...lats), Math.min(...lons)], [Math.max(...lats), Math.max(...lons)]], { maxZoom: 17, padding: [60, 60] });
        }
      });
      marker.addTo(mineLayer.current);
    });
  }, [shown, showMine, zoom, fresh]);

  const startCampaign = async () => {
    const { ids, excluded } = campaignPick(ready, picked);
    setStarting(true);
    try {
      const c = await campaignsApi.create({ name: `Map selection ${new Date().toISOString().slice(0, 10)}`, goal: "Prospects chosen on the map" });
      await campaignsApi.assign(c.id, ids);
      toast.success(`Campaign created with ${ids.length} approved prospect${ids.length === 1 ? "" : "s"}${excluded ? ` (${excluded} not approved, left out)` : ""}. Nothing is sent: open it to add steps.`);
      navigate("/app/campaigns");
    } catch (e) {
      toast.error(`${describeApiError(e)} The campaign was created empty: nothing was assigned.`);
    } finally {
      setStarting(false);
    }
  };
  const togglePick = (id) => setPicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const byHeat = (a, b) => ((b.heat && b.heat.value) || 0) - ((a.heat && a.heat.value) || 0);
  const list = group ? [...group].sort(byHeat) : [...shown].sort(byHeat).slice(0, 30); // hottest first
  const pickInfo = campaignPick(ready, picked);

  const known = useMemo(() => knownIds(mine), [mine]);
  const positions = useMemo(() => centroids(mine), [mine]); // where my prospects of each town are: a town of my leads is reachable at once

  // "Open on the map" from a suggested zone (?city=Lyon): fly there once, from my own prospects of that town when I have some,
  // else from the official communes list. Done after the first poll, so a town of my leads never costs a lookup.
  const [searchParams] = useSearchParams();
  const wanted = searchParams.get("city");
  const flownTo = useRef(null);
  useEffect(() => {
    if (!wanted || !updatedAt || flownTo.current === wanted || !map.current) return;
    flownTo.current = wanted;
    const at = positions.get(fold(wanted));
    if (at) { goTo({ lat: at.lat, lon: at.lon, population: null }); return; }
    lookup(wanted).then((towns) => { const town = towns.find((t) => t.lat !== null && t.lat !== undefined); if (town) goTo(town); }).catch(() => {});
  }, [wanted, updatedAt, positions, goTo]);
  // A popup must never open under a panel: keep the map's auto-pan away from the search card and the results drawer.
  const pad = useMemo(() => panelPadding({ narrow: window.innerWidth < 768, searchOpen, panelOpen, hidden: overlaysHidden }), [searchOpen, panelOpen, overlaysHidden]);
  // A place already in the prospects is shown by its prospect pin, not offered again.
  const places = useMemo(() => {
    const unique = new Map();
    for (const place of result?.places || []) {
      if (!known.has(place.external_id) && !unique.has(place.external_id)) unique.set(place.external_id, place);
    }
    return [...unique.values()];
  }, [result, known]);
  const found = useMemo(() => (showAllFound ? places : places.filter(reachablePlace)), [places, showAllFound]);
  const toggle = useCallback((id) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; }), []);

  useEffect(() => {
    if (!layer.current) return;
    layer.current.clearLayers();
    markers.current = new Map();
    found.forEach((p) => {
      const marker = L.marker([p.lat, p.lon], { icon: pin(p, selected.has(p.external_id)), title: p.name }).bindPopup(hostFor(p.external_id), {
        className: "map-popup", minWidth: 250, maxWidth: 300, autoPanPaddingTopLeft: pad.topLeft, autoPanPaddingBottomRight: pad.bottomRight,
      });
      marker.on("dblclick", () => toggle(p.external_id));
      marker.addTo(layer.current);
      markers.current.set(p.external_id, marker);
    });
  }, [found, selected, toggle, pad]);

  // A place was added: show it at once among "my prospects" (the next poll confirms it) and say what happened.
  const [added, setAdded] = useState(null); // the answer of the last addition, kept until closed
  const onAdded = useCallback((out, place, ctx) => {
    setAdded({ out, siteAsked: Boolean(ctx && ctx.siteAsked) });
    if (pullRef.current) pullRef.current();
    setSelected((s) => { const n = new Set(s); n.delete(place.external_id); return n; });
  }, []);
  const addOff = canImport ? null : "Adding places is off: set FEATURE_PROSPECT_IMPORT=true on the server.";
  const openPlace = (p) => {
    map.current.flyTo([p.lat, p.lon], 18, { duration: 0.8 });
    const marker = markers.current.get(p.external_id);
    if (marker) setTimeout(() => marker.openPopup(), 850);
  };

  const show = useCallback((out) => {
    setResult(out);
    setSelected(new Set());
    setPanelOpen(true);
  }, []);

  const search = useCallback(async () => {
    setBusy(true);
    setError(null);
    setJob(null);
    try {
      const out = await runSearch(mapApi, { ...bounds(map.current), category }, { onUpdate: setJob });
      setJob(out.job);
      if (out.places) show(out.places);
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy(false);
    }
  }, [category, show]);

  // After a refresh, a sign-in elsewhere or another device: the last finished search of the organisation comes back from the database.
  useEffect(() => {
    let alive = true;
    mapApi.recent(5).then(async (jobs) => {
      const last = jobs.find((j) => j.status === "succeeded");
      if (!last || !alive) return;
      const places = await mapApi.places(last.id);
      if (!alive) return;
      setJob(last);
      setCategory(last.category);
      show(places);
      map.current.fitBounds([[last.south, last.west], [last.north, last.east]]);
    }).catch(() => {});
    return () => { alive = false; };
  }, [show]);

  // Explicit fallback when the server could not reach OpenStreetMap: this browser asks a public server, the server stores the answer.
  const retryInBrowser = async () => {
    setRetrying(true);
    setError(null);
    try {
      const data = await fetchOverpass(job.fallback.query, job.fallback.endpoints);
      const done = await mapApi.ingest(job.id, data);
      setJob(done);
      show(await mapApi.places(done.id));
    } catch (e) {
      setError(e && e.failures ? e.message : describeApiError(e));
    } finally {
      setRetrying(false);
    }
  };

  const chosen = found.filter((p) => selected.has(p.external_id));

  return (
    <div ref={root} className="relative w-full h-[calc(100svh-11rem)] md:h-[calc(100vh-4.25rem)] min-h-0 md:min-h-[28rem] overflow-hidden bg-white/[0.04]" data-testid="map-page">
      <div ref={el} className="absolute inset-0 z-0" data-testid="map" aria-label="Interactive map" />
      {added && <AddedCard out={added.out} siteAsked={added.siteAsked} onClose={() => setAdded(null)} className="absolute z-[502] bottom-12 left-3 md:left-1/2 md:-translate-x-1/2" />}
      {found.map((p) => createPortal(<PlacePopup key={p.external_id} place={p} canAdd={canImport} offReason={addOff} onAdded={onAdded} />, hostFor(p.external_id)))}

      {/* always visible: hide every panel to see the whole map, or go full screen */}
      <div className={`absolute z-[503] top-3 right-3 md:left-1/2 md:right-auto md:-translate-x-1/2 flex gap-1 p-1 ${GLASS} !rounded-full`} role="toolbar" aria-label="Map view">
        <button className="btn-ghost !rounded-full !px-3 !py-1 text-xs" onClick={() => setOverlaysHidden((v) => !v)} aria-pressed={overlaysHidden} title="Hide or show every panel (H)" data-testid="map-hide-panels">
          {overlaysHidden ? <Eye size={14} /> : <EyeSlash size={14} />} {overlaysHidden ? "SHOW PANELS" : "FULL MAP"}
        </button>
        <button className="btn-ghost !rounded-full !px-2 !py-1" onClick={toggleFull} aria-label={full ? "Leave full screen" : "Full screen"} data-testid="map-fullscreen">
          {full ? <ArrowsIn size={14} /> : <ArrowsOut size={14} />}
        </button>
      </div>

      {/* search card, or its small pill */}
      {!overlaysHidden && !searchOpen && (
        <div className={`absolute z-[500] top-14 left-3 md:top-3 flex items-center gap-2 p-2 ${GLASS} !rounded-full`} data-testid="map-search-pill">
          <button className="btn-ghost !rounded-full !px-3 !py-1 text-xs" onClick={() => setSearchOpen(true)} aria-label="Expand the map search panel" aria-expanded="false" data-testid="map-search-expand">
            <CaretDown size={14} /> MAP SEARCH
          </button>
          <button className="btn-ink !rounded-full !px-3 !py-1 text-xs" onClick={search} disabled={busy || tooLarge} data-testid="map-search">
            <MagnifyingGlass size={14} /> {busy ? "SEARCHING…" : "SEARCH"}
          </button>
        </div>
      )}
      {!overlaysHidden && searchOpen && (
        <div className={`absolute z-[500] top-14 left-3 right-3 md:top-3 md:right-auto md:w-[26rem] max-h-[calc(100%-4rem)] md:max-h-[calc(100%-1.5rem)] overflow-y-auto p-4 space-y-3 ${GLASS}`} data-testid="map-search-card">
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="mono-accent">// live.map</div>
              <h1 className="text-2xl font-black tracking-tighter leading-none">Map search</h1>
            </div>
            <button className="btn-ghost !px-2" onClick={() => setSearchOpen(false)} aria-label="Minimise the map search panel" aria-expanded="true" data-testid="map-search-minimise">
              <CaretUp size={16} />
            </button>
          </div>
          <CityBox stats={cityStats} positions={positions} onPick={goTo} />
          <div className="flex gap-1.5 flex-wrap" role="group" aria-label="Business category">
            {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
              <button key={k} onClick={() => setCategory(k)} aria-pressed={category === k} data-testid={`map-cat-${k}`}
                className={`px-3 py-1 rounded-full text-xs border transition-colors ${category === k ? "bg-brand-violet text-white border-brand-violet" : "bg-card border-border hover:bg-white/[0.04]"}`}>
                {v.split(",")[0].split(" (")[0]}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-xs" data-testid="map-mine-toggle">
            <input type="checkbox" checked={showMine} onChange={(e) => setShowMine(e.target.checked)} />
            <span><b>Hot leads</b> (squares) — {readySummary(mine)}</span>
          </label>
          {mine.length > 0 && showMine && (
            <div className="space-y-2" data-testid="map-filters">
              <div className="grid grid-cols-2 gap-2">
                <select className="neo-input" aria-label="Filter by vertical" value={filter.vertical} onChange={(e) => setFilter({ ...filter, vertical: e.target.value })} data-testid="filter-vertical">
                  <option value="">All verticals</option>
                  {options.verticals.map((v) => <option key={v.value} value={v.value}>{v.value} ({v.count})</option>)}
                </select>
                <select className="neo-input" aria-label="Filter by review status" value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })} data-testid="filter-status">
                  <option value="">Any status</option>
                  {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
                <select className="neo-input" aria-label="Filter by detected signal" value={filter.signal} onChange={(e) => setFilter({ ...filter, signal: e.target.value })} data-testid="filter-signal">
                  <option value="">Any signal</option>
                  {options.signals.map((v) => <option key={v.value} value={v.value}>{signalLabel(v.value)} ({v.count})</option>)}
                </select>
                <input className="neo-input" type="number" min="0" max="100" placeholder="Min score" aria-label="Minimum score" value={filter.minScore} onChange={(e) => setFilter({ ...filter, minScore: e.target.value })} data-testid="filter-score" />
              </div>
              <div className="flex items-center justify-between gap-2 text-xs">
                <span data-testid="filter-summary">{filterSummary(shown.length, ready.length)}</span>
                {hasFilter(filter) && <button className="underline" onClick={() => { setFilter(EMPTY_FILTER); setGroup(null); }} data-testid="filter-clear">Clear</button>}
              </div>
              <p className="text-[11px] text-soft" data-testid="map-updated" aria-live="polite">
                {stale ? "Update failed: showing the last data. " : ""}{updatedAt ? `Updated ${updatedAt.toLocaleTimeString()} · refreshes every ${POLL_MS / 1000} s` : "Loading…"}
              </p>
            </div>
          )}
          <button className="btn-ink w-full justify-center" onClick={search} disabled={busy || tooLarge} data-testid="map-search">
            <MagnifyingGlass size={14} /> {busy ? "SEARCHING…" : "SEARCH THIS AREA"}
          </button>
          {tooLarge && <p className="text-xs text-amber-300" data-testid="map-zoom-hint">Zoom in on a town or a neighbourhood to search.</p>}
          {job && job.status !== "failed" && <p className="text-xs" role="status" aria-live="polite" data-testid="map-job">{jobLine(job)}{job.truncated ? " The area holds more places: zoom in to see the rest." : ""}</p>}
          {job && job.status === "failed" && (
            <div role="alert" className="text-sm text-red-300 space-y-2" data-testid="map-job-failed">
              <p>{job.error}</p>
              <p className="text-[11px] text-soft">Code: {job.error_code}. This search is saved with its error.</p>
              {canRetryInBrowser(job) && (
                <button className="btn-ghost" onClick={retryInBrowser} disabled={retrying} data-testid="map-retry-browser">
                  {retrying ? "ASKING OPENSTREETMAP…" : "RETRY FROM MY BROWSER"}
                </button>
              )}
            </div>
          )}
          {error && <div role="alert" className="text-sm text-red-300" data-testid="map-error">{error}</div>}
        </div>
      )}
      {/* the search status stays visible when the card is minimised */}
      {!overlaysHidden && !searchOpen && job && (
        <p className={`absolute z-[499] top-[3.9rem] left-3 text-xs px-3 py-1 ${GLASS} !rounded-full`} role="status" aria-live="polite" data-testid="map-job">
          {job.status === "failed" ? `${job.error_code}: open the panel for details.` : jobLine(job)}
        </p>
      )}

      {/* results drawer */}
      {!overlaysHidden && (
        <>
          <aside className={`absolute z-[500] bottom-11 left-3 right-3 md:left-auto md:top-3 md:bottom-8 md:w-[24rem] flex flex-col ${panelOpen ? "" : "md:translate-x-[calc(100%+1rem)] translate-y-[calc(100%+1rem)] md:translate-y-0 pointer-events-none"} transition-transform duration-300 max-h-[45%] md:max-h-none`} aria-label="Results" aria-hidden={!panelOpen}>
            <div className={`${GLASS} flex-1 min-h-0 flex flex-col overflow-hidden`}>
              <div className="flex items-center justify-between px-4 pt-3">
                <div className="mono-accent">// results</div>
                <button className="btn-ghost !px-2 !py-1" onClick={() => setPanelOpen(false)} aria-label="Close the results panel" data-testid="map-panel-close"><X size={14} /></button>
              </div>
              {mine.length > 0 && showMine && (
                <section className="p-4 border-b border-border max-h-[50%] overflow-y-auto" data-testid="map-mine-list">
                  <div className="flex items-center justify-between gap-2">
                    <h2 className="font-display text-lg font-bold">{group ? `Cluster · ${group.length} hot leads` : "Hot leads"}</h2>
                    {group && <button className="underline text-xs" onClick={() => setGroup(null)} data-testid="cluster-close">All</button>}
                  </div>
                  {list.length === 0 && <p className="text-sm text-soft mt-1" data-testid="mine-none">{ready.length === 0 ? "No hot lead with a phone and an e-mail yet." : "No hot lead matches the filters."}</p>}
                  <ul className="divide-y divide-border">
                    {list.map((p) => (
                      <li key={p.id} className="py-1.5 flex gap-2 items-start text-sm" data-testid="mine-row">
                        <input type="checkbox" checked={picked.has(p.id)} onChange={() => togglePick(p.id)} aria-label={`Select ${p.name}`} className="mt-1" />
                        <button className="text-left min-w-0 flex-1" onClick={() => map.current.flyTo([p.lat, p.lon], 17, { duration: 1 })}>
                          <span className="font-medium block truncate">{p.name}</span>
                          <span className="block text-xs text-soft truncate">{p.heat ? `${p.heat.tier} ${p.heat.value} · ` : ""}{STATUS_LABEL[p.review_status]} · {p.score === null || p.score === undefined ? "not scored" : `score ${p.score}`}{p.city ? ` · ${p.city}` : ""}</span>
                        </button>
                        <Link to={`/app/prospects/${p.id}`} className="text-xs underline shrink-0">open</Link>
                      </li>
                    ))}
                  </ul>
                  {!group && shown.length > list.length && <p className="text-xs text-soft mt-1">Showing the first {list.length} of {shown.length}: click a cluster or filter to narrow.</p>}
                  <button className="btn-ink w-full justify-center mt-2" disabled={starting || pickInfo.ids.length === 0} onClick={startCampaign} data-testid="start-campaign">
                    {starting ? "CREATING…" : `START CAMPAIGN (${pickInfo.ids.length})`}
                  </button>
                  <p className="text-[11px] text-soft mt-1" data-testid="start-campaign-note">
                    {picked.size === 0 ? "Tick prospects to start a campaign. Only approved ones can join; nothing is sent until you add steps and launch." : pickInfo.excluded > 0 ? `${pickInfo.excluded} selected prospect${pickInfo.excluded === 1 ? " is" : "s are"} not approved and will be left out.` : "Creates a draft campaign: nothing is sent."}
                  </p>
                </section>
              )}
              {!result ? (
                <div className="p-4" data-testid="map-empty">
                  <h2 className="font-display text-lg font-bold">Nothing searched yet</h2>
                  <p className="text-sm text-soft mt-1">Move the map to a town, choose a category and press “Search this area”.</p>
                </div>
              ) : (
                <section className="flex-1 min-h-0 flex flex-col" data-testid="map-results">
                  <div className="p-4 pb-2 space-y-2">
                    <p className="text-sm" data-testid="map-summary">{summaryText(places, result.truncated)}</p>
                    <label className="flex items-center gap-2 text-xs" data-testid="map-found-toggle">
                      <input type="checkbox" checked={showAllFound} onChange={(e) => setShowAllFound(e.target.checked)} />
                      <span>{found.length} of {places.length} shown: only places with a published phone and e-mail. Tick to show all of them.</span>
                    </label>
                    {found.length > 0 && (
                      <div className="flex gap-2 flex-wrap">
                        <button className="btn-ghost" onClick={() => setSelected(new Set(found.map((p) => p.external_id)))} data-testid="map-select-all">SELECT ALL</button>
                        <button className="btn-ghost" onClick={() => setSelected(new Set(found.filter((p) => p.email).map((p) => p.external_id)))} data-testid="map-select-email">ONLY WITH E-MAIL</button>
                        <button className="btn-ghost" onClick={() => setSelected(new Set())}>NONE</button>
                      </div>
                    )}
                  </div>
                  <ul className="flex-1 min-h-0 overflow-y-auto divide-y divide-border px-4">
                    {found.map((p) => (
                      <li key={p.external_id} className="py-2 flex gap-2 items-start text-sm">
                        <input type="checkbox" checked={selected.has(p.external_id)} onChange={() => toggle(p.external_id)} aria-label={`Select ${p.name}`} className="mt-1" />
                        <button className="text-left min-w-0 flex-1" onClick={() => openPlace(p)} data-testid="place-row" title="Show on the map and add to the CRM">
                          <span className="font-medium block truncate">{p.name}</span>
                          <span className="block text-xs text-soft truncate">{p.email || p.phone || "no contact published"}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              {canImport && chosen.length > 0 && (
                <div className="border-t border-border p-3 overflow-y-auto max-h-[50%]">
                  <ImportPanel selected={chosen} onDone={() => setSelected(new Set())} open={importOpen} onToggle={() => setImportOpen((v) => !v)} onClose={() => setSelected(new Set())} />
                </div>
              )}
              {!canImport && result && <p className="p-3 text-xs text-amber-300 border-t border-border" data-testid="map-import-off">Importing is off: set FEATURE_PROSPECT_IMPORT=true to import the selection.</p>}
            </div>
          </aside>
          <button className={`hidden md:flex absolute z-[501] top-1/2 ${GLASS} !rounded-full p-2 transition-all ${panelOpen ? "right-[24.6rem]" : "right-3"}`}
            onClick={() => setPanelOpen((o) => !o)} aria-label={panelOpen ? "Hide results" : "Show results"} aria-expanded={panelOpen} data-testid="map-panel-toggle">
            {panelOpen ? <CaretDoubleRight size={14} /> : <CaretDoubleLeft size={14} />}
          </button>
          <button className={`md:hidden absolute z-[501] bottom-1 left-16 ${GLASS} !rounded-full px-4 py-1.5 text-xs font-medium`}
            onClick={() => setPanelOpen((o) => !o)} aria-expanded={panelOpen} data-testid="map-panel-toggle-mobile">
            {panelOpen ? "Hide results" : result ? `Results (${found.length})` : "Results"}
          </button>
          <p className="absolute z-[400] bottom-1 left-40 text-[10px] text-foreground/80 bg-void-surface/85 px-2 rounded-full pointer-events-none hidden lg:block">
            Square: hot leads with a phone and an e-mail (blue to review, green approved) · round: places found by the search with a published phone and e-mail (green e-mail, amber phone/site, grey name) · click a pin to add it to the CRM · double-click to select several · H: hide panels
          </p>
        </>
      )}
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
        <p className="text-soft mt-1 max-w-3xl">
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
