import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowsClockwise, CaretLeft, CaretRight, ListChecks } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, prospectsApi, useAsync } from "@/lib/outreach";
import { REVIEW_META, describeApiError, domainOf } from "@/lib/outreachFormat";
import ScoreBadge from "@/components/outreach/ScoreBadge";
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
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") || "";
  const minScore = params.get("min") || "";
  const page = Math.max(0, parseInt(params.get("page") || "0", 10) || 0);
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState(null);
  const [runError, setRunError] = useState(null);

  const list = useAsync(
    () =>
      prospectsApi.list({
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        ...(status ? { review_status: status } : {}),
        ...(minScore ? { min_score: minScore } : {}),
      }),
    [status, minScore, page]
  );
  // Real totals per review status (one tiny request each), shown on the tabs.
  const counts = useAsync(async () => {
    const [pending, approved, rejected] = await Promise.all(
      ["pending", "approved", "rejected"].map((s) => prospectsApi.list({ limit: 1, review_status: s }))
    );
    return { pending: pending.total, approved: approved.total, rejected: rejected.total };
  }, []);

  const setParam = (key, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  };

  const runDiscovery = async () => {
    setRunning(true);
    setRunError(null);
    try {
      const r = await prospectsApi.runDiscovery();
      setLastRun(r);
      toast.success(`${r.listings_found} listings → ${r.entities} businesses (${r.duplicates_merged} duplicates merged)`);
      list.reload();
      counts.reload();
    } catch (e) {
      setRunError(describeApiError(e));
    } finally {
      setRunning(false);
    }
  };

  const items = list.data ? list.data.items : [];
  const total = list.data ? list.data.total : 0;
  const filtered = !!(status || minScore);
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="p-6 md:p-10 space-y-6" data-testid="prospects-page">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="mono-accent">// outreach.discovery</div>
          <h1 className="text-4xl font-black tracking-tighter">Prospects</h1>
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
          <button
            className="btn-primary"
            onClick={runDiscovery}
            disabled={running || !canDecide(user)}
            title={canDecide(user) ? "Reads the local fixture directory; no network" : "Requires owner or admin"}
            data-testid="run-discovery"
          >
            <ArrowsClockwise size={14} weight="bold" className={running ? "animate-spin" : ""} /> RUN DISCOVERY (DRY-RUN)
          </button>
        </div>
      </div>

      {runError && <ErrorBlock message={runError} />}
      {lastRun && (
        <div className="surface p-4 text-sm" data-testid="last-run">
          <div className="mono-accent mb-1">last discovery run · source {lastRun.source} · dry-run</div>
          {lastRun.listings_found} listings read, {lastRun.entities} distinct businesses ({lastRun.duplicates_merged} duplicates merged),{" "}
          {lastRun.prospects_created} new, {lastRun.prospects_updated} already known, {lastRun.suppressed} skipped as suppressed;{" "}
          {lastRun.sites_checked} homepages checked, {lastRun.signals_recorded} signal observations and {lastRun.scores_recorded} scores recorded.
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div className="flex gap-1 flex-wrap" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.key || "all"}
              role="tab"
              aria-selected={status === t.key}
              onClick={() => setParam("status", t.key)}
              className={`px-3 py-1.5 rounded-md text-sm border font-display ${
                status === t.key ? "bg-[#0F172A] text-white border-[#0F172A]" : "bg-white text-[#475569] border-[#D6D3C8] hover:border-[#0F172A]"
              }`}
              data-testid={`tab-${t.key || "all"}`}
            >
              {t.label}
              {t.key && counts.data ? ` · ${counts.data[t.key]}` : ""}
            </button>
          ))}
        </div>
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

      {list.data && items.length === 0 && !filtered && (
        <EmptyBlock title="No prospect yet" testId="empty-no-prospects">
          <p>Run discovery to read the local fixture directory (fictional restaurants). No network access is used and nothing is sent.</p>
          {canDecide(user) ? (
            <button className="btn-primary" onClick={runDiscovery} disabled={running} data-testid="empty-run-discovery">
              RUN DISCOVERY (DRY-RUN)
            </button>
          ) : (
            <p className="mono-accent">requires owner or admin</p>
          )}
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
            <thead className="bg-[#FAFAF7] border-b border-[#D6D3C8]">
              <tr className="text-left mono-accent">
                <th className="p-3">business</th>
                <th className="p-3">score</th>
                <th className="p-3">review</th>
                <th className="p-3 hidden md:table-cell">website</th>
                <th className="p-3 hidden md:table-cell">city</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id} className="border-b border-[#EDEBE0] hover:bg-[#FAF9F3]" data-testid="prospect-row">
                  <td className="p-3">
                    <Link to={`/app/prospects/${p.id}`} className="font-display font-semibold hover:text-[#DC2626]" data-testid="prospect-link">
                      {p.name}
                    </Link>
                  </td>
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
          <div className="flex items-center justify-between p-3 border-t border-[#D6D3C8] text-sm text-[#5F5F5A]">
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
