import { useState } from "react";
import { toast } from "sonner";
import { Lightning, Play, Stop } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { autopilotApi, canDecide, mapApi, useAsync } from "@/lib/outreach";
import { describeApiError } from "@/lib/outreachFormat";
import { zoneOf, zoneSummary } from "@/lib/mapSearch";
import { ACK_LABELS, frequencyLabel, missingRequirements, runSummary } from "@/lib/autopilotFormat";
import { ErrorBlock } from "@/components/outreach/States";

const FREQUENCIES = [6, 12, 24, 72, 168];

// « Pilote automatique » : what the application does by itself once an owner authorised it — search the zone when due, add
// the reachable places, approve the qualified prospects, prepare their drafts. It never sends: the active mandate does.
export default function AutopilotPanel() {
  const { user } = useAuth();
  const owner = user && user.role === "owner";
  const decide = canDecide(user);
  const state = useAsync(() => autopilotApi.get(), [], { key: "autopilot", intervalMs: 30000 });
  const lastSearch = useAsync(() => mapApi.recent(5).then((jobs) => (jobs || []).map(zoneOf).find(Boolean) || null).catch(() => null), [], { key: "autopilot:zone" });
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState(null);
  const [lastRun, setLastRun] = useState(null);
  const d = state.data;
  if (state.error && !d) return <ErrorBlock message={state.error} onRetry={state.reload} />;
  if (!d) return null;
  const missing = missingRequirements(d.requirements);
  const f = form || { zone: d.zone || lastSearch.data || null, search_every_hours: d.search_every_hours, max_approvals: d.max_approvals, drafts: d.drafts, acknowledgements: [] };
  const set = (patch) => setForm({ ...f, ...patch });
  const act = async (name, fn, done) => {
    setBusy(name);
    setError(null);
    try {
      const out = await fn();
      if (out && out.run) setLastRun(out.run);
      if (done) toast.success(done);
      setForm(null);
      state.reload();
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy("");
    }
  };
  const toggleAck = (code) => set({ acknowledgements: f.acknowledgements.includes(code) ? f.acknowledgements.filter((a) => a !== code) : [...f.acknowledgements, code] });
  return (
    <section className={`rounded-2xl border p-5 space-y-4 ${d.enabled ? "border-brand-violet/50 bg-brand-violet/10" : "border-border bg-card"}`} aria-label="Pilote automatique" data-testid="autopilot">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="eyebrow">Pilote automatique</div>
          <h2 className="mt-2 font-display text-xl font-bold" data-testid="autopilot-state">{d.enabled ? "Activé" : "Désactivé"}</h2>
          <p className="mt-1 max-w-2xl text-sm text-soft">
            Recherche la zone ({frequencyLabel(d.search_every_hours)}), ajoute les établissements joignables, approuve les prospects qualifiés
            (au plus {d.max_approvals} par passage) et prépare leurs brouillons. Il n&apos;envoie jamais rien lui-même : le mandat envoie, dans ses plafonds.
          </p>
          {d.enabled && d.zone && <p className="mt-1 text-xs text-faint" data-testid="autopilot-zone">{zoneSummary(d.zone)}</p>}
          {d.last_run_at && <p className="mt-1 text-xs text-faint">Dernier passage : {new Date(d.last_run_at).toLocaleString("fr-FR")}{d.next_search_at ? ` · prochaine recherche : ${new Date(d.next_search_at).toLocaleString("fr-FR")}` : ""}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          {d.enabled && decide && (
            <button type="button" className="btn-primary" disabled={Boolean(busy)} onClick={() => act("run", autopilotApi.run, "Passage terminé.")} data-testid="autopilot-run">
              <Play size={14} weight="fill" /> {busy === "run" ? "EN COURS…" : "LANCER MAINTENANT"}
            </button>
          )}
          {d.enabled && decide && (
            <button type="button" className="btn-ghost" disabled={Boolean(busy)} onClick={() => act("off", autopilotApi.disable, "Pilote automatique arrêté.")} data-testid="autopilot-disable">
              <Stop size={14} /> ARRÊTER
            </button>
          )}
        </div>
      </header>

      {lastRun && <p className="rounded-xl border border-border bg-card p-3 text-sm" role="status" data-testid="autopilot-last-run">{runSummary(lastRun)}</p>}

      {missing.length > 0 && (
        <div className="rounded-xl border border-amber-400/30 bg-amber-500/10 p-3 text-sm" data-testid="autopilot-missing">
          <p className="font-semibold">Pour une chaîne entièrement automatique, le serveur doit encore activer :</p>
          <ul className="mt-1 list-disc pl-5 text-soft">
            {missing.map((m) => <li key={m.key}>{m.label} : <code className="font-mono text-xs">{m.fix}</code></li>)}
          </ul>
        </div>
      )}

      {!d.enabled && owner && (
        <div className="space-y-3" data-testid="autopilot-form">
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="text-sm">Zone
              <span className="mt-1 block text-xs text-soft" data-testid="autopilot-form-zone">{f.zone ? zoneSummary(f.zone) : "Aucune : lancez d'abord une recherche sur la carte (sans zone, il approuve et prépare seulement)."}</span>
            </label>
            <label className="text-sm">Fréquence de recherche
              <select className="neo-input mt-1 w-full" value={f.search_every_hours} onChange={(e) => set({ search_every_hours: Number(e.target.value) })} data-testid="autopilot-frequency">
                {FREQUENCIES.map((h) => <option key={h} value={h}>{frequencyLabel(h)}</option>)}
              </select>
            </label>
            <label className="text-sm">Approbations par passage
              <input type="number" min={0} max={d.limits.max_approvals} className="neo-input mt-1 w-full" value={f.max_approvals} onChange={(e) => set({ max_approvals: Number(e.target.value) })} data-testid="autopilot-cap" />
            </label>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.drafts} onChange={(e) => set({ drafts: e.target.checked })} data-testid="autopilot-drafts" /> Préparer les brouillons IA (consomme des crédits)
          </label>
          <fieldset className="space-y-2">
            <legend className="text-sm font-semibold">Confirmations</legend>
            {d.acknowledgements.map((code) => (
              <label key={code} className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-1" checked={f.acknowledgements.includes(code)} onChange={() => toggleAck(code)} data-testid={`autopilot-ack-${code}`} />
                <span>{ACK_LABELS[code] || code}</span>
              </label>
            ))}
          </fieldset>
          <button type="button" className="btn-primary" disabled={Boolean(busy) || f.acknowledgements.length < d.acknowledgements.length}
            onClick={() => act("on", () => autopilotApi.enable({ zone: f.zone ? { south: f.zone.south, west: f.zone.west, north: f.zone.north, east: f.zone.east, category: f.zone.category } : null, search_every_hours: f.search_every_hours, max_approvals: f.max_approvals, drafts: f.drafts, acknowledgements: f.acknowledgements }), "Pilote automatique activé.")}
            data-testid="autopilot-enable">
            <Lightning size={14} weight="bold" /> {busy === "on" ? "ACTIVATION…" : "ACTIVER LE PILOTE AUTOMATIQUE"}
          </button>
        </div>
      )}
      {!d.enabled && !owner && <p className="text-xs text-soft">Seul un propriétaire peut activer le pilote automatique.</p>}
      {error && <p role="alert" className="text-sm text-red-300" data-testid="autopilot-error">{error}</p>}
    </section>
  );
}
