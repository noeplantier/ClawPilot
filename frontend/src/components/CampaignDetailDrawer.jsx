import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { describeLaunch, sendErrorText } from "@/lib/campaignLaunch";
import {
  X, Rocket, Users, Plus, Check, CircleNotch, Envelope, WhatsappLogo, Play, ChartBar, ArrowsClockwise,
} from "@phosphor-icons/react";

const CHIP = { email: <Envelope size={11} />, whatsapp: <WhatsappLogo size={11} weight="fill" /> };

export default function CampaignDetailDrawer({ open, campaignId, onClose, onUpdate }) {
  const [c, setC] = useState(null);
  const [leads, setLeads] = useState([]);
  const [allLeads, setAllLeads] = useState([]);
  const [showAssign, setShowAssign] = useState(false);
  const [runningStep, setRunningStep] = useState(null);
  const [stepResult, setStepResult] = useState(null);

  const load = async () => {
    if (!campaignId) return;
    const { data } = await api.get(`/campaigns/${campaignId}`);
    setC(data);
    // Resolve assigned leads
    if (data.lead_ids?.length) {
      const rs = await api.get("/leads", { params: { limit: 500 } });
      setLeads(rs.data.filter((l) => data.lead_ids.includes(l.id)));
    } else {
      setLeads([]);
    }
  };

  useEffect(() => {
    if (open) {
      load();
      api.get("/leads", { params: { limit: 500 } }).then((r) => setAllLeads(r.data));
      setStepResult(null);
    }
  }, [open, campaignId]); // eslint-disable-line

  const runStep = async (idx) => {
    setRunningStep(idx);
    setStepResult(null);
    try {
      const { data } = await api.post(`/campaigns/${campaignId}/run-step/${idx}`);
      setStepResult({ idx, ...data });
      const { level, text } = describeLaunch(data);
      toast[level](`Step ${idx + 1}: ${text}`);
      load();
      onUpdate?.();
    } catch (e) {
      toast.error(sendErrorText(e, "Run failed"));
    } finally {
      setRunningStep(null);
    }
  };

  if (!open || !c) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 bg-[#0F172A]/60 backdrop-blur-sm"
        onClick={onClose}
      >
        <motion.div
          initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40 }}
          transition={{ duration: 0.22 }}
          className="absolute right-0 top-0 h-full w-full max-w-2xl bg-[#FFFFFF] border-l-2 border-[#0F172A] overflow-y-auto"
          onClick={(e) => e.stopPropagation()}
          data-testid="campaign-detail-drawer"
        >
          <div className="sticky top-0 bg-[#FFFFFF] border-b border-[#D6D3C8] px-6 py-4 flex items-center justify-between z-10">
            <div>
              <div className="mono-accent">/// campaign · {c.status}</div>
              <h2 className="text-2xl font-black tracking-tighter text-[#0A0A0A]">{c.name}</h2>
            </div>
            <button onClick={onClose} className="text-[#595955] hover:text-[#DC2626]" data-testid="close-campaign-drawer">
              <X size={22} />
            </button>
          </div>

          <div className="p-6 space-y-6">
            {/* metrics */}
            <div className="grid grid-cols-4 gap-3">
              {[
                ["sent", c.sent, "#DC2626"],
                ["opened", c.opened, "#0F172A"],
                ["replied", c.replied, "#475569"],
                ["converted", c.converted, "#10B981"],
              ].map(([l, v, col]) => (
                <div key={l} className="surface p-3">
                  <div className="mono-accent" style={{ color: col }}>{l}</div>
                  <div className="font-mono text-2xl font-bold text-[#0A0A0A] tabular mt-0.5">{v || 0}</div>
                </div>
              ))}
            </div>

            {/* Leads assignment */}
            <div className="surface p-5">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <div className="mono-accent">/// assigned.leads</div>
                  <div className="font-display font-bold text-lg flex items-center gap-1.5"><Users size={16} /> {leads.length} assigned</div>
                </div>
                <button onClick={() => setShowAssign(true)} className="btn-primary !py-1.5 !px-3" data-testid="assign-leads-button">
                  <Plus size={12} weight="bold" /> ASSIGN LEADS
                </button>
              </div>
              {leads.length === 0 ? (
                <div className="text-sm text-[#999995] italic py-4 text-center">
                  No leads assigned yet — assign some to enable step execution.
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-2 max-h-[160px] overflow-y-auto">
                  {leads.map((l) => (
                    <div key={l.id} className="surface bg-[#FAFAF7] p-2 text-xs">
                      <div className="font-semibold text-[#0A0A0A] truncate">{l.full_name}</div>
                      <div className="font-mono text-[#595955] truncate">{l.email || l.phone || "—"}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Steps */}
            <div>
              <div className="mono-accent mb-2">/// automation.steps</div>
              <div className="space-y-2">
                {(c.steps || []).map((s, i) => (
                  <div
                    key={s.id || i}
                    className={`surface p-4 ${runningStep === i ? "border-beam glow-red" : ""}`}
                    data-testid={`step-${i}`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="chip chip-red font-mono">step {i + 1}</span>
                        <span className="chip">{CHIP[s.channel]} {s.channel}</span>
                        <span className="chip font-mono">+{s.delay_hours}h</span>
                        <span className="chip font-mono">{s.language}</span>
                      </div>
                      <button
                        onClick={() => runStep(i)}
                        disabled={runningStep !== null || leads.length === 0}
                        className="btn-ink !py-1.5 !px-3"
                        data-testid={`run-step-${i}`}
                      >
                        {runningStep === i ? <><CircleNotch size={12} className="spin-slow" /> RUNNING</> : <><Play size={12} weight="fill" /> RUN STEP</>}
                      </button>
                    </div>
                    {s.subject && <div className="mt-3 text-sm font-semibold text-[#0A0A0A]">{s.subject}</div>}
                    {s.body && <div className="text-xs font-mono text-[#595955] mt-1 whitespace-pre-wrap line-clamp-3">{s.body}</div>}

                    {stepResult?.idx === i && (
                      <motion.div
                        initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
                        className="surface bg-[#F4FDF9] border-[#10B981]/40 p-3 mt-3 flex items-start gap-3"
                      >
                        <ChartBar size={16} className="text-[#10B981] mt-0.5" />
                        <div className="text-xs font-mono flex-1">
                          <div className="font-display font-bold text-sm text-[#0A0A0A] mb-1">Step executed</div>
                          <div className="grid grid-cols-5 gap-2">
                            <Mini label="dispatched" value={stepResult.dispatched} color="#0F172A" />
                            <Mini label="sent" value={stepResult.sent} color="#10B981" />
                            <Mini label="mocked" value={stepResult.mocked} color="#F59E0B" />
                            <Mini label="failed" value={stepResult.failed} color="#DC2626" />
                            <Mini label="skipped" value={stepResult.skipped} color="#595955" />
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </div>
                ))}
                {(!c.steps || c.steps.length === 0) && (
                  <div className="surface p-5 text-center text-sm text-[#999995] italic">
                    No steps configured. Edit the campaign to add automation steps.
                  </div>
                )}
              </div>
            </div>
          </div>
        </motion.div>

        {showAssign && (
          <AssignLeadsSheet
            campaign={c}
            allLeads={allLeads}
            onClose={() => setShowAssign(false)}
            onSaved={() => { setShowAssign(false); load(); onUpdate?.(); }}
          />
        )}
      </motion.div>
    </AnimatePresence>
  );
}

function Mini({ label, value, color }) {
  return (
    <div>
      <div className="mono-accent" style={{ color, fontSize: 9 }}>{label}</div>
      <div className="font-mono text-sm font-bold tabular" style={{ color }}>{value || 0}</div>
    </div>
  );
}

function AssignLeadsSheet({ campaign, allLeads, onClose, onSaved }) {
  const already = new Set(campaign.lead_ids || []);
  const [selected, setSelected] = useState(new Set());
  const [search, setSearch] = useState("");
  const [saving, setSaving] = useState(false);

  const candidates = allLeads.filter((l) => !already.has(l.id) && (
    !search || (l.full_name || "").toLowerCase().includes(search.toLowerCase()) ||
    (l.company || "").toLowerCase().includes(search.toLowerCase())
  ));

  const save = async () => {
    if (selected.size === 0) return;
    setSaving(true);
    try {
      await api.post(`/campaigns/${campaign.id}/assign-leads`, { lead_ids: Array.from(selected) });
      toast.success(`Assigned ${selected.size} leads to ${campaign.name}`);
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Assign failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      className="absolute inset-0 bg-[#0F172A]/60 backdrop-blur-sm flex items-center justify-center p-4 z-10"
      onClick={onClose}
    >
      <motion.div
        initial={{ y: 10 }} animate={{ y: 0 }}
        className="surface w-full max-w-xl p-6 relative max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
        data-testid="assign-leads-modal"
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-[#595955] hover:text-[#DC2626]"><X size={20} /></button>
        <div className="mono-accent">/// assign.leads</div>
        <h3 className="text-xl font-black tracking-tighter mt-1">Add leads to campaign</h3>
        <input
          className="neo-input mt-4"
          placeholder="Search..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          data-testid="assign-search-input"
        />
        <div className="mt-3 max-h-[340px] overflow-y-auto divide-y divide-[#D6D3C8]">
          {candidates.map((l) => {
            const checked = selected.has(l.id);
            return (
              <label key={l.id} className="flex items-center gap-2 py-2 cursor-pointer" data-testid={`assign-lead-${l.id}`}>
                <input type="checkbox" checked={checked} onChange={() => {
                  setSelected((s) => {
                    const n = new Set(s);
                    checked ? n.delete(l.id) : n.add(l.id);
                    return n;
                  });
                }} className="accent-[#DC2626]" />
                <div className="flex-1 min-w-0 text-sm">
                  <div className="font-semibold">{l.full_name}</div>
                  <div className="text-xs font-mono text-[#595955] truncate">{l.email} {l.company && `· ${l.company}`}</div>
                </div>
              </label>
            );
          })}
          {candidates.length === 0 && (
            <div className="py-6 text-center text-[#999995] italic text-sm">All leads already assigned or no matches.</div>
          )}
        </div>
        <div className="flex gap-3 mt-5">
          <button onClick={save} disabled={saving || selected.size === 0} className="btn-primary" data-testid="save-assign-button">
            {saving ? "SAVING..." : <><Check size={14} weight="bold" /> ASSIGN {selected.size}</>}
          </button>
          <button onClick={onClose} className="btn-ghost">CANCEL</button>
        </div>
      </motion.div>
    </motion.div>
  );
}
