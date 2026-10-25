import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { sendErrorText } from "@/lib/campaignLaunch";
import { describeApiError } from "@/lib/outreachFormat";
import { Envelope, WhatsappLogo, PaperPlaneTilt, Sparkle, Users } from "@phosphor-icons/react";
import BatchComposerModal from "@/components/BatchComposerModal";
import { addressOf, matchLead, sendBlock, suggestLeads } from "@/lib/recipient";

const STATUS_CHIP = {
  sent: "chip-success", delivered: "chip-success", opened: "chip-cyan",
  replied: "chip-purple", failed: "chip-danger", queued: "chip-warn", mock: "chip-danger", // "mock" = legacy rows from before sends were real
};

export default function Messages() {
  const [list, setList] = useState([]);
  const [filter, setFilter] = useState("all");
  const [composer, setComposer] = useState({ open: false, channel: "email" });
  const [batchChannel, setBatchChannel] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    const params = filter === "all" ? {} : { channel: filter };
    setLoading(true);
    api.get("/messages", { params }).then((r) => { setList(r.data); setError(null); })
      .catch((e) => setError(e?.response?.data?.detail || "Messages are temporarily unavailable."))
      .finally(() => setLoading(false));
  }, [filter]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="p-6 md:p-10 space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="mono-accent">// transmission.log</div>
          <h1 className="text-4xl font-black tracking-tighter">Messages</h1>
          <p className="text-[#5F5F5A] mt-1">{list.length} transmissions recorded</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={() => setBatchChannel("email")} className="btn-ink" data-testid="batch-email-button"><Users size={14} /> BATCH EMAIL</button>
          <button onClick={() => setBatchChannel("whatsapp")} className="btn-ink" data-testid="batch-whatsapp-button"><Users size={14} /> BATCH WHATSAPP</button>
          <button onClick={() => setComposer({ open: true, channel: "email" })} className="btn-ghost" data-testid="new-email-button"><Envelope size={14} /> EMAIL</button>
          <button onClick={() => setComposer({ open: true, channel: "whatsapp" })} className="btn-primary" data-testid="new-whatsapp-button"><WhatsappLogo size={14} weight="fill" /> WHATSAPP</button>
        </div>
      </div>

      <div className="flex gap-2">
        {["all", "email", "whatsapp"].map((f) => (
          <button key={f} onClick={() => setFilter(f)} className={`chip ${filter === f ? "chip-cyan" : ""}`} data-testid={`filter-${f}`}>{f}</button>
        ))}
      </div>

      <div className="surface overflow-hidden">
        {error && <div role="alert" className="p-4 text-sm" data-testid="messages-error"><p>{error}</p><button onClick={load} className="btn-ghost mt-2">RETRY</button></div>}
        {loading && list.length === 0 && <p role="status" className="p-4 text-sm">Loading messages…</p>}
        <div className="overflow-x-auto">
        <table className="w-full min-w-[42rem] text-sm">
          <thead className="bg-[#F6F8FC] border-b border-[#D3DBEA]">
            <tr className="text-left mono-accent">
              <th className="p-3">Channel</th>
              <th className="p-3">To</th>
              <th className="p-3">Subject / Preview</th>
              <th className="p-3">Status</th>
              <th className="p-3">Sent</th>
            </tr>
          </thead>
          <tbody>
            {list.map((m) => (
              <tr key={m.id}
                className="border-b border-[#E6ECF6] hover:bg-[#F6F8FC]">
                <td className="p-3">
                  {m.channel === "email"
                    ? <span className="inline-flex items-center gap-1.5 text-[#4F46E5]"><Envelope size={14} /> email</span>
                    : <span className="inline-flex items-center gap-1.5 text-[#25D366]"><WhatsappLogo size={14} weight="fill" /> whatsapp</span>
                  }
                </td>
                <td className="p-3 font-mono text-xs text-[#1a1a1a]">{m.to}</td>
                <td className="p-3 text-[#5F5F5A] truncate max-w-sm">
                  {m.subject && <div className="text-[#0A0A0A]">{m.subject}</div>}
                  <div className="truncate">{m.body}</div>
                </td>
                <td className="p-3"><span className={`chip ${STATUS_CHIP[m.status]}`}>{m.status === "mock" ? "not sent" : m.status}</span></td>
                <td className="p-3 font-mono text-xs text-[#6B6B66]">{new Date(m.created_at).toLocaleString()}</td>
              </tr>
            ))}
            {!loading && !error && list.length === 0 && <tr><td colSpan="5" className="p-10 text-center text-[#5F5F5A]">No messages in this channel yet.</td></tr>}
          </tbody>
        </table>
        </div>
      </div>

      {composer.open && <Composer channel={composer.channel} onClose={() => setComposer({ ...composer, open: false })} onSent={() => { setComposer({ ...composer, open: false }); load(); }} />}
      <BatchComposerModal
        open={batchChannel !== null}
        onClose={() => { setBatchChannel(null); load(); }}
        defaultChannel={batchChannel || "email"}
      />
    </div>
  );
}

function Composer({ channel, onClose, onSent }) {
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [leads, setLeads] = useState(null); // null = loading
  const [leadsError, setLeadsError] = useState(false);
  const [focused, setFocused] = useState(false);
  const blurTimer = useRef(null); // the list closes a moment after the field loses focus (a click on a suggestion comes first)
  useEffect(() => () => clearTimeout(blurTimer.current), []);

  // A real e-mail belongs to a lead record (its footer carries that lead's unsubscribe link): the recipient is picked from,
  // or matched to, the organisation's leads, hottest first.
  useEffect(() => {
    let alive = true;
    api.get("/leads", { params: { limit: 500 } })
      .then((r) => { if (alive) setLeads(r.data); })
      .catch(() => { if (alive) { setLeads([]); setLeadsError(true); } });
    return () => { alive = false; };
  }, []);

  const lead = useMemo(() => matchLead(leads, to, channel), [leads, to, channel]);
  const suggestions = useMemo(() => (focused && !lead ? suggestLeads(leads, to, channel) : []), [focused, lead, leads, to, channel]);
  const block = leadsError && channel === "email" ? "load-error" : sendBlock(channel, to, lead, leads !== null);

  const aiWrite = async () => {
    if (!to) { toast.error("Enter recipient first"); return; }
    setGenerating(true);
    try {
      const { data } = await api.post("/ai/generate", {
        recipient_name: lead ? lead.full_name : to.split("@")[0] || to,
        ...(lead && lead.company ? { company: lead.company } : {}),
        product: "Plantiers - OutreachOS lead generation platform",
        language: "en",
        tone: "professional",
        channel,
        goal: "book a 15-min discovery call",
      });
      if (data.subject) setSubject(data.subject);
      setBody(data.body);
    } catch (e) { toast.error(describeApiError(e)); }
    finally { setGenerating(false); }
  };

  const send = async () => {
    if (!to || !body) { toast.error("To and body required"); return; }
    setSending(true);
    try {
      const path = channel === "email" ? "/messages/email" : "/messages/whatsapp";
      const link = lead ? { lead_id: lead.id } : {};
      const payload = channel === "email" ? { to: to.trim(), subject, body, ...link } : { to, body, ...link };
      const { data } = await api.post(path, payload);
      const status = data.result.status;
      if (status === "sent") toast.success("Sent");
      else toast.error(data.result.error || `Not sent (${status})`);
      onSent();
    } catch (e) { toast.error(sendErrorText(e)); }
    finally { setSending(false); }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="fixed inset-0 z-50 bg-[#0F172A]/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <motion.div initial={{ y: 10 }} animate={{ y: 0 }} className="surface w-full max-w-2xl p-8" onClick={(e) => e.stopPropagation()}>
        <div className="mono-accent">/// {channel}.compose</div>
        <h2 className="text-2xl font-black tracking-tighter mt-1">New {channel === "email" ? "Email" : "WhatsApp"}</h2>

        <div className="space-y-3 mt-6">
          <div className="relative">
            <label className="mono-accent block mb-1.5">{channel === "email" ? "to.email (one of your leads)" : "to.phone (+countrycode)"}</label>
            <input className="neo-input font-mono" value={to} onChange={(e) => setTo(e.target.value)}
              onFocus={() => { clearTimeout(blurTimer.current); setFocused(true); }}
              onBlur={() => { blurTimer.current = setTimeout(() => setFocused(false), 120); }} autoComplete="off"
              placeholder={channel === "email" ? "type a name or an address" : "+14155550123"} data-testid="compose-to" />
            {suggestions.length > 0 && (
              <ul className="absolute left-0 right-0 mt-1 z-10 max-h-56 overflow-auto rounded-lg py-1 bg-white border border-indigo-100 shadow-lg" role="listbox" data-testid="compose-suggestions">
                {suggestions.map((l, i) => (
                  <li key={l.id}>
                    <button type="button" role="option" aria-selected="false" className="w-full text-left px-3 py-2 text-sm hover:bg-indigo-50"
                      onMouseDown={(e) => e.preventDefault()} onClick={() => { setTo(addressOf(channel, l)); setFocused(false); }} data-testid={`compose-suggest-${i}`}>
                      <span className="font-semibold">{l.full_name}</span>
                      {l.company ? <span className="text-[#5F5F5A]"> · {l.company}</span> : null}
                      <span className="block font-mono text-xs text-[#6B7690]">{addressOf(channel, l)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {lead && (
              <p className="text-xs mt-1.5 text-[#065F46]" data-testid="compose-lead">
                Linked to <b>{lead.full_name}</b>{lead.review_status ? ` (prospect: ${lead.review_status === "pending" ? "to review" : lead.review_status})` : ""}: the e-mail carries its unsubscribe link.
              </p>
            )}
            {block === "not-a-lead" && (
              <p className="text-xs mt-1.5 text-[#92400E]" role="alert" data-testid="compose-no-lead">
                This address is not one of your leads. A real e-mail must be linked to a lead so that it carries a working unsubscribe link:{" "}
                <Link to="/app/leads" className="underline" onClick={onClose}>add it in Leads first</Link>.
              </p>
            )}
            {block === "load-error" && (
              <p className="text-xs mt-1.5 text-[#991B1B]" role="alert" data-testid="compose-leads-error">Your leads could not be loaded, so the recipient cannot be checked. Reload the page.</p>
            )}
          </div>
          {channel === "email" && (
            <div>
              <label className="mono-accent block mb-1.5">subject</label>
              <input className="neo-input" value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Quick question about scaling outreach" data-testid="compose-subject" />
            </div>
          )}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="mono-accent">body</label>
              <button onClick={aiWrite} disabled={generating} className="btn-purple !py-1 !px-2 text-xs" data-testid="compose-ai-button">
                <Sparkle size={10} weight="fill" /> {generating ? "WRITING..." : "AI WRITE"}
              </button>
            </div>
            <textarea rows={8} className="neo-input" value={body} onChange={(e) => setBody(e.target.value)} placeholder="Hi ..." data-testid="compose-body" />
          </div>
        </div>

        <div className="flex gap-3 mt-6">
          <button onClick={send} disabled={sending || Boolean(block)} className="btn-primary" data-testid="send-message-button"
            title={block ? "Pick one of your leads as the recipient" : undefined}>
            {sending ? "SENDING..." : <><PaperPlaneTilt size={14} weight="fill" /> DISPATCH</>}
          </button>
          <button onClick={onClose} className="btn-ghost">CANCEL</button>
        </div>
      </motion.div>
    </motion.div>
  );
}
