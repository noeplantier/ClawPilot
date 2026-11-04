import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ArrowsClockwise } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, draftJobsApi, useAsync } from "@/lib/outreach";
import { describeApiError, draftSummaryLine } from "@/lib/outreachFormat";

// Progress of the automatic drafts, as the server counts them. It sits beside the map and the queue, never in front of a
// marker: a draft that is slow, failed or waiting for the AI changes this line and nothing else. A draft is a proposal to review.
export default function DraftJobsStrip({ className = "" }) {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const state = useAsync(() => draftJobsApi.summary(), [], { key: "draft-jobs:summary", intervalMs: 5000 });
  const s = state.data;
  if (!s) return null;
  const pending = (s.counts.queued || 0) + (s.counts.unavailable || 0) + (s.counts.failed || 0);
  const run = async () => {
    setBusy(true);
    try {
      await draftJobsApi.run();
      toast.success("Drafts are being prepared in the background");
      state.reload();
    } catch (e) {
      toast.error(describeApiError(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className={`text-xs space-y-1 ${className}`} role="status" data-testid="draft-jobs-strip">
      <div>
        <b>Drafts</b> · {draftSummaryLine(s)}
      </div>
      {!s.offer_configured && (
        <div className="text-brand-lilac" data-testid="draft-offer-required">
          Offer required: describe what you sell in <Link to="/app/settings/offer" className="underline">your offer</Link> to get a draft for each qualified prospect.
        </div>
      )}
      {s.offer_configured && !s.ai_active && (
        <div data-testid="draft-ai-off">The AI is off on this server: drafts wait and resume as soon as it is configured. Nothing is written in its place.</div>
      )}
      {s.offer_configured && pending > 0 && canDecide(user) && (
        <button className="btn-ghost !px-2 !py-1 text-xs" onClick={run} disabled={busy} data-testid="draft-jobs-run">
          <ArrowsClockwise size={12} className={busy ? "animate-spin" : ""} /> PREPARE THE PENDING DRAFTS
        </button>
      )}
    </div>
  );
}
