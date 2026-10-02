import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ArrowRight, Check, SkipForward, X } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, prospectsApi, useAsync } from "@/lib/outreach";
import { describeApiError, domainOf } from "@/lib/outreachFormat";
import ScoreBadge from "@/components/outreach/ScoreBadge";
import ScoreBreakdown from "@/components/outreach/ScoreBreakdown";
import SourceList from "@/components/outreach/SourceList";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";

// One pending prospect at a time, best score first, with the evidence needed to decide.
// Approve/reject records a human decision (audited); skip just moves on without deciding.
export default function ReviewQueue() {
  const { user } = useAuth();
  const [skipped, setSkipped] = useState([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const queue = useAsync(() => prospectsApi.list({ review_status: "pending", limit: 100 }), []);
  const pending = queue.data ? queue.data.items.filter((p) => !skipped.includes(p.id)) : [];
  const current = pending[0];
  const detail = useAsync(() => (current ? prospectsApi.get(current.id) : Promise.resolve(null)), [current && current.id]);

  const decide = async (decision) => {
    setBusy(true);
    setError(null);
    try {
      await prospectsApi.review(current.id, decision, note);
      toast.success(decision === "approve" ? `${current.name} approved` : `${current.name} rejected`);
      setNote("");
      queue.reload();
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
        <p className="text-[#6B6B66] mt-1">
          Decide on each prospect from its evidence. An approval makes it eligible for a draft; it does not send anything.
        </p>
      </div>

      {queue.loading && !queue.data && <LoadingBlock label="Loading the queue…" />}
      {queue.error && <ErrorBlock message={queue.error} onRetry={queue.reload} />}

      {queue.data && !current && (
        <EmptyBlock title={queue.data.total === 0 ? "The review queue is empty" : "You skipped every pending prospect"} testId="queue-empty">
          {queue.data.total === 0 ? (
            <p>No prospect is waiting for a decision. Run discovery on the Prospects page to find more.</p>
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
          <div className="flex items-center justify-between text-sm text-[#6B6B66]" data-testid="queue-position">
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
                <p className="text-sm text-[#6B6B66]">
                  {[current.city, domainOf(current.website) || "no own website listed"].filter(Boolean).join(" · ")}
                </p>
              </div>
              <ScoreBadge score={current.score} coverage={current.coverage} showCoverage />
            </div>

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
            <div className="space-y-2 pt-2 border-t border-[#EDEBE0]">
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
                {!canDecide(user) && <span className="mono-accent self-center text-[#999995]">deciding requires owner or admin</span>}
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
