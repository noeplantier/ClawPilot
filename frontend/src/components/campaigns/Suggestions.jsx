import { useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { Lightbulb, Sparkle } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { LIVE_MS, useLive } from "@/lib/live";
import { describeApiError } from "@/lib/outreachFormat";
import { KIND_LABEL, basisLine, createLabel, emptyText, readyLine } from "@/lib/suggestions";

// Suggested campaigns, recomputed from your real leads and prospects every few seconds. Nothing is sent: "create"
// makes a draft and assigns the people who can join today.
export default function Suggestions({ onCreated }) {
  const live = useLive(() => api.get("/campaigns/suggestions").then((r) => r.data), [], { itemsOf: (d) => d.items });
  const [busy, setBusy] = useState(null);
  const d = live.data;

  const create = async (s) => {
    setBusy(s.id);
    try {
      const { data } = await api.post(`/campaigns/suggestions/${s.id}/create`);
      toast.success(`"${data.name}" created with ${data.assigned} ${data.assigned === 1 ? "person" : "people"}. ${data.note}`);
      live.reload();
      if (onCreated) onCreated(data);
    } catch (e) {
      toast.error(describeApiError(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="surface p-5 space-y-4" data-testid="suggestions" aria-label="Suggested campaigns">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="mono-accent inline-flex items-center gap-2"><Lightbulb size={14} weight="fill" /> // live.suggestions</div>
          <h2 className="font-display text-xl font-bold">Suggested campaigns</h2>
          <p className="text-xs text-[#5F5F5A]" data-testid="suggestions-basis">{d ? basisLine(d.basis) : ""} Hottest first.</p>
        </div>
        <p className="text-xs inline-flex items-center gap-2 text-[#4338CA]" role="status" aria-live="polite" data-testid="suggestions-live">
          <span className="pos-live-dot" aria-hidden="true" />
          {live.stale ? "Refresh failed: showing the last data. " : ""}
          {live.updatedAt ? `Live · updated ${live.updatedAt.toLocaleTimeString()} · every ${LIVE_MS / 1000} s` : "Loading…"}
        </p>
      </div>

      {live.error && <div role="alert" className="text-sm text-[#991B1B]" data-testid="suggestions-error">{live.error}</div>}
      {d && d.items.length === 0 && <p className="text-sm text-[#5F5F5A]" data-testid="suggestions-empty">{emptyText(d.basis)}</p>}

      <div className="grid lg:grid-cols-2 gap-3">
        <AnimatePresence initial={false}>
          {d && d.items.map((s) => (
            <motion.article
              key={s.id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              className={`rounded-xl border p-4 space-y-2 ${live.fresh.has(s.id) ? "border-cyan-400 bg-cyan-50/60" : "border-[#D3DBEA] bg-white/70"}`}
              data-testid="suggestion"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="chip chip-ink">{KIND_LABEL[s.kind]}</span>
                    {live.fresh.has(s.id) && <span className="chip chip-cyan" data-testid="suggestion-new">new</span>}
                    {s.hot > 0 && <span className="chip chip-hot">{s.hot} hot</span>}
                  </div>
                  <h3 className="font-display font-bold mt-1">{s.title}</h3>
                  {s.angle && <p className="text-xs text-[#4338CA]">{s.angle}</p>}
                </div>
                <span className="font-mono text-xs text-[#595955] shrink-0" title="Average heat of the hottest members">heat {s.avg_heat}</span>
              </div>
              <p className="text-sm text-[#5F5F5A]">{s.rationale}</p>
              <p className="text-xs text-[#6B6B66]">e.g. {s.examples.join(" · ")}</p>
              <p className={`text-xs ${s.eligible > 0 ? "text-[#065F46]" : "text-[#92400E]"}`} data-testid="suggestion-ready">{readyLine(s)}</p>
              <div className="flex items-center gap-2 flex-wrap">
                <button className="btn-ink !py-1.5" disabled={s.eligible === 0 || busy === s.id} onClick={() => create(s)} data-testid="suggestion-create">
                  <Sparkle size={13} weight="fill" /> {createLabel(s, busy === s.id)}
                </button>
                {s.pending_review > 0 && <Link to="/app/prospects/review" className="text-xs underline">review {s.pending_review} pending</Link>}
              </div>
            </motion.article>
          ))}
        </AnimatePresence>
      </div>
    </section>
  );
}
