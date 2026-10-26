import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const CATEGORIES = ["restaurant", "cafe", "hotel", "shop", "office", "beauty", "dentist", "company"];

export default function DiscoveryMap() {
  const [bounds, setBounds] = useState(["", "", "", ""]);
  const [category, setCategory] = useState("restaurant");
  const [job, setJob] = useState(null);
  const [places, setPlaces] = useState([]);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const bbox = useMemo(() => bounds.map(Number), [bounds]);

  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return undefined;
    const timer = setInterval(async () => {
      try {
        const { data } = await api.get(`/prospecting/jobs/${job.job_id}`);
        setJob(data);
        setPlaces(data.places || []);
      } catch { /* transient polling failure; next poll retries */ }
    }, 2500);
    return () => clearInterval(timer);
  }, [job]);

  const search = async (event) => {
    event.preventDefault();
    if (bounds.some((value) => value === "") || bbox.some((value) => !Number.isFinite(value))) {
      toast.error("Enter south, west, north and east coordinates");
      return;
    }
    setBusy(true); setPlaces([]); setSelected(null);
    try {
      const { data } = await api.post("/prospecting/search", { bbox, category });
      setJob(data);
      if (data.status === "completed") {
        const cached = await api.get(`/prospecting/jobs/${data.job_id}`);
        setJob(cached.data);
        setPlaces(cached.data.places || []);
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || "Could not queue map search");
    } finally { setBusy(false); }
  };

  const convert = async (place) => {
    try {
      const { data } = await api.post(`/prospecting/places/${place.id}/convert`, {});
      toast.success(data.created ? "Lead added to CRM" : "Lead already exists");
      setPlaces((list) => list.map((item) => item.id === place.id ? { ...item, lead_id: data.lead_id } : item));
    } catch (error) { toast.error(error.response?.data?.detail || "Could not add lead"); }
  };

  const enrich = async (place) => {
    try {
      const { data } = await api.post(`/prospecting/leads/${place.lead_id}/enrich`);
      toast.success(data.cached ? "Enrichment is already queued" : "Enrichment queued");
    } catch (error) { toast.error(error.response?.data?.detail || "Could not queue enrichment"); }
  };

  const position = (place) => {
    const [south, west, north, east] = bbox;
    return { left: `${Math.max(1, Math.min(99, ((place.longitude - west) / (east - west)) * 100))}%`, top: `${Math.max(1, Math.min(99, (1 - (place.latitude - south) / (north - south)) * 100))}%` };
  };

  return <section className="surface p-5 space-y-4">
    <div><div className="mono-accent">// public_sources.overpass</div><h2 className="text-2xl font-bold">Map discovery</h2><p className="text-sm text-[#6B6B66]">Search a small area. Results come from OpenStreetMap and are stored in your CRM workspace.</p></div>
    <form onSubmit={search} className="grid grid-cols-2 md:grid-cols-6 gap-2 items-end">
      <label className="text-xs">South<input aria-label="South latitude" className="neo-input w-full" type="number" step="any" value={bounds[0]} onChange={(e) => setBounds((v) => v.map((x, i) => i === 0 ? e.target.value : x))} /></label>
      <label className="text-xs">West<input aria-label="West longitude" className="neo-input w-full" type="number" step="any" value={bounds[1]} onChange={(e) => setBounds((v) => v.map((x, i) => i === 1 ? e.target.value : x))} /></label>
      <label className="text-xs">North<input aria-label="North latitude" className="neo-input w-full" type="number" step="any" value={bounds[2]} onChange={(e) => setBounds((v) => v.map((x, i) => i === 2 ? e.target.value : x))} /></label>
      <label className="text-xs">East<input aria-label="East longitude" className="neo-input w-full" type="number" step="any" value={bounds[3]} onChange={(e) => setBounds((v) => v.map((x, i) => i === 3 ? e.target.value : x))} /></label>
      <label className="text-xs">Category<select className="neo-input w-full" value={category} onChange={(e) => setCategory(e.target.value)}>{CATEGORIES.map((item) => <option key={item}>{item}</option>)}</select></label>
      <button className="btn-primary" disabled={busy}>{busy ? "QUEUING…" : "SEARCH MAP"}</button>
    </form>
    {job && <p className="mono-accent" role="status">Job {job.status}{job.result_count !== undefined ? ` · ${job.result_count} results` : ""}{job.error_code ? ` · ${job.error_code}` : ""}</p>}
    <div className="relative h-[420px] overflow-hidden rounded border border-[#D6D3C8] bg-[#E7E9DF]" aria-label="Map of discovered places">
      {bounds.every((value) => value !== "") && bbox.every(Number.isFinite) && <iframe title="OpenStreetMap search area" className="absolute inset-0 w-full h-full border-0 pointer-events-none" src={`https://www.openstreetmap.org/export/embed.html?bbox=${bbox[1]},${bbox[0]},${bbox[3]},${bbox[2]}&layer=mapnik`} />}
      {places.map((place) => <button key={place.id} type="button" title={place.name} aria-label={`Select ${place.name}`} onClick={() => setSelected(place)} className={`absolute -translate-x-1/2 -translate-y-1/2 w-7 h-7 rounded-full border-2 border-white shadow bg-brand-violet text-white text-xs font-bold ${selected?.id === place.id ? "ring-4 ring-brand-violet/30" : ""}`} style={position(place)}>•</button>)}
      {!places.length && <div className="absolute inset-0 flex items-center justify-center text-sm text-[#6B6B66]">Enter a bounding box and search to load real OpenStreetMap places.</div>}
      <div className="absolute bottom-2 right-2 text-[10px] bg-white/90 px-2 py-1 rounded">© OpenStreetMap contributors</div>
    </div>
    {selected && <div className="flex flex-wrap items-center justify-between gap-3 border border-[#D6D3C8] p-3 rounded">
      <div><strong>{selected.name}</strong><div className="text-xs text-[#6B6B66]">{selected.address || selected.category}{selected.website ? ` · ${selected.website}` : ""}</div></div>
      {selected.lead_id ? <div className="flex gap-2"><button className="btn-purple" onClick={() => enrich(selected)}>ENRICH</button><a className="btn-ghost" href={`/leads?lead=${selected.lead_id}`}>IN CRM</a></div> : <button className="btn-primary" onClick={() => convert(selected)}>ADD TO CRM</button>}
    </div>}
    <p className="text-[11px] text-[#6B6B66]">Data © OpenStreetMap contributors, available under the Open Database License (ODbL).</p>
  </section>;
}
