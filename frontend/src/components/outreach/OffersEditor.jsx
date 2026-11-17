import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Megaphone } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, offersApi, useAsync } from "@/lib/outreach";
import { describeApiError } from "@/lib/outreachFormat";
import { OFFER_LIMITS, isComplete, offersBody } from "@/lib/offersFormat";
import { ErrorBlock } from "@/components/outreach/States";

const EMPTY = { name: "", pitch: "", cta: "" };

// The three offers (refonte/maintenance, création, SEO/GEO), in the organisation's own words. Each automatic draft uses the
// offer that matches what is KNOWN of the prospect's site (the server decides, and says who receives each offer here).
// `onSaved(data)` lets the batch dispatch reuse the fresh answer; nothing is sent from here.
export default function OffersEditor({ onSaved, compact = false }) {
  const { user } = useAuth();
  const decide = canDecide(user);
  const state = useAsync(() => offersApi.get(), [], { key: "settings:offers" });
  const [forms, setForms] = useState({});
  const [defaultKind, setDefaultKind] = useState("seo_geo");
  const [language, setLanguage] = useState("fr");
  const [tab, setTab] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const d = state.data;
  useEffect(() => {
    if (!d) return;
    setForms(Object.fromEntries(d.cases.map((c) => [c.kind, c.offer ? { ...c.offer } : { ...EMPTY }])));
    if (d.default && d.default !== "single") setDefaultKind(d.default);
    setLanguage(d.language || "fr");
    setTab((t) => t || d.cases[0].kind);
  }, [d]);
  if (state.error && !d) return <ErrorBlock message={state.error} onRetry={state.reload} />;
  if (!d || !tab) return null;
  const current = d.cases.find((c) => c.kind === tab);
  const form = forms[tab] || EMPTY;
  const set = (key) => (e) => setForms((f) => ({ ...f, [tab]: { ...(f[tab] || EMPTY), [key]: e.target.value } }));
  const save = async (e) => {
    e.preventDefault();
    const out = offersBody(forms, defaultKind, language);
    if (!out.ok) { setError(out.error); return; }
    setBusy(true);
    setError(null);
    try {
      const saved = await offersApi.put(out.body);
      toast.success("Offres enregistrées : les brouillons concernés sont préparés à nouveau en arrière-plan. Rien n'est envoyé.");
      state.reload();
      if (onSaved) onSaved(saved);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className={compact ? "space-y-3" : "surface p-6 space-y-4"} data-testid="offers-editor" aria-label="Offres">
      {!compact && (
        <div className="flex items-center gap-2">
          <Megaphone size={18} className="text-brand-lilac" aria-hidden="true" />
          <h2 className="font-display text-xl font-bold">Vos trois offres</h2>
          <span className={`chip ${d.configured ? "chip-success" : "chip-warn"}`}>{d.configured ? "PRÊTES" : "À REMPLIR"}</span>
        </div>
      )}
      <div className="flex flex-wrap gap-1" role="tablist" aria-label="Offres">
        {d.cases.map((c) => (
          <button key={c.kind} type="button" role="tab" aria-selected={tab === c.kind} onClick={() => setTab(c.kind)} data-testid={`offers-tab-${c.kind}`}
            className={`px-3 py-1.5 rounded-md text-sm border font-display ${tab === c.kind ? "bg-brand-violet text-white border-white/20" : "bg-card text-soft border-border hover:border-white/20"}`}>
            {c.label.split(" de site")[0].split(" et présence")[0]}{isComplete(forms[c.kind]) ? " ✓" : ""}
          </button>
        ))}
      </div>
      <p className="text-sm text-soft" data-testid="offers-when"><strong>{current.label}.</strong> {current.when}</p>
      <form onSubmit={save} className="grid gap-3 md:grid-cols-2">
        <label className="text-sm">Nom de l&apos;offre<input className="neo-input w-full" value={form.name} onChange={set("name")} disabled={!decide} maxLength={OFFER_LIMITS.name[1]} data-testid="offers-name" /></label>
        <label className="text-sm">Langue<select className="neo-input w-full" value={language} onChange={(e) => setLanguage(e.target.value)} disabled={!decide}><option value="fr">Français</option><option value="en">English</option></select></label>
        <label className="text-sm md:col-span-2">Ce qu&apos;elle apporte au client (vos mots, sans chiffre inventé)<textarea className="neo-input w-full min-h-[5rem]" value={form.pitch} onChange={set("pitch")} disabled={!decide} maxLength={OFFER_LIMITS.pitch[1]} data-testid="offers-pitch" /></label>
        <label className="text-sm md:col-span-2">La prochaine étape demandée<input className="neo-input w-full" value={form.cta} onChange={set("cta")} disabled={!decide} maxLength={OFFER_LIMITS.cta[1]} data-testid="offers-cta" /></label>
        <label className="flex items-center gap-2 text-sm md:col-span-2">
          <input type="radio" name="offers-default" checked={defaultKind === tab} onChange={() => setDefaultKind(tab)} disabled={!decide} data-testid="offers-default" />
          Offre par défaut : aussi pour les prospects dont l&apos;état du site est inconnu
        </label>
        <div className="md:col-span-2 flex flex-wrap items-center gap-3">
          <button className="btn-primary" disabled={!decide || busy} data-testid="offers-save">{busy ? "ENREGISTREMENT…" : "ENREGISTRER LES OFFRES"}</button>
          {!decide && <span className="text-xs text-faint">Réservé au propriétaire ou à un administrateur.</span>}
          {error && <span role="alert" className="text-sm text-red-300" data-testid="offers-error">{error}</span>}
        </div>
      </form>
    </section>
  );
}
