import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  Plus, MagnifyingGlass, Envelope, Phone, Trash, Table, Kanban, Sparkle, X,
} from "@phosphor-icons/react";
import AIComposerModal from "@/components/AIComposerModal";

const STAGES = ["new", "contacted", "engaged", "qualified", "won", "lost"];
const STAGE_COLORS = {
  new: "#00E5FF", contacted: "#2962FF", engaged: "#BF55EC",
  qualified: "#F59E0B", won: "#10B981", lost: "#EF4444",
};

export default function Leads() {
  const [leads, setLeads] = useState([]);
  const [view, setView] = useState("table");
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiDefaults, setAiDefaults] = useState(null);

  const load = async () => {
    const { data } = await api.get("/leads", { params: { search } });
    setLeads(data);
  };
  useEffect(() => { load(); }, [search]); // eslint-disable-line

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
          <p className="text-[#8B949E] mt-1">{leads.length} contacts across the pipeline.</p>
        </div>
        <div className="flex gap-2 items-center">
          <div className="flex items-center gap-2 px-3 py-1.5 border border-[#262626] rounded-md bg-[#0A0A0A]">
            <MagnifyingGlass size={14} className="text-[#4B5563]" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search name, email, company" className="bg-transparent outline-none text-sm w-56 font-mono" data-testid="leads-search" />
          </div>
          <button onClick={() => setView(view === "table" ? "kanban" : "table")} className="btn-ghost" data-testid="toggle-view">
            {view === "table" ? <Kanban size={14} /> : <Table size={14} />} {view === "table" ? "KANBAN" : "TABLE"}
          </button>
          <button onClick={enrich} className="btn-purple" data-testid="enrich-leads-button"><Sparkle size={14} weight="fill" /> ENRICH</button>
          <button onClick={() => setShowCreate(true)} className="btn-primary" data-testid="add-lead-button"><Plus size={14} weight="bold" /> ADD LEAD</button>
        </div>
      </div>

      {view === "table" ? (
        <div className="surface overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-[#080808] border-b border-[#262626]">
              <tr className="text-left mono-accent">
                <th className="p-3">Name</th>
                <th className="p-3">Company</th>
                <th className="p-3">Email</th>
                <th className="p-3">Country</th>
                <th className="p-3">Stage</th>
                <th className="p-3">Score</th>
                <th className="p-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((l, i) => (
                <motion.tr
                  key={l.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: i * 0.02 }}
                  className="border-b border-[#141414] hover:bg-[#0c0c0c] transition-colors"
                  data-testid={`lead-row-${l.id}`}
                >
                  <td className="p-3">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-[#00E5FF]/30 to-[#BF55EC]/30 flex items-center justify-center text-xs font-bold">
                        {(l.full_name || "?").charAt(0)}
                      </div>
                      <div>
                        <div className="font-medium">{l.full_name}</div>
                        <div className="mono-accent text-[#4B5563] text-[10px]">{l.title || "—"}</div>
                      </div>
                    </div>
                  </td>
                  <td className="p-3 text-[#8B949E]">{l.company}</td>
                  <td className="p-3 font-mono text-xs text-[#8B949E]">{l.email}</td>
                  <td className="p-3 font-mono text-xs">{l.country}</td>
                  <td className="p-3">
                    <select
                      value={l.stage}
                      onChange={(e) => updateStage(l.id, e.target.value)}
                      className="bg-transparent border border-[#262626] rounded px-2 py-1 text-xs font-mono uppercase"
                      style={{ color: STAGE_COLORS[l.stage] }}
                      data-testid={`stage-select-${l.id}`}
                    >
                      {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td className="p-3">
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-1 bg-[#141414] rounded overflow-hidden">
                        <div className="h-full bg-gradient-to-r from-[#00E5FF] to-[#BF55EC]" style={{ width: `${l.score}%` }} />
                      </div>
                      <span className="font-mono text-xs w-6 text-right">{l.score}</span>
                    </div>
                  </td>
                  <td className="p-3">
                    <div className="flex justify-end gap-1">
                      <button onClick={() => writeFor(l)} className="btn-ghost !py-1 !px-2" title="AI write" data-testid={`ai-${l.id}`}><Sparkle size={12} /></button>
                      {l.email && <a href={`mailto:${l.email}`} className="btn-ghost !py-1 !px-2"><Envelope size={12} /></a>}
                      {l.phone && <a href={`tel:${l.phone}`} className="btn-ghost !py-1 !px-2"><Phone size={12} /></a>}
                      <button onClick={() => remove(l.id)} className="btn-ghost !py-1 !px-2 hover:!border-[#EF4444]" data-testid={`delete-lead-${l.id}`}><Trash size={12} /></button>
                    </div>
                  </td>
                </motion.tr>
              ))}
              {leads.length === 0 && (
                <tr><td colSpan="7" className="p-10 text-center text-[#8B949E]">No leads. Add your first or import.</td></tr>
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
                <div className="flex items-center justify-between mb-3 pb-2 border-b border-[#262626]">
                  <span className="mono-accent" style={{ color: STAGE_COLORS[s] }}>{s}</span>
                  <span className="font-mono text-xs text-[#8B949E]">{items.length}</span>
                </div>
                <div className="space-y-2">
                  {items.map((l) => (
                    <motion.div
                      key={l.id}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="surface p-3 text-xs cursor-pointer hover:border-[#00E5FF]/40 transition"
                    >
                      <div className="font-semibold text-sm text-white">{l.full_name}</div>
                      <div className="text-[#8B949E] mt-0.5">{l.company}</div>
                      <div className="mono-accent text-[#4B5563] mt-2 flex items-center justify-between">
                        <span>{l.country}</span>
                        <span>score · {l.score}</span>
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
      <AIComposerModal open={aiOpen} onClose={() => setAiOpen(false)} defaults={aiDefaults} />
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
      await api.post("/leads", f);
      toast.success("Lead added");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    } finally { setSaving(false); }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="fixed inset-0 z-50 bg-black/80 backdrop-blur-xl flex items-center justify-center p-4" onClick={onClose}>
      <motion.div initial={{ y: 10 }} animate={{ y: 0 }} className="surface w-full max-w-xl p-8 relative" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} className="absolute top-4 right-4 text-[#8B949E] hover:text-white" data-testid="close-create-lead"><X size={20} /></button>
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
