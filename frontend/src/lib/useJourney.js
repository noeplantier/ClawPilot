import { useCallback, useState } from "react";
import { toast } from "sonner";
import { journeysApi, useAsync } from "@/lib/outreach";
import { launchError } from "@/lib/launchFormat";

// Everything the journey screen reads and does for one campaign: the approval summary (recomputed by the server from the data as
// it is now), the compact follow-up, and the actions. A refused action shows the server's sentence and reloads what changed.
export function useJourney(id) {
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const summary = useAsync(() => journeysApi.get(id), [id, version], { key: `journey:${id}`, intervalMs: 30000 });
  const progress = useAsync(() => journeysApi.progress(id), [id, version], { key: `journey:${id}:progress`, intervalMs: 15000 });
  const reload = useCallback(() => setVersion((n) => n + 1), []);

  const act = useCallback(async (name, fn, done) => {
    setBusy(name);
    setError("");
    try {
      const out = await fn();
      if (done) toast.success(typeof done === "function" ? done(out) : done);
      return out;
    } catch (e) {
      setError(launchError(e));
      return null;
    } finally {
      setBusy("");
      reload();
    }
  }, [reload]);

  return {
    summary, progress, busy, error, reload, setError,
    saveTemplate: (subject, body) => act("template", () => journeysApi.putTemplate(id, { subject, body }), (o) => (o.changed ? `Message enregistré (version ${o.version}) : l'approbation précédente ne le couvre plus.` : "Rien n'a changé dans le message.")),
    approve: (hash, count) => act("approve", () => journeysApi.approve(id, hash, count), (o) => `Campagne approuvée : ${o.scheduled} message${o.scheduled === 1 ? "" : "s"} planifié${o.scheduled === 1 ? "" : "s"}, aucun n'est parti.`),
    revoke: () => act("revoke", () => journeysApi.revoke(id, "Retirée depuis l'écran de la campagne"), (o) => `Approbation retirée : ${o.cancelled} envoi${o.cancelled === 1 ? "" : "s"} annulé${o.cancelled === 1 ? "" : "s"}.`),
    pause: () => act("pause", () => journeysApi.pause(id), "Campagne en pause : rien ne part."),
    resume: () => act("resume", () => journeysApi.resume(id), "Campagne reprise."),
  };
}
