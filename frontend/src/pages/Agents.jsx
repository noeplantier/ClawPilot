import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Robot, Play, Pause, Trash, Plus, Terminal, Circle, X } from "@phosphor-icons/react";

const STATUS_STYLE = {
  running: { color: "#10B981", label: "RUNNING" },
  idle: { color: "#5F5F5A", label: "IDLE" },
  paused: { color: "#F59E0B", label: "PAUSED" },
  error: { color: "#EF4444", label: "ERROR" },
};

export default function Agents() {
  const [list, setList] = useState([]);
  const [logs, setLogs] = useState({});
  const [showCreate, setShowCreate] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try { const { data } = await api.get("/agents"); setList(data); setError(null); }
    catch (e) { setError(e?.response?.data?.detail || "Agent activity is temporarily unavailable."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    load();
    const id = setInterval(() => { if (!document.hidden) load(); }, 30000);
    return () => clearInterval(id);
  }, [load]);

  const toggle = async (id) => {
    await api.post(`/agents/${id}/toggle`);
    load();
  };
  const remove = async (id) => {
    if (!window.confirm("Terminate agent?")) return;
    await api.delete(`/agents/${id}`);
    load();
  };
  const showLogs = async (id) => {
    const { data } = await api.get(`/agents/${id}/logs`);
    setLogs((l) => ({ ...l, [id]: data.lines }));
  };

  const create = async (payload) => {
    await api.post("/agents", payload);
    toast.success("Agent spawned");
    setShowCreate(false);
    load();
  };

  return (
    <div className="p-6 md:p-10 space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="mono-accent">// orchestrator.outreachos</div>
          <h1 className="text-4xl font-black tracking-tighter">Agents</h1>
          <p className="text-[#5F5F5A] mt-1">{list.filter((a) => a.status === "running").length} active · {list.length} total</p>
        </div>
        <button onClick={() => setShowCreate(true)} className="btn-primary" data-testid="spawn-agent-button"><Plus size={14} weight="bold" /> SPAWN AGENT</button>
      </div>

      {error && <div role="alert" className="surface p-4 text-sm" data-testid="agents-error"><p>{error}</p><button onClick={load} className="btn-ghost mt-2">RETRY</button></div>}
      {loading && list.length === 0 && <p role="status" className="surface p-4 text-sm">Loading agent status…</p>}
      {!loading && !error && list.length === 0 && <p className="surface p-8 text-sm text-muted-foreground" data-testid="agents-empty">No agents are configured. Create one only when an operator is ready to supervise it.</p>}
      <div className="grid md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {list.map((a) => {
          const st = STATUS_STYLE[a.status] || STATUS_STYLE.idle;
          return (
            <div
              key={a.id}
              className={`surface surface-hover p-5 relative ${a.status === "running" ? "border-beam" : ""}`}
              data-testid={`agent-card-${a.id}`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <Robot size={24} weight="duotone" style={{ color: st.color }} />
                    <h3 className="font-display text-lg font-bold">{a.name}</h3>
                  </div>
                  <div className="mono-accent text-[#5F5F5A] mt-0.5">role · {a.role}</div>
                </div>
                <div className="flex items-center gap-1.5 text-xs font-mono" style={{ color: st.color }}>
                  <Circle size={8} weight="fill" className={a.status === "running" ? "pulse-dot" : ""} />
                  {st.label}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 mt-4">
                <div>
                  <div className="mono-accent text-[#5F5F5A]">tasks.done</div>
                  <div className="font-mono text-xl font-bold">{a.tasks_completed}</div>
                </div>
                <div>
                  <div className="mono-accent text-[#5F5F5A]">in.queue</div>
                  <div className="font-mono text-xl font-bold">{a.tasks_in_queue}</div>
                </div>
              </div>

              <div className="flex gap-2 mt-4">
                <button onClick={() => toggle(a.id)} className="btn-ghost flex-1 justify-center" data-testid={`toggle-agent-${a.id}`}>
                  {a.status === "running" ? <><Pause size={12} weight="fill" /> PAUSE</> : <><Play size={12} weight="fill" /> START</>}
                </button>
                <button onClick={() => showLogs(a.id)} className="btn-ghost" data-testid={`logs-${a.id}`}><Terminal size={12} /></button>
                <button onClick={() => remove(a.id)} className="btn-danger !py-1.5 !px-2" aria-label={`Delete agent ${a.name}`} data-testid={`delete-agent-${a.id}`}><Trash size={12} /></button>
              </div>

              {logs[a.id] && (
                <div className="mt-3 surface bg-[#F6F8FC] p-3 text-xs font-mono space-y-1 max-h-[140px] overflow-y-auto">
                  {logs[a.id].map((l, idx) => (
                    <div key={idx} className="text-[#10B981]/80">{l}</div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {showCreate && <CreateAgent onClose={() => setShowCreate(false)} onSave={create} />}
    </div>
  );
}

function CreateAgent({ onClose, onSave }) {
  const [name, setName] = useState("");
  const [role, setRole] = useState("outreach");
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="fixed inset-0 z-50 bg-[#0F172A]/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <motion.div initial={{ y: 10 }} animate={{ y: 0 }} className="surface w-full max-w-md p-8 relative" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} className="absolute top-4 right-4 text-[#5F5F5A] hover:text-[#0A0A0A]"><X size={20} /></button>
        <div className="mono-accent">/// spawn.agent</div>
        <h2 className="text-2xl font-black tracking-tighter mt-1">Deploy new agent</h2>

        <div className="space-y-3 mt-6">
          <div>
            <label className="mono-accent block mb-1.5">agent.name</label>
            <input className="neo-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Zephyr" data-testid="agent-name-input" />
          </div>
          <div>
            <label className="mono-accent block mb-1.5">role</label>
            <select className="neo-input" value={role} onChange={(e) => setRole(e.target.value)} data-testid="agent-role-select">
              <option value="outreach">outreach</option>
              <option value="enrichment">enrichment</option>
              <option value="scraper">scraper</option>
              <option value="responder">responder</option>
            </select>
          </div>
        </div>

        <div className="flex gap-3 mt-6">
          <button onClick={() => name ? onSave({ name, role }) : toast.error("Name required")} className="btn-primary" data-testid="save-agent-button">DEPLOY</button>
          <button onClick={onClose} className="btn-ghost">CANCEL</button>
        </div>
      </motion.div>
    </motion.div>
  );
}
