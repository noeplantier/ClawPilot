import { useState } from "react";
import { toast } from "sonner";
import StateChip from "@/components/outreach/StateChip";
import { prospectsApi } from "@/lib/outreach";
import { describeApiError, formatDateTime } from "@/lib/outreachFormat";

export const MIN_REASON = 5;

function DismissBox({ signal, prospectId, onChanged }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const ok = reason.trim().length >= MIN_REASON;
  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      await prospectsApi.dismissSignal(prospectId, signal.key, reason.trim());
      toast.success("Signal dismissed: it now counts as unknown and the score was recomputed");
      setOpen(false);
      setReason("");
      onChanged();
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy(false);
    }
  };
  if (!open) return <button className="btn-ghost mt-2" onClick={() => setOpen(true)} data-testid={`dismiss-${signal.key}`}>THIS IS WRONG</button>;
  return (
    <div className="mt-2 space-y-2" data-testid={`dismiss-box-${signal.key}`}>
      <label className="block text-xs text-[#5F5F5A]">Why is it wrong? (kept with the decision, at least {MIN_REASON} characters)
        <input className="neo-input w-full mt-1" value={reason} onChange={(e) => setReason(e.target.value)} data-testid={`dismiss-reason-${signal.key}`} />
      </label>
      {error && <div role="alert" className="text-xs text-[#991B1B]">{error}</div>}
      <div className="flex gap-2">
        <button className="btn-ink" disabled={busy || !ok} onClick={send} data-testid={`dismiss-confirm-${signal.key}`}>{busy ? "…" : "DISMISS SIGNAL"}</button>
        <button className="btn-ghost" onClick={() => setOpen(false)}>CANCEL</button>
      </div>
    </div>
  );
}

function RestoreButton({ signal, prospectId, onChanged }) {
  const [busy, setBusy] = useState(false);
  const restore = async () => {
    setBusy(true);
    try {
      await prospectsApi.restoreSignal(prospectId, signal.key);
      toast.success("Signal restored");
      onChanged();
    } catch (e) {
      toast.error(describeApiError(e));
    } finally {
      setBusy(false);
    }
  };
  return <button className="btn-ghost mt-2" disabled={busy} onClick={restore} data-testid={`restore-${signal.key}`}>RESTORE</button>;
}

export default function SignalList({ signals, prospectId, canReview = false, onChanged = () => {} }) {
  if (!signals || signals.length === 0) {
    return <p className="text-sm text-[#5F5F5A]">No signal has been recorded for this prospect.</p>;
  }
  return (
    <ul className="grid md:grid-cols-2 gap-3" data-testid="signal-list">
      {signals.map((s) => (
        <li key={s.key} className="border border-[#D6D3C8] rounded-md p-3 bg-white" data-testid={`signal-${s.key}`}>
          <div className="flex items-center justify-between gap-2">
            <span className="font-display font-semibold text-sm">{s.label}</span>
            <StateChip state={s.state} />
          </div>
          <p className="text-sm text-[#475569] mt-2">{s.evidence}</p>
          {s.dismissed && (
            <p className="text-sm mt-2 text-[#92400E]" data-testid={`dismissed-${s.key}`}>
              Dismissed by a reviewer ({s.dismissed_reason || "no reason given"}). Observed: {s.observed_state}. Counts as unknown.
            </p>
          )}
          <p className="mono-accent text-[#6B6B66] mt-2">observed {formatDateTime(s.observed_at)}</p>
          {canReview && prospectId && s.dismissed && <RestoreButton signal={s} prospectId={prospectId} onChanged={onChanged} />}
          {canReview && prospectId && !s.dismissed && s.state !== "unknown" && <DismissBox signal={s} prospectId={prospectId} onChanged={onChanged} />}
        </li>
      ))}
    </ul>
  );
}
