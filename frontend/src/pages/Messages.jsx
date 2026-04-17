import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Envelope, WhatsappLogo, PaperPlaneTilt, Sparkle } from "@phosphor-icons/react";

const STATUS_CHIP = {
  sent: "chip-success", delivered: "chip-success", opened: "chip-cyan",
  replied: "chip-purple", failed: "chip-danger", queued: "chip-warn", mock: "chip-warn",
};

export default function Messages() {
  const [list, setList] = useState([]);
  const [filter, setFilter] = useState("all");
  const [composer, setComposer] = useState({ open: false, channel: "email" });

  const load = () => {
    const params = filter === "all" ? {} : { channel: filter };
    api.get("/messages", { params }).then((r) => setList(r.data));
  };
  useEffect(() => { load(); }, [filter]); // eslint-disable-line

  return (
    <div className="p-6 md:p-10 space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="mono-accent">// transmission.log</div>
          <h1 className="text-4xl font-black tracking-tighter">Messages</h1>
          <p className="text-[#8B949E] mt-1">{list.length} transmissions recorded</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setComposer({ open: true, channel: "email" })} className="btn-ghost" data-testid="new-email-button"><Envelope size={14} /> NEW EMAIL</button>
          <button onClick={() => setComposer({ open: true, channel: "whatsapp" })} className="btn-primary" data-testid="new-whatsapp-button"><WhatsappLogo size={14} weight="fill" /> WHATSAPP</button>
        </div>
      </div>

      <div className="flex gap-2">
        {["all", "email", "whatsapp"].map((f) => (
          <button key={f} onClick={() => setFilter(f)} className={`chip ${filter === f ? "chip-cyan" : ""}`} data-testid={`filter-${f}`}>{f}</button>
        ))}
      </div>

      <div className="surface overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-[#080808] border-b border-[#262626]">
            <tr className="text-left mono-accent">
              <th className="p-3">Channel</th>
              <th className="p-3">To</th>
              <th className="p-3">Subject / Preview</th>
              <th className="p-3">Status</th>
              <th className="p-3">Sent</th>
            </tr>
          </thead>
          <tbody>
            {list.map((m, i) => (
              <motion.tr key={m.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                className="border-b border-[#141414] hover:bg-[#0c0c0c]">
                <td className="p-3">
                  {m.channel === "email"
                    ? <span className="inline-flex items-center gap-1.5 text-[#00E5FF]"><Envelope size={14} /> email</span>
                    : <span className="inline-flex items-center gap-1.5 text-[#25D366]"><WhatsappLogo size={14} weight="fill" /> whatsapp</span>
                  }
                </td>
                <td className="p-3 font-mono text-xs text-[#e6edf3]">{m.to}</td>
                <td className="p-3 text-[#8B949E] truncate max-w-sm">
                  {m.subject && <div className="text-white">{m.subject}</div>}
                  <div className="truncate">{m.body}</div>
                </td>
                <td className="p-3"><span className={`chip ${STATUS_CHIP[m.status]}`}>{m.status}</span></td>
                <td className="p-3 font-mono text-xs text-[#4B5563]">{new Date(m.created_at).toLocaleString()}</td>
              </motion.tr>
            ))}
            {list.length === 0 && <tr><td colSpan="5" className="p-10 text-center text-[#8B949E]">No messages yet.</td></tr>}
          </tbody>
        </table>
      </div>

      {composer.open && <Composer channel={composer.channel} onClose={() => setComposer({ ...composer, open: false })} onSent={() => { setComposer({ ...composer, open: false }); load(); }} />}
    </div>
  );
}

function Composer({ channel, onClose, onSent }) {
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [generating, setGenerating] = useState(false);

  const aiWrite = async () => {
    if (!to) { toast.error("Enter recipient first"); return; }
    setGenerating(true);
    try {
      const { data } = await api.post("/ai/generate", {
        recipient_name: to.split("@")[0] || to,
        product: "OpenClaw agent-powered outreach platform",
        language: "en",
        tone: "professional",
        channel,
        goal: "book a 15-min discovery call",
      });
      if (data.subject) setSubject(data.subject);
      setBody(data.body);
    } catch (e) { toast.error("AI generation failed"); }
    finally { setGenerating(false); }
  };

  const send = async () => {
    if (!to || !body) { toast.error("To and body required"); return; }
    setSending(true);
    try {
      const path = channel === "email" ? "/messages/email" : "/messages/whatsapp";
      const payload = channel === "email" ? { to, subject, body } : { to, body };
      const { data } = await api.post(path, payload);
      const status = data.result.status;
      if (status === "sent") toast.success("Dispatched successfully");
      else if (status === "mock") toast.info("Logged as MOCK — configure integration in Settings");
      else toast.error(`Status: ${status}`);
      onSent();
    } catch (e) { toast.error(e?.response?.data?.detail || "Send failed"); }
    finally { setSending(false); }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="fixed inset-0 z-50 bg-black/80 backdrop-blur-xl flex items-center justify-center p-4" onClick={onClose}>
      <motion.div initial={{ y: 10 }} animate={{ y: 0 }} className="surface w-full max-w-2xl p-8" onClick={(e) => e.stopPropagation()}>
        <div className="mono-accent">/// {channel}.compose</div>
        <h2 className="text-2xl font-black tracking-tighter mt-1">New {channel === "email" ? "Email" : "WhatsApp"}</h2>

        <div className="space-y-3 mt-6">
          <div>
            <label className="mono-accent block mb-1.5">{channel === "email" ? "to.email" : "to.phone (+countrycode)"}</label>
            <input className="neo-input font-mono" value={to} onChange={(e) => setTo(e.target.value)} placeholder={channel === "email" ? "priya@acme.io" : "+14155550123"} data-testid="compose-to" />
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
          <button onClick={send} disabled={sending} className="btn-primary" data-testid="send-message-button">
            {sending ? "SENDING..." : <><PaperPlaneTilt size={14} weight="fill" /> DISPATCH</>}
          </button>
          <button onClick={onClose} className="btn-ghost">CANCEL</button>
        </div>
      </motion.div>
    </motion.div>
  );
}
