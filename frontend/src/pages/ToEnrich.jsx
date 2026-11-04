import { Link, useSearchParams } from "react-router-dom";
import { CaretLeft, CaretRight, MapTrifold } from "@phosphor-icons/react";
import { LIVE_MS } from "@/lib/live";
import { prospectsApi, useAsync } from "@/lib/outreach";
import { REVIEW_META, gapLine } from "@/lib/outreachFormat";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";

const PAGE_SIZE = 25;

// Prospects that are not qualified yet: they stay here with what is missing, never contactable by default, and never on the
// commercial map until an e-mail, a phone, an address and a position from a fresh source are all known.
export default function ToEnrich() {
  const [params, setParams] = useSearchParams();
  const page = Math.max(0, parseInt(params.get("page") || "0", 10) || 0);
  const list = useAsync(() => prospectsApi.toEnrich({ limit: PAGE_SIZE, offset: page * PAGE_SIZE }), [page], {
    key: `prospects:to-enrich:${page}`,
    intervalMs: LIVE_MS,
  });
  const items = list.data ? list.data.items : [];
  const total = list.data ? list.data.total : 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const go = (n) => setParams(n > 0 ? { page: String(n) } : {}, { replace: true });
  return (
    <div className="p-6 md:p-10 space-y-6" data-testid="to-enrich-page">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="mono-accent">// outreach.qualification</div>
          <h1 className="text-4xl font-black tracking-tighter">To enrich</h1>
          <p className="text-soft mt-1 max-w-2xl">
            Prospects that lack something to be qualified. They are kept, not contactable, and join the map as soon as they have an e-mail, a phone, an address and
            a position from a fresh source.
          </p>
        </div>
        <Link to="/app/map" className="btn-primary"><MapTrifold size={14} weight="bold" /> OPEN THE MAP</Link>
      </div>
      {list.error && !list.data && <ErrorBlock message={list.error} />}
      {list.loading && !list.data && <LoadingBlock />}
      {list.data && items.length === 0 && (
        <EmptyBlock title="Nothing waits to be enriched">Every prospect that was found is qualified, or was excluded (suppressed, rejected).</EmptyBlock>
      )}
      {items.length > 0 && (
        <div className="surface divide-y divide-border" data-testid="to-enrich-list">
          {items.map((p) => (
            <Link key={p.id} to={`/app/prospects/${p.id}`} className="flex flex-wrap items-center gap-3 p-4 hover:bg-white/[0.03]" data-testid="to-enrich-row">
              <div className="min-w-0 flex-1">
                <div className="font-display font-semibold truncate">{p.name}</div>
                <div className="text-xs text-faint">{[p.city, p.email, p.phone].filter(Boolean).join(" · ") || "No contact detail known"}</div>
              </div>
              <span className="chip chip-warn" data-testid="to-enrich-gaps">{gapLine(p.missing_fields)}</span>
              {p.review_status && <span className={`chip ${REVIEW_META[p.review_status].chip}`}>{REVIEW_META[p.review_status].label}</span>}
            </Link>
          ))}
        </div>
      )}
      {total > PAGE_SIZE && (
        <div className="flex items-center gap-3 text-sm" role="navigation" aria-label="Pages">
          <button className="btn-ghost" disabled={page === 0} onClick={() => go(page - 1)}><CaretLeft size={14} /> PREVIOUS</button>
          <span>Page {page + 1} / {pages} · {total} prospects</span>
          <button className="btn-ghost" disabled={page + 1 >= pages} onClick={() => go(page + 1)}>NEXT <CaretRight size={14} /></button>
        </div>
      )}
    </div>
  );
}
