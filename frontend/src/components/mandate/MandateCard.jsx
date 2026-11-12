import { useState } from "react";
import { Pause, ShieldWarning, Stop } from "@phosphor-icons/react";
import { ACK_TEXT, activationBlock, journalLine, remainingLine, statusOf } from "@/lib/mandateFormat";
import { zoneSummary } from "@/lib/mapSearch";
import { formatDateTime } from "@/lib/outreachFormat";

// One mandate: its terms, its state, the explicit authorisation (four confirmations), pause and immediate revocation, and its journal.
export default function MandateCard({ mandate, overview, report, decide, owner, busy, onActivate, onSuspend, onRevoke, onRevalidate, onReport }) {
  const [acked, setAcked] = useState([]);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const status = statusOf(mandate.status);
  const block = activationBlock(overview, acked);
  const canActivate = ["draft", "suspended"].includes(mandate.status);
  const live = ["active", "suspended", "draft"].includes(mandate.status);
  const toggle = (code) => setAcked((list) => (list.includes(code) ? list.filter((c) => c !== code) : [...list, code]));
  const labels = overview.stop_labels || {}; // the reasons in words, from the server
  const zone = (mandate.zones || [])[0];

  return (
    <article className="rounded-2xl border border-border bg-card p-4 space-y-4" data-testid="mandate-card" aria-label={mandate.name}>
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-display text-lg font-bold">{mandate.name}</h3>
        <span className={`chip ${status.tone}`} data-testid="mandate-status">{status.label}</span>
      </header>
      <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2" data-testid="mandate-terms">
        <div><dt className="inline text-faint">Zone : </dt><dd className="inline">{zone ? zoneSummary(zone).replace("Périmètre recherché : ", "") : "—"}</dd></div>
        <div><dt className="inline text-faint">Message : </dt><dd className="inline">version {mandate.template_version}{mandate.ai_budget ? ` · budget IA ${mandate.ai_budget}` : " · sans IA"}</dd></div>
        <div><dt className="inline text-faint">Plafonds : </dt><dd className="inline">{mandate.daily_cap} par jour, {mandate.total_cap} au total</dd></div>
        <div><dt className="inline text-faint">Fenêtre : </dt><dd className="inline">{mandate.window[0]} h – {mandate.window[1]} h, {mandate.min_delay_seconds} s entre deux messages</dd></div>
        <div><dt className="inline text-faint">Expire : </dt><dd className="inline">{formatDateTime(mandate.expires_at)}</dd></div>
        <div><dt className="inline text-faint">Arrêt si : </dt><dd className="inline">rebonds &gt; {Math.round(mandate.stop_rules.max_bounce_rate * 100)} %, oppositions &gt; {Math.round(mandate.stop_rules.max_opt_out_rate * 100)} % (dès {mandate.stop_rules.min_sample} messages)</dd></div>
      </dl>
      {mandate.ended_label && <p className="text-sm text-amber-300" role="status" data-testid="mandate-ended">{mandate.ended_label}</p>}

      {canActivate && decide && (
        <fieldset className="space-y-2 rounded-xl border border-border p-3" data-testid="mandate-authorisation">
          <legend className="px-1 text-sm font-semibold"><ShieldWarning size={14} className="inline -mt-0.5" aria-hidden="true" /> Autorisation explicite</legend>
          {overview.acknowledgements.map((code) => (
            <label key={code} className="flex items-start gap-2 text-sm">
              <input type="checkbox" className="mt-1" checked={acked.includes(code)} onChange={() => toggle(code)} disabled={!owner} data-testid={`ack-${code}`} />
              <span>{ACK_TEXT[code] || code}</span>
            </label>
          ))}
          <div className="flex flex-wrap items-center gap-3 pt-1">
            <button className="btn-primary" disabled={Boolean(block) || !owner || busy === "activate"} onClick={() => onActivate(mandate.id, acked)} data-testid="mandate-activate" aria-describedby="activate-block">
              {busy === "activate" ? "ACTIVATION…" : mandate.status === "suspended" ? "REPRENDRE LE MANDAT" : "ACTIVER LE MANDAT"}
            </button>
            {(block || !owner) && <p id="activate-block" className="text-sm text-soft" data-testid="activate-block">{!owner ? "Seul un propriétaire peut donner cette autorisation." : block}</p>}
          </div>
        </fieldset>
      )}

      {decide && live && (
        <div className="flex flex-wrap items-center gap-2">
          {mandate.status === "active" && <button className="btn-ghost" onClick={() => onSuspend(mandate.id)} disabled={busy === "suspend"} data-testid="mandate-suspend"><Pause size={14} /> METTRE EN PAUSE</button>}
          {owner && mandate.status === "suspended" && <button className="btn-ghost" onClick={() => onRevalidate(mandate.id)} disabled={busy === "revalidate"} data-testid="mandate-revalidate">REVALIDER APRÈS UN CHANGEMENT</button>}
          {!confirmRevoke && <button className="btn-ghost" onClick={() => setConfirmRevoke(true)} data-testid="mandate-revoke-open"><Stop size={14} /> RÉVOQUER</button>}
          {confirmRevoke && (
            <span role="group" aria-label="Confirmer la révocation" className="flex flex-wrap items-center gap-2 rounded-xl border border-red-400/40 bg-red-500/10 px-3 py-1.5 text-sm">
              Immédiat et définitif : les envois planifiés sont annulés, ce qui est parti ne se rappelle pas.
              <button className="btn-primary" onClick={async () => { await onRevoke(mandate.id); setConfirmRevoke(false); }} disabled={busy === "revoke"} data-testid="mandate-revoke-confirm">RÉVOQUER</button>
              <button className="btn-ghost" onClick={() => setConfirmRevoke(false)}>ANNULER</button>
            </span>
          )}
        </div>
      )}

      <div>
        <button className="btn-ghost" onClick={() => onReport(mandate.id)} aria-expanded={Boolean(report)} data-testid="mandate-report-open">{report ? "ACTUALISER LE RAPPORT" : "VOIR LE RAPPORT ET LE JOURNAL"}</button>
        {report && (
          <div className="mt-3 space-y-2 text-sm" data-testid="mandate-report">
            <p>{report.last_24h ? `Dernières 24 h : ${report.last_24h.sent} envoyé${report.last_24h.sent === 1 ? "" : "s"}.` : ""} {report.total ? `Au total : ${report.total.sent}.` : ""} {remainingLine(report)}</p>
            <p className="text-xs text-faint">{report.note}</p>
            <ol className="space-y-1 text-xs text-soft" aria-label="Journal du mandat" data-testid="mandate-journal">
              {(report.journal || []).map((e, i) => <li key={`${e.at}-${i}`}>{journalLine(e, labels)}</li>)}
            </ol>
          </div>
        )}
      </div>
    </article>
  );
}
