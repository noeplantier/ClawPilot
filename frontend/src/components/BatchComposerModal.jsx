import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  X, PaperPlaneTilt, Sparkle, Envelope, WhatsappLogo, CheckCircle, Warning, CircleNotch, Users,
} from "@phosphor-icons/react";

const TOKEN_HINTS = ["{{first_name}}", "{{full_name}}", "{{company}}", "{{title}}", "{{country}}"];

export default function BatchComposerModal({ open, onClose, defaultChannel = "email" }) {
  const [channel, setChannel] = useState(defaultChannel);
  const [leads, setLeads] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [search, setSearch] = useState("");
  const [subject, setSubject] = useState("Quick idea for {{company}}");
  const [body, setBody] = useState(
    "Hi {{first_name}},\n\nI saw {{company}} is scaling fast — wanted to share how ClawPilot agents can 3x your outreach without adding headcount.\n\nWorth a 15-min chat this week?"
  );
  const [loading, setLoading] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (open) {
      api.get("/leads", { params: { limit: 500 } }).then((r) => setLeads(r.data));
      setResult(null);
      setSelected(new Set());
      setChannel(defaultChannel);
    }
  }, [open, defaultChannel]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return leads.filter((l) => {
      if (channel === "email" && !l.email) return false;
      if (channel === "whatsapp" && !l.phone) return false;
      if (!q) return true;
      return (
        (l.full_name || "").toLowerCase().includes(q) ||
        (l.company || "").toLowerCase().includes(q) ||
        (l.email || "").toLowerCase().includes(q)
      );
    });
  }, [leads, search, channel]);

  const toggleOne = (id) => {
    setSelected((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    setSelected((s) => (s.size === filtered.length ? new Set() : new Set(filtered.map((l) => l.id))));
  };

  const aiWrite = async () => {
    if (!leads.length) return;
    setAiLoading(true);
    try {
      // Use first selected (or first filtered) as personalization basis
      const sample = leads.find((l) => selected.has(l.id)) || filtered[0];
      const { data } = await api.post("/ai/generate", {
        recipient_name: sample?.full_name || "there",
        company: sample?.company || "",
        product: "ClawPilot agent-powered outreach platform",
        language: sample?.language || "en",
        tone: "professional",
        channel,
        goal: "book a 15-min discovery call",
      });
      if (data.subject && channel === "email") setSubject(data.subject);
      // Replace name with token for reusability
      const tokenized = (data.body || "").replace(new RegExp(sample?.full_name?.split(" ")?.[0] || "", "g"), "{{first_name}}");
      setBody(tokenized.replace(new RegExp(sample?.company || "###", "g"), "{{company}}"));
      toast.success("AI draft ready — tokens inserted");
    } catch (e) {
      toast.error("AI generation failed");
    } finally {
      setAiLoading(false);
    }
  };

  const dispatch = async () => {
    if (selected.size === 0) {
      toast.error("Select at least one lead");
      return;
    }
    if (!body) {
      toast.error("Body is required");
      return;
    }
    if (channel === "email" && !subject) {
      toast.error("Subject is required for email");
      return;
    }
    setLoading(true);
    try {
      const path = channel === "email" ? "/messages/email/batch" : "/messages/whatsapp/batch";
      const { data } = await api.post(path, {
        lead_ids: Array.from(selected),
        subject: channel === "email" ? subject : undefined,
        body,
      });
      setResult(data);
      const where = data.sent > 0 ? `${data.sent} live sends` : `${data.mocked} mocked dispatches`;
      toast.success(`Batch complete · ${data.dispatched} dispatched (${where})`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Batch send failed");
    } finally {
      setLoading(false);
    }
  };

  const previewLead = leads.find((l) => selected.has(l.id)) || filtered[0];
  const renderPreview = (t) => {
    if (!t || !previewLead) return t;
    const first = (previewLead.full_name || "").split(" ")[0] || "there";
    return t
      .replace(/\{\{first_name\}\}/g, first)
      .replace(/\{\{full_name\}\}/g, previewLead.full_name || "")
      .replace(/\{\{company\}\}/g, previewLead.company || "")
      .replace(/\{\{title\}\}/g, previewLead.title || "")
      .replace(/\{\{country\}\}/g, previewLead.country || "");
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 bg-[#0F172A]/60 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ y: 12 }} animate={{ y: 0 }}
            className="surface w-full max-w-5xl p-6 md:p-8 relative max-h-[94vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
            data-testid="batch-composer-modal"
          >
            <button onClick={onClose} className="absolute top-4 right-4 text-[#595955] hover:text-[#DC2626]" data-testid="close-batch-composer">
              <X size={20} />
            </button>

            <div className="mono-accent">/// batch.dispatch</div>
            <h2 className="text-2xl font-black tracking-tighter mt-1 flex items-center gap-2">
              {channel === "email" ? <Envelope size={22} weight="duotone" className="text-[#DC2626]" /> : <WhatsappLogo size={22} weight="fill" className="text-[#DC2626]" />}
              Batch {channel === "email" ? "Email" : "WhatsApp"} Dispatch
            </h2>
            <p className="text-[#595955] text-sm mt-1">Send personalized messages to multiple leads in one pass.</p>

            <div className="flex items-center gap-2 mt-4">
              <button onClick={() => setChannel("email")} className={`chip ${channel === "email" ? "chip-red" : ""}`} data-testid="batch-channel-email">
                <Envelope size={11} /> email
              </button>
              <button onClick={() => setChannel("whatsapp")} className={`chip ${channel === "whatsapp" ? "chip-red" : ""}`} data-testid="batch-channel-whatsapp">
                <WhatsappLogo size={11} weight="fill" /> whatsapp
              </button>
            </div>

            <div className="grid lg:grid-cols-5 gap-5 mt-5">
              {/* Left — lead picker */}
              <div className="lg:col-span-2 surface bg-[#FAFAF7] p-4 flex flex-col min-h-[380px]">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <div className="mono-accent">recipients</div>
                    <div className="font-display font-bold flex items-center gap-1.5"><Users size={16} /> {selected.size} / {filtered.length}</div>
                  </div>
                  <button onClick={toggleAll} className="chip chip-red" data-testid="select-all-leads">
                    {selected.size === filtered.length && filtered.length > 0 ? "CLEAR" : "SELECT ALL"}
                  </button>
                </div>
                <input
                  className="neo-input text-sm mb-2"
                  placeholder="Search leads..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  data-testid="batch-search-input"
                />
                <div className="flex-1 overflow-y-auto -mx-1 px-1 divide-y divide-[#E5E2D3]">
                  {filtered.map((l) => {
                    const checked = selected.has(l.id);
                    return (
                      <label key={l.id} className="flex items-start gap-2 py-2 cursor-pointer group" data-testid={`batch-lead-${l.id}`}>
                        <input type="checkbox" checked={checked} onChange={() => toggleOne(l.id)} className="mt-1 accent-[#DC2626]" />
                        <div className="flex-1 min-w-0 text-xs">
                          <div className="font-semibold text-[#0A0A0A]">{l.full_name}</div>
                          <div className="text-[#595955] truncate font-mono">
                            {channel === "email" ? l.email : l.phone} {l.company && `· ${l.company}`}
                          </div>
                        </div>
                      </label>
                    );
                  })}
                  {filtered.length === 0 && (
                    <div className="py-8 text-center text-[#999995] text-sm italic">
                      No leads match{channel === "email" ? " (with email)" : " (with phone)"}.
                    </div>
                  )}
                </div>
              </div>

              {/* Right — composer */}
              <div className="lg:col-span-3 space-y-3">
                {channel === "email" && (
                  <div>
                    <label className="mono-accent block mb-1.5">subject</label>
                    <input className="neo-input" value={subject} onChange={(e) => setSubject(e.target.value)} data-testid="batch-subject" />
                  </div>
                )}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="mono-accent">body</label>
                    <button onClick={aiWrite} disabled={aiLoading} className="btn-purple !py-1 !px-2 text-xs" data-testid="batch-ai-button">
                      <Sparkle size={10} weight="fill" /> {aiLoading ? "WRITING..." : "AI WRITE"}
                    </button>
                  </div>
                  <textarea rows={8} className="neo-input font-mono text-sm" value={body} onChange={(e) => setBody(e.target.value)} data-testid="batch-body" />
                </div>

                <div className="flex gap-1.5 flex-wrap">
                  {TOKEN_HINTS.map((t) => (
                    <button
                      key={t}
                      onClick={() => setBody((b) => b + " " + t)}
                      className="chip chip-red hover:border-[#DC2626]"
                    >
                      {t}
                    </button>
                  ))}
                </div>

                {previewLead && (
                  <div className="surface bg-[#FAFAF7] p-3">
                    <div className="mono-accent mb-1.5">preview · {previewLead.full_name}</div>
                    {channel === "email" && subject && (
                      <div className="text-sm font-semibold text-[#0A0A0A] mb-1">{renderPreview(subject)}</div>
                    )}
                    <div className="text-xs text-[#595955] whitespace-pre-wrap font-mono max-h-[110px] overflow-y-auto">
                      {renderPreview(body)}
                    </div>
                  </div>
                )}

                {result && (
                  <div className="surface bg-[#F4FDF9] border-[#10B981]/40 p-4" data-testid="batch-result">
                    <div className="flex items-center gap-2 font-display font-bold text-sm">
                      <CheckCircle size={16} weight="fill" className="text-[#10B981]" /> Dispatch complete
                    </div>
                    <div className="grid grid-cols-4 gap-2 mt-3 text-center">
                      <Stat label="dispatched" value={result.dispatched} color="#0F172A" />
                      <Stat label="sent" value={result.sent} color="#10B981" />
                      <Stat label="mocked" value={result.mocked} color="#F59E0B" />
                      <Stat label="failed/skip" value={(result.failed || 0) + (result.skipped || 0)} color="#DC2626" />
                    </div>
                    {result.mocked > 0 && (
                      <div className="mt-3 text-xs text-[#595955] flex gap-1.5 items-start">
                        <Warning size={12} className="text-[#F59E0B] flex-shrink-0 mt-0.5" />
                        {result.mocked} mocked — add a verified SendGrid sender / Twilio Account SID in Settings to go live.
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div className="flex gap-3 mt-6 items-center border-t border-[#D6D3C8] pt-4">
              <button onClick={dispatch} disabled={loading || selected.size === 0} className="btn-primary" data-testid="batch-dispatch-button">
                {loading ? <><CircleNotch size={14} className="spin-slow" /> DISPATCHING...</> : <><PaperPlaneTilt size={14} weight="fill" /> DISPATCH TO {selected.size} LEAD{selected.size !== 1 ? "S" : ""}</>}
              </button>
              <button onClick={onClose} className="btn-ghost">CLOSE</button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Stat({ label, value, color }) {
  return (
    <div className="surface p-2">
      <div className="mono-accent text-[10px]" style={{ color }}>{label}</div>
      <div className="font-mono text-xl font-bold tabular" style={{ color }}>{value || 0}</div>
    </div>
  );
}
