import { useState } from "react";
import { Link } from "react-router-dom";
import { ShieldCheck } from "@phosphor-icons/react";
import { approvalState, approveBlock, exclusionRows, scheduleLine, volumeLine } from "@/lib/journeyFormat";

function Row({ label, children, testId }) {
  return (
    <div className="grid gap-1 py-2 sm:grid-cols-[9rem_1fr] sm:gap-4" data-testid={testId}>
      <dt className="text-xs uppercase tracking-wider text-faint">{label}</dt>
      <dd className="text-sm min-w-0">{children}</dd>
    </div>
  );
}

// The synthesis the person approves: audience, exclusions, version of the message, volume, sender, schedule. The approval is
// bound to exactly this (the server refuses it if the message or the number changed since this screen was read).
export default function ApprovalPanel({ summary, decide, busy, onApprove }) {
  const [confirm, setConfirm] = useState(false);
  const { audience, template, volume, sender, schedule, approval } = summary;
  const state = approvalState(approval);
  const blocked = approveBlock(summary, decide);
  const exclusions = exclusionRows(audience);
  return (
    <section aria-label="Approbation" className="rounded-2xl border border-border bg-card p-4" data-testid="journey-approval">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-lg font-bold">Approbation</h2>
        <span className={`chip ${state.tone}`} data-testid="approval-state">{state.label}</span>
      </div>
      <dl className="mt-2 divide-y divide-border">
        <Row label="Audience" testId="approval-audience">
          <b>{audience.sendable}</b> établissement{audience.sendable === 1 ? "" : "s"} peu{audience.sendable === 1 ? "t" : "vent"} recevoir le message
          {audience.already_sent > 0 && <> · {audience.already_sent} déjà partis</>}
          {audience.held_back_count > 0 && <> · <span className="text-amber-300">{audience.held_back_count} retenus</span></>}
        </Row>
        {exclusions.length > 0 && (
          <Row label="Exclus" testId="approval-exclusions">
            <ul className="space-y-0.5">{exclusions.map((r) => <li key={r.code}>{r.count} · {r.label}</li>)}</ul>
          </Row>
        )}
        {audience.held_back.length > 0 && (
          <Row label="Retenus" testId="approval-held">
            <ul className="space-y-0.5 text-soft">{audience.held_back.slice(0, 5).map((h) => <li key={h.lead_id}><b>{h.name}</b> : {h.problems.join(" ; ")}</li>)}</ul>
          </Row>
        )}
        <Row label="Message" testId="approval-template">Version {template.version} · {template.subject}</Row>
        <Row label="Volume" testId="approval-volume">{volumeLine(volume)}</Row>
        <Row label="Expéditeur" testId="approval-sender">
          {sender.configured ? <>{sender.name}, {sender.company} · {sender.email} · via {sender.provider}</> : <span className="text-red-300">Identité d&apos;expéditeur non configurée</span>}
        </Row>
        <Row label="Calendrier" testId="approval-schedule">{scheduleLine(schedule)}</Row>
      </dl>
      {approval.approved && approval.expires_at && state.key === "valid" && <p className="mt-2 text-xs text-faint">L&apos;approbation expire le {new Date(approval.expires_at).toLocaleDateString("fr-FR")}.</p>}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        {!confirm ? (
          <button className="btn-primary" disabled={Boolean(blocked) || busy === "approve"} onClick={() => setConfirm(true)} data-testid="approve-open" aria-describedby={blocked ? "approve-block" : undefined}>
            <ShieldCheck size={16} /> APPROUVER LA CAMPAGNE
          </button>
        ) : (
          <div role="group" aria-label="Confirmer l'approbation" className="flex flex-wrap items-center gap-3 rounded-xl border border-brand-violet/50 bg-brand-violet/10 p-3">
            <p className="text-sm max-w-md" data-testid="approve-confirm-text">
              Vous approuvez {volume.messages} message{volume.messages === 1 ? "" : "s"} (version {template.version}), pas davantage, planifiés puis revérifiés un à un avant leur envoi.
            </p>
            <button className="btn-primary" onClick={async () => { await onApprove(template.content_hash, volume.messages); setConfirm(false); }} disabled={busy === "approve"} data-testid="approve-confirm">
              {busy === "approve" ? "APPROBATION…" : "CONFIRMER"}
            </button>
            <button className="btn-ghost" onClick={() => setConfirm(false)} data-testid="approve-cancel">ANNULER</button>
          </div>
        )}
        {blocked && <p id="approve-block" className="text-sm text-soft" data-testid="approve-block">{blocked}</p>}
        <Link to="/app/automation-max" className="text-xs underline text-faint ml-auto" data-testid="journey-to-max">Automatisation max (désactivée par défaut)</Link>
      </div>
    </section>
  );
}
