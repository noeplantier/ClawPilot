/* global AbortController */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Database, MagnifyingGlass } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, prospectsApi, sourcesApi, useAsync } from "@/lib/outreach";
import { describeApiError } from "@/lib/outreachFormat";
import {
  PAGE_SIZE, VERTICAL_LABELS, detectedSignals, hasContact, resultSummary, unknownCount, validateDiscover,
} from "@/lib/sourcesForm";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";

const EMPTY = { vertical: "restaurants", limit: 25, country: "", city: "", lat: "", lon: "", radius_m: 5000 };

function ProviderCard({ provider, active, onPick }) {
  return (
    <button type="button" onClick={() => provider.available && onPick(provider.name)} disabled={!provider.available} aria-pressed={active}
      className={`text-left surface p-4 space-y-1 transition ${active ? "ring-2 ring-[#0F172A]" : ""} ${provider.available ? "" : "opacity-60 cursor-not-allowed"}`}
      data-testid={`source-${provider.name}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-display font-bold">{provider.label}</span>
        <span className="mono-accent">{provider.kind === "network" ? "live data" : "local demo"}</span>
      </div>
      <p className="text-xs text-[#5F5F5A]">{provider.license_note}</p>
      <p className="text-xs">Cost: {provider.cost} · limit: {provider.rate_limit_per_minute}/min per organisation ({provider.rate_limit_note})</p>
      {!provider.available && <p className="text-xs text-[#92400E]" data-testid={`source-${provider.name}-off`}>{provider.unavailable_reason}</p>}
    </button>
  );
}

function Field({ label, error, children }) {
  return (
    <label className="block">
      <span className="mono-accent block mb-1">{label}</span>
      {children}
      {error && <span role="alert" className="text-xs text-[#991B1B] block mt-1">{error}</span>}
    </label>
  );
}

function TownSearch({ onPick }) {
  const [query, setQuery] = useState("");
  const [towns, setTowns] = useState([]);
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) { setTowns([]); return undefined; }
    const ctl = new AbortController();
    const t = setTimeout(() => {
      // French national address API (free, no key): only the typed town name leaves the browser.
      fetch(`https://api-adresse.data.gouv.fr/search/?q=${encodeURIComponent(q)}&type=municipality&limit=5`, { signal: ctl.signal })
        .then((r) => r.json())
        .then((d) => setTowns((d.features || []).map((f) => ({ label: `${f.properties.city} (${f.properties.postcode})`, city: f.properties.city, lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0] }))))
        .catch(() => setTowns([]));
    }, 300);
    return () => { clearTimeout(t); ctl.abort(); };
  }, [query]);
  return (
    <div className="relative">
      <input className="neo-input w-full" placeholder="Pick a French town… (or enter a position)" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Find a French town" data-testid="source-town" />
      {towns.length > 0 && (
        <ul className="absolute z-10 left-0 right-0 mt-1 surface max-h-48 overflow-auto">
          {towns.map((t) => (
            <li key={t.label}><button type="button" className="w-full text-left px-3 py-2 text-sm hover:bg-[#F4F2E7]" onClick={() => { onPick(t); setQuery(""); setTowns([]); }}>{t.label}</button></li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Results({ run, offset, onPage, selected, toggle, onSelectPage, flags, canAdd }) {
  const [attest, setAttest] = useState(false);
  const [sites, setSites] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(null);
  const add = async () => {
    setBusy(true); setError(null); setDone(null);
    try {
      const out = await sourcesApi.add(run.run_id, { external_ids: [...selected], attestation: attest, check_websites: sites && Boolean(flags.external_sources) });
      setDone(out);
      toast.success(`${out.created} added, ${out.updated} updated. They wait for your review.`);
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy(false);
    }
  };
  const last = Math.min(offset + PAGE_SIZE, run.total);
  return (
    <section className="space-y-3" data-testid="source-results">
      <p className="text-sm" data-testid="source-summary">{resultSummary(run)} <span className="text-[#5F5F5A]">Source: {run.license_note}</span></p>
      {run.total === 0 ? (
        <EmptyBlock title="No place found" testId="source-empty"><p>Try a larger radius, another vertical or another source.</p></EmptyBlock>
      ) : (
        <>
          <div className="surface overflow-x-auto">
            <table className="w-full text-sm" data-testid="source-table">
              <thead className="bg-[#FAFAF7] border-b border-[#D6D3C8]">
                <tr className="text-left mono-accent"><th className="p-3 w-10"><input type="checkbox" aria-label="Select this page" onChange={(e) => onSelectPage(e.target.checked)} /></th><th className="p-3">name</th><th className="p-3">where</th><th className="p-3">contact (as published)</th><th className="p-3">signals</th></tr>
              </thead>
              <tbody>
                {run.places.map((p) => (
                  <tr key={p.external_id} className="border-b border-[#F0F0EA] align-top" data-testid={`place-${p.external_id}`}>
                    <td className="p-3"><input type="checkbox" checked={selected.has(p.external_id)} onChange={() => toggle(p.external_id)} aria-label={`Select ${p.name}`} /></td>
                    <td className="p-3"><span className="font-medium">{p.name}</span><a className="block text-xs underline text-[#5F5F5A]" href={p.source_url.startsWith("http") ? p.source_url : undefined} rel="noopener noreferrer" target="_blank">{p.source_name}</a></td>
                    <td className="p-3 text-xs">{[p.city, p.postcode].filter(Boolean).join(" ") || <i>not published</i>}</td>
                    <td className="p-3 text-xs">{hasContact(p) ? [p.email, p.phone, p.website].filter(Boolean).join(" · ") : <i>no contact published</i>}</td>
                    <td className="p-3 text-xs">
                      {detectedSignals(p).map((s) => <span key={s.key} title={s.evidence} className="chip-red mr-1">{s.key.replace(/_/g, " ")}</span>)}
                      <span className="text-[#5F5F5A]">{unknownCount(p)} unknown</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <button className="btn-ghost" disabled={offset === 0} onClick={() => onPage(Math.max(0, offset - PAGE_SIZE))} data-testid="source-prev">PREVIOUS</button>
            <span data-testid="source-range">{offset + 1}–{last} of {run.total}</span>
            <button className="btn-ghost" disabled={last >= run.total} onClick={() => onPage(offset + PAGE_SIZE)} data-testid="source-next">NEXT</button>
          </div>
          {selected.size > 0 && (
            <div className="surface p-4 space-y-3" data-testid="source-add">
              <h2 className="font-display text-lg font-bold">Add {selected.size} to prospects</h2>
              <p className="text-xs text-[#5F5F5A]">They join the review queue with their source as provenance. Nothing is sent.</p>
              {flags.external_sources && (
                <label className="flex gap-2 text-sm"><input type="checkbox" checked={sites} onChange={(e) => setSites(e.target.checked)} className="mt-1" /><span>Look for a public contact e-mail on each business&apos;s own website (robots.txt respected, 25 sites max).</span></label>
              )}
              <label className="flex gap-2 text-sm"><input type="checkbox" checked={attest} onChange={(e) => setAttest(e.target.checked)} className="mt-1" data-testid="source-attest" /><span>I confirm that I may use these professional details for B2B prospecting (legitimate interest) and will honour opt-outs.</span></label>
              {!canAdd && <p className="text-xs text-[#92400E]" data-testid="source-add-off">Adding real data is off: set FEATURE_PROSPECT_IMPORT=true on the server.</p>}
              {error && <div role="alert" className="text-sm text-[#991B1B]" data-testid="source-add-error">{error}</div>}
              {done && <p className="text-sm text-[#166534]" data-testid="source-add-done">{done.created} added, {done.updated} updated. <Link className="underline" to="/app/prospects/review">Open the review queue</Link></p>}
              <button className="btn-ink" disabled={busy || !attest || !canAdd} onClick={add} data-testid="source-add-run">{busy ? "ADDING…" : `ADD ${selected.size}`}</button>
            </div>
          )}
        </>
      )}
    </section>
  );
}

export default function Sources() {
  const { user } = useAuth();
  const page = useAsync(async () => {
    const [providers, settings] = await Promise.all([sourcesApi.list(), prospectsApi.settings().catch(() => null)]);
    return { providers, flags: settings ? settings.flags : {} };
  }, []);
  const [name, setName] = useState("world_fixture");
  const [values, setValues] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [run, setRun] = useState(null);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(new Set());

  if (page.loading && !page.data) return <div className="p-6 md:p-10"><LoadingBlock label="Loading sources…" /></div>;
  if (page.error) return <div className="p-6 md:p-10"><ErrorBlock message={page.error} onRetry={page.reload} /></div>;
  const { providers, flags } = page.data;
  const provider = providers.find((p) => p.name === name) || providers[0];
  const edit = canDecide(user);
  const set = (k) => (e) => setValues((v) => ({ ...v, [k]: e.target.value }));
  const pick = (n) => { setName(n); setErrors({}); setRun(null); setError(null); setSelected(new Set()); setValues((v) => ({ ...v, vertical: providers.find((p) => p.name === n).verticals.includes(v.vertical) ? v.vertical : providers.find((p) => p.name === n).verticals[0] })); };

  const discover = async (e) => {
    e.preventDefault();
    const check = validateDiscover(provider, values);
    if (!check.ok) { setErrors(check.errors); return; }
    setErrors({}); setError(null); setBusy(true);
    try {
      setRun(await sourcesApi.discover(check.body));
      setOffset(0); setSelected(new Set());
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setBusy(false);
    }
  };
  const goto = async (next) => {
    try { setRun(await sourcesApi.page(run.run_id, next, PAGE_SIZE)); setOffset(next); } catch (err) { setError(describeApiError(err)); }
  };
  const toggle = (id) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const selectPage = (on) => setSelected((s) => { const n = new Set(s); run.places.forEach((p) => (on ? n.add(p.external_id) : n.delete(p.external_id))); return n; });

  return (
    <div className="p-6 md:p-10 space-y-6 max-w-6xl" data-testid="sources-page">
      <div>
        <div className="mono-accent">// discovery.sources</div>
        <h1 className="text-4xl font-black tracking-tighter flex items-center gap-3"><Database size={32} /> Sources</h1>
        <p className="text-[#5F5F5A] mt-1 max-w-3xl">One place to discover businesses from open and official data. Each result keeps its source and licence; signals say why, and “unknown” is never a verdict. Nothing is sent from here.</p>
      </div>
      <div className="grid md:grid-cols-3 gap-3">{providers.map((p) => <ProviderCard key={p.name} provider={p} active={p.name === provider.name} onPick={pick} />)}</div>

      <form onSubmit={discover} className="surface p-5 space-y-4" data-testid="source-form">
        <div className="grid md:grid-cols-4 gap-3">
          <Field label="vertical" error={errors.vertical}>
            <select className="neo-input w-full" value={values.vertical} onChange={set("vertical")} data-testid="source-vertical">
              {provider.verticals.map((v) => <option key={v} value={v}>{VERTICAL_LABELS[v] || v}</option>)}
            </select>
          </Field>
          <Field label="limit" error={errors.limit}><input className="neo-input w-full" type="number" value={values.limit} onChange={set("limit")} data-testid="source-limit" /></Field>
          <Field label="country (ISO, e.g. FR)" error={errors.country}><input className="neo-input w-full" value={values.country} onChange={set("country")} maxLength={2} data-testid="source-country" /></Field>
          {provider.kind === "local" && <Field label="city (optional)" error={errors.city}><input className="neo-input w-full" value={values.city} onChange={set("city")} data-testid="source-city" /></Field>}
        </div>
        {provider.kind === "network" && (
          <div className="space-y-3">
            <TownSearch onPick={(t) => setValues((v) => ({ ...v, lat: String(t.lat), lon: String(t.lon), city: t.city, country: "FR" }))} />
            <div className="grid md:grid-cols-3 gap-3">
              <Field label="latitude" error={errors.lat}><input className="neo-input w-full" value={values.lat} onChange={set("lat")} data-testid="source-lat" /></Field>
              <Field label="longitude" error={errors.lon}><input className="neo-input w-full" value={values.lon} onChange={set("lon")} data-testid="source-lon" /></Field>
              <Field label={`radius (m, max ${provider.max_radius_m})`} error={errors.radius_m}><input className="neo-input w-full" type="number" value={values.radius_m} onChange={set("radius_m")} data-testid="source-radius" /></Field>
            </div>
          </div>
        )}
        {!edit && <p className="text-xs text-[#92400E]">Only owners and admins can run a discovery.</p>}
        {error && <div role="alert" className="text-sm text-[#991B1B]" data-testid="source-error">{error}</div>}
        <button className="btn-ink" type="submit" disabled={busy || !edit} data-testid="source-discover"><MagnifyingGlass size={14} /> {busy ? "DISCOVERING…" : "DISCOVER"}</button>
      </form>

      {run && <Results run={run} offset={offset} onPage={goto} selected={selected} toggle={toggle} onSelectPage={selectPage} flags={flags} canAdd={provider.kind === "local" || Boolean(flags.prospect_import)} />}
    </div>
  );
}
