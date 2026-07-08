import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  X, Envelope, Phone, Buildings, Globe, NotePencil, CheckSquare, Tag as TagIcon,
  ClockCounterClockwise, Plus, Trash, Check, CircleNotch, WhatsappLogo, PaperPlaneTilt,
} from "@phosphor-icons/react";

const STAGE_COLORS = {
  new: "#DC2626", contacted: "#475569", engaged: "#0F172A",
  qualified: "#F59E0B", won: "#10B981", lost: "#EF4444",
};
const CONSENT_CHIP = {
  opted_in: "chip-success", opted_out: "chip-danger", unknown: "chip",
};
const TABS = [
  { key: "info", label: "Info", icon: Globe },
  { key: "notes", label: "Notes", icon: NotePencil },
  { key: "tasks", label: "Tasks", icon: CheckSquare },
  { key: "tags", label: "Tags", icon: TagIcon },
  { key: "history", label: "History", icon: ClockCounterClockwise },
];

export default function LeadDetailDrawer({ open, leadId, onClose, onUpdate }) {
  const [lead, setLead] = useState(null);
  const [tab, setTab] = useState("info");

  const load = async () => {
    if (!leadId) return;
    const { data } = await api.get(`/leads/${leadId}`);
    setLead(data);
  };

  useEffect(() => {
    if (open) {
      setTab("info");
      load();
    }
  }, [open, leadId]); // eslint-disable-line

  const notifyChanged = () => {
    load();
    onUpdate?.();
  };

  if (!open || !lead) return null;

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
          data-testid="lead-detail-drawer"
        >
          <div className="sticky top-0 bg-[#FFFFFF] border-b border-[#D6D3C8] px-6 py-4 flex items-center justify-between z-10">
            <div>
              <div className="mono-accent" style={{ color: STAGE_COLORS[lead.stage] }}>/// lead · {lead.stage}</div>
              <h2 className="text-2xl font-black tracking-tighter text-[#0A0A0A]">{lead.full_name}</h2>
            </div>
            <button onClick={onClose} className="text-[#595955] hover:text-[#DC2626]" data-testid="close-lead-drawer">
              <X size={22} />
            </button>
          </div>

          <div className="px-6 pt-4 flex items-center gap-1.5 border-b border-[#D6D3C8] overflow-x-auto">
            {TABS.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                className={`flex items-center gap-1.5 px-3 py-2 text-xs font-mono uppercase border-b-2 transition-colors whitespace-nowrap ${
                  tab === key ? "border-[#DC2626] text-[#DC2626]" : "border-transparent text-[#999995] hover:text-[#0A0A0A]"
                }`}
                data-testid={`lead-tab-${key}`}
              >
                <Icon size={13} weight={tab === key ? "bold" : "regular"} /> {label}
              </button>
            ))}
          </div>

          <div className="p-6">
            {tab === "info" && <InfoTab lead={lead} />}
            {tab === "notes" && <NotesTab leadId={lead.id} />}
            {tab === "tasks" && <TasksTab leadId={lead.id} />}
            {tab === "tags" && <TagsTab lead={lead} onChanged={notifyChanged} />}
            {tab === "history" && <HistoryTab leadId={lead.id} />}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

function InfoTab({ lead }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        {[
          [Envelope, "Email", lead.email],
          [Phone, "Phone", lead.phone],
          [Buildings, "Company", lead.company],
          [Globe, "Country", lead.country],
        ].map(([Icon, label, value]) => (
          <div key={label} className="surface p-3">
            <div className="mono-accent flex items-center gap-1"><Icon size={11} /> {label}</div>
            <div className="text-sm font-medium text-[#0A0A0A] mt-1 truncate">{value || "—"}</div>
          </div>
        ))}
      </div>

      <div className="surface p-4">
        <div className="mono-accent mb-2">/// lead.score</div>
        <div className="flex items-center gap-3">
          <div className="flex-1 h-2 bg-[#F0F0EA] rounded overflow-hidden">
            <div className="h-full bg-gradient-to-r from-[#DC2626] to-[#0F172A]" style={{ width: `${lead.score}%` }} />
          </div>
          <span className="font-mono text-sm font-bold">{lead.score}</span>
        </div>
      </div>

      <div className="surface p-4">
        <div className="mono-accent mb-2">/// consent</div>
        <div className="flex gap-2">
          <span className={`chip ${CONSENT_CHIP[lead.email_consent]}`}><Envelope size={11} /> email · {lead.email_consent}</span>
          <span className={`chip ${CONSENT_CHIP[lead.whatsapp_consent]}`}><WhatsappLogo size={11} /> whatsapp · {lead.whatsapp_consent}</span>
        </div>
      </div>

      {lead.tags?.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {lead.tags.map((t) => <span key={t} className="chip chip-ink">{t}</span>)}
        </div>
      )}
    </div>
  );
}

function NotesTab({ leadId }) {
  const [notes, setNotes] = useState([]);
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const { data } = await api.get("/notes", { params: { lead_id: leadId } });
    setNotes(data);
  };
  useEffect(() => { load(); }, [leadId]); // eslint-disable-line

  const add = async () => {
    if (!body.trim()) return;
    setSaving(true);
    try {
      await api.post("/notes", { lead_id: leadId, body: body.trim() });
      setBody("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to add note");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    await api.delete(`/notes/${id}`);
    load();
  };

  return (
    <div className="space-y-4">
      <div className="surface p-4">
        <textarea
          className="neo-input w-full min-h-[80px] resize-none"
          placeholder="Add a note — call outcome, objection, next step..."
          value={body}
          onChange={(e) => setBody(e.target.value)}
          data-testid="note-body-input"
        />
        <button onClick={add} disabled={saving || !body.trim()} className="btn-primary mt-2 !py-1.5 !px-3" data-testid="add-note-button">
          {saving ? <CircleNotch size={12} className="spin-slow" /> : <Plus size={12} weight="bold" />} ADD NOTE
        </button>
      </div>

      <div className="space-y-2">
        {notes.map((n) => (
          <motion.div key={n.id} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="surface p-3" data-testid={`note-${n.id}`}>
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm text-[#0A0A0A] whitespace-pre-wrap flex-1">{n.body}</p>
              <button onClick={() => remove(n.id)} className="text-[#999995] hover:text-[#DC2626] shrink-0"><Trash size={13} /></button>
            </div>
            <div className="mono-accent mt-2 text-[9px]">{new Date(n.created_at).toLocaleString()}</div>
          </motion.div>
        ))}
        {notes.length === 0 && (
          <div className="text-sm text-[#999995] italic py-4 text-center">No notes yet.</div>
        )}
      </div>
    </div>
  );
}

function TasksTab({ leadId }) {
  const [tasks, setTasks] = useState([]);
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const { data } = await api.get("/tasks", { params: { lead_id: leadId } });
    setTasks(data);
  };
  useEffect(() => { load(); }, [leadId]); // eslint-disable-line

  const add = async () => {
    if (!title.trim()) return;
    setSaving(true);
    try {
      await api.post("/tasks", { lead_id: leadId, title: title.trim() });
      setTitle("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to add task");
    } finally {
      setSaving(false);
    }
  };

  const toggleDone = async (t) => {
    await api.patch(`/tasks/${t.id}`, { status: t.status === "done" ? "open" : "done" });
    load();
  };

  const remove = async (id) => {
    await api.delete(`/tasks/${id}`);
    load();
  };

  return (
    <div className="space-y-4">
      <div className="surface p-4 flex gap-2">
        <input
          className="neo-input flex-1"
          placeholder="Follow up next Tuesday..."
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          data-testid="task-title-input"
        />
        <button onClick={add} disabled={saving || !title.trim()} className="btn-primary !py-1.5 !px-3" data-testid="add-task-button">
          {saving ? <CircleNotch size={12} className="spin-slow" /> : <Plus size={12} weight="bold" />}
        </button>
      </div>

      <div className="space-y-2">
        {tasks.map((t) => (
          <motion.div
            key={t.id} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
            className="surface p-3 flex items-center gap-3" data-testid={`task-${t.id}`}
          >
            <button onClick={() => toggleDone(t)} data-testid={`task-toggle-${t.id}`}>
              <CheckSquare
                size={18}
                weight={t.status === "done" ? "fill" : "regular"}
                className={t.status === "done" ? "text-[#10B981]" : "text-[#999995]"}
              />
            </button>
            <span className={`text-sm flex-1 ${t.status === "done" ? "line-through text-[#999995]" : "text-[#0A0A0A]"}`}>
              {t.title}
            </span>
            {t.due_at && <span className="mono-accent text-[9px]">{new Date(t.due_at).toLocaleDateString()}</span>}
            <button onClick={() => remove(t.id)} className="text-[#999995] hover:text-[#DC2626]"><Trash size={13} /></button>
          </motion.div>
        ))}
        {tasks.length === 0 && (
          <div className="text-sm text-[#999995] italic py-4 text-center">No tasks yet.</div>
        )}
      </div>
    </div>
  );
}

const TAG_COLORS = ["#DC2626", "#0F172A", "#10B981", "#F59E0B", "#475569", "#7C3AED"];

function TagsTab({ lead, onChanged }) {
  const [allTags, setAllTags] = useState([]);
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState(TAG_COLORS[0]);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const { data } = await api.get("/tags");
    setAllTags(data);
  };
  useEffect(() => { load(); }, []);

  const attached = allTags.filter((t) => lead.tags?.includes(t.name));
  const available = allTags.filter((t) => !lead.tags?.includes(t.name));

  const attach = async (tagId) => {
    setBusy(true);
    try {
      await api.post(`/leads/${lead.id}/tags/${tagId}`);
      onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to attach tag");
    } finally {
      setBusy(false);
    }
  };

  const detach = async (tagId) => {
    setBusy(true);
    try {
      await api.delete(`/leads/${lead.id}/tags/${tagId}`);
      onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to detach tag");
    } finally {
      setBusy(false);
    }
  };

  const createAndAttach = async () => {
    if (!newName.trim()) return;
    setBusy(true);
    try {
      const { data: tag } = await api.post("/tags", { name: newName.trim(), color: newColor });
      await api.post(`/leads/${lead.id}/tags/${tag.id}`);
      setNewName("");
      await load();
      onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to create tag");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <div className="mono-accent mb-2">/// attached</div>
        <div className="flex flex-wrap gap-1.5 min-h-[28px]">
          {attached.map((t) => (
            <span
              key={t.id}
              className="chip flex items-center gap-1.5"
              style={{ color: t.color || "#0A0A0A", borderColor: `${t.color || "#0A0A0A"}66` }}
              data-testid={`attached-tag-${t.id}`}
            >
              {t.name}
              <button onClick={() => detach(t.id)} disabled={busy}><X size={10} /></button>
            </span>
          ))}
          {attached.length === 0 && <span className="text-sm text-[#999995] italic">No tags attached.</span>}
        </div>
      </div>

      {available.length > 0 && (
        <div>
          <div className="mono-accent mb-2">/// available</div>
          <div className="flex flex-wrap gap-1.5">
            {available.map((t) => (
              <button
                key={t.id}
                onClick={() => attach(t.id)}
                disabled={busy}
                className="chip flex items-center gap-1.5 hover:opacity-70"
                style={{ color: t.color || "#0A0A0A", borderColor: `${t.color || "#0A0A0A"}66` }}
                data-testid={`available-tag-${t.id}`}
              >
                <Plus size={10} weight="bold" /> {t.name}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="surface p-4">
        <div className="mono-accent mb-2">/// new.tag</div>
        <div className="flex gap-2">
          <input
            className="neo-input flex-1"
            placeholder="e.g. Hot lead"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && createAndAttach()}
            data-testid="new-tag-name-input"
          />
          <div className="flex gap-1 items-center">
            {TAG_COLORS.map((c) => (
              <button
                key={c}
                onClick={() => setNewColor(c)}
                className="w-6 h-6 rounded-full border-2"
                style={{ background: c, borderColor: newColor === c ? "#0A0A0A" : "transparent" }}
                data-testid={`tag-color-${c}`}
              />
            ))}
          </div>
          <button onClick={createAndAttach} disabled={busy || !newName.trim()} className="btn-primary !py-1.5 !px-3" data-testid="create-tag-button">
            {busy ? <CircleNotch size={12} className="spin-slow" /> : <Check size={12} weight="bold" />}
          </button>
        </div>
      </div>
    </div>
  );
}

const CHANNEL_ICON = { email: <Envelope size={13} />, whatsapp: <WhatsappLogo size={13} weight="fill" /> };

function HistoryTab({ leadId }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/messages", { params: { lead_id: leadId } }).then((r) => setMessages(r.data)).finally(() => setLoading(false));
  }, [leadId]);

  if (loading) return <div className="text-sm text-[#999995] italic py-4 text-center">Loading...</div>;

  return (
    <div className="space-y-2">
      {messages.map((m) => (
        <div key={m.id} className="surface p-3" data-testid={`history-${m.id}`}>
          <div className="flex items-center justify-between">
            <span className="chip flex items-center gap-1.5">
              <PaperPlaneTilt size={11} /> {CHANNEL_ICON[m.channel]} {m.channel}
            </span>
            <span className="mono-accent text-[9px]">{new Date(m.created_at).toLocaleString()}</span>
          </div>
          {m.subject && <div className="text-sm font-semibold text-[#0A0A0A] mt-2">{m.subject}</div>}
          {m.body && <div className="text-xs font-mono text-[#595955] mt-1 whitespace-pre-wrap line-clamp-3">{m.body}</div>}
          <div className="mono-accent mt-2 text-[9px]">status · {m.status}</div>
        </div>
      ))}
      {messages.length === 0 && (
        <div className="text-sm text-[#999995] italic py-4 text-center">No messages sent to this lead yet.</div>
      )}
    </div>
  );
}
