import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/outreach";
import { LIVE_MS } from "@/lib/live";
import { toast } from "sonner";
import { Plus, Pause, Trash, Target, Rocket, X, ArrowRight, ArrowSquareOut, PencilSimple, Play, Users } from "@phosphor-icons/react";
import CampaignDetailDrawer from "@/components/CampaignDetailDrawer";
import Suggestions from "@/components/campaigns/Suggestions";
import { describeLaunch, launchErrorText } from "@/lib/campaignLaunch";
import { describeApiError } from "@/lib/outreachFormat";
import { STATUS_LABEL, confirmLines, groupCampaigns, nextAction, progressOf, recipientsOf, stepsOf } from "@/lib/campaignsFormat";

const STATUS_CHIP = { draft: "chip-warn", running: "chip-success", paused: "chip-warn", completed: "chip-cyan" };
const NEXT_ICON = { edit: PencilSimple, open: Users, launch: Rocket, pause: Pause, resume: Play };
const emptyStep = (delay = 0) => ({ channel: "email", delay_hours: delay, subject: "", body: "", language: "fr" });

// Séquences : des étapes successives, rangées par où elles en sont, avec une seule action décisive chacune.
// Un brouillon n'est pas un envoi : rien ne part sans « Lancer » confirmé, et chaque message repasse les portes du serveur.
export default function Campaigns({ embedded = false }) {
  const campaigns = useAsync(() => api.get("/campaigns").then((r) => r.data), [], { key: "campaigns", intervalMs: LIVE_MS });
  const list = campaigns.data || [];
  const { loading, error } = campaigns;
  const load = campaigns.reload;
  const [params, setParams] = useSearchParams();
  const focus = params.get("campaign") || "";
  const handled = useRef("");
  const [builder, setBuilder] = useState(null); // null = closed, {} = new, a campaign = its draft
  const [drawerId, setDrawerId] = useState(null);
  const [confirm, setConfirm] = useState(null); // { campaign, kind: "launch" | "resume" }
  const [busy, setBusy] = useState(false);

  const close = () => {
    if (focus) setParams((p) => { const next = new URLSearchParams(p); next.delete("campaign"); return next; }, { replace: true });
  };

  // « Créer le brouillon » (suggestion, carte) mène ici avec ?campaign=<id> : le brouillon s'ouvre directement.
  useEffect(() => {
    if (!focus || handled.current === focus) return;
    const c = (campaigns.data || []).find((x) => x.id === focus);
    if (!c) return;
    handled.current = focus;
    if (stepsOf(c)) setDrawerId(c.id);
    else setBuilder(c);
  }, [focus, campaigns.data]);

  const save = async (form) => {
    const body = { name: form.name, goal: form.goal, channels: form.channels, steps: form.steps };
    if (form.id) {
      await api.patch(`/campaigns/${form.id}`, body);
      toast.success("Brouillon enregistré. Rien n'est envoyé.");
    } else {
      await api.post("/campaigns", body);
      toast.success("Brouillon créé. Rien n'est envoyé.");
    }
    setBuilder(null);
    close();
    load();
  };

  const go = async () => {
    const { campaign: c, kind } = confirm;
    setBusy(true);
    try {
      if (kind === "launch") {
        const { data } = await api.post(`/campaigns/${c.id}/launch`);
        const { level, text } = describeLaunch(data);
        toast[level](text);
      } else {
        await api.patch(`/campaigns/${c.id}`, { status: "running" });
        toast.success(`« ${c.name} » a repris.`);
      }
    } catch (err) {
      toast.error(kind === "launch" ? launchErrorText(err) : describeApiError(err));
    } finally {
      setBusy(false);
      setConfirm(null);
      load();
    }
  };

  const act = async (c) => {
    const next = nextAction(c);
    if (next.key === "edit") return setBuilder(c);
    if (next.key === "open") return setDrawerId(c.id);
    if (next.key === "launch" || next.key === "resume") return setConfirm({ campaign: c, kind: next.key });
    try {
      await api.patch(`/campaigns/${c.id}`, { status: "paused" });
      toast.success(`« ${c.name} » est en pause : plus rien ne part.`);
    } catch (err) {
      toast.error(describeApiError(err));
    }
    load();
  };

  const remove = async (c) => {
    if (!window.confirm(`Supprimer « ${c.name} » ? Les messages déjà partis restent dans le journal.`)) return;
    await api.delete(`/campaigns/${c.id}`);
    toast.success("Campagne supprimée.");
    load();
  };

  const groups = groupCampaigns(list);
  return (
    <div className={embedded ? "space-y-6" : "p-6 md:p-10 space-y-6"}>
      <div className={`flex items-start flex-wrap gap-4 ${embedded ? "justify-end" : "justify-between"}`}>
        {!embedded && <div>
          <div className="eyebrow">outreach.campaigns</div>
          <h1 className="mt-3 text-4xl font-bold tracking-tight leading-[1.15]">Séquences</h1>
          <p className="text-soft mt-1">Des étapes successives, envoyées sous les limites d&apos;envoi.</p>
        </div>}
        <button onClick={() => setBuilder({})} className="btn-primary" data-testid="new-campaign-button">
          <Plus size={16} weight="bold" /> NOUVELLE SÉQUENCE
        </button>
      </div>

      <Suggestions onCreated={(data) => { load(); handled.current = ""; setParams({ campaign: data.campaign_id }); }} />

      {error && <div role="alert" className="surface p-4 text-sm" data-testid="campaigns-error"><p>{error}</p><button onClick={load} className="btn-ghost mt-2">RÉESSAYER</button></div>}
      {loading && list.length === 0 && <p role="status" className="surface p-4 text-sm">Chargement des séquences…</p>}
      {!loading && !error && list.length === 0 && (
        <div className="surface p-10 text-center text-soft" data-testid="campaigns-empty">
          Aucune séquence pour l&apos;instant. <button onClick={() => setBuilder({})} className="text-brand-lilac hover:underline">Créer la première.</button>
        </div>
      )}

      {groups.map((g) => (
        <section key={g.key} aria-label={g.label} className="space-y-2" data-testid={`campaigns-group-${g.key}`}>
          <div className="flex flex-wrap items-baseline gap-x-3">
            <h2 className="font-display text-lg font-bold">{g.label} <span className="text-faint font-mono text-sm">{g.items.length}</span></h2>
            <p className="text-xs text-soft">{g.hint}</p>
          </div>
          <ul className="flex gap-4 overflow-x-auto snap-x snap-mandatory pb-2" tabIndex={0} aria-label={`${g.label} : faire défiler`}>
            {g.items.map((c) => (
              <li key={c.id} className="snap-start shrink-0 w-[85%] sm:w-[22rem]">
                <CampaignCard c={c} focused={c.id === focus} onAct={() => act(c)} onOpen={() => setDrawerId(c.id)} onEdit={() => setBuilder(c)} onRemove={() => remove(c)} />
              </li>
            ))}
          </ul>
        </section>
      ))}

      <CampaignBuilder initial={builder} onClose={() => { setBuilder(null); close(); }} onSave={save} />
      <ConfirmSend confirm={confirm} busy={busy} onCancel={() => setConfirm(null)} onGo={go} />
      <CampaignDetailDrawer open={drawerId !== null} campaignId={drawerId} onClose={() => { setDrawerId(null); close(); }} onUpdate={load} />
    </div>
  );
}

function CampaignCard({ c, focused, onAct, onOpen, onEdit, onRemove }) {
  const p = progressOf(c);
  const next = nextAction(c);
  const Icon = NEXT_ICON[next.key] || ArrowRight;
  return (
    <article className={`surface surface-hover p-5 h-full flex flex-col gap-4 ${c.status === "running" ? "border-beam" : ""} ${focused ? "ring-1 ring-brand-lilac" : ""}`} data-testid={`campaign-card-${c.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Target size={16} weight="duotone" className="text-brand-lilac" />
            <h3 className="font-display font-bold truncate">{c.name}</h3>
            <span className={`chip ${STATUS_CHIP[c.status] || ""}`} data-testid="campaign-status">{STATUS_LABEL[c.status] || c.status}</span>
          </div>
          {c.goal && <p className="text-sm text-soft mt-1 line-clamp-2">{c.goal}</p>}
        </div>
        <div className="flex gap-1 shrink-0">
          <button onClick={onOpen} className="btn-ghost !py-1.5 !px-2" title={`Ouvrir ${c.name}`} aria-label={`Ouvrir ${c.name}`} data-testid={`view-campaign-${c.id}`}><ArrowSquareOut size={14} weight="bold" /></button>
          {c.status === "draft" && <button onClick={onEdit} className="btn-ghost !py-1.5 !px-2" title={`Modifier ${c.name}`} aria-label={`Modifier ${c.name}`} data-testid={`edit-campaign-${c.id}`}><PencilSimple size={14} weight="bold" /></button>}
          <button onClick={onRemove} className="btn-danger !py-1.5 !px-2" aria-label={`Supprimer ${c.name}`} data-testid={`delete-${c.id}`}><Trash size={14} /></button>
        </div>
      </div>

      <div data-testid="campaign-progress">
        {p.pct !== null && (
          <div className="h-1.5 rounded-full bg-border overflow-hidden" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={p.pct} aria-label="Messages acceptés sur prévus">
            <div className="h-full bg-brand-violet" style={{ width: `${p.pct}%` }} />
          </div>
        )}
        <p className="mt-1.5 text-xs text-soft">{p.text}</p>
      </div>

      <dl className="grid grid-cols-3 gap-2 text-xs">
        <div><dt className="text-faint">Ouvertures</dt><dd className="font-mono text-base font-bold">{c.opened || 0}</dd></div>
        <div><dt className="text-faint">Réponses</dt><dd className="font-mono text-base font-bold">{c.replied || 0}</dd></div>
        <div><dt className="text-faint">Gagnés</dt><dd className="font-mono text-base font-bold">{c.converted || 0}</dd></div>
      </dl>

      <div className="flex items-center gap-1.5 flex-wrap text-xs">
        {(c.channels || []).map((ch) => <span key={ch} className="chip chip-cyan">{ch}</span>)}
        <span className="chip">{stepsOf(c)} étape{stepsOf(c) === 1 ? "" : "s"}</span>
        <span className="chip"><Users size={10} /> {recipientsOf(c)} destinataire{recipientsOf(c) === 1 ? "" : "s"}</span>
      </div>

      <button onClick={onAct} className={`mt-auto ${next.key === "launch" ? "btn-primary" : "btn-ink"} justify-center`} data-testid={`next-${c.id}`} data-action={next.key}>
        <Icon size={14} weight="bold" /> {next.label}
      </button>
    </article>
  );
}

function ConfirmSend({ confirm, busy, onCancel, onGo }) {
  if (!confirm) return null;
  const { campaign: c, kind } = confirm;
  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onCancel}>
      <div role="dialog" aria-modal="true" aria-labelledby="confirm-send-title" className="surface w-full max-w-lg p-6 space-y-4" onClick={(e) => e.stopPropagation()} data-testid="confirm-send">
        <h2 id="confirm-send-title" className="font-display text-xl font-bold">{kind === "resume" ? "Reprendre la séquence ?" : "Lancer la séquence ?"}</h2>
        <ul className="list-disc pl-5 space-y-1.5 text-sm text-soft">
          {confirmLines(c, kind).map((line) => <li key={line}>{line}</li>)}
        </ul>
        <div className="flex flex-wrap gap-3 pt-1">
          <button className="btn-primary" disabled={busy} onClick={onGo} data-testid="confirm-send-go">
            {busy ? "ENVOI EN COURS…" : kind === "resume" ? <><Play size={14} weight="fill" /> REPRENDRE</> : <><Rocket size={14} weight="fill" /> LANCER</>}
          </button>
          <button className="btn-ghost" disabled={busy} onClick={onCancel} data-testid="confirm-send-cancel">ANNULER</button>
        </div>
      </div>
    </div>
  );
}

function CampaignBuilder({ initial, onClose, onSave }) {
  const open = initial !== null;
  const [form, setForm] = useState({ name: "", goal: "", channels: ["email"], steps: [emptyStep()] });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm({
      id: initial.id,
      name: initial.name || "",
      goal: initial.goal || "",
      channels: initial.channels?.length ? initial.channels : ["email"],
      steps: initial.steps?.length ? initial.steps : [emptyStep()],
    });
  }, [open, initial]);

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const updateStep = (i, k, v) => setForm((f) => ({ ...f, steps: f.steps.map((s, idx) => (idx === i ? { ...s, [k]: v } : s)) }));
  const addStep = () => update("steps", [...form.steps, emptyStep(24)]);
  const removeStep = (i) => update("steps", form.steps.filter((_, idx) => idx !== i));

  const submit = async () => {
    if (!form.name.trim()) { toast.error("Donnez un nom à la séquence."); return; }
    if (form.steps.some((s) => !s.body.trim())) { toast.error("Chaque étape a besoin d'un message."); return; }
    setSaving(true);
    try { await onSave(form); } catch (e) { toast.error(describeApiError(e)); } finally { setSaving(false); }
  };

  const recipients = recipientsOf(initial);
  return (
    <AnimatePresence>
      {open && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
          <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
            className="surface w-full max-w-3xl p-6 md:p-8 relative max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}
            data-testid="campaign-builder-modal">
            <button onClick={onClose} className="absolute top-4 right-4 text-soft hover:text-foreground" aria-label="Fermer" data-testid="close-campaign-builder"><X size={20} /></button>

            <div className="mono-accent">{form.id ? "brouillon" : "nouvelle séquence"}</div>
            <h2 className="text-2xl font-black tracking-tighter mt-1" data-testid="builder-title">{form.id ? form.name : "Nouvelle séquence"}</h2>
            <p className="text-sm text-soft mt-1" data-testid="builder-note">
              {form.id ? `${recipients} destinataire${recipients === 1 ? "" : "s"} assigné${recipients === 1 ? "" : "s"}. ` : ""}
              Enregistrer n&apos;envoie rien : la séquence part seulement quand vous la lancez, après confirmation.
            </p>

            <div className="space-y-4 mt-6">
              <div className="grid md:grid-cols-2 gap-3">
                <label className="block text-sm">
                  <span className="mono-accent block mb-1.5">Nom</span>
                  <input className="neo-input" value={form.name} onChange={(e) => update("name", e.target.value)} placeholder="Nom de la séquence" data-testid="campaign-name-input" />
                </label>
                <label className="block text-sm">
                  <span className="mono-accent block mb-1.5">Objectif (facultatif)</span>
                  <input className="neo-input" value={form.goal} onChange={(e) => update("goal", e.target.value)} placeholder="Ce que vous attendez de cette séquence" data-testid="campaign-goal-input" />
                </label>
              </div>

              <div>
                <div className="mono-accent mb-2">Canaux</div>
                <div className="flex gap-2">
                  {["email", "whatsapp"].map((ch) => {
                    const active = form.channels.includes(ch);
                    return (
                      <button key={ch} type="button" aria-pressed={active}
                        onClick={() => update("channels", active ? form.channels.filter((x) => x !== ch) : [...form.channels, ch])}
                        className={`chip ${active ? "chip-cyan" : ""}`} data-testid={`channel-${ch}`}>{ch}</button>
                    );
                  })}
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="mono-accent">Étapes</div>
                  <button onClick={addStep} className="btn-ghost !py-1.5 !px-2" data-testid="add-step-button"><Plus size={12} /> ÉTAPE</button>
                </div>
                <div className="space-y-3">
                  {form.steps.map((s, i) => (
                    <div key={s.id || i} className="surface p-4" data-testid={`builder-step-${i}`}>
                      <div className="flex items-center justify-between mb-3">
                        <span className="chip chip-purple font-mono">étape {i + 1}</span>
                        {form.steps.length > 1 && <button onClick={() => removeStep(i)} className="text-soft hover:text-foreground" aria-label={`Retirer l'étape ${i + 1}`}><Trash size={14} /></button>}
                      </div>
                      <div className="grid md:grid-cols-3 gap-3">
                        <label className="block text-sm">
                          <span className="mono-accent block mb-1">Canal</span>
                          <select className="neo-input" value={s.channel} onChange={(e) => updateStep(i, "channel", e.target.value)}>
                            <option value="email">email</option>
                            <option value="whatsapp">whatsapp</option>
                          </select>
                        </label>
                        <label className="block text-sm">
                          <span className="mono-accent block mb-1">Délai (heures)</span>
                          <input type="number" min="0" className="neo-input font-mono" value={s.delay_hours} onChange={(e) => updateStep(i, "delay_hours", parseInt(e.target.value || "0", 10))} />
                        </label>
                        <label className="block text-sm">
                          <span className="mono-accent block mb-1">Langue</span>
                          <input className="neo-input font-mono" value={s.language} onChange={(e) => updateStep(i, "language", e.target.value)} />
                        </label>
                      </div>
                      {s.channel === "email" && (
                        <label className="block text-sm mt-3">
                          <span className="mono-accent block mb-1">Objet</span>
                          <input className="neo-input" value={s.subject || ""} onChange={(e) => updateStep(i, "subject", e.target.value)} placeholder="Objet ({{company}} est remplacé par le nom)" data-testid={`step-subject-${i}`} />
                        </label>
                      )}
                      <label className="block text-sm mt-3">
                        <span className="mono-accent block mb-1">Message</span>
                        <textarea rows={4} className="neo-input" value={s.body} onChange={(e) => updateStep(i, "body", e.target.value)} placeholder="Bonjour {{first_name}}, …" data-testid={`step-body-${i}`} />
                      </label>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex gap-3 pt-3">
                <button onClick={submit} disabled={saving} className="btn-primary" data-testid="save-campaign-button">
                  {saving ? "ENREGISTREMENT…" : <>ENREGISTRER LE BROUILLON <ArrowRight size={14} weight="bold" /></>}
                </button>
                <button onClick={onClose} className="btn-ghost">ANNULER</button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
