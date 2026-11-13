import { Link, useSearchParams } from "react-router-dom";
import { CaretLeft, CaretRight, Robot } from "@phosphor-icons/react";
import { LIVE_MS } from "@/lib/live";
import { prospectsApi, useAsync } from "@/lib/outreach";
import { REVIEW_META, formatDateTime } from "@/lib/outreachFormat";
import DraftJobsStrip from "@/components/outreach/DraftJobsStrip";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";

const PAGE_SIZE = 25;
const TABS = [
  { key: "", label: "All" },
  { key: "draft", label: "To review" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
];
const CHIP = { draft: "chip-warn", approved: "chip-success", rejected: "chip-danger" };

// The drafts of the organisation, the automatic ones included. A draft is a proposal: it is read, edited and approved on the
// prospect's sheet, and nothing is sent from here.
export default function Drafts() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") || "";
  const page = Math.max(0, parseInt(params.get("page") || "0", 10) || 0);
  const list = useAsync(
    () => prospectsApi.drafts({ limit: PAGE_SIZE, offset: page * PAGE_SIZE, ...(status ? { status } : {}) }),
    [status, page],
    { key: `drafts:${status}:${page}`, intervalMs: LIVE_MS }
  );
  const items = list.data ? list.data.items : [];
  const total = list.data ? list.data.total : 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const set = (patch) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    setParams(next, { replace: true });
  };
  return (
    <div className="p-6 md:p-10 space-y-6" data-testid="drafts-page">
      <div>
        <div className="eyebrow">outreach.drafts</div>
        <h1 className="mt-3 text-4xl font-bold tracking-tight leading-[1.15]">AI drafts</h1>
        <p className="text-soft mt-1 max-w-2xl">One short proposal per qualified prospect, about your offer. Read it, change it, approve it: nothing is sent without you.</p>
      </div>
      <div className="surface p-4"><DraftJobsStrip /></div>
      <div className="flex gap-1.5 flex-wrap" role="tablist" aria-label="Draft status">
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={status === t.key} onClick={() => set({ status: t.key, page: "" })} data-testid={`drafts-tab-${t.key || "all"}`}
            className={`px-3 py-1 rounded-full text-xs border transition-colors ${status === t.key ? "bg-brand-violet text-white border-brand-violet" : "bg-card border-border hover:bg-white/[0.04]"}`}>
            {t.label}
          </button>
        ))}
      </div>
      {list.error && !list.data && <ErrorBlock message={list.error} onRetry={list.reload} />}
      {list.loading && !list.data && <LoadingBlock />}
      {list.data && items.length === 0 && (
        <EmptyBlock title="No draft here yet">
          Drafts appear once a prospect is qualified and your offer is described. <Link to="/app/settings/offer" className="underline text-brand-lilac">Describe your offer</Link>
        </EmptyBlock>
      )}
      {items.length > 0 && (
        <div className="surface divide-y divide-border" data-testid="drafts-list">
          {items.map((d) => (
            <Link key={d.id} to={`/app/prospects/${d.lead_id}`} className="flex flex-wrap items-center gap-3 p-4 hover:bg-white/[0.03]" data-testid="draft-row">
              <div className="min-w-0 flex-1">
                <div className="font-display font-semibold truncate">{d.lead_name}{d.city ? <span className="text-faint font-normal"> · {d.city}</span> : null}</div>
                <div className="text-sm text-soft truncate">{d.subject}</div>
              </div>
              {d.auto && <span className="chip chip-ink inline-flex items-center gap-1"><Robot size={12} /> AI</span>}
              {d.edited && <span className="chip chip-ink">Edited</span>}
              <span className={`chip ${CHIP[d.status]}`}>{d.status === "draft" ? "To review" : REVIEW_META[d.status] ? REVIEW_META[d.status].label : d.status}</span>
              <time className="text-xs text-faint w-36 text-right" dateTime={d.created_at}>{formatDateTime(d.created_at)}</time>
            </Link>
          ))}
        </div>
      )}
      {total > PAGE_SIZE && (
        <div className="flex items-center gap-3 text-sm" role="navigation" aria-label="Pages">
          <button className="btn-ghost" disabled={page === 0} onClick={() => set({ page: page > 1 ? String(page - 1) : "" })}><CaretLeft size={14} /> PREVIOUS</button>
          <span>Page {page + 1} / {pages} · {total} drafts</span>
          <button className="btn-ghost" disabled={page + 1 >= pages} onClick={() => set({ page: String(page + 1) })}>NEXT <CaretRight size={14} /></button>
        </div>
      )}
    </div>
  );
}
