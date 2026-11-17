import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { describeApiError } from "@/lib/outreachFormat";
import { offersApi } from "@/lib/outreach";
import { usableOffers } from "@/lib/offersFormat";
import { sendErrorText } from "@/lib/campaignLaunch";
import { Sparkle, X, Copy, Translate, ArrowClockwise, Stack, Check, PaperPlaneTilt } from "@phosphor-icons/react";

const LANGUAGES = [
  { v: "fr", l: "Français" }, { v: "en", l: "English" }, { v: "es", l: "Español" },
  { v: "de", l: "Deutsch" }, { v: "it", l: "Italiano" }, { v: "pt", l: "Português" },
];
const TONES = [
  { v: "professional", l: "professionnel" }, { v: "friendly", l: "chaleureux" }, { v: "casual", l: "décontracté" },
  { v: "urgent", l: "urgent" }, { v: "concise", l: "concis" },
];
const VARIANT_TONES = ["professional", "friendly", "urgent"];

// What the AI receives about the offer: the organisation's own words, never an invented product.
export const offerFields = (c) => (c && c.offer ? { offer: c.kind, product: `${c.offer.name} : ${c.offer.pitch}`, goal: c.offer.cta } : {});

// Composer IA : écrit un message à partir de votre offre. Ouvert depuis un lead (defaults.lead = { id, email }), il l'envoie à ce
// seul destinataire par POST /messages/email, après confirmation : consentement, limites, arrêt d'urgence et pied de conformité
// sont appliqués par le serveur. Sans lead, il ne fait que proposer un texte à copier.
export default function AIComposerModal({ open, onClose, defaults }) {
  const lead = defaults?.lead && defaults.lead.id && defaults.lead.email ? defaults.lead : null;
  const [form, setForm] = useState({ recipient_name: "", company: "", product: "", goal: "", offer: "", language: "fr", tone: "professional", channel: "email" });
  const [offers, setOffers] = useState([]);
  const [result, setResult] = useState(null);
  const [variants, setVariants] = useState(null);
  const [loading, setLoading] = useState(false);
  const [variantsLoading, setVariantsLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(null);

  useEffect(() => {
    if (!open) { setResult(null); setVariants(null); setConfirming(false); setSent(null); return; }
    const rest = { ...(defaults || {}) };
    delete rest.lead; // the lead's e-mail stays here: it is never part of what the AI receives
    setForm((f) => ({ ...f, ...rest, language: rest.language || "fr" }));
    let alive = true;
    offersApi.get().then((data) => {
      if (!alive) return;
      const list = usableOffers(data);
      setOffers(list);
      const chosen = list.find((c) => c.kind === (rest.offer || data.default)) || list[0];
      if (chosen) setForm((f) => (f.product ? f : { ...f, ...offerFields(chosen) }));
    }).catch(() => { if (alive) setOffers([]); });
    return () => { alive = false; };
  }, [open, defaults]);

  const update = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const pickOffer = (kind) => setForm({ ...form, ...offerFields(offers.find((c) => c.kind === kind)) });

  const ready = () => {
    if (!form.recipient_name || !form.product) {
      toast.error("Le destinataire et l'offre sont nécessaires : décrivez vos offres dans Outreach › Offres.");
      return false;
    }
    return true;
  };
  const body = () => {
    const rest = { ...form };
    delete rest.offer;
    return rest;
  };

  const generate = async () => {
    if (!ready()) return;
    setLoading(true);
    setVariants(null);
    setConfirming(false);
    try {
      const { data } = await api.post("/ai/generate", body());
      setResult(data);
    } catch (err) {
      toast.error(describeApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const genVariants = async () => {
    if (!ready()) return;
    setVariantsLoading(true);
    setResult(null);
    setConfirming(false);
    try {
      const { data } = await api.post("/ai/generate/variants", body());
      setVariants(data.variants);
    } catch (err) {
      toast.error(describeApiError(err));
    } finally {
      setVariantsLoading(false);
    }
  };

  const pickVariant = (v) => { setResult(v); setVariants(null); };

  const copy = () => {
    const text = (result?.subject ? `Objet : ${result.subject}\n\n` : "") + (result?.body || "");
    navigator.clipboard.writeText(text);
    toast.success("Copié dans le presse-papiers");
  };

  const send = async () => {
    setSending(true);
    try {
      const { data } = await api.post("/messages/email", { to: lead.email, subject: result.subject || "", body: result.body, lead_id: lead.id });
      const status = data?.result?.status;
      if (status === "sent") {
        setSent(`Accepté par le fournisseur pour ${lead.email}. La livraison et les réponses arrivent ensuite dans la boîte de réception.`);
        toast.success("Message accepté par le fournisseur.");
      } else {
        toast.error(data?.result?.error || `Non envoyé (${status || "statut inconnu"}).`);
      }
    } catch (err) {
      toast.error(sendErrorText(err, "Le message n'a pas pu être envoyé."));
    } finally {
      setSending(false);
      setConfirming(false);
    }
  };

  const canSend = lead && result && form.channel === "email" && (result.body || "").trim() && (result.subject || "").trim();

  return (
    <AnimatePresence>
      {open && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-start sm:items-center justify-center p-4 overflow-y-auto" onClick={onClose}>
          <motion.div initial={{ opacity: 0, y: 20, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10 }}
            onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="ai-composer-title"
            className={`relative w-full max-w-4xl surface p-5 md:p-8 max-h-[92vh] overflow-y-auto ${loading ? "glow-purple" : ""}`}
            data-testid="ai-composer-modal">
            <button onClick={onClose} className="absolute top-4 right-4 text-soft hover:text-brand-lilac" aria-label="Fermer" data-testid="close-ai-composer"><X size={20} /></button>

            <div className="flex items-center gap-2 mb-2"><Sparkle size={18} weight="fill" className="text-foreground" /><span className="mono-accent text-foreground">composer IA</span></div>
            <h2 id="ai-composer-title" className="text-2xl font-black tracking-tighter">{lead ? `Message pour ${form.company || form.recipient_name}` : "Composer IA"}</h2>
            <p className="text-soft text-sm mt-1">
              Écrit à partir de votre offre ; le nom, l&apos;entreprise, l&apos;offre et l&apos;objectif partent au fournisseur IA, jamais l&apos;e-mail ni le téléphone.
            </p>

            <div className="grid md:grid-cols-2 gap-6 mt-6">
              <div className="space-y-3">
                {offers.length > 0 ? (
                  <label className="block text-sm">
                    <span className="mono-accent block mb-1.5">Offre</span>
                    <select className="neo-input" value={form.offer || ""} onChange={(e) => pickOffer(e.target.value)} data-testid="ai-offer-select">
                      {!form.offer && <option value="">Choisir une offre</option>}
                      {offers.map((c) => <option key={c.kind} value={c.kind}>{c.label} · {c.offer.name}</option>)}
                    </select>
                  </label>
                ) : (
                  <p className="text-xs text-soft" data-testid="ai-no-offer">Aucune offre complète : <Link to="/app/settings/offer" className="underline text-brand-lilac" onClick={onClose}>décrivez vos offres</Link> pour que l&apos;IA parle de ce que vous vendez.</p>
                )}
                <label className="block text-sm">
                  <span className="mono-accent block mb-1.5">Destinataire</span>
                  <input className="neo-input" value={form.recipient_name} onChange={update("recipient_name")} placeholder="Prénom Nom" data-testid="ai-recipient-input" />
                </label>
                <label className="block text-sm">
                  <span className="mono-accent block mb-1.5">Entreprise</span>
                  <input className="neo-input" value={form.company} onChange={update("company")} placeholder="Nom de l'entreprise" data-testid="ai-company-input" />
                </label>
                <label className="block text-sm">
                  <span className="mono-accent block mb-1.5">Ce que vous proposez</span>
                  <textarea rows={3} className="neo-input" value={form.product} onChange={update("product")} placeholder="Votre offre, dans vos mots" data-testid="ai-product-input" />
                </label>
                <label className="block text-sm">
                  <span className="mono-accent block mb-1.5">Objectif</span>
                  <input className="neo-input" value={form.goal} onChange={update("goal")} placeholder="La prochaine étape que vous proposez" data-testid="ai-goal-input" />
                </label>
                <div className="grid grid-cols-3 gap-3">
                  <label className="block text-sm">
                    <span className="mono-accent block mb-1.5">Canal</span>
                    <select className="neo-input" value={form.channel} onChange={update("channel")} data-testid="ai-channel-select">
                      <option value="email">email</option>
                      <option value="whatsapp">whatsapp</option>
                    </select>
                  </label>
                  <label className="block text-sm">
                    <span className="mono-accent block mb-1.5">Ton</span>
                    <select className="neo-input" value={form.tone} onChange={update("tone")} data-testid="ai-tone-select">
                      {TONES.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
                    </select>
                  </label>
                  <label className="block text-sm">
                    <span className="mono-accent block mb-1.5">Langue</span>
                    <select className="neo-input" value={form.language} onChange={update("language")} data-testid="ai-language-select">
                      {LANGUAGES.map((l) => <option key={l.v} value={l.v}>{l.l}</option>)}
                    </select>
                  </label>
                </div>
                <button onClick={generate} disabled={loading || variantsLoading} className="btn-primary w-full justify-center mt-2" data-testid="ai-generate-button">
                  {loading ? <><ArrowClockwise size={16} className="spin-slow" /> RÉDACTION…</> : <><Sparkle size={16} weight="fill" /> RÉDIGER LE MESSAGE</>}
                </button>
                <button onClick={genVariants} disabled={loading || variantsLoading} className="btn-ink w-full justify-center" data-testid="ai-variants-button">
                  {variantsLoading ? <><ArrowClockwise size={16} className="spin-slow" /> RÉDACTION DE 3 VERSIONS…</> : <><Stack size={16} weight="fill" /> 3 VERSIONS</>}
                </button>
              </div>

              <div className="surface bg-white/[0.04] p-5 min-h-[300px] relative">
                <div className="flex items-center justify-between mb-3">
                  <span className="mono-accent">Message</span>
                  {result && <button onClick={copy} className="chip chip-cyan hover:border-brand-violet" data-testid="ai-copy-button"><Copy size={12} /> COPIER</button>}
                </div>
                {!result && !loading && !variants && !variantsLoading && (
                  <div className="flex flex-col items-center justify-center text-center text-faint py-16">
                    <Translate size={48} weight="duotone" className="text-faint mb-3" />
                    <p className="text-xs mt-2 max-w-[240px]">Choisissez l&apos;offre puis « Rédiger le message », ou demandez 3 versions.</p>
                  </div>
                )}
                {(loading || variantsLoading) && <div className="flex items-center justify-center py-16 text-brand-lilac"><ArrowClockwise size={32} className="spin-slow" /></div>}

                {variants && (
                  <div className="space-y-3">
                    {VARIANT_TONES.map((tone, i) => {
                      const v = variants[i];
                      if (!v) return null;
                      return (
                        <button key={tone} type="button" className="surface p-3 w-full text-left hover:border-brand-violet/40 transition" onClick={() => pickVariant(v)} data-testid={`variant-${tone}`}>
                          <div className="flex items-center justify-between mb-2">
                            <span className="chip">{TONES.find((t) => t.v === tone)?.l}</span>
                            <span className="btn-primary !py-1 !px-2 text-xs"><Check size={10} /> PRENDRE</span>
                          </div>
                          {v.subject && <div className="text-sm font-semibold text-foreground mb-1">{v.subject}</div>}
                          <div className="text-xs text-soft whitespace-pre-wrap line-clamp-4">{v.body}</div>
                        </button>
                      );
                    })}
                  </div>
                )}

                {result && (
                  <div className="space-y-3 text-sm">
                    {form.channel === "email" && (
                      <label className="block">
                        <span className="mono-accent text-soft block mb-1">Objet</span>
                        <input className="neo-input" value={result.subject || ""} onChange={(e) => setResult({ ...result, subject: e.target.value })} data-testid="ai-result-subject" />
                      </label>
                    )}
                    <label className="block">
                      <span className="mono-accent text-soft block mb-1">Message</span>
                      <textarea rows={10} className="neo-input font-sans" value={result.body || ""} onChange={(e) => setResult({ ...result, body: e.target.value })} data-testid="ai-result-body" />
                    </label>
                    <p className="text-xs text-faint">Le serveur ajoute le pied obligatoire (votre identité, l&apos;origine des données, le lien de désinscription).</p>

                    {lead && form.channel === "email" && !sent && !confirming && (
                      <button className="btn-primary w-full justify-center" disabled={!canSend} onClick={() => setConfirming(true)} data-testid="ai-send">
                        <PaperPlaneTilt size={14} weight="fill" /> ENVOYER À {lead.email}
                      </button>
                    )}
                    {confirming && (
                      <div className="rounded-xl border border-border p-4 space-y-3" role="alertdialog" aria-label="Confirmer l'envoi" data-testid="ai-send-confirm">
                        <ul className="list-disc pl-5 space-y-1 text-xs text-soft">
                          <li>Un seul destinataire : <b className="text-foreground">{lead.email}</b>, sans copie.</li>
                          <li>L&apos;objet et le message ci-dessus, tels quels, avec le pied de conformité ajouté par le serveur.</li>
                          <li>Le serveur revérifie au moment de l&apos;envoi : désinscription, limites, pause et arrêt d&apos;urgence. Un refus est affiché avec sa raison.</li>
                        </ul>
                        <div className="flex flex-wrap gap-2">
                          <button className="btn-primary" disabled={sending} onClick={send} data-testid="ai-send-go"><PaperPlaneTilt size={14} weight="fill" /> {sending ? "ENVOI…" : "ENVOYER"}</button>
                          <button className="btn-ghost" disabled={sending} onClick={() => setConfirming(false)} data-testid="ai-send-cancel">ANNULER</button>
                        </div>
                      </div>
                    )}
                    {sent && <p className="text-sm text-brand-lilac" role="status" data-testid="ai-sent">{sent}</p>}
                    <div className="pt-3 border-t border-border flex items-center justify-between text-xs">
                      <span className="chip">{result.language || form.language}</span>
                      <span className="text-faint">{(result.body || "").length} caractères</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
