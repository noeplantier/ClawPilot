import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ArrowRight, Check, SkipForward, X } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, prospectsApi, useAsync } from "@/lib/outreach";
import { LIVE_MS, useLive } from "@/lib/live";
import { FIELD_LABEL, LANES, LANE_LABEL, inLane, laneCounts } from "@/lib/heat";
import { readPref, writePref } from "@/lib/uiPrefs";
import HeatBadge from "@/components/outreach/HeatBadge";
import EmptyToggle from "@/components/outreach/EmptyToggle";
import { describeApiError, domainOf } from "@/lib/outreachFormat";
import ScoreBadge from "@/components/outreach/ScoreBadge";
import ScoreBreakdown from "@/components/outreach/ScoreBreakdown";
import SourceList from "@/components/outreach/SourceList";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";

// One pending prospect at a time, hottest first (real information + score), with the evidence needed to decide.
// The queue refreshes in the background; the card you are reading stays put, new arrivals join the lanes.
// Approve/reject records a human decision (audited); skip just moves on without deciding.
export default function ReviewQueue() {
  const { user } = useAuth();
  const [skipped, setSkipped] = useState([]);
  const [lane, setLane] = useState("all"); // all | top | hot | warm | cold
  const [showEmpty, setShowEmpty] = useState(() => readPref("review.showEmpty", false)); // prospects with no e-mail, phone or website
  const [pinned, setPinned] = useState(null); // the prospect being reviewed: a refresh never swaps it under your eyes
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const queue = useLive(
    () => prospectsApi.list({ review_status: "pending", order: "heat", limit: 100, ...(showEmpty ? {} : { hide_empty: true }) }),
    [showEmpty], { itemsOf: (d) => d.items },
  );
  const counts = useLive(() => prospectsApi.queues("pending", { hideEmpty: !showEmpty }), [showEmpty], { idOf: () => "counts", itemsOf: (d) => [d] });
  const toggleEmpty = () => setShowEmpty((v) => { writePref("review.showEmpty", !v); return !v; });
  const everyPending = useMemo(() => (queue.data ? queue.data.items.filter((p) => !skipped.includes(p.id)) : []), [queue.data, skipped]);
  const pending = useMemo(() => inLane(everyPending, lane), [everyPending, lane]);
  const loaded = laneCounts(everyPending);
  const server = counts.data || null; // counted by the server over the whole queue (the list holds the first 100)
  const current = pending.find((p) => p.id === pinned) || pending[0];
  useEffect(() => { setPinned(pending[0] ? pending[0].id : null); }, [lane]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!pinned || !pending.some((p) => p.id === pinned)) setPinned(pending[0] ? pending[0].id : null); }, [pending, pinned]);
  const detail = useAsync(() => (current ? prospectsApi.get(current.id) : Promise.resolve(null)), [current && current.id]);

  const decide = async (decision) => {
    setBusy(true);
    setError(null);
    try {
      await prospectsApi.review(current.id, decision, note);
      toast.success(decision === "approve" ? `${current.name} approved` : `${current.name} rejected`);
      setNote("");
      queue.reload();
      counts.reload();
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-6 md:p-10 space-y-6 max-w-5xl" data-testid="review-queue">
      <div>
        <div className="mono-accent">// human.review</div>
        <h1 className="text-4xl font-black tracking-tighter">Review queue</h1>
        <p className="text-[#5F5F5A] mt-1">
          Decide on each prospect from its evidence. An approval makes it eligible for a draft; it does not send anything.
        </p>
      </div>

      {queue.loading && !queue.data && <LoadingBlock label="Loading the queue…" />}
      {queue.error && <ErrorBlock message={queue.error} onRetry={queue.reload} />}

      {queue.data && (
        <div className="space-y-2" data-testid="queue-lanes-bar">
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Queues by heat">
            {LANES.map((k) => [k, `${LANE_LABEL[k]} ${k === "all" ? (server ? server.total : loaded.total) : (server ? server[k] : loaded[k])}`]).map(([key, label]) => (
              <button key={key} onClick={() => setLane(key)} aria-pressed={lane === key} data-testid={`queue-lane-${key}`}
                className={`px-3 py-1 rounded-full text-xs border transition-colors ${lane === key ? "bg-[#0B1020] text-white border-[#0B1020] shadow-[0_0_14px_-2px_rgba(99,102,241,0.7)]" : "bg-white/80 border-[#D3DBEA] hover:bg-white"}`}>
                {label}
              </button>
            ))}
            <span className="text-xs inline-flex items-center gap-2 text-[#4338CA]" role="status" aria-live="polite" data-testid="queue-live">
              <span className="pos-live-dot" aria-hidden="true" />
              {queue.stale ? "Refresh failed: showing the last data. " : ""}
              {queue.updatedAt ? `Live · updated ${queue.updatedAt.toLocaleTimeString()} · every ${LIVE_MS / 1000} s` : ""}
            </span>
            {server && <EmptyToggle empty={server.empty} showEmpty={showEmpty} onToggle={toggleEmpty} testId="queue-empty-toggle" />}
          </div>
          {queue.fresh.size > 0 && (
            <p className="text-xs text-[#0E7490]" data-testid="queue-new">{queue.fresh.size} new prospect{queue.fresh.size === 1 ? "" : "s"} joined the queue (hottest first).</p>
          )}
        </div>
      )}

      {queue.data && !current && (
        <EmptyBlock title={queue.data.total === 0 ? (!showEmpty && server && server.empty > 0 ? "Every prospect waiting is empty" : "The review queue is empty") : lane !== "all" && everyPending.length > 0 ? `No ${LANE_LABEL[lane].toLowerCase()} prospect waiting` : "You skipped every pending prospect"} testId="queue-empty">
          {queue.data.total === 0 ? (
            !showEmpty && server && server.empty > 0
              ? <p>{server.empty} prospect{server.empty === 1 ? "" : "s"} waiting {server.empty === 1 ? "has" : "have"} no e-mail, phone or website, so they are hidden. Show them above to decide on them anyway.</p>
              : <p>No prospect is waiting for a decision. Run discovery on the Prospects page to find more.</p>
          ) : (
            <button className="btn-ghost" onClick={() => setSkipped([])}>
              SHOW SKIPPED AGAIN
            </button>
          )}
          <Link to="/app/prospects" className="btn-ink inline-flex">
            BACK TO PROSPECTS
          </Link>
        </EmptyBlock>
      )}

      {current && (
        <>
          <div className="flex items-center justify-between text-sm text-[#5F5F5A]" data-testid="queue-position">
            <span>
              {pending.length} of {queue.data.total} pending prospect{queue.data.total === 1 ? "" : "s"} left in this session
            </span>
            <Link to={`/app/prospects/${current.id}`} className="underline inline-flex items-center gap-1">
              open full detail <ArrowRight size={12} />
            </Link>
          </div>

          <section className="surface p-5 space-y-4" data-testid="queue-card">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <h2 className="font-display text-2xl font-bold" data-testid="queue-name">{current.name}</h2>
                <p className="text-sm text-[#5F5F5A]">
                  {[current.city, domainOf(current.website) || "no own website listed"].filter(Boolean).join(" · ")}
                </p>
              </div>
              <div className="flex flex-col items-end gap-2">
                <HeatBadge heat={current.heat} />
                <ScoreBadge score={current.score} coverage={current.coverage} showCoverage />
              </div>
            </div>
            {current.heat && (
              <p className="text-xs text-[#5F5F5A]" data-testid="queue-known">
                Known: {current.heat.known.map((k) => FIELD_LABEL[k]).join(", ") || "nothing yet"}
                {current.heat.missing.length > 0 && <> · <span className="text-[#6B6B66]">not known: {current.heat.missing.map((k) => FIELD_LABEL[k]).join(", ")}</span></>}
              </p>
            )}

            {detail.loading && <LoadingBlock label="Loading evidence…" />}
            {detail.error && <ErrorBlock message={detail.error} onRetry={detail.reload} />}
            {detail.data && (
              <>
                <ScoreBreakdown detail={detail.data.score_detail} />
                <div>
                  <h3 className="font-display font-bold mb-2">Where the data comes from</h3>
                  <SourceList sources={detail.data.sources} />
                </div>
              </>
            )}

            {error && (
              <div role="alert" className="text-sm text-[#991B1B] bg-[#FEF2F2] border border-[#FCA5A5] rounded-md p-3" data-testid="queue-error">
                {error}
              </div>
            )}
            <div className="space-y-2 pt-2 border-t border-[#E9EEF7]">
              <label className="mono-accent block" htmlFor="review-note">
                note (optional, kept on the prospect, not in the audit trail)
              </label>
              <textarea id="review-note" className="neo-input" rows={2} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} data-testid="review-note" />
              <div className="flex flex-wrap gap-2">
                <button className="btn-primary" disabled={!canDecide(user) || busy} onClick={() => decide("approve")} data-testid="queue-approve">
                  <Check size={14} weight="bold" /> APPROVE
                </button>
                <button className="btn-ghost" disabled={!canDecide(user) || busy} onClick={() => decide("reject")} data-testid="queue-reject">
                  <X size={14} /> REJECT
                </button>
                <button className="btn-ghost" disabled={busy} onClick={() => setSkipped((s) => [...s, current.id])} data-testid="queue-skip">
                  <SkipForward size={14} /> SKIP
                </button>
                {!canDecide(user) && <span className="mono-accent self-center text-[#6B6B66]">deciding requires owner or admin</span>}
              </div>
            </div>
          </section>
          {pending.length > 1 && (
            <section className="surface p-4" data-testid="queue-next">
              <h3 className="font-display font-bold mb-2">Up next</h3>
              <ul className="divide-y divide-[#E3E9F4]">
                {pending.filter((p) => p.id !== current.id).slice(0, 6).map((p) => (
                  <li key={p.id} className={`py-2 flex items-center justify-between gap-3 ${queue.fresh.has(p.id) ? "bg-cyan-50" : ""}`} data-testid="queue-next-row">
                    <span className="min-w-0">
                      <span className="font-medium block truncate">{p.name}{queue.fresh.has(p.id) && <span className="chip chip-cyan ml-2">new</span>}</span>
                      <span className="text-xs text-[#5F5F5A]">{[p.city, domainOf(p.website) || "no own website listed"].filter(Boolean).join(" · ")}</span>
                    </span>
                    <span className="flex items-center gap-2 shrink-0">
                      <HeatBadge heat={p.heat} compact />
                      <button className="btn-ghost !py-1 !px-2 text-xs" onClick={() => setPinned(p.id)} data-testid="queue-open-next">REVIEW NOW</button>
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
