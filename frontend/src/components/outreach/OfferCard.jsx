import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Megaphone } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, offerApi, useAsync } from "@/lib/outreach";
import { describeApiError } from "@/lib/outreachFormat";

const EMPTY = { name: "", pitch: "", cta: "", language: "fr" };
const LIMITS = { name: [2, 120], pitch: [20, 600], cta: [3, 160] };

// What the organisation sells. The automatic drafts talk about this offer and nothing else: with no offer saved, no draft
// is prepared and no offer is invented.
export default function OfferCard() {
  const { user } = useAuth();
  const current = useAsync(() => offerApi.get(), [], { key: "settings:offer" });
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (current.data && current.data.offer) setForm(current.data.offer);
  }, [current.data]);
  const decide = canDecide(user);
  const complete = Object.entries(LIMITS).every(([key, [low, high]]) => form[key].trim().length >= low && form[key].trim().length <= high);
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await offerApi.put({ ...form, name: form.name.trim(), pitch: form.pitch.trim(), cta: form.cta.trim() });
      toast.success("Offer saved: drafts for the qualified prospects are prepared in the background");
      current.reload();
    } catch (err) {
      toast.error(describeApiError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section id="offer" className="surface p-6 space-y-4" data-testid="offer-card">
      <div className="flex items-center gap-2">
        <Megaphone size={18} className="text-brand-lilac" />
        <h2 className="font-display text-xl font-bold">Offer</h2>
        {current.data && <span className={`chip ${current.data.configured ? "chip-success" : "chip-warn"}`}>{current.data.configured ? "READY" : "REQUIRED"}</span>}
      </div>
      <p className="text-sm text-soft">What you sell, in your own words. Each qualified prospect gets a draft about this offer to review; nothing is sent without your approval.</p>
      <form onSubmit={save} className="grid gap-3 md:grid-cols-2">
        <label className="text-sm">Name<input className="neo-input w-full" value={form.name} onChange={set("name")} disabled={!decide} maxLength={120} data-testid="offer-name" /></label>
        <label className="text-sm">Language<select className="neo-input w-full" value={form.language} onChange={set("language")} disabled={!decide}><option value="fr">Français</option><option value="en">English</option></select></label>
        <label className="text-sm md:col-span-2">What it brings to the customer<textarea className="neo-input w-full min-h-[5rem]" value={form.pitch} onChange={set("pitch")} disabled={!decide} maxLength={600} data-testid="offer-pitch" /></label>
        <label className="text-sm md:col-span-2">The one next step you ask for<input className="neo-input w-full" value={form.cta} onChange={set("cta")} disabled={!decide} maxLength={160} data-testid="offer-cta" /></label>
        <div className="md:col-span-2 flex items-center gap-3">
          <button className="btn-primary" disabled={!decide || !complete || busy} data-testid="offer-save">SAVE THE OFFER</button>
          {!decide && <span className="text-xs text-faint">Requires owner or admin.</span>}
          {decide && !complete && <span className="text-xs text-faint">Name 2+, description 20+, next step 3+ characters.</span>}
        </div>
      </form>
    </section>
  );
}
