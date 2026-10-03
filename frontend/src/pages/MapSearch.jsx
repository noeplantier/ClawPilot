import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { MagnifyingGlass } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, importsApi, mapApi, prospectsApi, useAsync } from "@/lib/outreach";
import { describeApiError } from "@/lib/outreachFormat";
import {
  CATEGORY_LABELS, IMPORT_ORIGIN, MAX_SITES_CHECKED, areaTooLarge, importRows, markerColor, summaryText,
} from "@/lib/mapSearch";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";

const START = { center: [45.764, 4.8357], zoom: 14 }; // Lyon; move the map anywhere in the world

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
  const el = useRef(null);
  const map = useRef(null);
  const layer = useRef(null);
  const [category, setCategory] = useState("restaurants");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [tooLarge, setTooLarge] = useState(false);

  useEffect(() => {
    const m = L.map(el.current, { center: START.center, zoom: START.zoom });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "© <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> contributors",
    }).addTo(m);
    layer.current = L.layerGroup().addTo(m);
    const check = () => setTooLarge(areaTooLarge(bounds(m)));
    m.on("moveend", check);
    check();
    map.current = m;
    return () => m.remove();
  }, []);

  const places = useMemo(() => (result ? result.places : []), [result]);

  useEffect(() => {
    if (!layer.current) return;
    layer.current.clearLayers();
    places.forEach((p) => {
      const dot = L.circleMarker([p.lat, p.lon], {
        radius: selected.has(p.external_id) ? 10 : 7, color: "#0F172A", weight: selected.has(p.external_id) ? 3 : 1,
        fillColor: markerColor(p), fillOpacity: 0.9,
      }).bindPopup(popupHtml(p));
      dot.on("dblclick", () => toggle(p.external_id));
      dot.addTo(layer.current);
    });
  }, [places, selected]);

  const toggle = (id) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  const search = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await mapApi.search({ ...bounds(map.current), category });
      setResult(out);
      setSelected(new Set());
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy(false);
    }
  }, [category]);

  const chosen = places.filter((p) => selected.has(p.external_id));

  return (
    <div className="grid lg:grid-cols-3 gap-4">
      <div className="lg:col-span-2 space-y-3">
        <div className="flex gap-2 flex-wrap items-center">
          <select className="neo-input !w-64" value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Business category" data-testid="map-category">
            {Object.entries(CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <button className="btn-ink" onClick={search} disabled={busy || tooLarge} data-testid="map-search">
            <MagnifyingGlass size={14} /> {busy ? "SEARCHING…" : "SEARCH THIS AREA"}
          </button>
          {tooLarge && <span className="text-xs text-[#92400E]" data-testid="map-zoom-hint">Zoom in on a town or a neighbourhood to search.</span>}
        </div>
        {error && <div role="alert" className="text-sm text-[#991B1B]" data-testid="map-error">{error}</div>}
        <div ref={el} className="h-[28rem] md:h-[34rem] w-full rounded-md border border-[#D6D3C8]" data-testid="map" aria-label="Interactive map" />
        <p className="text-xs text-[#5F5F5A]">
          Green: e-mail published · amber: phone or website only · grey: name and place only. Double-click a dot to select it.
          Data © OpenStreetMap contributors (ODbL); only what contributors published is shown, nothing is guessed.
        </p>
      </div>
      <div className="space-y-4">
        {!result && <EmptyBlock title="Nothing searched yet" testId="map-empty"><p>Move the map to a town, choose a category and press “Search this area”.</p></EmptyBlock>}
        {result && (
          <section className="surface p-4 space-y-2" data-testid="map-results">
            <p className="text-sm" data-testid="map-summary">{summaryText(places, result.truncated)}</p>
            {places.length > 0 && (
              <div className="flex gap-2">
                <button className="btn-ghost" onClick={() => setSelected(new Set(places.map((p) => p.external_id)))} data-testid="map-select-all">SELECT ALL</button>
                <button className="btn-ghost" onClick={() => setSelected(new Set(places.filter((p) => p.email).map((p) => p.external_id)))} data-testid="map-select-email">ONLY WITH E-MAIL</button>
              </div>
            )}
            <ul className="max-h-80 overflow-y-auto divide-y divide-[#EDEBE0]">
              {places.map((p) => (
                <li key={p.external_id} className="py-2 flex gap-2 items-start text-sm">
                  <input type="checkbox" checked={selected.has(p.external_id)} onChange={() => toggle(p.external_id)} aria-label={`Select ${p.name}`} className="mt-1" />
                  <button className="text-left" onClick={() => { map.current.setView([p.lat, p.lon], 18); }}>
                    <span className="font-medium">{p.name}</span>
                    <span className="block text-xs text-[#5F5F5A]">{p.email || p.phone || "no contact published"}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
        {canImport && chosen.length > 0 && <ImportPanel selected={chosen} onDone={() => setSelected(new Set())} />}
      </div>
    </div>
  );
}

export default function MapSearch() {
  const { user } = useAuth();
  const page = useAsync(() => prospectsApi.settings(), []);
  const flags = page.data ? page.data.flags : {};
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
      {page.data && flags.external_sources && canDecide(user) && <MapView canImport={Boolean(flags.prospect_import)} />}
      {page.data && flags.external_sources && canDecide(user) && !flags.prospect_import && (
        <p className="text-xs text-[#92400E]" data-testid="map-import-off">Importing is off: set FEATURE_PROSPECT_IMPORT=true to import the selection.</p>
      )}
    </div>
  );
}
