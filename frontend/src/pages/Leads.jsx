import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  Plus, MagnifyingGlass, Envelope, Phone, Trash, Table, Kanban, Sparkle, X, UploadSimple, PaperPlaneTilt,
} from "@phosphor-icons/react";
import AIComposerModal from "@/components/AIComposerModal";
import BulkLeadsModal from "@/components/BulkLeadsModal";
import BatchComposerModal from "@/components/BatchComposerModal";
import LeadsBulkBar from "@/components/LeadsBulkBar";
import LeadDetailDrawer from "@/components/LeadDetailDrawer";
import HeatBadge from "@/components/outreach/HeatBadge";
import EmptyToggle from "@/components/outreach/EmptyToggle";
import { LANES, LANE_LABEL, inLane, laneCounts, splitEmpty } from "@/lib/heat";
import { LIVE_MS, useLive } from "@/lib/live";
import { readPref, writePref } from "@/lib/uiPrefs";
import DiscoveryMap from "@/components/DiscoveryMap";

// Where a prospect from discovery (map, sources, import) stands in the human review; a CRM lead has none.
const REVIEW_LABEL = { pending: "to review", approved: "approved", rejected: "rejected" };
const REVIEW_CHIP = { pending: "chip-warn", approved: "chip-success", rejected: "chip-danger" };
const STAGES = ["new", "contacted", "engaged", "qualified", "won", "lost"];
const STAGE_COLORS = {
  new: "#9B74FA", contacted: "#94A3B8", engaged: "#C4B5FD",
  qualified: "#F59E0B", won: "#10B981", lost: "#EF4444",
};

export default function Leads() {
  const [searchParams, setSearchParams] = useSearchParams();
  const view = searchParams.get("view") === "kanban" ? "kanban" : searchParams.get("view") === "map" ? "map" : "table";
  const [search, setSearch] = useState("");
  const [lane, setLane] = useState("all"); // heat filter: all | top | hot | warm | cold
  const [showEmpty, setShowEmpty] = useState(() => readPref("leads.showEmpty", false)); // leads with no e-mail, phone or website
  const [showCreate, setShowCreate] = useState(false);
  const [showBulk, setShowBulk] = useState(false);
  const [showBatch, setShowBatch] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiDefaults, setAiDefaults] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [detailLeadId, setDetailLeadId] = useState(null);
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [fitSort, setFitSort] = useState(false);
  const [scoringJob, setScoringJob] = useState(null);
  const [scoringError, setScoringError] = useState(null);

  // Real leads, hottest first (real information + score), refreshed in the background.
  const live = useLive(() => api.get("/leads", { params: { search, sort: "heat" } }).then((r) => r.data), [search], { key: `leads:${search || ""}` });
  const liveReload = live.reload;
  const everyLead = useMemo(() => live.data || [], [live.data]);
  const { shown: reachable, empty } = useMemo(() => splitEmpty(everyLead, showEmpty), [everyLead, showEmpty]);
  const counts = useMemo(() => laneCounts(reachable), [reachable]);
  const leads = useMemo(() => {
    let result = inLane(reachable, lane);
    if (priorityFilter !== "all") result = result.filter((lead) => lead.priority === priorityFilter);
    if (fitSort) result = [...result].sort((a, b) => (b.fit_score ?? -1) - (a.fit_score ?? -1));
    return result;
  }, [reachable, lane, priorityFilter, fitSort]);
  const toggleEmpty = () => setShowEmpty((v) => { writePref("leads.showEmpty", !v); return !v; });
  const setCrmView = (next) => {
    setSearchParams(next === "table" ? {} : { view: next }, { replace: true });
  };

  const allVisible = leads.map((l) => l.id);
  const toggleOne = (id) =>
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  const toggleAll = () =>
    setSelected((s) => (s.size === allVisible.length ? new Set() : new Set(allVisible)));

  const load = () => live.reload();

  const startScoring = async () => {
    if (!selected.size || selected.size > 200 || scoringJob) return;
    setScoringError(null);
    try {
      const { data } = await api.post("/leads/score", { lead_ids: Array.from(selected) });
      setScoringJob({ id: data.job_id, status: data.status, total_items: data.lead_count, processed_items: 0, failed_items: 0 });
    } catch (error) {
      setScoringError(error?.response?.data?.detail || "Impossible de démarrer le scoring.");
    }
  };

  const activeJobId = scoringJob && !["succeeded", "partial", "failed"].includes(scoringJob.status) ? scoringJob.id : null;
  const scoringActive = !!activeJobId;
  useEffect(() => {
    if (!activeJobId) return undefined;
    let stopped = false;
    let timer;
    const poll = async () => {
      try {
        const { data } = await api.get(`/jobs/${activeJobId}`);
        if (stopped) return;
        setScoringJob(data);
        if (["succeeded", "partial", "failed"].includes(data.status)) {
          setSelected(new Set());
          liveReload();
          if (data.status === "succeeded") toast.success("Scoring terminé");
          else if (data.status === "partial") toast.warning(data.error || "Scoring partiel");
          else toast.error(data.error || "Le job de scoring a échoué");
        } else {
          timer = setTimeout(poll, 2500);
        }
      } catch (error) {
        if (stopped) return;
        setScoringError(error?.response?.data?.detail || "Le suivi du job est momentanément indisponible.");
        timer = setTimeout(poll, 5000);
      }
    };
    poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [activeJobId, liveReload]);

  const updateStage = async (id, stage) => {
    await api.patch(`/leads/${id}`, { stage });
    load();
  };

  const remove = async (id) => {
    if (!window.confirm("Delete lead?")) return;
    await api.delete(`/leads/${id}`);
    toast.success("Lead removed");
    load();
  };

  const enrich = async () => {
    const { data } = await api.post("/leads/enrich");
    toast.success(`Enriched ${data.enriched} leads`);
    load();
  };

  const writeFor = (l) => {
    setAiDefaults({ recipient_name: l.full_name, company: l.company || "", language: l.language || "en" });
    setAiOpen(true);
  };

  return (
    <div className="p-6 md:p-10 space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="mono-accent">// crm.pipeline</div>
          <h1 className="text-4xl font-black tracking-tighter">Leads</h1>
          <p className="text-soft mt-1">
            {leads.length}{lane !== "all" ? ` ${LANE_LABEL[lane].toLowerCase()}` : ""} contact{leads.length === 1 ? "" : "s"} across the pipeline, hottest first.
          </p>
          <p className="text-xs mt-1 inline-flex items-center gap-2 text-brand-lilac" role="status" aria-live="polite" data-testid="leads-live">
            <span className="pos-live-dot" aria-hidden="true" />
            {live.stale ? "Refresh failed: showing the last data. " : ""}
            {live.updatedAt ? `Live · updated ${live.updatedAt.toLocaleTimeString()} · every ${LIVE_MS / 1000} s` : "Loading…"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <div className="flex items-center gap-2 px-3 py-1.5 border border-border rounded-md bg-card">
            <MagnifyingGlass size={14} className="text-faint" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search name, email, company" className="bg-transparent outline-none text-sm w-40 sm:w-56 font-mono" data-testid="leads-search" />
          </div>
          <button onClick={() => setCrmView(view === "map" ? "table" : "map")} className="btn-ghost" data-testid="toggle-map">
            {view === "map" ? <Table size={14} /> : <MagnifyingGlass size={14} />} {view === "map" ? "CRM TABLE" : "MAP SEARCH"}
          </button>
          {view !== "map" && <button onClick={() => setCrmView(view === "table" ? "kanban" : "table")} className="btn-ghost" data-testid="toggle-view">
            {view === "table" ? <Kanban size={14} /> : <Table size={14} />} {view === "table" ? "KANBAN" : "TABLE"}
          </button>}
          {view !== "map" && <button onClick={() => setShowBatch(true)} className="btn-ink" data-testid="open-batch-send"><PaperPlaneTilt size={14} weight="fill" /> BATCH SEND</button>}
          {view !== "map" && <button onClick={enrich} className="btn-purple" data-testid="enrich-leads-button"><Sparkle size={14} weight="fill" /> ENRICH</button>}
          <button onClick={() => setShowBulk(true)} className="btn-ghost" data-testid="open-bulk-import"><UploadSimple size={14} /> BULK IMPORT</button>
          <button onClick={() => setShowCreate(true)} className="btn-primary" data-testid="add-lead-button"><Plus size={14} weight="bold" /> ADD LEAD</button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter by heat" data-testid="leads-lanes">
        {LANES.map((k) => [k, `${LANE_LABEL[k]} ${k === "all" ? counts.total : counts[k]}`]).map(([key, label]) => (
          <button key={key} onClick={() => setLane(key)} aria-pressed={lane === key} data-testid={`lane-${key}`}
            className={`px-3 py-1 rounded-full text-xs border transition-colors ${lane === key ? "bg-brand-violet text-white border-brand-violet" : "bg-card border-border hover:bg-white/[0.04]"}`}>
            {label}
          </button>
        ))}
        <span className="text-xs text-soft">Heat = real information known + score; TOP = 80 or more. Hover a badge to see what is missing.</span>
        <EmptyToggle empty={empty} showEmpty={showEmpty} onToggle={toggleEmpty} testId="leads-empty-toggle" />
      </div>

      <div className="flex flex-wrap items-center gap-3" data-testid="qualification-controls">
        <label className="text-xs flex items-center gap-2">Priority
          <select value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)} data-testid="priority-filter" className="border rounded px-2 py-1">
            <option value="all">All</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
          </select>
        </label>
        <button type="button" onClick={() => setFitSort((value) => !value)} aria-pressed={fitSort} data-testid="fit-sort" className="btn-ghost !py-1 !px-2">
          {fitSort ? "FIT SCORE ↓" : "SORT BY FIT SCORE"}
        </button>
        <button type="button" onClick={startScoring} disabled={!selected.size || selected.size > 200 || scoringActive} className="btn-primary !py-1 !px-3" data-testid="score-selected">
          {scoringActive ? "SCORING…" : `SCORER LA SÉLECTION${selected.size ? ` (${selected.size})` : ""}`}
        </button>
        {selected.size > 200 && <span className="text-xs text-red-300" role="alert">Select at most 200 leads.</span>}
      </div>

      {scoringError && <div role="alert" className="text-sm text-red-300" data-testid="scoring-error">{scoringError}</div>}
      {scoringJob && <section className="surface p-4 space-y-2" role="status" aria-live="polite" data-testid="scoring-job">
        <div className="flex justify-between text-sm"><strong>{scoringJob.status === "running" ? "Scoring en cours" : scoringJob.status === "queued" ? "Scoring en attente" : `Scoring ${scoringJob.status}`}</strong>
          <span>{scoringJob.processed_items || 0} / {scoringJob.total_items} · {scoringJob.failed_items || 0} failed</span></div>
        <progress className="w-full" max={scoringJob.total_items || 1} value={(scoringJob.processed_items || 0) + (scoringJob.failed_items || 0)} aria-label="Scoring progress" />
        {scoringJob.error && <p className="text-sm text-red-300">{scoringJob.error}</p>}
      </section>}

      {live.error && <div role="alert" className="text-sm text-red-300" data-testid="leads-error">{live.error}</div>}

      {view === "map" ? <DiscoveryMap /> : view === "table" ? (
        <div className="surface overflow-hidden overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-white/[0.04] border-b border-border">
              <tr className="text-left mono-accent">
                <th className="p-3 w-10">
                  <input
                    type="checkbox"
                    checked={selected.size > 0 && selected.size === allVisible.length}
                    onChange={toggleAll}
                    className="accent-brand-violet"
                    aria-label="Select all visible leads"
                    data-testid="leads-select-all"
                  />
                </th>
                <th className="p-3">Name</th>
                <th className="p-3">Company</th>
                <th className="p-3">Contact</th>
                <th className="p-3">Country</th>
                <th className="p-3">Stage</th>
                <th className="p-3">Heat</th>
                <th className="p-3">Score</th>
                <th className="p-3">Qualification</th>
                <th className="p-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((l) => (
                <tr
                  key={l.id}
                  onClick={() => setDetailLeadId(l.id)}
                  className={`border-b border-border hover:bg-white/[0.04] transition-colors cursor-pointer ${selected.has(l.id) ? "bg-white/10" : live.fresh.has(l.id) ? "bg-brand-violet/10" : ""}`}
                  data-testid={`lead-row-${l.id}`}
                >
                  <td className="p-3" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selected.has(l.id)}
                      onChange={() => toggleOne(l.id)}
                      className="accent-brand-violet"
                      aria-label={`Select ${l.full_name}`}
                      data-testid={`lead-check-${l.id}`}
                    />
                  </td>
                  <td className="p-3">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-brand-violet/30 to-void-surface/30 flex items-center justify-center text-xs font-bold">
                        {(l.full_name || "?").charAt(0)}
                      </div>
                      <div>
                        <div className="font-medium">
                          {l.full_name}
                          {live.fresh.has(l.id) && <span className="chip chip-cyan ml-2" data-testid="lead-new">new</span>}
                          {l.review_status && (
                            <Link to={`/app/prospects/${l.id}`} className={`chip ml-2 ${REVIEW_CHIP[l.review_status]}`} data-testid={`lead-review-${l.id}`} title="Open the prospect: its sources, signals and review">
                              {REVIEW_LABEL[l.review_status]}
                            </Link>
                          )}
                        </div>
                        <div className="mono-accent text-faint text-[10px]">{l.title || "—"}</div>
                      </div>
                    </div>
                  </td>
                  <td className="p-3 text-soft">{l.company}</td>
                  <td className="p-3 font-mono text-xs text-soft">
                    <div>{l.email || <span className="text-faint">e-mail not known</span>}</div>
                    <div>{l.phone || <span className="text-faint">phone not known</span>}</div>
                  </td>
                  <td className="p-3 font-mono text-xs">{l.country}</td>
                  <td className="p-3" onClick={(e) => e.stopPropagation()}>
                    <select
                      value={l.stage}
                      onChange={(e) => updateStage(l.id, e.target.value)}
                      className="bg-transparent border border-border rounded px-2 py-1 text-xs font-mono uppercase"
                      style={{ color: STAGE_COLORS[l.stage] }}
                      aria-label={`Stage of ${l.full_name}`}
                      data-testid={`stage-select-${l.id}`}
                    >
                      {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td className="p-3"><HeatBadge heat={l.heat} /></td>
                  <td className="p-3">
                    {l.heat && !l.heat.scored ? (
                      <span className="text-xs text-faint" data-testid="lead-not-scored">not scored</span>
                    ) : (
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1 bg-white/[0.04] rounded overflow-hidden">
                          <div className="h-full bg-gradient-to-r from-brand-violet to-void-surface" style={{ width: `${l.score}%` }} />
                        </div>
                        <span className="font-mono text-xs w-6 text-right">{l.score}</span>
                      </div>
                    )}
                  </td>
                  <td className="p-3 min-w-48" data-testid={`qualification-${l.id}`}>
                    {l.enrichment_status !== "completed" ? <span className="text-xs text-amber-300">Enrichissement requis</span> : l.fit_score == null ? <span className="text-xs text-faint">Scoring requis</span> : (
                      <div className="space-y-1">
                        <div className="flex items-center gap-2"><span className={`chip ${l.priority === "high" ? "chip-purple" : l.priority === "medium" ? "chip-warn" : "chip-ink"}`}>{l.priority ? (l.priority === "high" ? "Priority" : l.priority[0].toUpperCase() + l.priority.slice(1)) : "Unknown"}</span><span className="font-mono text-xs">Fit {l.fit_score}</span></div>
                        <div className="text-[10px] text-soft">Website {l.website_quality ?? "Unknown"} · Digital {l.digital_maturity ?? "Unknown"}</div>
                      </div>
                    )}
                  </td>
                  <td className="p-3" onClick={(e) => e.stopPropagation()}>
                    <div className="flex justify-end gap-1">
                      <button onClick={() => writeFor(l)} className="btn-ghost !py-1 !px-2" title="AI write" aria-label={`Write to ${l.full_name} with AI`} data-testid={`ai-${l.id}`}><Sparkle size={12} /></button>
                      {l.email && <a href={`mailto:${l.email}`} className="btn-ghost !py-1 !px-2" aria-label={`E-mail ${l.full_name}`}><Envelope size={12} /></a>}
                      {l.phone && <a href={`tel:${l.phone}`} className="btn-ghost !py-1 !px-2" aria-label={`Call ${l.full_name}`}><Phone size={12} /></a>}
                      <button onClick={() => remove(l.id)} className="btn-danger !py-1 !px-2" aria-label={`Delete ${l.full_name}`} data-testid={`delete-lead-${l.id}`}><Trash size={12} /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {leads.length === 0 && (
                <tr><td colSpan="10" className="p-10 text-center text-soft" data-testid="leads-none">
                  {everyLead.length === 0 ? "No leads. Add your first or import." : reachable.length === 0 ? "Every lead is empty (no e-mail, phone or website): they are hidden. Show them above, or add contact details." : "No lead in this heat tier."}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {STAGES.map((s) => {
            const items = leads.filter((l) => l.stage === s);
            return (
              <div key={s} className="kanban-column p-3 min-h-[400px]" data-testid={`kanban-${s}`}>
                <div className="flex items-center justify-between mb-3 pb-2 border-b border-border">
                  <span className="mono-accent" style={{ color: STAGE_COLORS[s] }}>{s}</span>
                  <span className="font-mono text-xs text-soft">{items.length}</span>
                </div>
                <div className="space-y-2">
                  {items.map((l) => (
                    <motion.div
                      key={l.id}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      onClick={() => setDetailLeadId(l.id)}
                      className="surface p-3 text-xs cursor-pointer hover:border-brand-violet/40 transition"
                      data-testid={`kanban-card-${l.id}`}
                    >
                      <div className="font-semibold text-sm text-foreground">{l.full_name}</div>
                      <div className="text-soft mt-0.5">{l.company}</div>
                      <div className="mt-2"><HeatBadge heat={l.heat} compact /></div>
                      <div className="mono-accent text-faint mt-2 flex items-center justify-between">
                        <span>{l.country}</span>
                        <span>{l.heat && !l.heat.scored ? "not scored" : `score · ${l.score}`}</span>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {showCreate && <CreateLead onClose={() => setShowCreate(false)} onSaved={() => { setShowCreate(false); load(); }} />}
      <BulkLeadsModal open={showBulk} onClose={() => setShowBulk(false)} onDone={load} />
      <BatchComposerModal open={showBatch} onClose={() => setShowBatch(false)} />
      <AIComposerModal open={aiOpen} onClose={() => setAiOpen(false)} defaults={aiDefaults} />
      <LeadDetailDrawer open={!!detailLeadId} leadId={detailLeadId} onClose={() => setDetailLeadId(null)} onUpdate={load} />
      <LeadsBulkBar
        selectedIds={Array.from(selected)}
        onCleared={() => setSelected(new Set())}
        onDone={() => { setSelected(new Set()); load(); }}
      />
    </div>
  );
}

function CreateLead({ onClose, onSaved }) {
  const [f, setF] = useState({ full_name: "", email: "", phone: "", company: "", title: "", country: "", language: "en" });
  const [saving, setSaving] = useState(false);
  const u = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const save = async () => {
    if (!f.full_name) { toast.error("Name required"); return; }
    setSaving(true);
    try {
      const payload = { ...f };
      ["email", "phone", "company", "title", "country"].forEach((key) => {
        payload[key] = f[key].trim() || null;
      });
      await api.post("/leads", payload);
      toast.success("Lead added");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    } finally { setSaving(false); }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <motion.div initial={{ y: 10 }} animate={{ y: 0 }} className="surface w-full max-w-xl p-8 relative" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} className="absolute top-4 right-4 text-soft hover:text-foreground" data-testid="close-create-lead"><X size={20} /></button>
        <div className="mono-accent">/// new.lead</div>
        <h2 className="text-2xl font-black tracking-tighter mt-1">Add Lead</h2>

        <div className="grid md:grid-cols-2 gap-3 mt-6">
          {[
            ["full_name", "Full Name", "Priya Shah"],
            ["email", "Email", "priya@acme.io"],
            ["phone", "Phone", "+14155550123"],
            ["company", "Company", "Acme Labs"],
            ["title", "Title", "VP Growth"],
            ["country", "Country", "IN"],
          ].map(([k, l, p]) => (
            <div key={k} className={k === "full_name" ? "md:col-span-2" : ""}>
              <label className="mono-accent block mb-1.5">{l}</label>
              <input className="neo-input" value={f[k]} onChange={u(k)} placeholder={p} data-testid={`lead-${k}`} />
            </div>
          ))}
        </div>
        <div className="flex gap-3 mt-6">
          <button onClick={save} disabled={saving} className="btn-primary" data-testid="save-lead-button">
            {saving ? "SAVING..." : "ADD LEAD"}
          </button>
          <button onClick={onClose} className="btn-ghost">CANCEL</button>
        </div>
      </motion.div>
    </motion.div>
  );
}
