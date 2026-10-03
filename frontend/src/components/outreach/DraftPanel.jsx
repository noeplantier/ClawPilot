import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Check, X, PaperPlaneTilt, NotePencil } from "@phosphor-icons/react";
import { outboundApi, prospectsApi } from "@/lib/outreach";
import { MESSAGE_STATUS_CHIP, describeApiError, formatDateTime } from "@/lib/outreachFormat";

const DRAFT_CHIP = { draft: "chip-warn", approved: "chip-success", rejected: "chip-danger" };

// Drafts of one prospect: prepare, approve or reject (a human decision), then dispatch. Nothing leaves the
// system while dry-run is on, and the page says so.
export default function DraftPanel({ prospect, drafts, messages, canDecide, dryRun, onChanged }) {
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const approved = prospect.review_status === "approved";
  const messageOf = (draftId) => (messages || []).find((m) => m.draft_id === draftId);

  const act = async (key, fn, success) => {
    setBusy(key);
    setError(null);
    try {
      await fn();
      toast.success(success);
      await onChanged();
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy(null);
    }
  };

  let createHint = null;
  if (!approved) createHint = "Approve the prospect first: drafts are only prepared for approved prospects.";
  else if (!prospect.contact_email) createHint = "This prospect has no public e-mail address, so no e-mail draft can be prepared.";

  return (
    <div className="space-y-4" data-testid="draft-panel">
      {dryRun && (
        <p className="text-xs text-[#475569] border border-[#D6D3C8] bg-[#FAFAF7] rounded-md p-2" data-testid="dry-run-note">
          Dry-run is on: dispatching records the message and applies every limit, but nothing leaves the system.
        </p>
      )}
      {error && (
        <div role="alert" className="text-sm text-[#991B1B] bg-[#FEF2F2] border border-[#FCA5A5] rounded-md p-3" data-testid="draft-error">
          {error}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button
          className="btn-ink"
          disabled={!canDecide || !!createHint || busy === "create"}
          onClick={() => act("create", () => prospectsApi.createDraft(prospect.id), "Draft prepared")}
          data-testid="create-draft"
        >
          <NotePencil size={14} /> PREPARE DRAFT
        </button>
        {!canDecide && <span className="mono-accent text-[#999995]">requires owner or admin</span>}
        {canDecide && createHint && <span className="text-xs text-[#5F5F5A]" data-testid="create-hint">{createHint}</span>}
      </div>

      {(!drafts || drafts.length === 0) && (
        <p className="text-sm text-[#5F5F5A]" data-testid="drafts-empty">No draft has been prepared for this prospect.</p>
      )}

      {(drafts || []).map((d) => {
        const msg = messageOf(d.id);
        return (
          <article key={d.id} className="border border-[#D6D3C8] rounded-md bg-white" data-testid="draft-item">
            <header className="flex flex-wrap items-center gap-2 p-3 border-b border-[#EDEBE0]">
              <span className="font-display font-semibold text-sm flex-1 min-w-0 truncate">{d.subject}</span>
              <span className={`chip ${DRAFT_CHIP[d.status] || "chip"}`} data-testid="draft-status">{d.status}</span>
              {d.dry_run && <span className="chip chip-ink">dry-run</span>}
              <span className="mono-accent text-[#999995]">{d.template_version}</span>
            </header>
            <div className="p-3 space-y-3">
              {d.facts.length > 0 ? (
                <div>
                  <div className="mono-accent mb-1">facts stated · each backed by a detected signal</div>
                  <ul className="list-disc ml-5 text-sm text-[#475569]">
                    {d.facts.map((f) => (
                      <li key={f}>{f}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="text-xs text-[#5F5F5A]">No signal supports a specific statement, so the draft stays neutral.</p>
              )}
              <pre className="whitespace-pre-wrap text-sm font-sans bg-[#FAFAF7] border border-[#EDEBE0] rounded-md p-3" data-testid="draft-body">
                {d.body}
              </pre>
              {msg && (
                <p className="text-sm" data-testid="draft-message">
                  <span className={`chip ${MESSAGE_STATUS_CHIP[msg.status] || "chip"} mr-2`}>{msg.status}</span>
                  Dispatched {msg.dry_run ? "(dry-run, not delivered) " : ""}on {formatDateTime(msg.dispatched_at)} ·{" "}
                  <Link to="/app/sending" className="underline">see sending</Link>
                </p>
              )}
              {canDecide && (
                <div className="flex flex-wrap gap-2">
                  {d.status === "draft" && (
                    <>
                      <button
                        className="btn-primary"
                        disabled={busy === `a-${d.id}`}
                        onClick={() => act(`a-${d.id}`, () => prospectsApi.reviewDraft(d.id, "approve"), "Draft approved")}
                        data-testid="approve-draft"
                      >
                        <Check size={14} weight="bold" /> APPROVE DRAFT
                      </button>
                      <button
                        className="btn-ghost"
                        disabled={busy === `r-${d.id}`}
                        onClick={() => act(`r-${d.id}`, () => prospectsApi.reviewDraft(d.id, "reject"), "Draft rejected")}
                        data-testid="reject-draft"
                      >
                        <X size={14} /> REJECT
                      </button>
                    </>
                  )}
                  {d.status === "approved" && !msg && (
                    <button
                      className="btn-ink"
                      disabled={busy === `d-${d.id}`}
                      onClick={() => act(`d-${d.id}`, () => outboundApi.dispatch(d.id), dryRun ? "Dispatched in dry-run" : "Dispatched")}
                      data-testid="dispatch-draft"
                    >
                      <PaperPlaneTilt size={14} weight="fill" /> DISPATCH{dryRun ? " (DRY-RUN)" : ""}
                    </button>
                  )}
                </div>
              )}
            </div>
          </article>
        );
      })}
    </div>
  );
}
