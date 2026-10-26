import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CaretLeft, CaretRight, ListChecks, MapTrifold } from "@phosphor-icons/react";
import { prospectsApi, useAsync } from "@/lib/outreach";
import { REVIEW_META, domainOf } from "@/lib/outreachFormat";
import ScoreBadge from "@/components/outreach/ScoreBadge";
import HeatBadge from "@/components/outreach/HeatBadge";
import EmptyToggle from "@/components/outreach/EmptyToggle";
import { readPref, writePref } from "@/lib/uiPrefs";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";

const PAGE_SIZE = 25;
const TABS = [
  { key: "", label: "All" },
  { key: "pending", label: "Pending review" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
];
const MIN_SCORES = [
  { value: "", label: "Any score" },
  { value: "30", label: "30 and above" },
  { value: "50", label: "50 and above" },
  { value: "70", label: "70 and above" },
];

export default function Prospects() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") || "";
  const minScore = params.get("min") || "";
  const page = Math.max(0, parseInt(params.get("page") || "0", 10) || 0);
  const [showEmpty, setShowEmpty] = useState(() => readPref("prospects.showEmpty", false)); // no e-mail, phone or website
  const toggleEmpty = () => setShowEmpty((v) => { writePref("prospects.showEmpty", !v); return !v; });

  const list = useAsync(
    () =>
      prospectsApi.list({
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        ...(status ? { review_status: status } : {}),
        ...(minScore ? { min_score: minScore } : {}),
        ...(showEmpty ? {} : { hide_empty: true }),
        segment: "strict",
      }),
    [status, minScore, page, showEmpty]
  );
  // Real totals per review status (one tiny request each, counted by the server), shown on the tabs, and how many empty leads
  // (no e-mail, phone or website) each holds.
  const counts = useAsync(async () => {
    const [pending, approved, rejected] = await Promise.all(
      ["pending", "approved", "rejected"].map((s) => prospectsApi.queues(s, { hideEmpty: !showEmpty, segment: "strict" }))
    );
    return {
      pending: pending.total, approved: approved.total, rejected: rejected.total,
      empty: { pending: pending.empty, approved: approved.empty, rejected: rejected.empty },
    };
  }, [showEmpty]);

  const setParam = (key, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  };

  const items = list.data ? list.data.items : [];
  const total = list.data ? list.data.total : 0;
  const filtered = !!(status || minScore);
  const emptyCount = counts.data ? (status ? counts.data.empty[status] : counts.data.empty.pending + counts.data.empty.approved + counts.data.empty.rejected) : 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="p-6 md:p-10 space-y-6" data-testid="prospects-page">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="mono-accent">// outreach.discovery</div>
        <h1 className="text-4xl font-black tracking-tighter">Strictly qualified</h1>
          <p className="text-[#5F5F5A] mt-1 max-w-2xl">
            Businesses found in authorised sources, scored from verifiable signals. Nothing is contacted until a person approves it.
          </p>
        </div>
        <div className="flex gap-2 items-center flex-wrap">
          <Link to="/app/prospects/import" className="btn-ghost" data-testid="open-import">
            IMPORT A LIST
          </Link>
          <Link to="/app/prospects/review" className="btn-ghost" data-testid="open-review-queue">
            <ListChecks size={14} /> REVIEW QUEUE{counts.data ? ` (${counts.data.pending})` : ""}
          </Link>
          <Link to="/app/map" className="btn-primary" data-testid="open-map-search">
            <MapTrifold size={14} weight="bold" /> FIND ON THE MAP
          </Link>
        </div>
      </div>

      <p className="text-xs text-[#5F5F5A]" role="status" data-testid="active-qualification-segment">
        Segment actif : strictement qualifiés · email sourcé, WhatsApp publié, site officiel vérifié récemment et adéquation ICP.
      </p>

      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div className="flex gap-1 flex-wrap" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.key || "all"}
              role="tab"
              aria-selected={status === t.key}
              onClick={() => setParam("status", t.key)}
              className={`px-3 py-1.5 rounded-md text-sm border font-display ${
                status === t.key ? "bg-[#0F172A] text-white border-[#0F172A]" : "bg-white text-[#475569] border-[#D3DBEA] hover:border-[#0F172A]"
              }`}
              data-testid={`tab-${t.key || "all"}`}
            >
              {t.label}
              {t.key && counts.data ? ` · ${counts.data[t.key]}` : ""}
            </button>
          ))}
        </div>
        <EmptyToggle empty={emptyCount} showEmpty={showEmpty} onToggle={toggleEmpty} testId="prospects-empty-toggle" />
        <label className="flex items-center gap-2 text-sm text-[#475569]">
          <span className="mono-accent">min score</span>
          <select className="neo-input !w-auto" value={minScore} onChange={(e) => setParam("min", e.target.value)} data-testid="min-score">
            {MIN_SCORES.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {list.loading && !list.data && <LoadingBlock label="Loading prospects…" />}
      {list.error && <ErrorBlock message={list.error} onRetry={list.reload} />}

      {list.data && items.length === 0 && !filtered && counts.data && emptyCount > 0 && !showEmpty && (
        <EmptyBlock title="Every prospect is empty" testId="empty-all-hidden">
          <p>{emptyCount} prospect{emptyCount === 1 ? " has" : "s have"} no e-mail, phone or website, so {emptyCount === 1 ? "it is" : "they are"} hidden. Show them to complete them, or find better ones on the map.</p>
          <button className="btn-ghost" onClick={toggleEmpty} data-testid="empty-show-all">SHOW THEM</button>
        </EmptyBlock>
      )}
      {list.data && items.length === 0 && !filtered && counts.data && !(emptyCount > 0 && !showEmpty) && (
        <EmptyBlock title="No strictly qualified prospect" testId="empty-no-prospects">
          <p>
            No prospect currently meets every source, freshness, email, WhatsApp, website and ICP requirement. Incomplete prospects remain in
            the review queue to enrich; the criteria are not relaxed to fill this list.
          </p>
          <div className="flex gap-2 justify-center flex-wrap">
            <Link to="/app/prospects/review" className="btn-ghost">OPEN “À ENRICHIR”</Link>
            <Link to="/app/map" className="btn-primary" data-testid="empty-open-map">
              <MapTrifold size={14} weight="bold" /> FIND ON THE MAP
            </Link>
            <Link to="/app/prospects/import" className="btn-ghost">IMPORT A LIST</Link>
          </div>
        </EmptyBlock>
      )}
      {list.data && items.length === 0 && filtered && (
        <EmptyBlock title="No prospect matches this filter" testId="empty-filtered">
          <button className="btn-ghost" onClick={() => setParams({}, { replace: true })}>
            CLEAR FILTERS
          </button>
        </EmptyBlock>
      )}

      {items.length > 0 && (
        <div className="surface overflow-hidden">
          <table className="w-full text-sm" data-testid="prospects-table">
            <thead className="bg-[#F6F8FC] border-b border-[#D3DBEA]">
              <tr className="text-left mono-accent">
                <th className="p-3">business</th>
                <th className="p-3">priority</th>
                <th className="p-3">score</th>
                <th className="p-3">review</th>
                <th className="p-3 hidden md:table-cell">website</th>
                <th className="p-3 hidden md:table-cell">city</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id} className="border-b border-[#E9EEF7] hover:bg-[#F7F9FD]" data-testid="prospect-row">
                  <td className="p-3">
                    <Link to={`/app/prospects/${p.id}`} className="font-display font-semibold hover:text-[#4F46E5]" data-testid="prospect-link">
                      {p.name}
                    </Link>
                  </td>
                  <td className="p-3"><HeatBadge heat={p.heat} /></td>
                  <td className="p-3">
                    <ScoreBadge score={p.score} coverage={p.coverage} showCoverage />
                  </td>
                  <td className="p-3">
                    <span className={`chip ${REVIEW_META[p.review_status].chip}`}>{REVIEW_META[p.review_status].label}</span>
                  </td>
                  <td className="p-3 hidden md:table-cell font-mono text-xs">{domainOf(p.website) || <span className="text-[#6B6B66]">none listed</span>}</td>
                  <td className="p-3 hidden md:table-cell text-[#475569]">{p.city || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center justify-between p-3 border-t border-[#D3DBEA] text-sm text-[#5F5F5A]">
            <span data-testid="prospects-total">{total} prospect{total === 1 ? "" : "s"}</span>
            <span className="flex items-center gap-2">
              <button className="btn-ghost" disabled={page === 0} onClick={() => setParam("page", String(page - 1))} aria-label="Previous page">
                <CaretLeft size={14} />
              </button>
              <span className="font-mono">
                {page + 1} / {pages}
              </span>
              <button className="btn-ghost" disabled={page + 1 >= pages} onClick={() => setParam("page", String(page + 1))} aria-label="Next page">
                <CaretRight size={14} />
              </button>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
