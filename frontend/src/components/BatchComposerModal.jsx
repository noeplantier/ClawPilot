import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { blockText, describeApiError } from "@/lib/outreachFormat";
import { Link } from "react-router-dom";
import { offersApi, useAsync } from "@/lib/outreach";
import { prefillFromOffer, usableOffers } from "@/lib/offersFormat";
import OffersEditor from "@/components/outreach/OffersEditor";
import {
  X, PaperPlaneTilt, Sparkle, Envelope, WhatsappLogo, CheckCircle, Warning, CircleNotch, Users,
} from "@phosphor-icons/react";

const TOKEN_HINTS = ["{{first_name}}", "{{full_name}}", "{{company}}", "{{title}}", "{{country}}"];

export default function BatchComposerModal({ open, onClose, defaultChannel = "email" }) {
  const [channel, setChannel] = useState(defaultChannel);
  const [leads, setLeads] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [search, setSearch] = useState("");
  // No invented sentence: the message starts from the chosen offer's own words (step 1), or from what the person writes.
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const offers = useAsync(() => (open ? offersApi.get() : Promise.resolve(null)), [open], { key: "settings:offers" });
  const [offerKind, setOfferKind] = useState(null);
  const [editOffers, setEditOffers] = useState(false);
  const usable = usableOffers(offers.data);
  const chosenOffer = usable.find((c) => c.kind === offerKind) || null;
  const pickOffer = (c) => {
    setOfferKind(c.kind);
    const t = prefillFromOffer(c.offer, offers.data ? offers.data.language : "fr");
    if (t) { setSubject(t.subject); setBody(t.body); }
  };
  const [loading, setLoading] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (open) {
      api.get("/leads", { params: { limit: 500 } }).then((r) => setLeads(r.data));
      setResult(null);
      setSelected(new Set());
      setChannel(defaultChannel);
    }
  }, [open, defaultChannel]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return leads.filter((l) => {
      if (channel === "email" && !l.email) return false;
      if (channel === "whatsapp" && !l.phone) return false;
      if (!q) return true;
      return (
        (l.full_name || "").toLowerCase().includes(q) ||
        (l.company || "").toLowerCase().includes(q) ||
        (l.email || "").toLowerCase().includes(q)
      );
    });
  }, [leads, search, channel]);

  const toggleOne = (id) => {
    setSelected((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    setSelected((s) => (s.size === filtered.length ? new Set() : new Set(filtered.map((l) => l.id))));
  };

  const aiWrite = async () => {
    if (!leads.length) return;
    if (!chosenOffer) { toast.error("Choisissez d'abord l'offre de ce lot (étape 1)."); return; }
    setAiLoading(true);
    try {
      // Use first selected (or first filtered) as personalization basis
      const sample = leads.find((l) => selected.has(l.id)) || filtered[0];
      const { data } = await api.post("/ai/generate", {
        recipient_name: sample?.full_name || "there",
        company: sample?.company || "",
        product: chosenOffer ? `${chosenOffer.offer.name} : ${chosenOffer.offer.pitch}` : "",
        language: sample?.language || "en",
        tone: "professional",
        channel,
        goal: chosenOffer ? chosenOffer.offer.cta : "",
      });
      if (data.subject && channel === "email") setSubject(data.subject);
      // Replace name with token for reusability
      const tokenized = (data.body || "").replace(new RegExp(sample?.full_name?.split(" ")?.[0] || "", "g"), "{{first_name}}");
      setBody(tokenized.replace(new RegExp(sample?.company || "###", "g"), "{{company}}"));
      toast.success("AI draft ready — tokens inserted");
    } catch (e) {
      toast.error(describeApiError(e));
    } finally {
      setAiLoading(false);
    }
  };

  const dispatch = async () => {
    if (selected.size === 0) {
      toast.error("Select at least one lead");
      return;
    }
    if (!body) {
      toast.error("Body is required");
      return;
    }
    if (channel === "email" && !subject) {
      toast.error("Subject is required for email");
      return;
    }
    setLoading(true);
    try {
      const path = channel === "email" ? "/messages/email/batch" : "/messages/whatsapp/batch";
      const { data } = await api.post(path, {
        lead_ids: Array.from(selected),
        subject: channel === "email" ? subject : undefined,
        body,
      });
      setResult(data);
      if (data.sent > 0) toast.success(`${data.sent} sent${data.failed ? `, ${data.failed} failed` : ""}${data.skipped ? `, ${data.skipped} skipped` : ""}`);
      else toast.error(data.blocked ? blockText(data.blocked.code) || data.blocked.message : "Nothing was sent. See the details below.");
    } catch (e) {
      toast.error(describeApiError(e));
    } finally {
      setLoading(false);
    }
  };

  const previewLead = leads.find((l) => selected.has(l.id)) || filtered[0];
  const renderPreview = (t) => {
    if (!t || !previewLead) return t;
    const first = (previewLead.full_name || "").split(" ")[0] || "there";
    return t
      .replace(/\{\{first_name\}\}/g, first)
      .replace(/\{\{full_name\}\}/g, previewLead.full_name || "")
      .replace(/\{\{company\}\}/g, previewLead.company || "")
      .replace(/\{\{title\}\}/g, previewLead.title || "")
      .replace(/\{\{country\}\}/g, previewLead.country || "");
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ y: 12 }} animate={{ y: 0 }}
            className="surface w-full max-w-5xl p-6 md:p-8 relative max-h-[94vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
            data-testid="batch-composer-modal"
          >
            <button onClick={onClose} className="absolute top-4 right-4 text-soft hover:text-brand-lilac" data-testid="close-batch-composer">
              <X size={20} />
            </button>

            <div className="mono-accent">/// batch.dispatch</div>
            <h2 className="text-2xl font-black tracking-tighter mt-1 flex items-center gap-2">
              {channel === "email" ? <Envelope size={22} weight="duotone" className="text-brand-lilac" /> : <WhatsappLogo size={22} weight="fill" className="text-brand-lilac" />}
              Batch {channel === "email" ? "Email" : "WhatsApp"} Dispatch
            </h2>
            <p className="text-soft text-sm mt-1">Un message par destinataire, avec les portes, limites et oppositions habituelles.</p>

            {/* 1 · the offer of this batch: its own words fill the message, nothing is said about the prospect */}
            <section className="mt-4 rounded-xl border border-border bg-white/[0.03] p-4 space-y-3" aria-label="Offre de ce lot" data-testid="batch-offer">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="eyebrow">1 · Offre de ce lot</h3>
                <button type="button" className="btn-ghost !py-1 !px-2 text-xs" onClick={() => setEditOffers((v) => !v)} aria-expanded={editOffers} data-testid="batch-edit-offers">
                  {editOffers ? "FERMER" : "MODIFIER LES OFFRES"}
                </button>
              </div>
              {usable.length === 0 && !offers.loading && (
                <p className="text-sm text-soft" data-testid="batch-offer-none">Aucune offre complète : remplissez-en une (« Modifier les offres »), ou écrivez votre message vous-même à l&apos;étape 3.</p>
              )}
              {usable.length > 0 && (
                <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Offre">
                  {usable.map((c) => (
                    <button key={c.kind} type="button" role="radio" aria-checked={offerKind === c.kind} onClick={() => pickOffer(c)} data-testid={`batch-offer-${c.kind}`}
                      className={`rounded-xl border px-3 py-1.5 text-left text-sm ${offerKind === c.kind ? "border-brand-violet bg-brand-violet/15" : "border-border hover:border-white/20"}`}>
                      <span className="block font-semibold">{c.offer.name}</span>
                      <span className="block text-[11px] text-soft">{c.when}</span>
                    </button>
                  ))}
                </div>
              )}
              <p className="text-xs text-soft">
                Pour un message personnalisé par prospect, avec l&apos;offre choisie selon l&apos;état connu de son site : <Link to="/app/drafts" className="underline">Brouillons IA</Link>.
              </p>
              {editOffers && <OffersEditor compact onSaved={() => offers.reload()} />}
            </section>

            <div className="flex items-center gap-2 mt-4">
              <button onClick={() => setChannel("email")} className={`chip ${channel === "email" ? "chip-red" : ""}`} data-testid="batch-channel-email">
                <Envelope size={11} /> email
              </button>
              <button onClick={() => setChannel("whatsapp")} className={`chip ${channel === "whatsapp" ? "chip-red" : ""}`} data-testid="batch-channel-whatsapp">
                <WhatsappLogo size={11} weight="fill" /> whatsapp
              </button>
            </div>

            <div className="grid lg:grid-cols-5 gap-5 mt-5">
              {/* Left — lead picker */}
              <div className="lg:col-span-2 surface bg-white/[0.04] p-4 flex flex-col min-h-[380px]">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <div className="eyebrow">2 · Destinataires</div>
                    <div className="font-display font-bold flex items-center gap-1.5"><Users size={16} /> {selected.size} / {filtered.length}</div>
                  </div>
                  <button onClick={toggleAll} className="chip chip-red" data-testid="select-all-leads">
                    {selected.size === filtered.length && filtered.length > 0 ? "CLEAR" : "SELECT ALL"}
                  </button>
                </div>
                <input
                  className="neo-input text-sm mb-2"
                  placeholder="Search leads..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  data-testid="batch-search-input"
                />
                <div className="flex-1 overflow-y-auto -mx-1 px-1 divide-y divide-border">
                  {filtered.map((l) => {
                    const checked = selected.has(l.id);
                    return (
                      <label key={l.id} className="flex items-start gap-2 py-2 cursor-pointer group" data-testid={`batch-lead-${l.id}`}>
                        <input type="checkbox" checked={checked} onChange={() => toggleOne(l.id)} className="mt-1 accent-violet-500" />
                        <div className="flex-1 min-w-0 text-xs">
                          <div className="font-semibold text-foreground">{l.full_name}</div>
                          <div className="text-soft truncate font-mono">
                            {channel === "email" ? l.email : l.phone} {l.company && `· ${l.company}`}
                          </div>
                        </div>
                      </label>
                    );
                  })}
                  {filtered.length === 0 && (
                    <div className="py-8 text-center text-faint text-sm italic">
                      No leads match{channel === "email" ? " (with email)" : " (with phone)"}.
                    </div>
                  )}
                </div>
              </div>

              {/* Right — composer */}
              <div className="lg:col-span-3 space-y-3">
                <div className="eyebrow">3 · Message et envoi</div>
                {channel === "email" && (
                  <div>
                    <label className="mono-accent block mb-1.5">subject</label>
                    <input className="neo-input" value={subject} onChange={(e) => setSubject(e.target.value)} data-testid="batch-subject" />
                  </div>
                )}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="mono-accent">body</label>
                    <button onClick={aiWrite} disabled={aiLoading} className="btn-purple !py-1 !px-2 text-xs" data-testid="batch-ai-button">
                      <Sparkle size={10} weight="fill" /> {aiLoading ? "WRITING..." : "AI WRITE"}
                    </button>
                  </div>
                  <textarea rows={8} className="neo-input font-mono text-sm" value={body} onChange={(e) => setBody(e.target.value)} data-testid="batch-body" />
                </div>

                <div className="flex gap-1.5 flex-wrap">
                  {TOKEN_HINTS.map((t) => (
                    <button
                      key={t}
                      onClick={() => setBody((b) => b + " " + t)}
                      className="chip chip-red hover:border-brand-violet"
                    >
                      {t}
                    </button>
                  ))}
                </div>

                {previewLead && (
                  <div className="surface bg-white/[0.04] p-3">
                    <div className="mono-accent mb-1.5">preview · {previewLead.full_name}</div>
                    {channel === "email" && subject && (
                      <div className="text-sm font-semibold text-foreground mb-1">{renderPreview(subject)}</div>
                    )}
                    <div className="text-xs text-soft whitespace-pre-wrap font-mono max-h-[110px] overflow-y-auto">
                      {renderPreview(body)}
                    </div>
                  </div>
                )}

                {result && (
                  <div className="surface bg-emerald-500/10 border-emerald-400/40 p-4" data-testid="batch-result">
                    <div className="flex items-center gap-2 font-display font-bold text-sm">
                      <CheckCircle size={16} weight="fill" className="text-emerald-400" /> {result.sent > 0 ? "Dispatch complete" : "Nothing was sent"}
                    </div>
                    <div className="grid grid-cols-4 gap-2 mt-3 text-center">
                      <Stat label="sent" value={result.sent} color="#10B981" />
                      <Stat label="failed" value={result.failed || 0} color="#DC2626" />
                      <Stat label="skipped" value={result.skipped || 0} color="#9CA3AF" />
                      <Stat label="not attempted" value={result.not_attempted || 0} color="#F59E0B" />
                    </div>
                    {result.blocked && (
                      <div className="mt-3 text-xs text-soft flex gap-1.5 items-start" role="alert" data-testid="batch-blocked">
                        <Warning size={12} className="text-amber-400 flex-shrink-0 mt-0.5" />
                        {blockText(result.blocked.code) || result.blocked.message}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div className="flex gap-3 mt-6 items-center border-t border-border pt-4">
              <button onClick={dispatch} disabled={loading || selected.size === 0} className="btn-primary" data-testid="batch-dispatch-button">
                {loading ? <><CircleNotch size={14} className="spin-slow" /> DISPATCHING...</> : <><PaperPlaneTilt size={14} weight="fill" /> DISPATCH TO {selected.size} LEAD{selected.size !== 1 ? "S" : ""}</>}
              </button>
              <button onClick={onClose} className="btn-ghost">CLOSE</button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Stat({ label, value, color }) {
  return (
    <div className="surface p-2">
      <div className="mono-accent text-[10px]" style={{ color }}>{label}</div>
      <div className="font-mono text-xl font-bold tabular" style={{ color }}>{value || 0}</div>
    </div>
  );
}
