import { Link } from "react-router-dom";
import { draftJobsApi, useAsync } from "@/lib/outreach";
import { DRAFT_JOB_META, SITE_STATE_LABEL } from "@/lib/outreachFormat";

// The automatic draft of one prospect: its state, what the message could say about the website, and why it is not ready.
// Nothing here prepares or sends anything; the draft itself appears in the list below once it is ready, to review.
export default function DraftJobStatus({ prospectId }) {
  const job = useAsync(() => draftJobsApi.forLead(prospectId), [prospectId], { key: `draft-job:${prospectId}`, intervalMs: 5000 });
  const j = job.data;
  if (!j) return null;
  const meta = DRAFT_JOB_META[j.status];
  return (
    <div className="surface p-4 text-sm space-y-1" data-testid="draft-job-status" data-status={j.status}>
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`chip ${meta.chip}`}>{meta.label}</span>
        <span className="text-faint">{SITE_STATE_LABEL[j.site_state]}</span>
      </div>
      {j.error && <p className="text-soft">{j.error}</p>}
      {j.status === "offer_required" && (
        <p><Link to="/app/settings/offer" className="underline text-brand-lilac">Describe your offer</Link> to get this draft.</p>
      )}
    </div>
  );
}
