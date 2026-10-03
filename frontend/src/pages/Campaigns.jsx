import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  Plus, Play, Pause, Trash, Target, PaperPlaneTilt, Eye, ChatCircleDots, Rocket, X, ArrowRight, Sparkle, ArrowSquareOut, Users,
} from "@phosphor-icons/react";
import CampaignDetailDrawer from "@/components/CampaignDetailDrawer";
import { describeLaunch, launchErrorText } from "@/lib/campaignLaunch";

const STATUS_CHIP = {
  draft: "chip-warn",
  running: "chip-success",
  paused: "chip-warn",
  completed: "chip-cyan",
};

export default function Campaigns() {
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [drawerId, setDrawerId] = useState(null);

  const load = () => api.get("/campaigns").then((r) => setList(r.data));

  useEffect(() => { load(); }, []);

  const create = async (payload) => {
    await api.post("/campaigns", payload);
    toast.success("Campaign created");
    setOpen(false);
    load();
  };

  const launch = async (id) => {
    try {
      const { data } = await api.post(`/campaigns/${id}/launch`);
      const { level, text } = describeLaunch(data);
      toast[level](text);
    } catch (err) {
      toast.error(launchErrorText(err));
    }
    load();
  };

  const toggle = async (c) => {
    const next = c.status === "running" ? "paused" : "running";
    await api.patch(`/campaigns/${c.id}`, { status: next });
    toast.success(`Campaign ${next}`);
    load();
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this campaign?")) return;
    await api.delete(`/campaigns/${id}`);
    toast.success("Deleted");
    load();
  };

  return (
    <div className="p-6 md:p-10 space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="mono-accent">// outreach.campaigns</div>
          <h1 className="text-4xl font-black tracking-tighter">Campaigns</h1>
          <p className="text-[#5F5F5A] mt-1">Multi-step automations dispatched by OutreachOS under the send limits.</p>
        </div>
        <button onClick={() => { setEditing(null); setOpen(true); }} className="btn-primary" data-testid="new-campaign-button">
          <Plus size={16} weight="bold" /> NEW CAMPAIGN
        </button>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        {list.map((c, i) => (
          <motion.div
            key={c.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04 }}
            className={`surface surface-hover p-6 relative ${c.status === "running" ? "border-beam" : ""}`}
            data-testid={`campaign-card-${c.id}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <Target size={16} weight="duotone" className="text-[#DC2626]" />
                  <h3 className="font-display font-bold text-lg truncate">{c.name}</h3>
                  <span className={`chip ${STATUS_CHIP[c.status]}`}>{c.status}</span>
                </div>
                <p className="text-sm text-[#5F5F5A] mt-1 line-clamp-1">{c.goal || "—"}</p>
              </div>
              <div className="flex gap-2">
                <button onClick={() => setDrawerId(c.id)} className="btn-ghost !py-1.5 !px-2" title="open" data-testid={`view-campaign-${c.id}`}>
                  <ArrowSquareOut size={14} weight="bold" />
                </button>
                <button onClick={() => toggle(c)} className="btn-ghost !py-1.5 !px-2" title="toggle" data-testid={`toggle-${c.id}`}>
                  {c.status === "running" ? <Pause size={14} weight="fill" /> : <Play size={14} weight="fill" />}
                </button>
                <button onClick={() => launch(c.id)} className="btn-ghost !py-1.5 !px-2" title="launch" data-testid={`launch-${c.id}`}>
                  <Rocket size={14} weight="fill" />
                </button>
                <button onClick={() => remove(c.id)} className="btn-ghost !py-1.5 !px-2 hover:!border-[#EF4444] hover:!text-[#EF4444]" data-testid={`delete-${c.id}`}>
                  <Trash size={14} />
                </button>
              </div>
            </div>

            <div className="grid grid-cols-4 gap-3 mt-5">
              <Metric icon={PaperPlaneTilt} value={c.sent} label="sent" color="#DC2626" />
              <Metric icon={Eye} value={c.opened} label="opened" color="#0F172A" />
              <Metric icon={ChatCircleDots} value={c.replied} label="replied" color="#475569" />
              <Metric icon={Target} value={c.converted} label="won" color="#10B981" />
            </div>

            <div className="flex items-center gap-2 mt-4 flex-wrap">
              {(c.channels || []).map((ch) => (
                <span key={ch} className="chip chip-cyan">{ch}</span>
              ))}
              <span className="chip">{(c.steps || []).length} steps</span>
              <span className="chip"><Users size={10} /> {(c.lead_ids || []).length} leads</span>
              <span className="chip font-mono text-[#999995]">id · {c.id.slice(0, 8)}</span>
            </div>
          </motion.div>
        ))}

        {list.length === 0 && (
          <div className="surface p-10 text-center col-span-full text-[#5F5F5A]">
            No campaigns yet. <button onClick={() => setOpen(true)} className="text-[#DC2626] hover:underline">Create your first.</button>
          </div>
        )}
      </div>

      <CampaignBuilder open={open} onClose={() => setOpen(false)} onSave={create} initial={editing} />
      <CampaignDetailDrawer
        open={drawerId !== null}
        campaignId={drawerId}
        onClose={() => setDrawerId(null)}
        onUpdate={load}
      />
    </div>
  );
}

function Metric({ icon: Icon, value, label, color }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 mono-accent" style={{ color }}>
        <Icon size={11} weight="fill" /> {label}
      </div>
      <div className="font-mono text-xl font-bold mt-0.5">{value || 0}</div>
    </div>
  );
}

function CampaignBuilder({ open, onClose, onSave, initial }) {
  const [form, setForm] = useState({
    name: "",
    goal: "",
    channels: ["email"],
    steps: [{ channel: "email", delay_hours: 0, subject: "", body: "", language: "en" }],
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(initial || {
        name: "",
        goal: "",
        channels: ["email"],
        steps: [{ channel: "email", delay_hours: 0, subject: "", body: "", language: "en" }],
      });
    }
  }, [open, initial]);

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const updateStep = (i, k, v) => setForm((f) => ({ ...f, steps: f.steps.map((s, idx) => idx === i ? { ...s, [k]: v } : s) }));
  const addStep = () => update("steps", [...form.steps, { channel: "email", delay_hours: 24, subject: "", body: "", language: "en" }]);
  const removeStep = (i) => update("steps", form.steps.filter((_, idx) => idx !== i));

  const submit = async () => {
    if (!form.name) { toast.error("Name required"); return; }
    setSaving(true);
    try { await onSave(form); } finally { setSaving(false); }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 bg-[#0F172A]/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
          <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
            className="surface w-full max-w-3xl p-8 relative max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}
            data-testid="campaign-builder-modal">
            <button onClick={onClose} className="absolute top-4 right-4 text-[#5F5F5A] hover:text-[#0A0A0A]" data-testid="close-campaign-builder"><X size={20} /></button>

            <div className="mono-accent">/// build.campaign</div>
            <h2 className="text-2xl font-black tracking-tighter mt-1">Multi-step Campaign Builder</h2>

            <div className="space-y-4 mt-6">
              <div className="grid md:grid-cols-2 gap-3">
                <div>
                  <label className="mono-accent block mb-1.5">name</label>
                  <input className="neo-input" value={form.name} onChange={(e) => update("name", e.target.value)} placeholder="APAC Q2 Outreach" data-testid="campaign-name-input" />
                </div>
                <div>
                  <label className="mono-accent block mb-1.5">goal</label>
                  <input className="neo-input" value={form.goal} onChange={(e) => update("goal", e.target.value)} placeholder="Book 25 discovery calls" data-testid="campaign-goal-input" />
                </div>
              </div>

              <div>
                <label className="mono-accent block mb-2">channels</label>
                <div className="flex gap-2">
                  {["email", "whatsapp"].map((c) => {
                    const active = form.channels.includes(c);
                    return (
                      <button key={c} type="button"
                        onClick={() => update("channels", active ? form.channels.filter((x) => x !== c) : [...form.channels, c])}
                        className={`chip ${active ? "chip-cyan" : ""}`} data-testid={`channel-${c}`}>
                        {c}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="mono-accent">automation.steps</div>
                  <button onClick={addStep} className="btn-ghost !py-1.5 !px-2" data-testid="add-step-button"><Plus size={12} /> STEP</button>
                </div>

                <div className="space-y-3">
                  {form.steps.map((s, i) => (
                    <div key={i} className="surface p-4">
                      <div className="flex items-center justify-between mb-3">
                        <span className="chip chip-purple font-mono">step {i + 1}</span>
                        {form.steps.length > 1 && <button onClick={() => removeStep(i)} className="text-[#5F5F5A] hover:text-[#EF4444]"><Trash size={14} /></button>}
                      </div>
                      <div className="grid md:grid-cols-3 gap-3">
                        <div>
                          <label className="mono-accent block mb-1">channel</label>
                          <select className="neo-input" value={s.channel} onChange={(e) => updateStep(i, "channel", e.target.value)}>
                            <option value="email">email</option>
                            <option value="whatsapp">whatsapp</option>
                          </select>
                        </div>
                        <div>
                          <label className="mono-accent block mb-1">delay (hours)</label>
                          <input type="number" min="0" className="neo-input font-mono" value={s.delay_hours} onChange={(e) => updateStep(i, "delay_hours", parseInt(e.target.value || "0"))} />
                        </div>
                        <div>
                          <label className="mono-accent block mb-1">language</label>
                          <input className="neo-input font-mono" value={s.language} onChange={(e) => updateStep(i, "language", e.target.value)} />
                        </div>
                      </div>
                      {s.channel === "email" && (
                        <div className="mt-3">
                          <label className="mono-accent block mb-1">subject</label>
                          <input className="neo-input" value={s.subject || ""} onChange={(e) => updateStep(i, "subject", e.target.value)} placeholder="Quick question about {{company}}" />
                        </div>
                      )}
                      <div className="mt-3">
                        <label className="mono-accent block mb-1">body</label>
                        <textarea rows={4} className="neo-input" value={s.body} onChange={(e) => updateStep(i, "body", e.target.value)} placeholder="Hi {{first_name}}, ..." />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex gap-3 pt-3">
                <button onClick={submit} disabled={saving} className="btn-primary" data-testid="save-campaign-button">
                  {saving ? "SAVING..." : <>SAVE CAMPAIGN <ArrowRight size={14} weight="bold" /></>}
                </button>
                <button onClick={onClose} className="btn-ghost">CANCEL</button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
