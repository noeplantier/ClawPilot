import { useMemo, useState } from "react";
import { formDefaults, toPayload, validateForm } from "@/lib/mandateFormat";

const FIELD = "neo-input w-full";

function Num({ form, set, errors, name, label, hint, min, max, step = 1 }) {
  return (
    <label className="block text-sm">
      <span className="text-soft">{label}</span>
      <input className={FIELD} type="number" inputMode="decimal" min={min} max={max} step={step} value={form[name]} onChange={(e) => set(name, e.target.value)} aria-invalid={Boolean(errors[name])} aria-describedby={errors[name] ? `err-${name}` : undefined} data-testid={`mandate-${name}`} />
      {hint && <span className="text-xs text-faint">{hint}</span>}
      {errors[name] && <span id={`err-${name}`} className="block text-xs text-red-300" role="alert">{errors[name]}</span>}
    </label>
  );
}

// The bounds of ONE mandate: everything the automatic mode may do is written here, and nothing else.
export default function MandateForm({ limits, journeys, busy, onCreate }) {
  const [campaignId, setCampaignId] = useState(journeys[0] ? journeys[0].id : "");
  const campaign = journeys.find((j) => j.id === campaignId);
  const [form, setForm] = useState(() => formDefaults(limits, journeys[0]));
  const [shown, setShown] = useState(false);
  const errors = useMemo(() => validateForm(form, limits), [form, limits]);
  const set = (name, value) => setForm((f) => ({ ...f, [name]: value }));
  const invalid = Object.keys(errors).length > 0 || !campaign;

  if (journeys.length === 0) {
    return <p className="text-sm text-soft" data-testid="mandate-no-journey">Un mandat s&apos;appuie sur une campagne par zone : créez-en une d&apos;abord (carte, « Continuer vers la campagne »).</p>;
  }
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); setShown(true); if (!invalid) onCreate(toPayload(form, campaignId)); }} data-testid="mandate-form" noValidate>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="block text-sm">
          <span className="text-soft">Campagne (zone, message, expéditeur)</span>
          <select className={FIELD} value={campaignId} onChange={(e) => { setCampaignId(e.target.value); set("name", `Mandat · ${(journeys.find((j) => j.id === e.target.value) || {}).name}`.slice(0, 120)); }} data-testid="mandate-campaign">
            {journeys.map((j) => <option key={j.id} value={j.id}>{j.name}</option>)}
          </select>
        </label>
        <label className="block text-sm">
          <span className="text-soft">Nom du mandat</span>
          <input className={FIELD} value={form.name} onChange={(e) => set("name", e.target.value)} minLength={2} maxLength={120} data-testid="mandate-name" />
        </label>
        <Num form={form} set={set} errors={errors} name="daily_cap" label="Plafond par jour" min={1} max={limits.max_daily} />
        <Num form={form} set={set} errors={errors} name="total_cap" label="Plafond total de messages" min={1} max={limits.max_total} />
        <Num form={form} set={set} errors={errors} name="days" label="Durée (jours), puis le mandat expire" min={1} max={limits.max_days} />
        <Num form={form} set={set} errors={errors} name="min_delay_seconds" label="Délai minimal entre deux messages (s)" min={limits.min_delay_seconds} max={3600} />
        <Num form={form} set={set} errors={errors} name="window_start_hour" label="Début de la fenêtre d'envoi (h)" min={0} max={23} />
        <Num form={form} set={set} errors={errors} name="window_end_hour" label="Fin de la fenêtre d'envoi (h)" min={1} max={24} />
        <Num form={form} set={set} errors={errors} name="search_every_hours" label="Fréquence de recherche (h)" hint="Le mandat ne cherche pas lui-même de nouveaux établissements : il traite ceux de la zone." min={limits.min_search_hours} max={168} />
        <Num form={form} set={set} errors={errors} name="ai_budget" label="Budget IA (générations)" hint="0 = aucune : le message est le modèle approuvé, rendu sans IA." min={0} max={1000} />
        <Num form={form} set={set} errors={errors} name="max_bounce_rate" label="Arrêt si les rebonds dépassent" hint="Part des messages, de 0,01 à 0,10." min={0.01} max={0.1} step={0.01} />
        <Num form={form} set={set} errors={errors} name="max_opt_out_rate" label="Arrêt si les oppositions dépassent" hint="Part des messages, de 0,01 à 0,20." min={0.01} max={0.2} step={0.01} />
      </div>
      <p className="text-xs text-faint">Arrêts fixes, non désactivables : arrêt d&apos;urgence, erreur d&apos;authentification, réponses non lues, changement du message, de la zone, de l&apos;offre, de l&apos;expéditeur ou du fournisseur, expiration, plafond total.</p>
      {shown && invalid && <p role="alert" className="text-sm text-red-300" data-testid="mandate-form-invalid">Corrigez les champs signalés avant de créer le mandat.</p>}
      <button className="btn-ink" disabled={busy === "create"} data-testid="mandate-create">{busy === "create" ? "CRÉATION…" : "CRÉER LE MANDAT (SANS L'ACTIVER)"}</button>
    </form>
  );
}
